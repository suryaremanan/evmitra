"""
EV Mitra — routers/route.py
/route/stream — Live highway trip planner (SSE).
"""

import json
import math
import queue as queue_module
import threading

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.config import (
    HIGHWAY_ROUTES,
    THREAD_JOIN_TIMEOUT_SEC,
    normalize_city,
    normalize_country,
    logger,
)
from car_profiles import get_profile as get_car_profile
from services.charger_service import fetch_live_chargers
from services.tinyfish_service import discover_route_via_tinyfish

router = APIRouter()


class RouteRequest(BaseModel):
    country: str = "India"
    from_city: str = "Mumbai"
    to_city: str = "Goa"
    car_model: str = "Tata Nexon EV Max"
    start_charge_pct: float = 1.0


def _lookup_route(from_city: str, to_city: str) -> tuple[dict | None, bool]:
    route = HIGHWAY_ROUTES.get((from_city, to_city))
    if route:
        return route, False
    route = HIGHWAY_ROUTES.get((to_city, from_city))
    if route:
        total = route["distance_km"]
        rev = dict(route)
        rev["waypoints"] = sorted(
            [{"name": wp["name"], "km": total - wp["km"], "state": wp["state"]}
             for wp in route["waypoints"]],
            key=lambda x: x["km"],
        )
        return rev, True
    return None, False


def plan_stops(route: dict, car_profile: dict, start_charge_pct: float = 1.0) -> tuple[list, bool]:
    hw_range = car_profile.get("real_range_highway_km",
                               int(car_profile["real_range_city_km"] * 1.15))
    usable    = hw_range * 0.85
    buffer    = hw_range * 0.12
    charge_to = hw_range * 0.80

    total_km  = route["distance_km"]
    waypoints = sorted(route["waypoints"], key=lambda x: x["km"])

    chain = (
        [{"name": "__start__", "km": 0}]
        + waypoints
        + [{"name": "__dest__", "km": total_km}]
    )

    stops  = []
    charge = usable * start_charge_pct

    for i in range(1, len(chain)):
        leg     = chain[i]["km"] - chain[i - 1]["km"]
        is_dest = chain[i]["name"] == "__dest__"
        needed  = leg + (buffer if not is_dest else 0)

        if charge < needed:
            prev = chain[i - 1]
            if prev["name"] not in ("__start__", "__dest__"):
                if prev not in stops:
                    stops.append(prev)
                charge = charge_to
            if charge < leg:
                return stops, False

        charge -= leg

    return stops, charge >= -usable * 0.05


def estimate_charge_time_min(car_profile: dict, station_power_kw: int) -> int:
    car_kw = car_profile.get("dc_fast_charge_kw", 50)
    actual = max(1, min(station_power_kw, car_kw))
    ref    = car_profile.get("full_charge_min_dc", 57)
    return math.ceil(ref * car_kw / actual)


@router.post("/route/stream")
def stream_route(req: RouteRequest):
    from_city   = normalize_city(req.from_city)
    to_city     = normalize_city(req.to_city)
    country     = normalize_country(req.country)
    car_profile = get_car_profile(req.car_model)

    def generate():
        route, _reversed = _lookup_route(from_city, to_city)
        if not route:
            yield f"data: {json.dumps({'type': 'PLANNING', 'message': f'Route {from_city} → {to_city} not in database — querying live via TinyFish...'})}\n\n"
            route = discover_route_via_tinyfish(from_city, to_city, country)
            if not route:
                supported = ", ".join(f"{a}↔{b}" for a, b in HIGHWAY_ROUTES.keys())
                yield f"data: {json.dumps({'type': 'ERROR', 'message': f'Could not find route data for {from_city} → {to_city}. Pre-loaded routes: {supported}'})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'status': 'error'})}\n\n"
                return
            dist_label = route["distance_km"]
            yield f"data: {json.dumps({'type': 'PLANNING', 'message': f'Route discovered: {dist_label}km via TinyFish live lookup'})}\n\n"

        dist_km = route["distance_km"]
        highway = route["highway"]
        yield f"data: {json.dumps({'type': 'PLANNING', 'message': f'Analyzing {from_city} to {to_city} — {dist_km}km via {highway}...'})}\n\n"

        stops, feasible = plan_stops(route, car_profile, req.start_charge_pct)

        n_stops    = len(stops)
        stop_names = ", ".join(s["name"] for s in stops) if stops else "none needed"
        stop_word  = "stops" if n_stops != 1 else "stop"
        yield f"data: {json.dumps({'type': 'CALCULATING', 'message': f'{n_stops} charging {stop_word} needed — {stop_names}'})}\n\n"

        q          = queue_module.Queue()
        stop_data  = {}

        def fetch_stop(wp):
            q.put({"type": "SCRAPING_STOP",
                   "message": f"Checking live chargers at {wp['name']} (km {wp['km']})...",
                   "_wp": wp["name"]})
            try:
                data = fetch_live_chargers(wp["name"], country=country, quick_mode=True, hard_deadline_sec=3)
            except Exception:
                data = {"stations": [], "total_found": 0, "source_type": "static_fallback"}
            q.put({"type": "STOP_DONE", "_wp": wp["name"], "_data": data})

        threads = [threading.Thread(target=fetch_stop, args=(wp,), daemon=True) for wp in stops]
        for t in threads:
            t.start()

        pending_stops = len(stops)
        while pending_stops > 0:
            try:
                msg = q.get(timeout=350)
                if "_data" in msg:
                    data  = msg["_data"]
                    name  = msg["_wp"]
                    stop_data[name] = data
                    count = data.get("total_found", len(data.get("stations", [])))
                    dc    = [s for s in data.get("stations", []) if "DC" in s.get("connector_types", [])]
                    top_kw = max((s.get("power_kw", 0) for s in dc), default=0)
                    src   = data.get("source_type", "static_fallback")
                    badge = "live" if src == "live" else "cache" if src == "cache" else "fallback"
                    found_msg = (f"[{badge}] {name}: {count} stations, {len(dc)} DC ({top_kw}kW max)"
                                 if count > 0 else f"{name}: no chargers found via live scrape")
                    yield f"data: {json.dumps({'type': 'STOP_FOUND', 'message': found_msg, 'stop_name': name})}\n\n"
                    pending_stops -= 1
                else:
                    out = {k: v for k, v in msg.items() if not k.startswith("_")}
                    yield f"data: {json.dumps(out)}\n\n"
            except queue_module.Empty:
                yield f"data: {json.dumps({'type': 'STOP_FOUND', 'message': 'Charger fetch timed out — continuing with cached data'})}\n\n"
                break

        for t in threads:
            t.join(timeout=THREAD_JOIN_TIMEOUT_SEC)

        yield f"data: {json.dumps({'type': 'BUILDING_PLAN', 'message': 'Building your trip plan...'})}\n\n"

        stop_plans = []
        for wp in stops:
            cd        = stop_data.get(wp["name"], {"stations": [], "total_found": 0})
            stations  = cd.get("stations", [])
            dc        = [s for s in stations if "DC" in s.get("connector_types", [])]
            best_kw   = max((s.get("power_kw", 0) for s in dc), default=25)
            charge_min = estimate_charge_time_min(car_profile, best_kw)
            network   = (dc[0] if dc else stations[0]).get("network", cd.get("network", "Unknown")) if stations else "Unknown"
            address   = (dc[0] if dc else {}).get("address", "")
            stop_plans.append({
                "waypoint":       wp["name"],
                "km":             wp["km"],
                "total_stations": cd.get("total_found", len(stations)),
                "dc_stations":    len(dc),
                "best_power_kw":  best_kw,
                "network":        network,
                "address":        address,
                "charge_time_min": charge_min,
                "source_type":    cd.get("source_type", "static_fallback"),
            })

        # ── Validate stops and assign fallbacks ──
        yield f"data: {json.dumps({'type': 'VALIDATING_STOPS', 'message': 'Validating each stop for DC availability...'})}\n\n"

        operator_actions = []
        weak_stops = [s for s in stop_plans if s["dc_stations"] <= 0]
        route_waypoints = sorted(route.get("waypoints", []), key=lambda x: x["km"])

        for weak in weak_stops:
            wpt_name = weak["waypoint"]
            yield f"data: {json.dumps({'type': 'STOP_WEAK', 'message': f'{wpt_name} has weak DC coverage. Searching fallback...'})}\n\n"
            weak_km = weak["km"]
            candidates = [
                wp for wp in route_waypoints
                if wp["name"] != weak["waypoint"] and abs(wp["km"] - weak_km) <= 140
            ][:3]

            fallback_rows = []
            for cand in candidates:
                try:
                    data = fetch_live_chargers(cand["name"], country=country, quick_mode=True, hard_deadline_sec=3)
                except Exception:
                    data = {"stations": [], "total_found": 0, "source_type": "static_fallback"}
                stations = data.get("stations", [])
                dc = [s for s in stations if "DC" in s.get("connector_types", [])]
                best_kw = max((s.get("power_kw", 0) for s in dc), default=0)
                fallback_rows.append({
                    "name": cand["name"],
                    "dc": len(dc),
                    "total": data.get("total_found", len(stations)),
                    "best_kw": best_kw,
                    "source_type": data.get("source_type", "static_fallback"),
                })

            fallback_rows.sort(key=lambda x: (x["dc"], x["best_kw"], x["total"]), reverse=True)
            winner = fallback_rows[0] if fallback_rows and fallback_rows[0]["dc"] > 0 else None

            if winner:
                winner_name = winner["name"]
                weak["fallback_stop"] = winner_name
                weak["fallback_dc_stations"] = winner["dc"]
                weak["fallback_best_power_kw"] = winner["best_kw"]
                weak["operator_status"] = "fallback_assigned"
                operator_actions.append(
                    f"Replace stop {wpt_name} with fallback {winner_name} ({winner['dc']} DC, {winner['best_kw']}kW max)."
                )
                yield f"data: {json.dumps({'type': 'FALLBACK_ASSIGNED', 'message': f'Fallback set: {wpt_name} → {winner_name}'})}\n\n"
            else:
                weak["operator_status"] = "manual_review_required"
                operator_actions.append(
                    f"Manual review required at {wpt_name}: no reliable fallback within 140km."
                )
                yield f"data: {json.dumps({'type': 'FALLBACK_MISSING', 'message': f'No fallback found near {wpt_name}. Manual intervention needed.'})}\n\n"

        total_charge_min  = sum(s["charge_time_min"] for s in stop_plans)
        driving_time_hr   = round(route["distance_km"] / 70, 1)
        total_time_hr     = round(driving_time_hr + total_charge_min / 60, 1)
        hw_range          = car_profile.get("real_range_highway_km",
                                            int(car_profile["real_range_city_km"] * 1.15))

        result = {
            "from_city":            from_city,
            "to_city":              to_city,
            "country":              country,
            "distance_km":          route["distance_km"],
            "highway":              route["highway"],
            "car":                  req.car_model,
            "real_range_highway_km": hw_range,
            "stops":                stop_plans,
            "total_stops":          len(stop_plans),
            "total_charge_time_min": total_charge_min,
            "est_driving_time_hr":  driving_time_hr,
            "est_total_time_hr":    total_time_hr,
            "trip_feasible":        feasible,
            "risk_level": ("comfortable" if len(stop_plans) <= 1 and feasible
                           else "manageable" if feasible else "challenging"),
            "operator_action_report": {
                "workflow_completed": [
                    "discover_live_charger_availability",
                    "validate_each_stop",
                    "assign_fallbacks_for_weak_stops",
                    "generate_dispatch_actions",
                ],
                "weak_stops_detected": len(weak_stops),
                "actions": operator_actions or ["No fallback actions required. Proceed with primary plan."],
            },
        }

        yield f"data: {json.dumps({'type': 'COMPLETE', 'data': result})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'status': 'complete'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

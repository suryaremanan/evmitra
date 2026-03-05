"""
EV Mitra — routers/verdict.py
/verdict/stream (SSE) and /verdict (blocking) endpoints.
"""

import json
import queue as queue_module
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.config import (
    SSE_QUEUE_TIMEOUT_SEC,
    THREAD_JOIN_TIMEOUT_SEC,
    normalize_city,
    normalize_country,
    get_country_config,
    get_incentives_for_locale,
    logger,
)
from core.cache import charger_cache_key, CHARGER_CACHE, TEAMBHP_CACHE, teambhp_cache_key
from car_profiles import CAR_PROFILES, get_profile as get_car_profile
from synthesis import calculate_anxiety_scores, extract_owner_insights, build_prompt, call_llm
from services.charger_service import fetch_live_chargers, _static_city_fallback
from services.teambhp_service import fetch_live_teambhp
import user_store

router = APIRouter()

# ALL_DATA is set at startup
_ALL_DATA: dict = {}


def set_all_data(data: dict):
    global _ALL_DATA
    _ALL_DATA = data


# ── Models ──

class QueryRequest(BaseModel):
    country: str = "India"
    city: str = "Nagpur"
    daily_km: int = 25
    occasional_km: int = 230
    car_model: str = "Tata Nexon EV Max"
    has_home_charging: bool = False
    user_description: str = ""
    user_id: str = ""


class VerdictResponse(BaseModel):
    city: str
    car: str
    daily_km: int
    occasional_km: int
    scores: dict
    verdict: str
    sources_used: list[str]


class CompareRequest(BaseModel):
    country: str = "India"
    city: str = "Nagpur"
    daily_km: int = 25
    occasional_km: int = 230
    has_home_charging: bool = False
    car_models: List[str]


# ── /verdict/stream ──

@router.post("/verdict/stream")
def stream_verdict(query: QueryRequest):
    city = normalize_city(query.city)
    country = normalize_country(query.country)
    car_model = query.car_model
    car_profile = get_car_profile(car_model)
    user_id = query.user_id.strip() or None

    def generate():
        q = queue_module.Queue()
        charger_holder: list[dict] = [{}]
        teambhp_holder: list[dict] = [{}]

        def do_chargers():
            q.put({"type": "SCRAPING_CHARGERS",
                   "message": f"Checking live stations in {city}, {country.title()}..."})
            try:
                started_at = time.time()
                data = fetch_live_chargers(city, country=country, quick_mode=True, hard_deadline_sec=3)
                charger_holder[0] = data
                count = data.get("total_found", len(data.get("stations", [])))
                if data.get("background_refresh_started"):
                    q.put({"type": "PROGRESS",
                           "message": "Returned fast result. Live refresh continues in background..."})

                    def watch_refresh():
                        key = charger_cache_key(city, country)
                        for _ in range(12):
                            time.sleep(1)
                            entry = CHARGER_CACHE.get(key)
                            if entry and entry.get("timestamp", 0) > started_at:
                                data_live = dict(entry["data"])
                                charger_holder[0] = data_live
                                q.put({
                                    "type": "CHARGERS_REFRESHED",
                                    "message": f"Live refresh complete: {data_live.get('total_found', 0)} stations from {data_live.get('provider', 'provider')}"
                                })
                                return

                    threading.Thread(target=watch_refresh, daemon=True).start()

                q.put({"type": "CHARGERS_DONE",
                       "message": f"Found {count} charging stations in {city}",
                       "_done": "chargers"})
            except Exception:
                charger_holder[0] = {"stations": [], "total_found": 0}
                q.put({"type": "CHARGERS_DONE",
                       "message": "Charger scrape failed — using fallback data",
                       "_done": "chargers"})

        def do_teambhp():
            if country != "india":
                teambhp_holder[0] = {}
                q.put({"type": "TEAMBHP_DONE",
                       "message": "Owner experience data not available for this region. Using global knowledge.",
                       "_done": "teambhp"})
                return
            q.put({"type": "SCRAPING_TEAMBHP",
                   "message": "Reading owner experiences on Team-BHP..."})
            try:
                data = fetch_live_teambhp(car_model, quick_mode=True, hard_deadline_sec=3)
                teambhp_holder[0] = data
                q.put({"type": "TEAMBHP_DONE",
                       "message": "Team-BHP owner insights loaded",
                       "_done": "teambhp"})
            except Exception:
                teambhp_holder[0] = None
                q.put({"type": "TEAMBHP_DONE",
                       "message": "Using cached Team-BHP data",
                       "_done": "teambhp"})

        t1 = threading.Thread(target=do_chargers, daemon=True)
        t2 = threading.Thread(target=do_teambhp, daemon=True)
        t1.start()
        t2.start()

        pending = 2
        while pending > 0:
            try:
                msg = q.get(timeout=SSE_QUEUE_TIMEOUT_SEC)
                out = {k: v for k, v in msg.items() if not k.startswith("_")}
                yield f"data: {json.dumps(out)}\n\n"
                if msg.get("_done"):
                    pending -= 1
            except queue_module.Empty:
                yield f"data: {json.dumps({'type': 'CHARGERS_DONE', 'message': 'Live scrape timed out — using cached data'})}\n\n"
                break

        while True:
            try:
                msg = q.get_nowait()
                out = {k: v for k, v in msg.items() if not k.startswith("_")}
                yield f"data: {json.dumps(out)}\n\n"
            except queue_module.Empty:
                break

        t1.join(timeout=THREAD_JOIN_TIMEOUT_SEC)
        t2.join(timeout=THREAD_JOIN_TIMEOUT_SEC)

        # ── Scoring ──
        yield f"data: {json.dumps({'type': 'SCORING', 'message': 'Calculating your anxiety score...'})}\n\n"

        charger_data = charger_holder[0] or {}
        if not charger_data.get("stations"):
            charger_data = _static_city_fallback(city, country)

        scores = calculate_anxiety_scores(
            charger_data, query.daily_km, query.occasional_km, car_profile=car_profile,
        )
        if query.has_home_charging:
            scores["daily_score"] = max(1, scores["daily_score"] - 1)

        if country == "india":
            teambhp_live = bool(teambhp_holder[0] and teambhp_holder[0].get("honest_verdict"))
            live_t1 = teambhp_holder[0] if teambhp_live else _ALL_DATA.get("teambhp_thread1", {})
            nexon_selected = "nexon" in car_model.lower()
            if nexon_selected:
                t2_data = _ALL_DATA.get("teambhp_thread2", {})
                t3_data = _ALL_DATA.get("teambhp_thread3", {})
            else:
                t2_data = live_t1
                t3_data = live_t1
        else:
            teambhp_live = False
            live_t1 = {}
            t2_data = {}
            t3_data = {}
        insights = extract_owner_insights(live_t1, t2_data, t3_data)

        # ── LLM synthesis ──
        yield f"data: {json.dumps({'type': 'LLM', 'message': 'Synthesising honest verdict...'})}\n\n"

        user_desc = query.user_description or (
            f"I live in {city}, {country.title()}. "
            f"Daily commute: {query.daily_km}km round trip. "
            f"Occasional trips: {query.occasional_km}km one way. "
            f"Car I'm considering: {query.car_model}. "
            f"Home charging: {'Yes' if query.has_home_charging else 'No — will rely on public chargers'}."
        )

        subsidy = get_incentives_for_locale(city, country)
        prompt = build_prompt(user_desc, scores, insights, subsidy, car_profile=car_profile, country=country)
        verdict_text = call_llm(prompt)

        if not verdict_text:
            yield f"data: {json.dumps({'type': 'ERROR', 'message': 'LLM synthesis failed. Check API keys.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'status': 'error', 'reason': 'API key missing or invalid. Set ANTHROPIC_API_KEY or FIREWORKS_API_KEY.'})}\n\n"
            return

        # ── Data freshness ──
        charger_src = charger_data.get("source_type", "static_fallback")
        charger_fetched = charger_data.get("fetched_at")
        charger_age = None
        if charger_src == "cache":
            entry = CHARGER_CACHE.get(charger_cache_key(city, country))
            charger_age = int((time.time() - entry["timestamp"]) / 60) if entry else None

        data_freshness = {
            "chargers": {
                "source_type": charger_src,
                "fetched_at": charger_fetched,
                "age_minutes": charger_age,
            },
            "owner_insights": {
                "source_type": ("live" if teambhp_live else "cache") if country == "india" else "global",
                "fetched_at": TEAMBHP_CACHE.get(teambhp_cache_key(car_model), {}).get("data", {}).get("fetched_at") if (country == "india" and not teambhp_live) else (datetime.now(timezone.utc).isoformat() if country == "india" else None),
                "age_minutes": None,
            },
        }

        charger_age_str = ""
        if charger_src == "cache" and charger_age is not None:
            charger_age_str = f" · updated {charger_age}m ago" if charger_age > 0 else " · just scraped"

        result = {
            "country": country,
            "city": city,
            "car": query.car_model,
            "daily_km": query.daily_km,
            "occasional_km": query.occasional_km,
            "scores": scores,
            "verdict": verdict_text,
            "data_freshness": data_freshness,
            "sources_used": [
                f"Charger network — {charger_src} ({scores['total_stations']} stations in {city}){charger_age_str}",
                f"Owner forums — {'scraped live' if teambhp_live else 'cached data'} ({car_model})" if country == "india" else f"Global EV knowledge base ({car_model})",
                subsidy["source"],
                "TinyFish Web Agent (real-time browser automation)",
            ],
            "operator_report": {
                "workflow": [
                    "Discover live charger availability",
                    "Validate each stop against fast-charger availability",
                    "Pick fallback stops when a stop has weak/no DC coverage",
                    "Generate operator action report",
                ],
                "recommended_primary_city": city,
                "fallback_city": next(
                    (c for c in get_country_config(country)["default_cities"] if c != city),
                    city,
                ),
                "risk": "high" if scores["occasional_score"] >= 7 else "medium" if scores["occasional_score"] >= 4 else "low",
                "action": (
                    "Pre-book charging slots and keep backup stop active"
                    if scores["occasional_score"] >= 7 else
                    "Run this workflow before each dispatch window"
                ),
            },
        }

        what_changed = None
        if user_id:
            what_changed = user_store.get_what_changed(user_id, result)
            user_store.save_verdict(user_id, result)
            try:
                user_store.upsert_profile(user_id, {
                    "preferred_city": city,
                    "preferred_car": car_model,
                    "preferred_daily_km": query.daily_km,
                    "preferred_occasional_km": query.occasional_km,
                    "has_home_charging": query.has_home_charging,
                })
            except Exception:
                pass

        if what_changed:
            result["what_changed"] = what_changed

        yield f"data: {json.dumps({'type': 'COMPLETE', 'data': result})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'status': 'complete'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── /verdict (blocking) ──

@router.post("/verdict", response_model=VerdictResponse)
def get_verdict(query: QueryRequest):
    city = normalize_city(query.city)
    country = normalize_country(query.country)
    car_profile = get_car_profile(query.car_model)
    logger.info("Blocking verdict for %s, %s", city, country)

    with ThreadPoolExecutor(max_workers=2) as ex:
        charger_future = ex.submit(fetch_live_chargers, city, country, False, 12)
        teambhp_future = ex.submit(fetch_live_teambhp, query.car_model, False, 12) if country == "india" else None
        charger_data = charger_future.result()
        teambhp_live = teambhp_future.result() if teambhp_future is not None else {}

    if not charger_data.get("stations"):
        charger_data = _static_city_fallback(city, country)

    scores = calculate_anxiety_scores(
        charger_data, query.daily_km, query.occasional_km, car_profile=car_profile
    )
    if query.has_home_charging:
        scores["daily_score"] = max(1, scores["daily_score"] - 1)

    if country == "india":
        teambhp_was_live = bool(teambhp_live and teambhp_live.get("honest_verdict"))
        live_t1 = teambhp_live if teambhp_was_live else _ALL_DATA.get("teambhp_thread1", {})
        nexon_selected_v = "nexon" in query.car_model.lower()
        t2_v = _ALL_DATA.get("teambhp_thread2", {}) if nexon_selected_v else live_t1
        t3_v = _ALL_DATA.get("teambhp_thread3", {}) if nexon_selected_v else live_t1
    else:
        teambhp_was_live = False
        live_t1 = {}
        t2_v = {}
        t3_v = {}
    insights = extract_owner_insights(live_t1, t2_v, t3_v)

    user_desc = query.user_description or (
        f"I live in {city}, {country.title()}. "
        f"Daily commute: {query.daily_km}km round trip. "
        f"Occasional trips: {query.occasional_km}km one way. "
        f"Car I'm considering: {query.car_model}. "
        f"Home charging: {'Yes' if query.has_home_charging else 'No — will rely on public chargers'}."
    )

    subsidy = get_incentives_for_locale(city, country)
    prompt = build_prompt(user_desc, scores, insights, subsidy, car_profile=car_profile, country=country)
    verdict = call_llm(prompt)

    if not verdict:
        raise HTTPException(status_code=500, detail="LLM synthesis failed. Check your ANTHROPIC_API_KEY or FIREWORKS_API_KEY.")

    return VerdictResponse(
        city=city,
        car=query.car_model,
        daily_km=query.daily_km,
        occasional_km=query.occasional_km,
        scores=scores,
        verdict=verdict,
        sources_used=[
            f"Charger network — {charger_data.get('source_type','live')} ({scores['total_stations']} stations in {city})",
            f"Owner forums — {'scraped live' if teambhp_was_live else 'cached'} ({query.car_model})" if country == "india" else f"Global EV knowledge base ({query.car_model})",
            subsidy["source"],
            "TinyFish Web Agent (real-time browser automation)",
        ]
    )


# ── /compare ──

@router.post("/compare")
def compare_cars(req_body: CompareRequest):
    city = normalize_city(req_body.city)
    country = normalize_country(req_body.country)
    car_models = req_body.car_models[:3]

    if not car_models:
        raise HTTPException(status_code=400, detail="Provide at least one car_model")

    charger_data = fetch_live_chargers(city, country=country, quick_mode=True, hard_deadline_sec=3)
    if not charger_data.get("stations"):
        charger_data = _static_city_fallback(city, country)

    results = []
    for model in car_models:
        cp = get_car_profile(model)
        scores = calculate_anxiety_scores(
            charger_data, req_body.daily_km, req_body.occasional_km, car_profile=cp,
        )
        if req_body.has_home_charging:
            scores["daily_score"] = max(1, scores["daily_score"] - 1)

        daily_s = scores["daily_score"]
        occ_s = scores["occasional_score"]
        combined = daily_s + occ_s
        if daily_s <= 3 and occ_s <= 4:
            best_for = "all-round"
        elif daily_s <= 3:
            best_for = "daily commute"
        elif occ_s <= 4:
            best_for = "long trips"
        elif cp["ex_showroom_inr"] < 1600000 and combined <= 12:
            best_for = "value"
        elif cp["ex_showroom_inr"] >= 3000000:
            best_for = "premium ownership"
        else:
            best_for = "needs good charging infra"

        results.append({
            "car": model,
            "segment": cp["segment"],
            "daily_score": scores["daily_score"],
            "occasional_score": scores["occasional_score"],
            "daily_rationale": scores["daily_rationale"],
            "occasional_rationale": scores["occasional_rationale"],
            "real_range_city_km": cp["real_range_city_km"],
            "real_range_highway_km": cp["real_range_highway_km"],
            "worst_case_km": cp["worst_case_km"],
            "ex_showroom_inr": cp["ex_showroom_inr"],
            "running_cost_per_km_inr": cp["running_cost_per_km_inr"],
            "dc_fast_charge_kw": cp["dc_fast_charge_kw"],
            "full_charge_min_dc": cp["full_charge_min_dc"],
            "battery_kwh": cp["battery_kwh"],
            "best_for": best_for,
            "confidence": scores["confidence"],
        })

    results.sort(key=lambda x: x["daily_score"] + x["occasional_score"])

    return {
        "country": country,
        "city": city,
        "daily_km": req_body.daily_km,
        "occasional_km": req_body.occasional_km,
        "charger_source_type": charger_data.get("source_type", "unknown"),
        "total_city_stations": charger_data.get("total_found", len(charger_data.get("stations", []))),
        "cars": results,
    }

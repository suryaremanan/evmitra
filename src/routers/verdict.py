"""
EV Mitra — routers/verdict.py
/verdict/stream (SSE) and /verdict (blocking) endpoints.
"""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import quote_plus

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
from car_profiles import get_profile as get_car_profile
from synthesis import calculate_anxiety_scores, extract_owner_insights, build_prompt, call_llm
from services.charger_service import fetch_live_chargers, _static_city_fallback, provider_sources_for_city
from services.teambhp_service import fetch_live_teambhp
from services.tinyfish_service import parallel_tinyfish_sources
from global_config import get_currency
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


def _dedupe_places(rows: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        address = str(row.get("address") or "").strip()
        if not name and not address:
            continue
        key = (name.lower(), address.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name or address, "address": address})
    return out


def _merge_first_non_empty(results: list[dict], key: str):
    for result in results:
        value = result.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _to_int(value) -> int:
    try:
        return int(str(value).replace(",", "").split()[0])
    except Exception:
        return 0


def _to_bool(value):
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "available", "supported"}:
        return True
    if text in {"false", "no", "not available", "unsupported"}:
        return False
    return None


def _is_missing_vehicle_field(field: str, value) -> bool:
    numeric_fields = {
        "battery_kwh",
        "real_range_city_km",
        "real_range_highway_km",
        "worst_case_km",
        "dc_fast_charge_kw",
    }
    if field in numeric_fields:
        return _to_int(value) <= 0
    return value in (None, "", [], {})


def _merge_missing_vehicle_fields(vehicle_details: dict, supplement: dict, fields: tuple[str, ...]) -> dict:
    merged = dict(vehicle_details)
    for field in fields:
        if _is_missing_vehicle_field(field, merged.get(field)) and not _is_missing_vehicle_field(field, supplement.get(field)):
            merged[field] = supplement.get(field)
    merged["is_fast_charging"] = _to_int(merged.get("dc_fast_charge_kw")) >= 50
    return merged


def _fetch_missing_vehicle_specs(city: str, country: str, car_model: str, missing_fields: tuple[str, ...]) -> dict:
    if not missing_fields:
        return {}

    field_defaults = {
        "battery_kwh": 0,
        "real_range_city_km": 0,
        "real_range_highway_km": 0,
        "worst_case_km": 0,
        "dc_fast_charge_kw": 0,
        "charger_type": "",
        "battery_warranty": "",
    }
    template_lines = [f'  "{field}": {json.dumps(field_defaults[field])}' for field in missing_fields if field in field_defaults]
    if not template_lines:
        return {}

    market_query = quote_plus(f"{car_model} {country} official specs battery capacity range fast charging battery warranty")
    broad_query = quote_plus(f"{car_model} battery kWh range fast charging warranty")
    sources = [
        {"name": "Google Search Specs", "url": f"https://www.google.com/search?q={market_query}", "profile": "lite"},
        {"name": "Google Search Broad", "url": f"https://www.google.com/search?q={broad_query}", "profile": "lite"},
    ]
    goal = f"""Find the missing live product specs for the {car_model} sold in {country.title()}.
Return JSON exactly like this:
{{
{",/n".join(template_lines)}
}}
Only include these fields: {", ".join(missing_fields)}.
Use the battery capacity in kWh and charging power in kW when available.
For any requested field you cannot confirm, return the default shown above.
Do not include any extra fields.
"""

    async def run():
        return await parallel_tinyfish_sources(sources, lambda _network: goal, None, False)

    results = [result for _source, result in asyncio.run(run()) if isinstance(result, dict)]
    return {
        field: _merge_first_non_empty(results, field)
        for field in missing_fields
    }


def _build_live_car_profile(vehicle_details: dict) -> dict | None:
    battery_kwh = _to_int(vehicle_details.get("battery_kwh"))
    dc_kw = _to_int(vehicle_details.get("dc_fast_charge_kw"))
    range_city = _to_int(vehicle_details.get("real_range_city_km"))
    range_highway = _to_int(vehicle_details.get("real_range_highway_km"))
    worst_case = _to_int(vehicle_details.get("worst_case_km"))

    if not range_city or not range_highway:
        return None

    return {
        "real_range_city_km": range_city,
        "real_range_highway_km": range_highway,
        "worst_case_km": worst_case or min(range_city, range_highway),
        "battery_kwh": battery_kwh,
        "dc_fast_charge_kw": dc_kw,
        "segment": "electric vehicle",
    }


def _build_text_report(result: dict) -> str:
    review_breakdown = result.get("review_breakdown", {})
    vehicle = result.get("vehicle_details", {})
    battery_kwh = _to_int(vehicle.get("battery_kwh"))
    lines = [
        f"EV Verdict Report: {result['car']}",
        f"Location: {result['city']}, {result['country']}",
        "",
        "ANXIETY SCORE",
        f"- Daily commute: {result['scores']['daily_score']}/10",
        f"- Long trips: {result['scores']['occasional_score']}/10",
        f"- Daily rationale: {result['scores']['daily_rationale']}",
        f"- Long-trip rationale: {result['scores']['occasional_rationale']}",
        "",
        "CHARGING",
        f"- Charging stations found: {result.get('charging_station_count', 0)}",
        *[f"- {station['name']} | {station['address']}" for station in result.get("stations", [])],
        "",
        "GOOD",
        *[f"- {item}" for item in review_breakdown.get("good", [])],
        "",
        "BAD",
        *[f"- {item}" for item in review_breakdown.get("bad", [])],
        "",
        "UGLY",
        *[f"- {item}" for item in review_breakdown.get("ugly", [])],
        "",
        "VEHICLE",
        f"- Battery capacity: {f'{battery_kwh} kWh' if battery_kwh else 'N/A'}",
        f"- Charger type: {vehicle.get('charger_type') or 'N/A'}",
        f"- Battery warranty: {vehicle.get('battery_warranty') or 'N/A'}",
        f"- IoT map available: {vehicle.get('iot_map_available')}",
        f"- Local price: {vehicle.get('price_formatted') or 'N/A'}",
        f"- Cost analysis: {result.get('cost_analysis') or vehicle.get('cost_analysis') or 'N/A'}",
        "",
        "SHOWROOMS",
        *[f"- {row['name']} | {row['address']}" for row in vehicle.get("showrooms", [])],
        "",
        "DISTRIBUTORS",
        *[f"- {row['name']} | {row['address']}" for row in vehicle.get("distributors", [])],
        "",
        "OWNER REVIEW SUMMARY",
        result.get("owner_review", ""),
    ]
    return "\n".join(lines)


def _review_sources_for_country(car_model: str, country: str) -> list[dict]:
    search_term = quote_plus(f"{car_model} owner review {country}")
    by_country = {
        "india": [
            {"name": "Reddit", "url": f"https://www.google.com/search?q=site%3Areddit.com+{search_term}", "profile": "lite"},
            {"name": "Team-BHP", "url": f"https://www.google.com/search?q=site%3Ateam-bhp.com+{search_term}", "profile": "stealth"},
        ],
        "uk": [
            {"name": "Reddit", "url": f"https://www.google.com/search?q=site%3Areddit.com+{search_term}", "profile": "lite"},
            {"name": "SpeakEV", "url": f"https://www.google.com/search?q=site%3Aspeakev.com+{search_term}", "profile": "lite"},
        ],
        "usa": [
            {"name": "Reddit", "url": f"https://www.google.com/search?q=site%3Areddit.com+{search_term}", "profile": "lite"},
            {"name": "InsideEVs Forum", "url": f"https://www.google.com/search?q=site%3Ainsideevsforum.com+{search_term}", "profile": "lite"},
        ],
        "germany": [
            {"name": "Reddit", "url": f"https://www.google.com/search?q=site%3Areddit.com+{search_term}", "profile": "lite"},
            {"name": "GoingElectric", "url": f"https://www.google.com/search?q=site%3Agoingelectric.de+{search_term}", "profile": "lite"},
        ],
        "uae": [
            {"name": "Reddit", "url": f"https://www.google.com/search?q=site%3Areddit.com+{search_term}", "profile": "lite"},
            {"name": "Drive Arabia Forum", "url": f"https://www.google.com/search?q=site%3Adrivearabia.com+{search_term}", "profile": "lite"},
        ],
    }
    return by_country.get(country) or by_country["usa"]


def _fetch_live_chargers_strict(city: str, country: str) -> dict:
    sources = provider_sources_for_city(city, country)

    async def run():
        return await parallel_tinyfish_sources(
            sources,
            lambda network: f"""Find all EV charging stations listed for {city}, {country.title()} on this page.
Return JSON exactly like this:
{{
  "stations": [
    {{
      "name": "station name",
      "address": "full address",
      "connector_types": ["DC", "AC"],
      "power_kw": 50
    }}
  ]
}}
Only include stations physically in {city}, {country.title()}.
Include connector_types and power_kw when available. Do not include reviews or any extra fields.""",
            None,
            False,
        )

    results = asyncio.run(run())
    stations = []
    for _source, result in results:
        for station in result.get("stations") or []:
            if isinstance(station, dict):
                stations.append({
                    "name": station.get("name", ""),
                    "address": station.get("address", ""),
                    "connector_types": [str(v) for v in (station.get("connector_types") or [])],
                    "power_kw": _to_int(station.get("power_kw")),
                    "status": "live",
                })
    deduped = []
    seen = set()
    for station in stations:
        key = (station["name"].strip().lower(), station["address"].strip().lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(station)
    return {
        "stations": deduped,
        "total_found": len(deduped),
        "source_type": "live",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _fetch_vehicle_details_strict(city: str, country: str, car_model: str) -> dict:
    query = quote_plus(f"{car_model} {city} {country} showroom distributor battery warranty charger iot map price")
    maps_query = quote_plus(f"{car_model} showroom distributor in {city} {country}")
    sources = [
        {"name": "Google Search", "url": f"https://www.google.com/search?q={query}", "profile": "lite"},
        {"name": "Google Maps", "url": f"https://www.google.com/maps/search/{maps_query}", "profile": "lite"},
    ]

    goal = f"""Find live seller and product details for the {car_model} in {city}, {country.title()}.
Return JSON exactly like this:
{{
  "price_formatted": "local price string",
  "battery_kwh": 0,
  "real_range_city_km": 0,
  "real_range_highway_km": 0,
  "worst_case_km": 0,
  "dc_fast_charge_kw": 0,
  "charger_type": "CCS2",
  "battery_warranty": "warranty text",
  "iot_map_available": true,
  "showrooms": [
    {{"name": "showroom name", "address": "full address"}}
  ],
  "distributors": [
    {{"name": "distributor name", "address": "full address"}}
  ],
  "cost_analysis": "2-3 sentence cost analysis for buying and charging this vehicle in this market"
}}
Only include showrooms and distributors located in {city}, {country.title()} that sell the {car_model}.
Do not include service centers unless they also sell the vehicle.
Only include the requested fields."""

    async def run():
        return await parallel_tinyfish_sources(sources, lambda _network: goal, None, False)

    results = [result for _source, result in asyncio.run(run()) if isinstance(result, dict)]
    showrooms = []
    distributors = []
    for result in results:
        showrooms.extend(result.get("showrooms") or [])
        distributors.extend(result.get("distributors") or [])

    return {
        "price_formatted": _merge_first_non_empty(results, "price_formatted"),
        "battery_kwh": _to_int(_merge_first_non_empty(results, "battery_kwh")),
        "real_range_city_km": _to_int(_merge_first_non_empty(results, "real_range_city_km")),
        "real_range_highway_km": _to_int(_merge_first_non_empty(results, "real_range_highway_km")),
        "worst_case_km": _to_int(_merge_first_non_empty(results, "worst_case_km")),
        "dc_fast_charge_kw": _to_int(_merge_first_non_empty(results, "dc_fast_charge_kw")),
        "is_fast_charging": _to_int(_merge_first_non_empty(results, "dc_fast_charge_kw")) >= 50,
        "charger_type": _merge_first_non_empty(results, "charger_type"),
        "battery_warranty": _merge_first_non_empty(results, "battery_warranty"),
        "iot_map_available": _to_bool(_merge_first_non_empty(results, "iot_map_available")),
        "showrooms": _dedupe_places(showrooms),
        "distributors": _dedupe_places(distributors),
        "cost_analysis": _merge_first_non_empty(results, "cost_analysis"),
        "source_type": "live",
    }


def _fetch_owner_reviews_strict(country: str, car_model: str) -> dict:
    sources = _review_sources_for_country(car_model, country)
    goal = f"""Use only Reddit posts and country-specific EV or owner forums from these sources to evaluate the {car_model} in {country.title()}.
Do not use Wikipedia, manufacturer sites, dealer sites, press releases, or generic news articles.
Return JSON exactly like this:
{{
  "owner_review": "4-6 sentence honest summary of customer sentiment, complaints, and positives",
  "good": ["2-4 things owners genuinely like"],
  "bad": ["2-4 recurring complaints or compromises"],
  "ugly": ["1-3 serious issues, risks, or dealbreakers owners mention"],
  "review_sources": ["Reddit", "Forum name"]
}}
The review must clearly sound like owner sentiment from posts, not brochure language."""

    async def run():
        return await parallel_tinyfish_sources(sources, lambda _network: goal, None, False)

    results = [result for _source, result in asyncio.run(run()) if isinstance(result, dict)]
    owner_review = ""
    review_sources: list[str] = []
    good: list[str] = []
    bad: list[str] = []
    ugly: list[str] = []
    for result in results:
        candidate = str(result.get("owner_review") or "").strip()
        if len(candidate) > len(owner_review):
            owner_review = candidate
        review_sources.extend(str(src).strip() for src in (result.get("review_sources") or []) if str(src).strip())
        good.extend(str(item).strip() for item in (result.get("good") or []) if str(item).strip())
        bad.extend(str(item).strip() for item in (result.get("bad") or []) if str(item).strip())
        ugly.extend(str(item).strip() for item in (result.get("ugly") or []) if str(item).strip())

    deduped_sources = []
    seen = set()
    for source in review_sources:
        key = source.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped_sources.append(source)
    review_breakdown = {
        "good": list(dict.fromkeys(good))[:4],
        "bad": list(dict.fromkeys(bad))[:4],
        "ugly": list(dict.fromkeys(ugly))[:3],
    }
    return {
        "owner_review": owner_review,
        "review_sources": deduped_sources,
        "review_breakdown": review_breakdown,
    }


# ── /verdict/stream ──

@router.post("/verdict/stream")
def stream_verdict(query: QueryRequest):
    city = normalize_city(query.city)
    country = normalize_country(query.country)
    car_model = query.car_model
    user_id = query.user_id.strip() or None
    currency_code = get_country_config(country).get("currency", "USD")
    currency_info = get_currency(currency_code)

    def generate():
        yield f"data: {json.dumps({'type': 'SCRAPING_CHARGERS', 'message': f'Scraping live charging stations in {city}, {country.title()}...'})}\n\n"
        charger_data = _fetch_live_chargers_strict(city, country)
        if not charger_data.get("stations"):
            yield f"data: {json.dumps({'type': 'ERROR', 'message': f'No live charging stations were scraped for {city}, {country.title()}.'})}\n\n"
            return
        chargers_done_msg = f"Found {charger_data['total_found']} charging stations in {city}."
        yield f"data: {json.dumps({'type': 'CHARGERS_DONE', 'message': chargers_done_msg})}\n\n"

        yield f"data: {json.dumps({'type': 'SCRAPING_SPECS', 'message': f'Scraping live seller and vehicle details for {car_model} in {city}...'})}\n\n"
        vehicle_details = _fetch_vehicle_details_strict(city, country, car_model)
        if not vehicle_details.get("showrooms"):
            yield f"data: {json.dumps({'type': 'ERROR', 'message': f'No live showroom data was scraped for {car_model} in {city}.'})}\n\n"
            return
        required_live_vehicle_fields = (
            "real_range_city_km",
            "real_range_highway_km",
            "dc_fast_charge_kw",
            "charger_type",
            "battery_warranty",
        )
        missing_vehicle_fields = tuple(
            field for field in required_live_vehicle_fields if _is_missing_vehicle_field(field, vehicle_details.get(field))
        )
        if missing_vehicle_fields:
            logger.info("Retrying missing live vehicle specs for %s: %s", car_model, ", ".join(missing_vehicle_fields))
            recovered_fields = _fetch_missing_vehicle_specs(city, country, car_model, missing_vehicle_fields)
            vehicle_details = _merge_missing_vehicle_fields(vehicle_details, recovered_fields, missing_vehicle_fields)
            missing_vehicle_fields = tuple(
                field for field in required_live_vehicle_fields if _is_missing_vehicle_field(field, vehicle_details.get(field))
            )
        if missing_vehicle_fields:
            missing_fields_msg = ", ".join(missing_vehicle_fields)
            error_msg = f"Live TinyFish vehicle data is incomplete for {car_model}: missing {missing_fields_msg}."
            yield f"data: {json.dumps({'type': 'ERROR', 'message': error_msg})}\n\n"
            return
        specs_done_msg = (
            f"Found {len(vehicle_details.get('showrooms', []))} showrooms and "
            f"{len(vehicle_details.get('distributors', []))} distributors in {city}."
        )
        yield f"data: {json.dumps({'type': 'SPECS_DONE', 'message': specs_done_msg})}\n\n"

        yield f"data: {json.dumps({'type': 'SCRAPING_OWNERS', 'message': 'Reading Reddit and local EV forum owner posts...'})}\n\n"
        owner_reviews = _fetch_owner_reviews_strict(country, car_model)
        if not owner_reviews.get("owner_review"):
            yield f"data: {json.dumps({'type': 'ERROR', 'message': 'No Reddit/forum owner review summary was scraped for this vehicle.'})}\n\n"
            return
        review_breakdown = owner_reviews.get("review_breakdown", {})
        if not review_breakdown.get("good") or not review_breakdown.get("bad") or not review_breakdown.get("ugly"):
            yield f"data: {json.dumps({'type': 'ERROR', 'message': 'Live TinyFish review data is incomplete: good/bad/ugly owner sections were not all scraped.'})}\n\n"
            return
        yield f"data: {json.dumps({'type': 'OWNERS_DONE', 'message': 'Owner review summary loaded from Reddit and EV forums.'})}\n\n"
        yield f"data: {json.dumps({'type': 'SCORING', 'message': 'Calculating anxiety scores from range and charging density...'})}\n\n"
        live_car_profile = _build_live_car_profile(vehicle_details)
        if not live_car_profile:
            yield f"data: {json.dumps({'type': 'ERROR', 'message': f'Live TinyFish range/spec data is incomplete for anxiety scoring on {car_model}.'})}\n\n"
            return
        scores = calculate_anxiety_scores(
            charger_data,
            query.daily_km,
            query.occasional_km,
            car_profile=live_car_profile,
        )
        if query.has_home_charging:
            scores["daily_score"] = max(1, scores["daily_score"] - 1)
            scores["daily_rationale"] += " Home charging reduces day-to-day charging stress."
        yield f"data: {json.dumps({'type': 'REPORT', 'message': 'Building the final report and visual summary...'})}\n\n"

        result = {
            "country": country,
            "city": city,
            "car": query.car_model,
            "currency": currency_code,
            "currency_symbol": currency_info.get("symbol", currency_code),
            "daily_km": query.daily_km,
            "occasional_km": query.occasional_km,
            "scores": scores,
            "stations": charger_data["stations"],
            "charging_station_count": charger_data["total_found"],
            "vehicle_details": vehicle_details,
            "owner_review": owner_reviews["owner_review"],
            "review_sources": owner_reviews.get("review_sources", []),
            "review_breakdown": review_breakdown,
            "cost_analysis": vehicle_details.get("cost_analysis"),
            "verdict": owner_reviews["owner_review"],
            "data_freshness": {
                "chargers": {"source_type": "live", "fetched_at": charger_data.get("fetched_at")},
                "owner_reviews": {"source_type": "live", "fetched_at": datetime.now(timezone.utc).isoformat()},
            },
            "incentives": {"headline": "", "source": ""},
            "sources_used": [
                "TinyFish Web Agent (live charger scrape)",
                "TinyFish Web Agent (live seller/spec scrape)",
                "Reddit + country EV forums only",
            ],
        }
        result["text_report"] = _build_text_report(result)

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

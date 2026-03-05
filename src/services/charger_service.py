"""
EV Mitra — services/charger_service.py
Live charger fetching with cache, static fallback, and background refresh.
"""

import asyncio
import threading
import time
from datetime import datetime, timezone

from core.config import (
    CACHE_TTL_SECONDS,
    WARMUP_DEADLINE_SEC,
    QUICK_MODE_DEADLINE_SEC,
    normalize_city,
    normalize_country,
    get_country_config,
    market_region_for_city,
    logger,
)
from core.cache import (
    charger_cache_key,
    get_charger_cached,
    get_charger_stale,
    put_charger,
    mark_refresh_in_flight,
    clear_refresh_in_flight,
)
from services.tinyfish_service import tinyfish_call, parallel_tinyfish_sources

# ALL_DATA is set at app startup by backend.py calling set_all_data()
_ALL_DATA: dict = {}


def set_all_data(data: dict):
    global _ALL_DATA
    _ALL_DATA = data


def _static_city_fallback(city: str, country: str) -> dict:
    if country != "india":
        return {"stations": [], "total_found": 0, "source_type": "static_fallback", "fetched_at": None}
    key = f"chargers_{city.lower()}"
    data = dict(_ALL_DATA.get(key, {"stations": [], "total_found": 0}))
    data.setdefault("source_type", "static_fallback")
    data.setdefault("fetched_at", None)
    return data


def provider_sources_for_city(city: str, country: str) -> list[dict]:
    state = market_region_for_city(city, country)
    cfg = get_country_config(country)
    out = []
    for p in cfg["providers"]:
        out.append({
            "name": p["name"],
            "profile": p.get("profile", "lite"),
            "url": p["url"].format(city=city, city_lower=city.lower(), state=state),
        })
    return out


def _charger_goal(city: str, country: str, network: str) -> str:
    return f"""
Find all EV charging stations listed for {city}, {country} on this page.
Return JSON:
{{
  "city": "{city}",
  "country": "{country}",
  "network": "{network}",
  "stations": [
    {{
      "name": "station name",
      "address": "full address with area",
      "connector_types": ["DC", "AC"],
      "power_kw": 50
    }}
  ],
  "total_found": 0
}}
If no stations found, return total_found: 0 and empty stations array.
"""


def _best_charger_result(city: str, country: str, results: list[tuple[dict, dict]]) -> dict:
    candidates: list[tuple[int, dict, dict]] = []
    for source, result in results:
        stations = result.get("stations") or []
        if stations:
            candidates.append((len(stations), source, result))
    if not candidates:
        return {}
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, source, winner = candidates[0]
    winner = dict(winner)
    winner["total_found"] = winner.get("total_found") or len(winner.get("stations", []))
    winner["source_type"] = "live"
    winner["country"] = country
    winner["city"] = city
    winner["provider"] = source["name"]
    winner["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return winner


def _refresh_chargers_worker(city: str, country: str, key: str):
    try:
        live = fetch_live_chargers(city, country=country, quick_mode=False, hard_deadline_sec=WARMUP_DEADLINE_SEC)
        if live.get("stations"):
            logger.info("Background refresh updated %s, %s: %d stations", city, country, live.get("total_found", 0))
    finally:
        clear_refresh_in_flight(key)


def _ensure_background_refresh(city: str, country: str) -> bool:
    key = charger_cache_key(city, country)
    if not mark_refresh_in_flight(key):
        return False
    threading.Thread(target=_refresh_chargers_worker, args=(city, country, key), daemon=True).start()
    return True


def fetch_live_chargers(city: str, country: str = "india", quick_mode: bool = False, hard_deadline_sec: int = QUICK_MODE_DEADLINE_SEC) -> dict:
    city = normalize_city(city)
    c = normalize_country(country)
    cache_key = charger_cache_key(city, c)

    cached = get_charger_cached(cache_key)
    if cached:
        age_min = int((time.time() - cached["timestamp"]) / 60)
        logger.debug("Charger cache hit for %s, %s (%dm ago)", city, c, age_min)
        data = dict(cached["data"])
        data["source_type"] = "cache"
        data["age_minutes"] = age_min
        return data

    stale_cache = get_charger_stale(cache_key)
    static_fallback = _static_city_fallback(city, c)
    sources = provider_sources_for_city(city, c)

    async def run_parallel_scrape(timeout_per_source: int) -> dict:
        results = await parallel_tinyfish_sources(
            sources,
            lambda network: _charger_goal(city, c, network),
            timeout_per_source,
        )
        return _best_charger_result(city, c, results)

    if quick_mode:
        fallback = stale_cache or static_fallback
        fallback = dict(fallback)
        fallback["source_type"] = fallback.get("source_type", "cache" if stale_cache else "static_fallback")
        fallback["country"] = c
        fallback["city"] = city

        try:
            live = asyncio.run(asyncio.wait_for(run_parallel_scrape(timeout_per_source=hard_deadline_sec), timeout=hard_deadline_sec))
        except Exception:
            live = {}

        if live.get("stations"):
            put_charger(cache_key, live)
            return live

        refresh_started = _ensure_background_refresh(city, c)
        fallback["background_refresh_started"] = refresh_started
        fallback.setdefault("fetched_at", None)
        return fallback

    try:
        live = asyncio.run(asyncio.wait_for(run_parallel_scrape(timeout_per_source=hard_deadline_sec), timeout=hard_deadline_sec + 1))
    except Exception:
        live = {}

    if live.get("stations"):
        put_charger(cache_key, live)
        return live

    fallback = stale_cache or static_fallback
    fallback = dict(fallback)
    fallback["country"] = c
    fallback["city"] = city
    fallback.setdefault("source_type", "static_fallback")
    fallback.setdefault("fetched_at", None)
    return fallback

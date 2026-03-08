"""
EV Mitra — services/ev_model_service.py
Live EV model fetching via TinyFish with in-memory cache.
"""

import asyncio
import time
from typing import Optional

from core.config import logger
from services.tinyfish_service import tinyfish_call

# ── Cache ──
EV_MODEL_CACHE: dict[str, dict] = {}  # country_code → {timestamp, models}
EV_MODEL_CACHE_TTL = 3600  # 1 hour

# ── Scraping sources per country ──
_COUNTRY_SOURCES: dict[str, list[dict]] = {
    "india": [
        {
            "name": "CarAndBike India EV",
            "url": "https://www.carandbike.com/electric-cars",
            "profile": "lite",
        },
        {
            "name": "CardEkho India EV",
            "url": "https://www.cardekho.com/electric-cars",
            "profile": "lite",
        },
    ],
    "usa": [
        {
            "name": "EV Database US",
            "url": "https://ev-database.org/us/",
            "profile": "lite",
        },
        {
            "name": "MotorTrend EV",
            "url": "https://www.motortrend.com/cars/electric/",
            "profile": "lite",
        },
    ],
    "uk": [
        {
            "name": "EV Database UK",
            "url": "https://ev-database.org/uk/",
            "profile": "lite",
        },
        {
            "name": "Autocar UK EV",
            "url": "https://www.autocar.co.uk/electric-cars",
            "profile": "lite",
        },
    ],
    "germany": [
        {
            "name": "EV Database DE",
            "url": "https://ev-database.org/de/",
            "profile": "lite",
        },
    ],
    "uae": [
        {
            "name": "MotorME UAE EV",
            "url": "https://www.motoringme.com/car-type/electric/",
            "profile": "lite",
        },
    ],
    "_global": [
        {
            "name": "EV Database Global",
            "url": "https://ev-database.org/",
            "profile": "lite",
        },
    ],
}

_COUNTRY_GOAL: dict[str, str] = {
    "india": (
        "List every electric passenger car model that is currently available to buy new in India. "
        "Return only active consumer EV model names sold in India right now. "
        "Exclude discontinued, upcoming, concept, fleet-only, bus, truck, and two-wheeler models. "
        "Use full brand plus model names. Return exactly: {\"models\": [\"Brand Model\", ...]}"
    ),
    "usa": (
        "List every electric passenger car model that is currently available to buy new in the United States. "
        "Return only active consumer EV model names sold in the US right now. "
        "Exclude discontinued, upcoming, concept, fleet-only, bus, truck, and two-wheeler models. "
        "Use full brand plus model names. Return exactly: {\"models\": [\"Brand Model\", ...]}"
    ),
    "uk": (
        "List every electric passenger car model that is currently available to buy new in the United Kingdom. "
        "Return only active consumer EV model names sold in the UK right now. "
        "Exclude discontinued, upcoming, concept, fleet-only, bus, truck, and two-wheeler models. "
        "Use full brand plus model names. Return exactly: {\"models\": [\"Brand Model\", ...]}"
    ),
    "germany": (
        "List every electric passenger car model that is currently available to buy new in Germany. "
        "Return only active consumer EV model names sold in Germany right now. "
        "Exclude discontinued, upcoming, concept, fleet-only, bus, truck, and two-wheeler models. "
        "Use full brand plus model names. Return exactly: {\"models\": [\"Brand Model\", ...]}"
    ),
    "uae": (
        "List every electric passenger car model that is currently available to buy new in the UAE. "
        "Return only active consumer EV model names sold in the UAE right now. "
        "Exclude discontinued, upcoming, concept, fleet-only, bus, truck, and two-wheeler models. "
        "Use full brand plus model names. Return exactly: {\"models\": [\"Brand Model\", ...]}"
    ),
    "_global": (
        "List every electric passenger car model currently available to buy new in this market. "
        "Return only active consumer EV model names. "
        "Exclude discontinued, upcoming, concept, fleet-only, bus, truck, and two-wheeler models. "
        "Use full brand plus model names. Return exactly: {\"models\": [\"Brand Model\", ...]}"
    ),
}


def _shape_live_model(raw: str | dict) -> Optional[dict]:
    """Normalise a raw scraped model name into the EvModel schema."""
    if isinstance(raw, str):
        name = raw.strip()
    elif isinstance(raw, dict):
        name = str(raw.get("name") or raw.get("model") or raw.get("car") or "").strip()
    else:
        name = ""
    if not name or len(name) < 3:
        return None
    return {
        "name": name,
        "brand": name.split()[0],
        "segment": "ev",
        "real_range_city_km": 0,
        "real_range_highway_km": 0,
        "battery_kwh": 0,
        "dc_fast_charge_kw": 0,
        "base_price_usd": 0,
        "source": "live",
    }


def _extract_models_from_result(result: dict) -> list[dict]:
    """Extract and shape model list from a TinyFish result dict."""
    raw_list = result.get("models") or result.get("car_models") or result.get("names") or []
    if not isinstance(raw_list, list):
        return []
    out = []
    for raw in raw_list:
        shaped = _shape_live_model(raw)
        if shaped:
            out.append(shaped)
    return out


def _merge_models(live_models: list[dict]) -> list[dict]:
    """Deduplicate model names while preserving first-seen order."""
    merged = []
    seen = set()
    for lm in live_models:
        key = lm["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(lm)
    return merged


async def fetch_live_ev_models(country: str, use_cache: bool = False) -> list[dict]:
    """
    Fetch EV models for a country using TinyFish parallel scraping.
    Returns TinyFish live model names for the selected market.
    Each call can be forced to hit TinyFish directly by disabling cache.
    """
    cached = EV_MODEL_CACHE.get(country)
    if use_cache and cached and (time.time() - cached["timestamp"]) < EV_MODEL_CACHE_TTL:
        logger.info("EV model cache hit for %s (%d models)", country, len(cached["models"]))
        return cached["models"]

    sources = _COUNTRY_SOURCES.get(country) or _COUNTRY_SOURCES["_global"]
    goal = _COUNTRY_GOAL.get(country) or _COUNTRY_GOAL["_global"]
    timeout = None

    async def _fetch_one(source: dict):
        try:
            result = await asyncio.to_thread(
                tinyfish_call, source["url"], goal, source.get("profile", "lite"), timeout, False
            )
            return result if isinstance(result, dict) else {}
        except Exception as exc:
            logger.warning("EV model fetch failed for %s: %s", source["name"], exc)
            return {}

    tasks = [_fetch_one(s) for s in sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    live_models: list[dict] = []
    for res in results:
        if isinstance(res, Exception) or not res:
            continue
        live_models.extend(_extract_models_from_result(res))

    if live_models:
        merged = _merge_models(live_models)
        EV_MODEL_CACHE[country] = {"timestamp": time.time(), "models": merged}
        logger.info("EV model live fetch OK for %s: %d models", country, len(merged))
        return merged

    logger.warning("EV model live fetch returned nothing for %s", country)
    return []

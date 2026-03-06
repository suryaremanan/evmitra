"""
EV Mitra — routers/health.py
Operational endpoints: health, debug-keys, cache-status, data-freshness, cars, profile.
"""

import os
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from core.config import TINYFISH_API_KEY, normalize_country, logger
from core.cache import CHARGER_CACHE, TEAMBHP_CACHE
from car_profiles import CAR_PROFILES, CAR_MODEL_LIST, get_models_for_country
from services.tinyfish_service import tinyfish_cb
from global_config import COUNTRIES, CURRENCIES
import user_store

router = APIRouter()

# Injected at startup by backend.py
ALL_DATA: dict = {}


def set_all_data(data: dict):
    global ALL_DATA
    ALL_DATA = data


# ── models ──


class ProfileRequest(BaseModel):
    user_id: str
    preferred_city: Optional[str] = None
    preferred_car: Optional[str] = None
    preferred_daily_km: Optional[int] = None
    preferred_occasional_km: Optional[int] = None
    has_home_charging: Optional[bool] = None


# ── endpoints ──


@router.get("/countries")
def get_countries():
    result = []
    for code, c in COUNTRIES.items():
        currency_code = c.get("currency", "USD")
        currency_symbol = CURRENCIES.get(currency_code, {}).get("symbol", currency_code)
        result.append({
            "code": code,
            "name": c["name"],
            "flag": c.get("flag", "🌐"),
            "currency": currency_code,
            "currency_symbol": currency_symbol,
            "cities": c.get("cities", []),
            "region_label": c.get("region_label", "City"),
        })
    return {"countries": result}


@router.get("/health")
def health():
    return {
        "status": "ok",
        "tinyfish_api_key_set": bool(TINYFISH_API_KEY),
        "tinyfish_circuit_breaker": tinyfish_cb.status,
        "owner_data_loaded": {
            "teambhp_thread1": bool(ALL_DATA.get("teambhp_thread1")),
            "teambhp_thread2": bool(ALL_DATA.get("teambhp_thread2")),
            "teambhp_thread3": bool(ALL_DATA.get("teambhp_thread3")),
        },
        "mode": "live_tinyfish_streaming",
        "car_profiles_loaded": CAR_MODEL_LIST,
        "charger_cache_cities": list(CHARGER_CACHE.keys()),
        "teambhp_cache_models": list(TEAMBHP_CACHE.keys()),
    }


@router.get("/debug-keys")
def debug_keys():
    _root_env = Path(__file__).resolve().parent.parent.parent / ".env"
    _src_env  = Path(__file__).resolve().parent.parent / ".env"
    return {
        "keys": {
            "ANTHROPIC_API_KEY":  "present" if os.environ.get("ANTHROPIC_API_KEY")  else "MISSING",
            "FIREWORKS_API_KEY":  "present" if os.environ.get("FIREWORKS_API_KEY")  else "MISSING",
            "TINYFISH_API_KEY":   "present" if os.environ.get("TINYFISH_API_KEY")   else "MISSING",
        },
        "dotenv_files": {
            "project_root_.env": {
                "path": str(_root_env),
                "exists": _root_env.exists(),
            },
            "src_.env": {
                "path": str(_src_env),
                "exists": _src_env.exists(),
            },
        },
        "llm_will_work": (
            bool(os.environ.get("ANTHROPIC_API_KEY")) or
            bool(os.environ.get("FIREWORKS_API_KEY"))
        ),
        "tinyfish": {
            "circuit_breaker": tinyfish_cb.status,
        },
    }


@router.get("/cache-status")
def cache_status():
    now = time.time()
    charger_status = {}

    for key, entry in CHARGER_CACHE.items():
        if ":" in key:
            country, city = key.split(":", 1)
        else:
            country, city = "india", key
        age_min = int((now - entry["timestamp"]) / 60)
        charger_status[f"{country}:{city}"] = {
            "cached": True,
            "age_min": age_min,
            "fresh": age_min < 60,
            "stations": entry["data"].get("total_found", 0),
            "country": country,
            "city": city,
        }
        if country == "india":
            charger_status[city] = charger_status[f"{country}:{city}"]

    for key, val in ALL_DATA.items():
        if key.startswith("chargers_") and val:
            city = key.replace("chargers_", "").capitalize()
            if city not in charger_status:
                charger_status[city] = {
                    "cached": True,
                    "age_min": None,
                    "fresh": False,
                    "stations": val.get("total_found", len(val.get("stations", []))),
                }

    return {
        "charger_cache": charger_status,
        "teambhp_cache": list(TEAMBHP_CACHE.keys()),
    }


@router.get("/data-freshness")
def data_freshness():
    now = time.time()
    charger_info = {}

    for key, entry in CHARGER_CACHE.items():
        if ":" in key:
            country, city = key.split(":", 1)
        else:
            country, city = "india", key
        age_min = int((now - entry["timestamp"]) / 60)
        charger_info[f"{country}:{city}"] = {
            "source_type": "live" if age_min == 0 else "cache",
            "age_minutes": age_min,
            "fetched_at": entry["data"].get("fetched_at"),
            "total_stations": entry["data"].get("total_found", 0),
            "country": country,
            "city": city,
        }

    for key in ALL_DATA:
        if key.startswith("chargers_") and ALL_DATA[key]:
            city = key.replace("chargers_", "").capitalize()
            if city not in charger_info:
                charger_info[city] = {
                    "source_type": "static_fallback",
                    "age_minutes": None,
                    "fetched_at": None,
                    "total_stations": ALL_DATA[key].get("total_found", 0),
                }

    teambhp_info = {}
    for model, entry in TEAMBHP_CACHE.items():
        age_min = int((now - entry["timestamp"]) / 60)
        teambhp_info[model] = {
            "source_type": "cache" if age_min > 0 else "live",
            "age_minutes": age_min,
        }

    return {
        "chargers": charger_info,
        "teambhp": teambhp_info,
        "supported_cars": CAR_MODEL_LIST,
    }


@router.get("/cars")
def list_cars(country: str = "india"):
    """Returns car models available for the given country."""
    c = normalize_country(country)
    models = get_models_for_country(c)
    return {
        "country": c,
        "models": [
            {"name": name, "segment": CAR_PROFILES[name]["segment"], "markets": CAR_PROFILES[name]["markets"]}
            for name in models
        ],
    }


@router.post("/profile")
def save_profile(req_body: ProfileRequest):
    prefs = req_body.model_dump(exclude={"user_id"}, exclude_none=True)
    profile = user_store.upsert_profile(req_body.user_id, prefs)
    return {"status": "ok", "profile": profile}


@router.get("/profile/{user_id}")
def get_profile_endpoint(user_id: str):
    profile = user_store.get_profile(user_id)
    if not profile:
        return {"profile": None}
    return {"profile": profile}

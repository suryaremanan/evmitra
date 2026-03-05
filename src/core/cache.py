"""
EV Mitra — core/cache.py
Thread-safe TTL cache for charger and Team-BHP data.
"""

import threading
import time

from core.config import CACHE_TTL_SECONDS, logger

# ── Global caches ──
CHARGER_CACHE: dict[str, dict] = {}   # "country:city" → {data, timestamp}
TEAMBHP_CACHE: dict[str, dict] = {}   # car_model_lower  → {data, timestamp}

_REFRESH_LOCK = threading.Lock()
_REFRESH_IN_FLIGHT: set[str] = set()


def charger_cache_key(city: str, country: str) -> str:
    return f"{country}:{city}"


def teambhp_cache_key(car_model: str) -> str:
    return car_model.strip().lower()


def get_charger_cached(key: str) -> dict | None:
    entry = CHARGER_CACHE.get(key)
    if entry and (time.time() - entry["timestamp"]) < CACHE_TTL_SECONDS:
        return entry
    return None


def get_charger_stale(key: str) -> dict | None:
    entry = CHARGER_CACHE.get(key)
    return dict(entry["data"]) if entry else None


def put_charger(key: str, data: dict):
    CHARGER_CACHE[key] = {"data": data, "timestamp": time.time()}


def get_teambhp_cached(key: str) -> dict | None:
    entry = TEAMBHP_CACHE.get(key)
    if entry and (time.time() - entry["timestamp"]) < CACHE_TTL_SECONDS:
        return entry
    return None


def put_teambhp(key: str, data: dict):
    TEAMBHP_CACHE[key] = {"data": data, "timestamp": time.time()}


def mark_refresh_in_flight(key: str) -> bool:
    """Returns True if this key was NOT already in-flight (i.e., we claimed it)."""
    with _REFRESH_LOCK:
        if key in _REFRESH_IN_FLIGHT:
            return False
        _REFRESH_IN_FLIGHT.add(key)
        return True


def clear_refresh_in_flight(key: str):
    with _REFRESH_LOCK:
        _REFRESH_IN_FLIGHT.discard(key)

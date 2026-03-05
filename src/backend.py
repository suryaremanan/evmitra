"""
EV Mitra — backend.py
Slim entry-point: creates FastAPI app, registers routers,
loads data, warms caches.

Usage:
  pip install fastapi uvicorn anthropic python-dotenv
  python backend.py          # or: uvicorn src.backend:app
"""

import time
import threading
from pathlib import Path

# ── Load .env early ──
try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve().parent
    load_dotenv(_here / ".env", override=False)
    load_dotenv(_here.parent / ".env", override=False)
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import (
    TINYFISH_API_KEY, CACHE_TTL_SECONDS,
    COUNTRY_CONFIG, WARMUP_COUNTRIES, logger,
)
from core.cache import CHARGER_CACHE, charger_cache_key
from synthesis import load_all_data
from services.charger_service import fetch_live_chargers
from services.tinyfish_service import tinyfish_cb
import user_store

# ── Import routers ──
from routers import verdict, route, intelligence, chargers, health

# ── Import services that need ALL_DATA injected ──
from services import charger_service, teambhp_service

# ── Create app ──
app = FastAPI(title="EV Mitra API", version="4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ──
app.include_router(verdict.router)
logger.info("Router registered: verdict (/verdict/stream, /verdict, /compare)")
app.include_router(route.router)
logger.info("Router registered: route (/route/stream)")
app.include_router(intelligence.router)
logger.info("Router registered: intelligence (/intelligence-report)")
app.include_router(chargers.router)
logger.info("Router registered: chargers (/chargers/stream)")
app.include_router(health.router)
logger.info("Router registered: health (/health, /cache-status, /cars, ...)")

# ── Load static data & inject into modules that need it ──
logger.info("Loading owner insight data files...")
ALL_DATA = load_all_data()
logger.info("Data ready")

charger_service.set_all_data(ALL_DATA)
teambhp_service.set_all_data(ALL_DATA)
verdict.set_all_data(ALL_DATA)
health.set_all_data(ALL_DATA)

user_store.init_db()
logger.info("User store ready")


# ── Startup cache warmup — country-aware ──

def warm_cache():
    """Pre-warm charger cache for countries listed in WARMUP_COUNTRIES env var."""
    if not WARMUP_COUNTRIES:
        logger.info("Warmup: WARMUP_COUNTRIES is empty — skipping")
        return

    logger.info("Warming cache for: %s", ", ".join(WARMUP_COUNTRIES))

    if tinyfish_cb.is_open:
        logger.info("TinyFish circuit breaker open — skipping live warmup")
        return

    for country in WARMUP_COUNTRIES:
        cfg = COUNTRY_CONFIG.get(country) or COUNTRY_CONFIG.get("_global")
        if not cfg:
            continue
        cities = cfg.get("warmup_cities", [])
        if not cities:
            logger.info("  %s: no warmup_cities configured — skipping", country)
            continue
        logger.info("Warming %s: %s", country, ", ".join(cities))
        for city in cities:
            cache_key = charger_cache_key(city, country)
            cached = CHARGER_CACHE.get(cache_key)
            if cached and (time.time() - cached["timestamp"]) < CACHE_TTL_SECONDS:
                logger.debug("  %s: already in cache", city)
                continue

            static_key = f"chargers_{city.lower()}"
            if ALL_DATA.get(static_key, {}).get("stations"):
                logger.debug("  %s: using static JSON", city)
                continue

            try:
                logger.info("  Warming %s...", city)
                data = fetch_live_chargers(city, country=country, quick_mode=False, hard_deadline_sec=12)
                if data.get("stations"):
                    logger.info("  %s: %s stations cached", city, data.get("total_found", 0))
                else:
                    logger.warning("  %s: no stations found via TinyFish", city)
            except Exception:
                logger.warning("  %s warmup failed", city, exc_info=True)


threading.Thread(target=warm_cache, daemon=True).start()


if __name__ == "__main__":
    import uvicorn
    logger.info("EV Mitra backend starting...")
    logger.info("  API:     http://localhost:8080")
    logger.info("  Docs:    http://localhost:8080/docs")
    logger.info("  Health:  http://localhost:8080/health")
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)

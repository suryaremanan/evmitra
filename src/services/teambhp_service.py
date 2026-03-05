"""
EV Mitra — services/teambhp_service.py
Live Team-BHP scraping with cache fallback.
India-only: callers gate on country before invoking.
"""

import asyncio
import threading
import time
from datetime import datetime, timezone

from core.config import QUICK_MODE_DEADLINE_SEC, WARMUP_DEADLINE_SEC, logger
from core.cache import teambhp_cache_key, get_teambhp_cached, put_teambhp
from services.tinyfish_service import parallel_tinyfish_sources

# Set at startup by backend.py
_ALL_DATA: dict = {}


def set_all_data(data: dict):
    global _ALL_DATA
    _ALL_DATA = data


def _teambhp_sources(car_model: str) -> list[dict]:
    search_term = car_model.replace(" ", "+")
    return [
        {
            "name": "Team-BHP Search",
            "url": f"https://www.team-bhp.com/forum/search.php?searchid=0&q={search_term}+review+ownership&submit=Search",
            "profile": "stealth",
        },
        {
            "name": "Team-BHP EV Forum",
            "url": f"https://www.team-bhp.com/forum/electric-cars/?q={search_term}",
            "profile": "stealth",
        },
        {
            "name": "Google site:Team-BHP",
            "url": f"https://www.google.com/search?q=site%3Ateam-bhp.com+{search_term}+ownership+review",
            "profile": "lite",
        },
    ]


def fetch_live_teambhp(car_model: str, quick_mode: bool = False, hard_deadline_sec: int = QUICK_MODE_DEADLINE_SEC) -> dict:
    """
    Scrapes Team-BHP live for owner insights on the given EV model.
    Checks TTL cache first; falls back to static JSON if scrape fails.
    """
    cache_key = teambhp_cache_key(car_model)
    cached = get_teambhp_cached(cache_key)
    if cached:
        age_min = int((time.time() - cached["timestamp"]) / 60)
        logger.debug("Team-BHP cache hit for %s (%dm ago)", car_model, age_min)
        return cached["data"]

    goal = f"""Search Team-BHP forum for owner reviews of the {car_model} electric vehicle.
Read the search results and find real, long-term owner experiences.
Extract genuine ownership insights and return JSON exactly like this:
{{
  "car_model": "{car_model}",
  "source": "Team-BHP",
  "honest_verdict": "One sentence overall verdict from real owners",
  "real_world_range": {{
    "city_ac_on_km": 180,
    "highway_kmph_100": 230,
    "worst_case_km": 120,
    "best_case_km": 250
  }},
  "long_term_issues": [
    "Specific issue reported by owners",
    "Another issue reported by multiple owners"
  ],
  "things_owners_love": [
    "Genuine positive from owners",
    "Another positive"
  ],
  "charging_network_experiences": [
    {{"quote": "Direct owner quote about charging reliability"}}
  ],
  "most_honest_quote": "Most candid owner quote about the car",
  "would_buy_again": true,
  "biggest_regret": "Most common regret from owners"
}}
Use ONLY real data from the forum. Be honest about issues — accuracy is what makes this valuable.
If you cannot find specific numbers, return null for that field. Do not invent or estimate.
"""

    sources = _teambhp_sources(car_model)

    async def run_parallel_teambhp(timeout_per_source: int) -> dict:
        results = await parallel_tinyfish_sources(
            sources,
            lambda _network: goal,
            timeout_per_source,
        )
        for _source, result in results:
            if result.get("honest_verdict"):
                result = dict(result)
                result["source_type"] = "live"
                result["fetched_at"] = datetime.now(timezone.utc).isoformat()
                return result
        return {}

    if quick_mode:
        try:
            result = asyncio.run(asyncio.wait_for(run_parallel_teambhp(timeout_per_source=hard_deadline_sec), timeout=hard_deadline_sec))
        except Exception:
            result = {}
        if result and result.get("honest_verdict"):
            put_teambhp(cache_key, result)
            logger.info("Team-BHP scraped live for %s", car_model)
            return result
        stale = dict(cached["data"]) if cached else None
        fallback = stale or _ALL_DATA.get("teambhp_thread1", {})
        fallback = dict(fallback)
        fallback.setdefault("source_type", "cache" if stale else "static_fallback")

        def bg_refresh():
            try:
                full = fetch_live_teambhp(car_model, quick_mode=False, hard_deadline_sec=WARMUP_DEADLINE_SEC)
                if full.get("honest_verdict"):
                    logger.info("Team-BHP background refresh updated %s", car_model)
            except Exception:
                pass

        threading.Thread(target=bg_refresh, daemon=True).start()
        return fallback

    try:
        result = asyncio.run(asyncio.wait_for(run_parallel_teambhp(timeout_per_source=hard_deadline_sec), timeout=hard_deadline_sec + 1))
    except Exception:
        result = {}

    if result and result.get("honest_verdict"):
        put_teambhp(cache_key, result)
        logger.info("Team-BHP scraped live for %s", car_model)
        return result

    logger.debug("Team-BHP fallback to static JSON for %s", car_model)
    return _ALL_DATA.get("teambhp_thread1", {})

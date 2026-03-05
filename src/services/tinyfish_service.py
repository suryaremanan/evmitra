"""
EV Mitra — services/tinyfish_service.py
TinyFish API client with circuit breaker and parallel fan-out.
"""

import asyncio
import json

import requests as req

from core.config import TINYFISH_API_KEY, TINYFISH_BASE_URL, TINYFISH_DEFAULT_TIMEOUT, logger
from core.circuit_breaker import CircuitBreaker

# Module-level circuit breaker for TinyFish
tinyfish_cb = CircuitBreaker(name="tinyfish")


def tinyfish_call(url: str, goal: str, profile: str = "lite", timeout: int = TINYFISH_DEFAULT_TIMEOUT) -> dict:
    """Single TinyFish SSE call — returns parsed result or empty dict on failure."""
    if tinyfish_cb.is_open:
        return {}
    try:
        with req.post(
            TINYFISH_BASE_URL,
            json={"url": url, "goal": goal, "browser_profile": profile},
            headers={
                "X-API-Key": TINYFISH_API_KEY,
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            stream=True,
            timeout=timeout,
        ) as resp:
            if resp.status_code != 200:
                try:
                    err_body = resp.json()
                    err_msg = (err_body.get("error") or {}).get("message") or str(err_body)
                except Exception:
                    err_msg = resp.text[:200] or f"HTTP {resp.status_code}"
                unrecoverable = resp.status_code in (401, 403) or "credits" in err_msg.lower() or "forbidden" in err_msg.lower()
                if unrecoverable:
                    tinyfish_cb.trip(err_msg)
                    logger.error("TinyFish disabled: %s", err_msg)
                    logger.info("Top up credits at https://tinyfish.ai or set a new TINYFISH_API_KEY in .env")
                else:
                    tinyfish_cb.record_failure(err_msg)
                    logger.warning("TinyFish HTTP %d: %s", resp.status_code, err_msg)
                return {}
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                    if event.get("type") == "COMPLETE":
                        result = event.get("resultJson", {})
                        if isinstance(result, str):
                            result = json.loads(result)
                        tinyfish_cb.record_success()
                        return result
                    elif event.get("type") == "ERROR":
                        logger.warning("TinyFish error event: %s", event.get("message"))
                        tinyfish_cb.record_failure(event.get("message", ""))
                        return {}
                except json.JSONDecodeError:
                    continue
    except (req.exceptions.Timeout, req.exceptions.ConnectionError):
        pass  # timeouts/connection drops are expected with short deadlines
    except Exception as e:
        if "timed out" not in str(e).lower() and "timeout" not in str(e).lower():
            logger.warning("TinyFish call failed: %s", e)
    return {}


async def parallel_tinyfish_sources(
    sources: list[dict],
    goal_builder,
    timeout_per_source: int,
) -> list[tuple[dict, dict]]:
    """Fan-out multiple TinyFish calls in parallel. Returns [(source, result), ...]."""
    async def one(source: dict):
        result = await asyncio.to_thread(
            tinyfish_call,
            source["url"],
            goal_builder(source["name"]),
            source.get("profile", "lite"),
            timeout_per_source,
        )
        return source, result if isinstance(result, dict) else {}

    tasks = [one(source) for source in sources]
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[tuple[dict, dict]] = []
    for item in raw:
        if isinstance(item, Exception):
            logger.warning("TinyFish parallel task exception: %s", item)
            continue
        out.append(item)  # type: ignore[arg-type]
    return out


def discover_route_via_tinyfish(from_city: str, to_city: str, country: str) -> dict | None:
    """
    Discover distance + waypoints for an unknown city pair via Google Maps scrape.
    Returns a route dict compatible with HIGHWAY_ROUTES schema, or None.
    """
    country_label = country.title()
    url = f"https://www.google.com/maps/dir/{from_city}+{country_label}/{to_city}+{country_label}"
    goal = f"""Find the driving distance from {from_city} to {to_city} in {country_label}.
Return JSON exactly like this:
{{
  "distance_km": 350,
  "highway": "NH44",
  "waypoints": [
    {{"name": "Major city or town en route", "km": 120, "state": "state-name"}}
  ]
}}
List 2-4 major towns/cities along the route as waypoints with their approximate cumulative km from {from_city}.
Be accurate. Do not invent waypoints — only list real towns on this route."""
    result = tinyfish_call(url, goal, profile="lite", timeout=90)
    if result and result.get("distance_km"):
        return result
    return None

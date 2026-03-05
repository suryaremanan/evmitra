"""
EV Mitra — backend.py
FastAPI server wrapping the synthesis pipeline.

Usage:
  pip install fastapi uvicorn anthropic python-dotenv
  python backend.py

API runs at http://localhost:8080
"""

import json
import math
import os
import asyncio
import queue as queue_module
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional
import requests as req
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Load .env — check src dir first, then project root (works for both
# `python backend.py` from src/ and `uvicorn src.backend:app` from project root)
try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve().parent          # always absolute: .../src
    load_dotenv(_here / ".env", override=False)      # src/.env (if it exists)
    load_dotenv(_here.parent / ".env", override=False)  # project-root/.env
except ImportError:
    pass  # python-dotenv not installed, rely on OS env vars

# ── Import synthesis logic ──
from synthesis import (
    load_all_data,
    calculate_anxiety_scores,
    extract_owner_insights,
    build_prompt,
    call_llm,
    MAHARASHTRA_SUBSIDY,
)

# ── Import car profiles and user store ──
from car_profiles import CAR_PROFILES, CAR_MODEL_LIST, get_profile as get_car_profile, get_models_for_country
import user_store

app = FastAPI(title="EV Mitra API", version="3.0")

# Allow frontend to call backend locally
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── TinyFish config ──
TINYFISH_API_KEY = os.environ.get("TINYFISH_API_KEY", "")
if TINYFISH_API_KEY:
    masked = TINYFISH_API_KEY[:20] + "..." + TINYFISH_API_KEY[-5:]
    print(f"🔑 TinyFish key loaded: {masked}")
else:
    print("⚠️  TINYFISH_API_KEY not set — live scraping will fail")
TINYFISH_BASE_URL = "https://agent.tinyfish.ai/v1/automation/run-sse"
# Circuit breaker: set to True after the first unrecoverable TinyFish error
# (e.g. 0 credits, invalid key) so subsequent calls skip immediately.
_TINYFISH_DISABLED = False
_TINYFISH_DISABLE_REASON = ""

# Pre-load static owner/subsidy data once at startup
print("📂 Loading owner insight data files...")
ALL_DATA = load_all_data()
print("✅ Data ready")

# Initialize SQLite user store
user_store.init_db()
print("🗄️  User store ready\n")

# ── Result caches with TTL (Fix 4) ──
CHARGER_CACHE: dict[str, dict] = {}   # city → {data, timestamp}
TEAMBHP_CACHE: dict[str, dict] = {}   # car_model → {data, timestamp}
CACHE_TTL_SECONDS = 3600              # 1 hour
_REFRESH_LOCK = threading.Lock()
_REFRESH_IN_FLIGHT: set[str] = set()

# ── Country configuration — single source of truth for all regions ──
# Each entry has: providers, currency, city_region_map, default_cities, incentives.
# "_global" is the fallback for any unrecognised country.
COUNTRY_CONFIG: dict[str, dict] = {
    "india": {
        "currency": "INR",
        "city_region_map": {
            "Nagpur":     "maharashtra",
            "Pune":       "maharashtra",
            "Mumbai":     "maharashtra",
            "Delhi":      "delhi",
            "Bangalore":  "karnataka",
            "Hyderabad":  "telangana",
            "Chennai":    "tamil-nadu",
            "Ahmedabad":  "gujarat",
        },
        "default_cities": ["Nagpur", "Pune", "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Ahmedabad"],
        "providers": [
            {"name": "ChargeZone",  "url": "https://chargezone.in/charging-stations/{state}/{city}",           "profile": "lite"},
            {"name": "EVSE India",  "url": "https://evseindia.org/charging-station/{city}",                    "profile": "lite"},
            {"name": "Statiq",      "url": "https://www.statiq.in/charging-stations/{city_lower}",             "profile": "stealth"},
        ],
        "incentives": {
            "maharashtra": MAHARASHTRA_SUBSIDY,
            "default": {
                "state_name": "India",
                "fame2_status": "FAME II ended March 2024. FAME III under discussion.",
                "total_estimated_saving_inr": 0,
                "note": "Verify current EV incentives with a local dealer. Most states offer road tax and registration benefits.",
                "source": "State EV policy (verify locally)",
            },
        },
    },
    "uae": {
        "currency": "AED",
        "city_region_map": {
            "Dubai":     "dubai",
            "Abu Dhabi": "abu-dhabi",
            "Sharjah":   "sharjah",
        },
        "default_cities": ["Dubai", "Abu Dhabi", "Sharjah"],
        "providers": [
            {"name": "PlugShare UAE",   "url": "https://www.plugshare.com/search?query={city}+UAE+EV+charging",        "profile": "stealth"},
            {"name": "Google Maps UAE", "url": "https://www.google.com/maps/search/EV+charging+stations+in+{city}+UAE","profile": "lite"},
            {"name": "UAEV Portal",     "url": "https://uaev.ae/search?city={city}",                                   "profile": "lite"},
        ],
        "incentives": {
            "dubai": {
                "state_name": "Dubai",
                "fame2_status": "No FAME equivalent. Incentives are utility/tariff and parking-policy dependent.",
                "total_estimated_saving_inr": 0,
                "note": "Incentives vary by authority (DEWA/RTA/free-zone). Verify latest EV charging and parking policies.",
                "source": "Dubai EV Green Charger / RTA policy pages",
            },
            "default": {
                "state_name": "UAE",
                "fame2_status": "No national purchase subsidy baseline for all emirates.",
                "total_estimated_saving_inr": 0,
                "note": "Verify EV incentives with local authority and utility provider.",
                "source": "UAE local authority policy pages",
            },
        },
    },
    "uk": {
        "currency": "GBP",
        "city_region_map": {},
        "default_cities": ["London", "Manchester", "Birmingham", "Edinburgh", "Bristol"],
        "providers": [
            {"name": "PlugShare UK",    "url": "https://www.plugshare.com/search?query={city}+UK+EV+charging",         "profile": "stealth"},
            {"name": "Zap-Map",         "url": "https://www.zap-map.com/charge-points/map/?search={city}",             "profile": "lite"},
            {"name": "Pod Point",       "url": "https://pod-point.com/charging-near-me/{city_lower}",                  "profile": "lite"},
        ],
        "incentives": {
            "default": {
                "state_name": "United Kingdom",
                "fame2_status": "UK Plug-in Car Grant ended June 2022. OZEV home charger grant (EVHS) still active.",
                "total_estimated_saving_inr": 0,
                "note": "Check current OZEV grants and local council EV incentives.",
                "source": "UK OZEV (Office for Zero Emission Vehicles)",
            },
        },
    },
    "usa": {
        "currency": "USD",
        "city_region_map": {},
        "default_cities": ["New York", "Los Angeles", "Chicago", "Houston", "San Francisco"],
        "providers": [
            {"name": "PlugShare USA",   "url": "https://www.plugshare.com/search?query={city}+EV+charging",            "profile": "stealth"},
            {"name": "ChargePoint",     "url": "https://www.chargepoint.com/find-charging/search/?query={city}",       "profile": "lite"},
            {"name": "EVgo",            "url": "https://www.evgo.com/find-a-charger/?zipcode={city}",                  "profile": "lite"},
        ],
        "incentives": {
            "default": {
                "state_name": "United States",
                "fame2_status": "Federal EV Tax Credit up to $7,500 (IRA 2022) — income and MSRP caps apply.",
                "total_estimated_saving_inr": 0,
                "note": "Verify eligibility at IRS.gov. Many states add additional incentives.",
                "source": "IRS Clean Vehicle Credit / US DOE AFDC",
            },
        },
    },
    "germany": {
        "currency": "EUR",
        "city_region_map": {},
        "default_cities": ["Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne"],
        "providers": [
            {"name": "PlugShare DE",    "url": "https://www.plugshare.com/search?query={city}+Germany+EV+charging",    "profile": "stealth"},
            {"name": "IONITY",          "url": "https://ionity.eu/en/find-hpc.html?search={city}",                     "profile": "lite"},
            {"name": "EnBW mobility+",  "url": "https://www.enbw.com/elektromobilitaet/laden/ladesaeulenkarte/?city={city}", "profile": "lite"},
        ],
        "incentives": {
            "default": {
                "state_name": "Germany",
                "fame2_status": "German EV subsidy (Umweltbonus) ended Dec 2023 for private buyers.",
                "total_estimated_saving_inr": 0,
                "note": "Check current BAFA commercial fleet grants. State-level incentives vary.",
                "source": "German BAFA / Bundesregierung EV policy",
            },
        },
    },
    "_global": {
        "currency": "USD",
        "city_region_map": {},
        "default_cities": [],
        "providers": [
            {"name": "PlugShare",       "url": "https://www.plugshare.com/search?query={city}+EV+charging",            "profile": "stealth"},
            {"name": "OpenChargeMap",   "url": "https://openchargemap.org/site/poi/search?country=&query={city}",      "profile": "lite"},
            {"name": "Google Maps EV",  "url": "https://www.google.com/maps/search/EV+charging+stations+near+{city}", "profile": "lite"},
        ],
        "incentives": {
            "default": {
                "state_name": "Unknown",
                "fame2_status": "No default policy configured for this country.",
                "total_estimated_saving_inr": 0,
                "note": "Verify local EV incentives with your dealer and city authority.",
                "source": "Local policy portal",
            },
        },
    },
}

# ── Indian highway routes — (from, to): distance + waypoints ──
# Waypoints are major cities/towns along the route where chargers exist.
# km = cumulative distance from origin city.
HIGHWAY_ROUTES: dict[tuple, dict] = {
    ("Mumbai", "Pune"): {
        "distance_km": 150, "highway": "NH48",
        "waypoints": [
            {"name": "Khopoli",  "km": 80,  "state": "maharashtra"},
        ],
    },
    ("Mumbai", "Goa"): {
        "distance_km": 580, "highway": "NH66",
        "waypoints": [
            {"name": "Pune",     "km": 150, "state": "maharashtra"},
            {"name": "Satara",   "km": 265, "state": "maharashtra"},  # fills the 230km Pune→Kolhapur gap
            {"name": "Kolhapur", "km": 380, "state": "maharashtra"},
            {"name": "Belgaum",  "km": 490, "state": "karnataka"},
        ],
    },
    ("Mumbai", "Nagpur"): {
        "distance_km": 830, "highway": "NH44",
        "waypoints": [
            {"name": "Nashik",    "km": 170, "state": "maharashtra"},
            {"name": "Aurangabad","km": 340, "state": "maharashtra"},
            {"name": "Jalgaon",   "km": 455, "state": "maharashtra"},
            {"name": "Akola",     "km": 565, "state": "maharashtra"},
            {"name": "Amravati",  "km": 700, "state": "maharashtra"},
        ],
    },
    ("Pune", "Nagpur"): {
        "distance_km": 710, "highway": "NH61",
        "waypoints": [
            {"name": "Solapur",  "km": 240, "state": "maharashtra"},
            {"name": "Latur",    "km": 370, "state": "maharashtra"},
            {"name": "Nanded",   "km": 490, "state": "maharashtra"},
            {"name": "Akola",    "km": 590, "state": "maharashtra"},
        ],
    },
    ("Nagpur", "Hyderabad"): {
        "distance_km": 500, "highway": "NH44",
        "waypoints": [
            {"name": "Chandrapur", "km": 150, "state": "maharashtra"},
            {"name": "Adilabad",   "km": 280, "state": "telangana"},
            {"name": "Nizamabad",  "km": 390, "state": "telangana"},
        ],
    },
    ("Delhi", "Agra"): {
        "distance_km": 230, "highway": "YE",
        "waypoints": [
            {"name": "Mathura",  "km": 170, "state": "uttar-pradesh"},
        ],
    },
    ("Delhi", "Jaipur"): {
        "distance_km": 280, "highway": "NH48",
        "waypoints": [
            {"name": "Gurugram",      "km": 30,  "state": "haryana"},
            {"name": "Shahjahanpur",  "km": 190, "state": "rajasthan"},
        ],
    },
    ("Bangalore", "Chennai"): {
        "distance_km": 350, "highway": "NH44",
        "waypoints": [
            {"name": "Hosur",        "km": 40,  "state": "tamil-nadu"},
            {"name": "Krishnagiri",  "km": 95,  "state": "tamil-nadu"},
            {"name": "Vellore",      "km": 215, "state": "tamil-nadu"},
        ],
    },
    ("Bangalore", "Hyderabad"): {
        "distance_km": 570, "highway": "NH44",
        "waypoints": [
            {"name": "Kolar",      "km": 70,  "state": "karnataka"},
            {"name": "Anantapur",  "km": 250, "state": "andhra-pradesh"},
            {"name": "Kurnool",    "km": 390, "state": "andhra-pradesh"},
            {"name": "Jadcherla", "km": 490, "state": "telangana"},    # bridges 180km Kurnool→dest gap
        ],
    },
    ("Chennai", "Hyderabad"): {
        "distance_km": 630, "highway": "NH65",
        "waypoints": [
            {"name": "Vellore",  "km": 130, "state": "tamil-nadu"},
            {"name": "Tirupati", "km": 250, "state": "andhra-pradesh"},
            {"name": "Nellore",  "km": 380, "state": "andhra-pradesh"},
            {"name": "Ongole",   "km": 490, "state": "andhra-pradesh"},
        ],
    },
    ("Ahmedabad", "Mumbai"): {
        "distance_km": 530, "highway": "NH48",
        "waypoints": [
            {"name": "Vadodara", "km": 110, "state": "gujarat"},
            {"name": "Surat",    "km": 260, "state": "gujarat"},
            {"name": "Vapi",     "km": 370, "state": "gujarat"},
        ],
    },
    ("Ahmedabad", "Pune"): {
        "distance_km": 660, "highway": "NH48",
        "waypoints": [
            {"name": "Vadodara", "km": 110, "state": "gujarat"},
            {"name": "Surat",    "km": 260, "state": "gujarat"},
            {"name": "Nashik",   "km": 460, "state": "maharashtra"},
        ],
    },
    ("Hyderabad", "Bangalore"): {
        "distance_km": 570, "highway": "NH44",
        "waypoints": [
            {"name": "Kurnool",   "km": 180, "state": "andhra-pradesh"},
            {"name": "Anantapur", "km": 320, "state": "andhra-pradesh"},
            {"name": "Kolar",     "km": 500, "state": "karnataka"},
        ],
    },
    ("Dubai", "Abu Dhabi"): {
        "distance_km": 140, "highway": "E11",
        "waypoints": [
            {"name": "Jebel Ali", "km": 40, "state": "dubai"},
            {"name": "Yas Island", "km": 115, "state": "abu-dhabi"},
        ],
    },
    ("Dubai", "Sharjah"): {
        "distance_km": 35, "highway": "E11",
        "waypoints": [
            {"name": "Al Qusais", "km": 20, "state": "dubai"},
        ],
    },
}


def _lookup_route(from_city: str, to_city: str) -> tuple[dict | None, bool]:
    """Return (route_dict, is_reversed). Handles both directions."""
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
    """
    Greedy stop planner: drive until buffer < 15%, then charge to 80%.
    Uses highway range (more realistic for highway trips).

    Key fix: when the NEXT leg is too long, stop at the PREVIOUS waypoint
    (chain[i-1]), not at the unreachable next one.

    Returns (list_of_stop_waypoints, trip_feasible).
    """
    hw_range = car_profile.get("real_range_highway_km",
                               int(car_profile["real_range_city_km"] * 1.15))
    usable    = hw_range * 0.85       # 15% safety margin (plan not to go below 15%)
    buffer    = hw_range * 0.12       # stop when range left drops below 12%
    charge_to = hw_range * 0.80       # DC fast charge takes you to 80% SoC

    total_km  = route["distance_km"]
    waypoints = sorted(route["waypoints"], key=lambda x: x["km"])

    # Build a chain: virtual start → waypoints → virtual destination
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
        # For intermediate points keep a buffer; for destination just reach it
        needed  = leg + (buffer if not is_dest else 0)

        if charge < needed:
            # Can't safely reach chain[i] — charge at the PREVIOUS waypoint
            prev = chain[i - 1]
            if prev["name"] not in ("__start__", "__dest__"):
                if prev not in stops:
                    stops.append(prev)
                charge = charge_to
            # If even after charging the leg is impossible, route is infeasible
            if charge < leg:
                return stops, False

        charge -= leg

    return stops, charge >= -usable * 0.05   # 5% tolerance on arrival


def estimate_charge_time_min(car_profile: dict, station_power_kw: int) -> int:
    """Minutes to charge ~10→80% at the given station power."""
    car_kw = car_profile.get("dc_fast_charge_kw", 50)
    actual = max(1, min(station_power_kw, car_kw))
    ref    = car_profile.get("full_charge_min_dc", 57)   # ref = 10→80% at car_kw
    return math.ceil(ref * car_kw / actual)


def _normalize_country(country: str) -> str:
    c = (country or "india").strip().lower()
    aliases = {
        "in": "india", "india": "india",
        "ae": "uae", "uae": "uae", "united arab emirates": "uae",
        "gb": "uk", "uk": "uk", "united kingdom": "uk", "england": "uk", "britain": "uk",
        "us": "usa", "usa": "usa", "united states": "usa", "united states of america": "usa",
        "de": "germany", "germany": "germany", "deutschland": "germany",
    }
    return aliases.get(c, c)


def _market_region_for_city(city: str, country: str) -> str:
    cfg = COUNTRY_CONFIG.get(country) or COUNTRY_CONFIG["_global"]
    return cfg["city_region_map"].get(city, "default").lower()


def get_incentives_for_locale(city: str, country: str) -> dict:
    """Return locale incentives based on country + region."""
    c = _normalize_country(country)
    region = _market_region_for_city(city, c)
    cfg = COUNTRY_CONFIG.get(c) or COUNTRY_CONFIG["_global"]
    incentives = cfg["incentives"]
    return incentives.get(region) or incentives.get("default") or COUNTRY_CONFIG["_global"]["incentives"]["default"]


# MODELS
# ─────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    country: str = "India"
    city: str = "Nagpur"
    daily_km: int = 25
    occasional_km: int = 230
    car_model: str = "Tata Nexon EV Max"
    has_home_charging: bool = False
    user_description: str = ""
    user_id: str = ""           # Optional — auto-generated by frontend


class ProfileRequest(BaseModel):
    user_id: str
    preferred_city: Optional[str] = None
    preferred_car: Optional[str] = None
    preferred_daily_km: Optional[int] = None
    preferred_occasional_km: Optional[int] = None
    has_home_charging: Optional[bool] = None


class CompareRequest(BaseModel):
    country: str = "India"
    city: str = "Nagpur"
    daily_km: int = 25
    occasional_km: int = 230
    has_home_charging: bool = False
    car_models: List[str]


class RouteRequest(BaseModel):
    country: str = "India"
    from_city: str = "Mumbai"
    to_city: str = "Goa"
    car_model: str = "Tata Nexon EV Max"
    start_charge_pct: float = 1.0   # 0.0–1.0, default = full charge


class IntelligenceRequest(BaseModel):
    country: str = "India"
    city: str = "Bangalore"
    report_type: str = "charger_gap_analysis"


class VerdictResponse(BaseModel):
    city: str
    car: str
    daily_km: int
    occasional_km: int
    scores: dict
    verdict: str
    sources_used: list[str]


# ─────────────────────────────────────────────────────────
# /chargers/stream — SSE proxy for TinyFish live scraping
# Kept for backward compat; frontend now uses /verdict/stream
# ─────────────────────────────────────────────────────────

@app.get("/chargers/stream")
async def stream_chargers(city: str = "Nagpur"):
    """
    Streams TinyFish scraping events as Server-Sent Events (SSE).
    Each event is one of: PROGRESS, COMPLETE, ERROR.
    """
    city = city.strip().capitalize()

    payload = {
        "url": f"https://www.statiq.in/charging-stations/{city.lower()}",
        "goal": f"""
List all EV charging stations on this page for {city}, India.
Return JSON exactly like this:
{{
  "city": "{city}",
  "network": "Statiq",
  "stations": [
    {{
      "name": "station name",
      "address": "full address with area",
      "connector_types": ["DC", "AC"],
      "power_kw": 50,
      "status": "available"
    }}
  ],
  "total_found": 0
}}
If no stations found for {city}, return total_found: 0 and empty stations array. Be honest.
        """,
        "browser_profile": "lite",
    }

    def generate():
        if _TINYFISH_DISABLED:
            yield f"data: {json.dumps({'type': 'ERROR', 'message': f'TinyFish unavailable: {_TINYFISH_DISABLE_REASON}'})}\n\n"
            return
        yield f"data: {json.dumps({'type': 'STATUS', 'message': f'Connecting to TinyFish for {city}...'})}\n\n"

        try:
            with req.post(
                TINYFISH_BASE_URL,
                json=payload,
                headers={
                    "X-API-Key": TINYFISH_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                stream=True,
                timeout=180,
            ) as resp:
                if resp.status_code != 200:
                    try:
                        err_msg = (resp.json().get("error") or {}).get("message") or f"HTTP {resp.status_code}"
                    except Exception:
                        err_msg = f"HTTP {resp.status_code}"
                    yield f"data: {json.dumps({'type': 'ERROR', 'message': f'TinyFish error: {err_msg}'})}\n\n"
                    return

                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                        event_type = event.get("type", "")

                        if event_type == "COMPLETE":
                            charger_data = event.get("resultJson", {"stations": [], "total_found": 0})
                            if isinstance(charger_data, str):
                                try:
                                    charger_data = json.loads(charger_data)
                                except Exception:
                                    charger_data = {"stations": [], "total_found": 0}
                            yield f"data: {json.dumps({'type': 'COMPLETE', 'data': charger_data})}\n\n"
                            return
                        elif event_type == "ERROR":
                            yield f"data: {json.dumps({'type': 'ERROR', 'message': event.get('message', 'Unknown error')})}\n\n"
                            return
                        else:
                            msg = event.get("message") or event.get("step") or event_type
                            yield f"data: {json.dumps({'type': 'PROGRESS', 'step': event_type, 'message': str(msg)})}\n\n"

                    except json.JSONDecodeError:
                        continue

        except req.Timeout:
            yield f"data: {json.dumps({'type': 'ERROR', 'message': 'TinyFish timed out after 180s'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'ERROR', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────────────────────────────────────────────
# /verdict/stream — Unified streaming endpoint (Fix 2)
# Runs charger + Team-BHP scrapes in parallel, streams events
# ─────────────────────────────────────────────────────────

@app.post("/verdict/stream")
def stream_verdict(query: QueryRequest):
    """
    Streams the full verdict pipeline as SSE events.
    Events: SCRAPING_CHARGERS, SCRAPING_TEAMBHP, SCORING, LLM, COMPLETE, ERROR.
    Both TinyFish calls run in parallel threads.
    """
    city = _normalize_city(query.city)
    country = _normalize_country(query.country)
    car_model = query.car_model
    car_profile = get_car_profile(car_model)
    user_id = query.user_id.strip() or None

    def generate():
        q = queue_module.Queue()
        charger_holder: list[dict] = [{}]
        teambhp_holder: list[dict] = [{}]

        def do_chargers():
            q.put({"type": "SCRAPING_CHARGERS",
                   "message": f"🌐 Checking live stations in {city}, {country.title()}..."})
            try:
                started_at = time.time()
                data = fetch_live_chargers(city, country=country, quick_mode=True, hard_deadline_sec=3)
                charger_holder[0] = data
                count = data.get("total_found", len(data.get("stations", [])))
                if data.get("background_refresh_started"):
                    q.put({
                        "type": "PROGRESS",
                        "message": "⏱️ Returned fast result in under 3s. Live refresh continues in background..."
                    })

                    def watch_refresh():
                        key = _charger_cache_key(city, country)
                        for _ in range(12):
                            time.sleep(1)
                            entry = CHARGER_CACHE.get(key)
                            if entry and entry.get("timestamp", 0) > started_at:
                                data_live = dict(entry["data"])
                                charger_holder[0] = data_live
                                q.put({
                                    "type": "CHARGERS_REFRESHED",
                                    "message": f"🔄 Live refresh complete: {data_live.get('total_found', 0)} stations from {data_live.get('provider', 'provider')}"
                                })
                                return

                    threading.Thread(target=watch_refresh, daemon=True).start()

                q.put({"type": "CHARGERS_DONE",
                       "message": f"⚡ Found {count} charging stations in {city}",
                       "_done": "chargers"})
            except Exception:
                charger_holder[0] = {"stations": [], "total_found": 0}
                q.put({"type": "CHARGERS_DONE",
                       "message": "⚠️ Charger scrape failed — using fallback data",
                       "_done": "chargers"})

        def do_teambhp():
            if country != "india":
                teambhp_holder[0] = {}
                q.put({"type": "TEAMBHP_DONE",
                       "message": "Owner forum data: India-only (Team-BHP). Using global knowledge for this country.",
                       "_done": "teambhp"})
                return
            q.put({"type": "SCRAPING_TEAMBHP",
                   "message": "📖 Reading owner experiences on Team-BHP..."})
            try:
                data = fetch_live_teambhp(car_model, quick_mode=True, hard_deadline_sec=3)
                teambhp_holder[0] = data
                q.put({"type": "TEAMBHP_DONE",
                       "message": "✅ Team-BHP owner insights loaded",
                       "_done": "teambhp"})
            except Exception:
                teambhp_holder[0] = None
                q.put({"type": "TEAMBHP_DONE",
                       "message": "📦 Using cached Team-BHP data",
                       "_done": "teambhp"})

        t1 = threading.Thread(target=do_chargers, daemon=True)
        t2 = threading.Thread(target=do_teambhp, daemon=True)
        t1.start()
        t2.start()

        # Stream events as they arrive from both parallel threads.
        # Timeout = 3 sources × 120s each + 40s buffer = 400s per q.get call.
        # On timeout, gracefully continue with whatever data is already in holders
        # (fallback to static JSON) rather than erroring out the whole request.
        pending = 2
        while pending > 0:
            try:
                msg = q.get(timeout=30)
                # Strip internal routing keys before sending to frontend
                out = {k: v for k, v in msg.items() if not k.startswith("_")}
                yield f"data: {json.dumps(out)}\n\n"
                if msg.get("_done"):
                    pending -= 1
            except queue_module.Empty:
                # Timed out — notify frontend but continue with fallback data
                yield f"data: {json.dumps({'type': 'CHARGERS_DONE', 'message': '⚠️ Live scrape timed out — using cached data'})}\n\n"
                break

        # Drain any opportunistic background refresh event that arrived.
        while True:
            try:
                msg = q.get_nowait()
                out = {k: v for k, v in msg.items() if not k.startswith("_")}
                yield f"data: {json.dumps(out)}\n\n"
            except queue_module.Empty:
                break

        t1.join(timeout=5)
        t2.join(timeout=5)

        # ── Scoring ──
        yield f"data: {json.dumps({'type': 'SCORING', 'message': '📊 Calculating your anxiety score...'})}\n\n"

        charger_data = charger_holder[0] or {}
        if not charger_data.get("stations"):
            charger_data = _static_city_fallback(city, country)

        scores = calculate_anxiety_scores(
            charger_data,
            query.daily_km,
            query.occasional_km,
            car_profile=car_profile,
        )
        if query.has_home_charging:
            scores["daily_score"] = max(1, scores["daily_score"] - 1)

        # Team-BHP data is India-only; use empty dicts for other countries
        if country == "india":
            teambhp_live = bool(teambhp_holder[0] and teambhp_holder[0].get("honest_verdict"))
            live_t1 = teambhp_holder[0] if teambhp_live else ALL_DATA.get("teambhp_thread1", {})
            # thread2 / thread3 are static Nexon JSON files.
            # When a non-Nexon car is selected, we reuse the live_t1 scrape to
            # fill in supplementary fields (most_honest_quote, biggest_regret, etc.)
            # so the prompt never silently blends Nexon opinions into a BYD verdict.
            nexon_selected = "nexon" in car_model.lower()
            if nexon_selected:
                t2 = ALL_DATA.get("teambhp_thread2", {})
                t3 = ALL_DATA.get("teambhp_thread3", {})
            else:
                # Use the live scraped data (same car) for supplementary fields
                t2 = live_t1
                t3 = live_t1
        else:
            teambhp_live = False
            live_t1 = {}
            t2 = {}
            t3 = {}
        insights = extract_owner_insights(live_t1, t2, t3)

        # ── LLM synthesis ──
        yield f"data: {json.dumps({'type': 'LLM', 'message': '🤖 Synthesising honest verdict...'})}\n\n"

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
            return

        # ── Data freshness metadata ──
        charger_src = charger_data.get("source_type", "static_fallback")
        charger_fetched = charger_data.get("fetched_at")
        charger_age = None
        if charger_src == "cache":
            entry = CHARGER_CACHE.get(_charger_cache_key(city, country))
            charger_age = int((time.time() - entry["timestamp"]) / 60) if entry else None

        data_freshness = {
            "chargers": {
                "source_type": charger_src,
                "fetched_at": charger_fetched,
                "age_minutes": charger_age,
            },
            "teambhp": {
                "source_type": "live" if teambhp_live else "cache",
                "fetched_at": TEAMBHP_CACHE.get(_teambhp_cache_key(car_model), {}).get("data", {}).get("fetched_at") if not teambhp_live else datetime.now(timezone.utc).isoformat(),
                "age_minutes": None,
            },
        }

        # ── Source labels ──
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
                f"⚡ Charger network — {charger_src} ({scores['total_stations']} stations in {city}){charger_age_str}",
                f"{'🔑 Team-BHP — scraped live' if teambhp_live else '📦 Team-BHP — cached data'} ({car_model})",
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
                    (c for c in (COUNTRY_CONFIG.get(country) or COUNTRY_CONFIG["_global"])["default_cities"] if c != city),
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

        # ── Save verdict + compute what_changed ──
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

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────────────────────────────────────────────
# /verdict — Blocking endpoint (kept for backward compat)
# Now also uses fetch_live_teambhp() in parallel (Fix 1)
# ─────────────────────────────────────────────────────────

@app.post("/verdict", response_model=VerdictResponse)
def get_verdict(query: QueryRequest):
    """
    Blocking verdict endpoint. Fetches charger + Team-BHP in parallel,
    then generates verdict via LLM.
    """
    from concurrent.futures import ThreadPoolExecutor

    city = _normalize_city(query.city)
    country = _normalize_country(query.country)
    car_profile = get_car_profile(query.car_model)
    print(f"\n🌐 Fetching live data for {city}, {country} via TinyFish (parallel)...")

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
        live_t1 = teambhp_live if teambhp_was_live else ALL_DATA.get("teambhp_thread1", {})
        # thread2/3 are static Nexon files — only use them for actual Nexon queries.
        # For all other cars, reuse the live scrape for supplementary fields.
        nexon_selected_v = "nexon" in query.car_model.lower()
        t2_v = ALL_DATA.get("teambhp_thread2", {}) if nexon_selected_v else live_t1
        t3_v = ALL_DATA.get("teambhp_thread3", {}) if nexon_selected_v else live_t1
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
        raise HTTPException(
            status_code=500,
            detail="LLM synthesis failed. Check your ANTHROPIC_API_KEY or FIREWORKS_API_KEY."
        )

    return VerdictResponse(
        city=city,
        car=query.car_model,
        daily_km=query.daily_km,
        occasional_km=query.occasional_km,
        scores=scores,
        verdict=verdict,
        sources_used=[
            f"⚡ Charger network — {charger_data.get('source_type','live')} ({scores['total_stations']} stations in {city})",
            f"{'🔑 Team-BHP — scraped live' if teambhp_was_live else '📦 Team-BHP — cached'} ({query.car_model})",
            subsidy["source"],
            "TinyFish Web Agent (real-time browser automation)",
        ]
    )


# ─────────────────────────────────────────────────────────
# /health
# ─────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "tinyfish_api_key_set": bool(TINYFISH_API_KEY),
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


# ─────────────────────────────────────────────────────────
# /debug-keys — verify environment variable loading
# Shows present/missing without exposing actual values.
# ─────────────────────────────────────────────────────────

@app.get("/debug-keys")
def debug_keys():
    _root_env = Path(__file__).resolve().parent.parent / ".env"
    _src_env  = Path(__file__).resolve().parent / ".env"
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
            "status": "disabled" if _TINYFISH_DISABLED else ("ready" if TINYFISH_API_KEY else "no_key"),
            "reason": _TINYFISH_DISABLE_REASON or None,
        },
    }


# ─────────────────────────────────────────────────────────
# /cache-status — which cities have warm cache (Fix 3)
# ─────────────────────────────────────────────────────────

@app.get("/cache-status")
def cache_status():
    now = time.time()
    charger_status = {}

    # Live-scraped cached cities
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
        # Backward compatibility for current India-only frontend mapping.
        if country == "india":
            charger_status[city] = charger_status[f"{country}:{city}"]

    # Static JSON cities (Nagpur, Pune from day 1)
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


# ─────────────────────────────────────────────────────────
# /data-freshness — per city + model freshness metadata
# ─────────────────────────────────────────────────────────

@app.get("/data-freshness")
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


# ─────────────────────────────────────────────────────────
# /cars — return car models filtered by country
# ─────────────────────────────────────────────────────────

@app.get("/cars")
def list_cars(country: str = "india"):
    """Returns car models available for the given country.
    India returns all models; other markets return only globally-sold models.
    """
    c = _normalize_country(country)
    models = get_models_for_country(c)
    return {
        "country": c,
        "models": [
            {"name": name, "segment": CAR_PROFILES[name]["segment"], "markets": CAR_PROFILES[name]["markets"]}
            for name in models
        ],
    }


# ─────────────────────────────────────────────────────────
# /profile — user preferences (save + retrieve)
# ─────────────────────────────────────────────────────────

@app.post("/profile")
def save_profile(req_body: ProfileRequest):
    prefs = req_body.model_dump(exclude={"user_id"}, exclude_none=True)
    profile = user_store.upsert_profile(req_body.user_id, prefs)
    return {"status": "ok", "profile": profile}


@app.get("/profile/{user_id}")
def get_profile(user_id: str):
    profile = user_store.get_profile(user_id)
    if not profile:
        return {"profile": None}
    return {"profile": profile}


# ─────────────────────────────────────────────────────────
# /compare — side-by-side multi-car comparison
# ─────────────────────────────────────────────────────────

@app.post("/compare")
def compare_cars(req_body: CompareRequest):
    city = _normalize_city(req_body.city)
    country = _normalize_country(req_body.country)
    car_models = req_body.car_models[:3]  # max 3

    if not car_models:
        raise HTTPException(status_code=400, detail="Provide at least one car_model")

    # One charger fetch shared across all cars (same city)
    charger_data = fetch_live_chargers(city, country=country, quick_mode=True, hard_deadline_sec=3)
    if not charger_data.get("stations"):
        charger_data = _static_city_fallback(city, country)

    _subsidy = get_incentives_for_locale(city, country)  # noqa: F841
    results = []

    for model in car_models:
        cp = get_car_profile(model)
        scores = calculate_anxiety_scores(
            charger_data,
            req_body.daily_km,
            req_body.occasional_km,
            car_profile=cp,
        )
        if req_body.has_home_charging:
            scores["daily_score"] = max(1, scores["daily_score"] - 1)

        # Determine best_for tag
        # Guards: 'value' only when BOTH scores are acceptable (≤6), not just cheap.
        # 'premium ownership' only for genuinely premium price points (≥₹30L).
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
            # Value only if affordably priced AND not terrible on both axes
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

    # Sort by combined score (lower = less anxious = better)
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


# ─────────────────────────────────────────────────────────
# /route/stream — Live highway trip planner
# Scrapes charger data for each stop in parallel via TinyFish,
# streams events so the judge sees TinyFish working in real time.
# ─────────────────────────────────────────────────────────

@app.post("/route/stream")
def stream_route(req: RouteRequest):
    """
    Streaming route planner.
    Events: PLANNING, CALCULATING, SCRAPING_STOP, STOP_FOUND, BUILDING_PLAN, COMPLETE, ERROR.
    """
    from_city   = _normalize_city(req.from_city)
    to_city     = _normalize_city(req.to_city)
    country     = _normalize_country(req.country)
    car_profile = get_car_profile(req.car_model)

    def generate():
        route, _reversed = _lookup_route(from_city, to_city)
        if not route:
            # Unknown route — try TinyFish to discover distance + key stops
            yield f"data: {json.dumps({'type': 'PLANNING', 'message': f'🔍 Route {from_city} → {to_city} not in database — querying live via TinyFish...'})}\n\n"
            route = _discover_route_via_tinyfish(from_city, to_city, country)
            if not route:
                supported = ", ".join(f"{a}↔{b}" for a, b in HIGHWAY_ROUTES.keys())
                yield f"data: {json.dumps({'type': 'ERROR', 'message': f'Could not find route data for {from_city} → {to_city}. Pre-loaded routes: {supported}'})}\n\n"
                return
            discovered_msg = f"✅ Route discovered: {route['distance_km']}km via TinyFish live lookup"
            yield f"data: {json.dumps({'type': 'PLANNING', 'message': discovered_msg})}\n\n"

        dist_km = route["distance_km"]
        highway = route["highway"]
        yield f"data: {json.dumps({'type': 'PLANNING', 'message': f'Analyzing {from_city} to {to_city} — {dist_km}km via {highway}...'})}\n\n"

        stops, feasible = plan_stops(route, car_profile, req.start_charge_pct)

        n_stops    = len(stops)
        stop_names = ", ".join(s["name"] for s in stops) if stops else "none needed"
        stop_word  = "stops" if n_stops != 1 else "stop"
        yield f"data: {json.dumps({'type': 'CALCULATING', 'message': f'{n_stops} charging {stop_word} needed — {stop_names}'})}\n\n"

        # ── Scrape charger data for each stop in parallel ──
        q          = queue_module.Queue()
        stop_data  = {}   # name → charger dict

        def fetch_stop(wp):
            q.put({"type": "SCRAPING_STOP",
                   "message": f"⚡ Checking live chargers at {wp['name']} (km {wp['km']})...",
                   "_wp": wp["name"]})
            try:
                data = fetch_live_chargers(wp["name"], country=country, quick_mode=True, hard_deadline_sec=3)
            except Exception:
                data = {"stations": [], "total_found": 0, "source_type": "static_fallback"}
            q.put({"type": "STOP_DONE", "_wp": wp["name"], "_data": data})

        threads = [threading.Thread(target=fetch_stop, args=(wp,), daemon=True) for wp in stops]
        for t in threads:
            t.start()

        pending = len(stops)
        while pending > 0:
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
                    badge = "🟢" if src == "live" else "🟡" if src == "cache" else "🔴"
                    found_msg = (f"{badge} {name}: {count} stations, {len(dc)} DC ({top_kw}kW max)"
                                 if count > 0 else f"⚠️  {name}: no chargers found via live scrape")
                    yield f"data: {json.dumps({'type': 'STOP_FOUND', 'message': found_msg, 'stop_name': name})}\n\n"
                    pending -= 1
                else:
                    out = {k: v for k, v in msg.items() if not k.startswith("_")}
                    yield f"data: {json.dumps(out)}\n\n"
            except queue_module.Empty:
                yield f"data: {json.dumps({'type': 'STOP_FOUND', 'message': '⚠️  Charger fetch timed out — continuing with cached data'})}\n\n"
                break

        for t in threads:
            t.join(timeout=5)

        yield f"data: {json.dumps({'type': 'BUILDING_PLAN', 'message': '🔧 Building your trip plan...'})}\n\n"

        # ── Assemble stop plan ──
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

        # ── Operator workflow: validate each planned stop and assign live fallback if weak ──
        yield f"data: {json.dumps({'type': 'VALIDATING_STOPS', 'message': '🧪 Validating each stop for DC availability...'})}\n\n"

        operator_actions = []
        weak_stops = [s for s in stop_plans if s["dc_stations"] <= 0]
        route_waypoints = sorted(route.get("waypoints", []), key=lambda x: x["km"])

        for weak in weak_stops:
            wpt_name = weak["waypoint"]
            _sw_msg = f"⚠️ {wpt_name} has weak DC coverage. Searching fallback..."
            yield f"data: {json.dumps({'type': 'STOP_WEAK', 'message': _sw_msg})}\n\n"
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
                _fa_msg = f"✅ Fallback set: {wpt_name} → {winner_name}"
                yield f"data: {json.dumps({'type': 'FALLBACK_ASSIGNED', 'message': _fa_msg})}\n\n"
            else:
                weak["operator_status"] = "manual_review_required"
                operator_actions.append(
                    f"Manual review required at {wpt_name}: no reliable fallback within 140km."
                )
                _fm_msg = f"🚨 No fallback found near {wpt_name}. Manual intervention needed."
                yield f"data: {json.dumps({'type': 'FALLBACK_MISSING', 'message': _fm_msg})}\n\n"

        total_charge_min  = sum(s["charge_time_min"] for s in stop_plans)
        driving_time_hr   = round(route["distance_km"] / 70, 1)   # ~70kmph avg Indian highway
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

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────────────
# /intelligence-report — B2B competitive charger gap analysis
# Scrapes ALL networks independently (not stop-at-first).
# Useful for charging networks, fleet operators, city planners.
# ─────────────────────────────────────────────────────────

@app.post("/intelligence-report")
def intelligence_report(req: IntelligenceRequest):
    """
    Streams competitive charger gap analysis via SSE.
    Scrapes all 3 networks in parallel; emits NETWORK_DONE per network
    so the frontend can show progress, then COMPLETE with the full report.
    """
    import queue as _queue

    city = _normalize_city(req.city)
    country = _normalize_country(req.country)
    _state = _market_region_for_city(city, country)  # noqa: F841  (used in goal f-string)

    def goal(network):
        return f"""Find all EV charging stations for {city}, {country.title()} on this page.
Return JSON:
{{
  "city": "{city}",
  "country": "{country}",
  "network": "{network}",
  "stations": [
    {{
      "name": "station name",
      "address": "full address",
      "connector_types": ["DC", "AC"],
      "power_kw": 50
    }}
  ],
  "total_found": 0
}}
Be honest. Return total_found: 0 if none found."""

    sources = _provider_sources_for_city(city, country)

    def generate():
        yield f"data: {json.dumps({'type': 'SCANNING', 'message': f'Scanning {len(sources)} networks for {city}, {country.title()} in parallel...'})}\n\n"

        result_q = _queue.Queue()

        def scrape(source):
            data = _tinyfish_call(source["url"], goal(source["name"]), source["profile"], timeout=110)
            result_q.put((source["name"], data))

        threads = [threading.Thread(target=scrape, args=(s,), daemon=True) for s in sources]
        for t in threads:
            t.start()

        network_data = {}
        for _ in sources:
            name, data = result_q.get()
            network_data[name] = data
            n = len(data.get("stations") or [])
            yield f"data: {json.dumps({'type': 'NETWORK_DONE', 'network': name, 'stations_found': n})}\n\n"

        for t in threads:
            t.join()

        # ── Analyse per-network ──
        breakdown = {}
        for name, data in network_data.items():
            stations  = data.get("stations") or []
            dc        = [s for s in stations if "DC" in (s.get("connector_types") or [])]
            fast      = [s for s in dc if (s.get("power_kw") or 0) >= 50]
            breakdown[name] = {
                "total":             len(stations),
                "dc_chargers":       len(dc),
                "fast_dc_50kw_plus": len(fast),
                "max_power_kw":      max(((s.get("power_kw") or 0) for s in stations), default=0),
            }

        all_stations = [s for d in network_data.values() for s in (d.get("stations") or [])]
        total      = len(all_stations)
        dc_total   = sum(b["dc_chargers"]       for b in breakdown.values())
        fast_total = sum(b["fast_dc_50kw_plus"] for b in breakdown.values())

        dominant = max(breakdown, key=lambda k: breakdown[k]["dc_chargers"]) if breakdown else "Unknown"
        dom_dc   = breakdown.get(dominant, {}).get("dc_chargers", 0)
        dom_pct  = round(dom_dc / max(dc_total, 1) * 100)

        gaps = []
        if fast_total < 5:
            gaps.append(f"Only {fast_total} fast chargers (≥50kW) across all networks — insufficient for highway-adjacent EV use.")
        if dom_pct > 60:
            gaps.append(f"{dominant} controls {dom_pct}% of DC capacity — single-network dependency creates reliability risk for fleet operators.")
        if dc_total < total * 0.5:
            gaps.append(f"Only {dc_total}/{total} stations offer DC fast charging — AC-heavy coverage limits quick top-ups on busy days.")
        if not gaps:
            gaps.append("Healthy multi-network redundancy detected — strong coverage foundation for EV adoption.")

        shortfall = max(0, 10 - fast_total)
        opportunity = (
            f"{'High-growth opportunity' if total < 20 else 'Competitive market'}: "
            f"{city} needs {shortfall} more 50kW+ chargers to meet projected demand for {total * 3}+ EVs."
            if shortfall > 0 else
            f"{city} has solid fast-DC infrastructure. Expansion opportunity is in AC home-charging support and reliability monitoring."
        )

        payload = {
            "type":                        "COMPLETE",
            "country":                     country,
            "city":                        city,
            "report_type":                 req.report_type,
            "total_stations_all_networks": total,
            "dc_fast_chargers":            dc_total,
            "fast_50kw_plus":              fast_total,
            "network_breakdown":           breakdown,
            "dominant_network":            dominant,
            "dominant_dc_share_pct":       dom_pct,
            "gaps_and_risks":              gaps,
            "opportunity":                 opportunity,
            "data_freshness": {
                "source_type": "live" if any((network_data[k].get("stations") or []) for k in network_data)
                               else "static_fallback",
                "scraped_at":  datetime.now(timezone.utc).isoformat(),
            },
        }
        yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ─────────────────────────────────────────────────────────
# ROUTE DISCOVERY — TinyFish fallback for unknown city pairs
# ─────────────────────────────────────────────────────────

def _discover_route_via_tinyfish(from_city: str, to_city: str, country: str) -> dict | None:
    """
    When a city pair isn't in HIGHWAY_ROUTES, asks TinyFish to discover the
    distance and major waypoints via Google Maps / MapMyIndia.
    Returns a route dict compatible with HIGHWAY_ROUTES schema, or None on failure.
    """
    c = _normalize_country(country)
    country_label = c.title()
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
    result = _tinyfish_call(url, goal, profile="lite", timeout=90)
    if result and result.get("distance_km"):
        return result
    return None


# ─────────────────────────────────────────────────────────
# CORE TINYFISH CALLER
# ─────────────────────────────────────────────────────────

def _tinyfish_call(url: str, goal: str, profile: str = "lite", timeout: int = 120) -> dict:
    """Single TinyFish SSE call — returns result or empty dict on failure."""
    global _TINYFISH_DISABLED, _TINYFISH_DISABLE_REASON
    if _TINYFISH_DISABLED:
        return {}  # circuit open — skip silently
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
                # Try to extract a human-readable reason from the response body
                try:
                    err_body = resp.json()
                    err_msg = (err_body.get("error") or {}).get("message") or str(err_body)
                except Exception:
                    err_msg = resp.text[:200] or f"HTTP {resp.status_code}"
                # Unrecoverable errors: trip the circuit breaker so we don't spam
                unrecoverable = resp.status_code in (401, 403) or "credits" in err_msg.lower() or "forbidden" in err_msg.lower()
                if unrecoverable and not _TINYFISH_DISABLED:
                    _TINYFISH_DISABLED = True
                    _TINYFISH_DISABLE_REASON = err_msg
                    print(f"🚫 TinyFish disabled for this session: {err_msg}")
                    print("   👉 Top up credits at https://tinyfish.ai or set a new TINYFISH_API_KEY in .env")
                elif not unrecoverable:
                    print(f"⚠️  TinyFish HTTP {resp.status_code}: {err_msg}")
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
                        return result
                    elif event.get("type") == "ERROR":
                        print(f"⚠️  TinyFish error: {event.get('message')}")
                        return {}
                except json.JSONDecodeError:
                    continue
    except (req.exceptions.Timeout, req.exceptions.ConnectionError):
        pass  # timeouts/connection drops are expected with short deadlines
    except Exception as e:
        if "timed out" not in str(e).lower() and "timeout" not in str(e).lower():
            print(f"⚠️  TinyFish call failed: {e}")
    return {}


# ─────────────────────────────────────────────────────────
# LIVE CHARGER FETCHER — with TTL cache (Fix 4)
# ─────────────────────────────────────────────────────────

def _normalize_city(city: str) -> str:
    return " ".join(part.capitalize() for part in (city or "").split()).strip()


def _charger_cache_key(city: str, country: str) -> str:
    return f"{_normalize_country(country)}:{_normalize_city(city)}"


def _teambhp_cache_key(car_model: str) -> str:
    return car_model.strip().lower()


def _static_city_fallback(city: str, country: str) -> dict:
    # Static JSON fallback is currently available only for India seed cities.
    if _normalize_country(country) != "india":
        return {"stations": [], "total_found": 0, "source_type": "static_fallback", "fetched_at": None}
    key = f"chargers_{city.lower()}"
    data = dict(ALL_DATA.get(key, {"stations": [], "total_found": 0}))
    data.setdefault("source_type", "static_fallback")
    data.setdefault("fetched_at", None)
    return data


def _provider_sources_for_city(city: str, country: str) -> list[dict]:
    c = _normalize_country(country)
    state = _market_region_for_city(city, c)
    cfg = COUNTRY_CONFIG.get(c) or COUNTRY_CONFIG["_global"]
    providers = cfg["providers"]
    out = []
    for p in providers:
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


async def _parallel_tinyfish_sources(sources: list[dict], goal_builder, timeout_per_source: int) -> list[tuple[dict, dict]]:
    async def one(source: dict):
        result = await asyncio.to_thread(
            _tinyfish_call,
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
            continue
        # item is already checked to be a tuple
        out.append(item)  # type: ignore[arg-type]
    return out


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
    winner["country"] = _normalize_country(country)
    winner["city"] = city
    winner["provider"] = source["name"]
    winner["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return winner


def _refresh_chargers_worker(city: str, country: str, key: str):
    try:
        live = fetch_live_chargers(city, country=country, quick_mode=False, hard_deadline_sec=12)
        if live.get("stations"):
            print(f"🔄 Background refresh updated {city}, {country}: {live.get('total_found', 0)} stations")
    finally:
        with _REFRESH_LOCK:
            _REFRESH_IN_FLIGHT.discard(key)


def _ensure_background_refresh(city: str, country: str):
    key = _charger_cache_key(city, country)
    with _REFRESH_LOCK:
        if key in _REFRESH_IN_FLIGHT:
            return False
        _REFRESH_IN_FLIGHT.add(key)
    threading.Thread(target=_refresh_chargers_worker, args=(city, country, key), daemon=True).start()
    return True

def fetch_live_chargers(city: str, country: str = "India", quick_mode: bool = False, hard_deadline_sec: int = 3) -> dict:
    """
    Fetches live charger data for a city + country.
    - quick_mode=True: returns cached/static in <= hard_deadline_sec and triggers background refresh.
    - quick_mode=False: performs full parallel live scrape fan-out.
    """
    city = _normalize_city(city)
    c = _normalize_country(country)
    cache_key = _charger_cache_key(city, c)

    cached = CHARGER_CACHE.get(cache_key)
    if cached and (time.time() - cached["timestamp"]) < CACHE_TTL_SECONDS:
        age_min = int((time.time() - cached["timestamp"]) / 60)
        print(f"📦 Charger data from cache for {city}, {c} ({age_min}m ago)")
        data = dict(cached["data"])
        data["source_type"] = "cache"
        data["age_minutes"] = age_min
        return data

    stale_cache = dict(cached["data"]) if cached else None
    static_fallback = _static_city_fallback(city, c)
    sources = _provider_sources_for_city(city, c)

    async def run_parallel_scrape(timeout_per_source: int) -> dict:
        results = await _parallel_tinyfish_sources(
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
            CHARGER_CACHE[cache_key] = {"data": live, "timestamp": time.time()}
            return live

        refresh_started = _ensure_background_refresh(city, c)
        fallback["background_refresh_started"] = refresh_started
        fallback.setdefault("fetched_at", None)
        return fallback

    # Full live scrape mode: run all providers in parallel with bounded timeout.
    try:
        live = asyncio.run(asyncio.wait_for(run_parallel_scrape(timeout_per_source=hard_deadline_sec), timeout=hard_deadline_sec + 1))
    except Exception:
        live = {}

    if live.get("stations"):
        CHARGER_CACHE[cache_key] = {"data": live, "timestamp": time.time()}
        return live

    fallback = stale_cache or static_fallback
    fallback = dict(fallback)
    fallback["country"] = c
    fallback["city"] = city
    fallback.setdefault("source_type", "static_fallback")
    fallback.setdefault("fetched_at", None)
    return fallback


# ─────────────────────────────────────────────────────────
# LIVE TEAM-BHP FETCHER — scrapes live with TinyFish (Fix 1)
# ─────────────────────────────────────────────────────────

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


def fetch_live_teambhp(car_model: str, quick_mode: bool = False, hard_deadline_sec: int = 3) -> dict:
    """
    Scrapes Team-BHP live for owner insights on the given EV model.
    Returns data compatible with teambhp_thread1 schema.
    Checks TTL cache first; falls back to static JSON if scrape fails.
    """
    cache_key = _teambhp_cache_key(car_model)
    cached = TEAMBHP_CACHE.get(cache_key)
    if cached and (time.time() - cached["timestamp"]) < CACHE_TTL_SECONDS:
        age_min = int((time.time() - cached["timestamp"]) / 60)
        print(f"📦 Team-BHP from cache for {car_model} ({age_min}m ago)")
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
        results = await _parallel_tinyfish_sources(
            sources,
            lambda _network: goal,
            timeout_per_source,
        )
        # Pick first valid result with honest_verdict
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
            TEAMBHP_CACHE[cache_key] = {"data": result, "timestamp": time.time()}
            print(f"🔑 Team-BHP scraped live for {car_model}")
            return result
        # Hard deadline mode: return cache/static immediately, refresh in background.
        stale = dict(cached["data"]) if cached else None
        fallback = stale or ALL_DATA.get("teambhp_thread1", {})
        fallback = dict(fallback)
        fallback.setdefault("source_type", "cache" if stale else "static_fallback")

        def bg_refresh():
            try:
                full = fetch_live_teambhp(car_model, quick_mode=False, hard_deadline_sec=12)
                if full.get("honest_verdict"):
                    print(f"🔄 Team-BHP background refresh updated {car_model}")
            except Exception:
                pass

        threading.Thread(target=bg_refresh, daemon=True).start()
        return fallback

    try:
        result = asyncio.run(asyncio.wait_for(run_parallel_teambhp(timeout_per_source=hard_deadline_sec), timeout=hard_deadline_sec + 1))
    except Exception:
        result = {}

    if result and result.get("honest_verdict"):
        TEAMBHP_CACHE[cache_key] = {"data": result, "timestamp": time.time()}
        print(f"🔑 Team-BHP scraped live for {car_model}")
        return result

    # Fallback to static data
    print(f"📦 Team-BHP fallback to static JSON for {car_model}")
    return ALL_DATA.get("teambhp_thread1", {})


# ─────────────────────────────────────────────────────────
# STARTUP WARMUP — Pre-cache major cities (Fix 3)
# ─────────────────────────────────────────────────────────

def warm_cache():
    """
    Pre-warm charger cache for major cities + key route waypoints.
    Runs at startup so verdicts and route plans feel instant.
    """
    # Major cities for verdict tab
    city_warmup = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Ahmedabad"]
    # Key highway waypoints for the demo routes (Mumbai→Goa, Bangalore→Chennai)
    waypoint_warmup = ["Kolhapur", "Khopoli", "Vellore", "Krishnagiri"]
    warmup_cities = city_warmup + waypoint_warmup
    print("\n🔥 Warming cache for major cities + route waypoints in background...")
    if _TINYFISH_DISABLED:
        print(f"   ⏭️  TinyFish disabled ({_TINYFISH_DISABLE_REASON}) — skipping live warmup, using static data")
        return

    for city in warmup_cities:
        # Skip if recently cached
        cache_key = _charger_cache_key(city, "india")
        cached = CHARGER_CACHE.get(cache_key)
        if cached and (time.time() - cached["timestamp"]) < CACHE_TTL_SECONDS:
            print(f"   ♻️  {city}: already in cache")
            continue

        # Skip if static JSON is available
        if ALL_DATA.get(f"chargers_{city.lower()}", {}).get("stations"):
            print(f"   📦 {city}: using static JSON")
            continue

        try:
            print(f"   🌐 Warming {city}...")
            data = fetch_live_chargers(city, country="india", quick_mode=False, hard_deadline_sec=12)
            if data.get("stations"):
                print(f"   ✅ {city}: {data['total_found']} stations cached")
            else:
                print(f"   ⚠️  {city}: no stations found via TinyFish")
        except Exception as e:
            print(f"   ⚠️  {city} warmup failed: {e}")


# Start cache warmup in background when server starts
threading.Thread(target=warm_cache, daemon=True).start()


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 EV Mitra backend starting (TinyFish Live + Streaming Mode)...")
    print("   API:     http://localhost:8080")
    print("   Docs:    http://localhost:8080/docs")
    print("   Health:  http://localhost:8080/health")
    print("   Cache:   http://localhost:8080/cache-status")
    print("   Stream:  POST http://localhost:8080/verdict/stream\n")
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)

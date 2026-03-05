"""
EV Mitra — core/config.py
Single source of truth for all configuration, constants, and country data.
Zero magic numbers in business logic.
"""

import logging
import os
from pathlib import Path

from synthesis import MAHARASHTRA_SUBSIDY

# ── Logging setup ──
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("evmitra")

# ── Paths ──
BASE_DIR = Path(__file__).resolve().parent.parent          # src/
PROJECT_ROOT = BASE_DIR.parent if (BASE_DIR.parent / "data").exists() else BASE_DIR

# ── TinyFish ──
TINYFISH_API_KEY = os.environ.get("TINYFISH_API_KEY", "")
TINYFISH_BASE_URL = "https://agent.tinyfish.ai/v1/automation/run-sse"

# ── Cache TTL ──
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "3600"))

# ── Timeouts ──
TINYFISH_DEFAULT_TIMEOUT = int(os.environ.get("TINYFISH_DEFAULT_TIMEOUT", "120"))
QUICK_MODE_DEADLINE_SEC = int(os.environ.get("QUICK_MODE_DEADLINE_SEC", "3"))
WARMUP_DEADLINE_SEC = int(os.environ.get("WARMUP_DEADLINE_SEC", "12"))
SSE_QUEUE_TIMEOUT_SEC = int(os.environ.get("SSE_QUEUE_TIMEOUT_SEC", "30"))
THREAD_JOIN_TIMEOUT_SEC = int(os.environ.get("THREAD_JOIN_TIMEOUT_SEC", "5"))

# ── Circuit Breaker ──
CIRCUIT_BREAKER_THRESHOLD = int(os.environ.get("CB_THRESHOLD", "3"))
CIRCUIT_BREAKER_COOLDOWN_SEC = int(os.environ.get("CB_COOLDOWN_SEC", "60"))

# ── Warmup ──
# Comma-separated list of countries to warm on startup. Empty = no warmup.
WARMUP_COUNTRIES = [c.strip().lower() for c in os.environ.get("WARMUP_COUNTRIES", "").split(",") if c.strip()]

# ── Country aliases ──
COUNTRY_ALIASES: dict[str, str] = {
    "in": "india", "india": "india",
    "ae": "uae", "uae": "uae", "united arab emirates": "uae",
    "gb": "uk", "uk": "uk", "united kingdom": "uk", "england": "uk", "britain": "uk",
    "us": "usa", "usa": "usa", "united states": "usa", "united states of america": "usa",
    "de": "germany", "germany": "germany", "deutschland": "germany",
}


def normalize_country(country: str) -> str:
    c = (country or "india").strip().lower()
    return COUNTRY_ALIASES.get(c, c)


def normalize_city(city: str) -> str:
    return " ".join(part.capitalize() for part in (city or "").split()).strip()


# ── Country configuration — single source of truth for all regions ──
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
        "warmup_cities": ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Ahmedabad",
                          "Kolhapur", "Khopoli", "Vellore", "Krishnagiri"],
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
        "warmup_cities": [],
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
        "warmup_cities": [],
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
        "warmup_cities": [],
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
        "warmup_cities": [],
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
        "warmup_cities": [],
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


def market_region_for_city(city: str, country: str) -> str:
    cfg = COUNTRY_CONFIG.get(country) or COUNTRY_CONFIG["_global"]
    return cfg["city_region_map"].get(city, "default").lower()


def get_country_config(country: str) -> dict:
    return COUNTRY_CONFIG.get(country) or COUNTRY_CONFIG["_global"]


def get_incentives_for_locale(city: str, country: str) -> dict:
    c = normalize_country(country)
    region = market_region_for_city(city, c)
    cfg = get_country_config(c)
    incentives = cfg["incentives"]
    return incentives.get(region) or incentives.get("default") or COUNTRY_CONFIG["_global"]["incentives"]["default"]


# ── Highway routes ──
HIGHWAY_ROUTES: dict[tuple, dict] = {
    ("Mumbai", "Pune"): {
        "distance_km": 150, "highway": "NH48",
        "waypoints": [{"name": "Khopoli", "km": 80, "state": "maharashtra"}],
    },
    ("Mumbai", "Goa"): {
        "distance_km": 580, "highway": "NH66",
        "waypoints": [
            {"name": "Pune",     "km": 150, "state": "maharashtra"},
            {"name": "Satara",   "km": 265, "state": "maharashtra"},
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
            {"name": "Solapur", "km": 240, "state": "maharashtra"},
            {"name": "Latur",   "km": 370, "state": "maharashtra"},
            {"name": "Nanded",  "km": 490, "state": "maharashtra"},
            {"name": "Akola",   "km": 590, "state": "maharashtra"},
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
        "waypoints": [{"name": "Mathura", "km": 170, "state": "uttar-pradesh"}],
    },
    ("Delhi", "Jaipur"): {
        "distance_km": 280, "highway": "NH48",
        "waypoints": [
            {"name": "Gurugram",     "km": 30,  "state": "haryana"},
            {"name": "Shahjahanpur", "km": 190, "state": "rajasthan"},
        ],
    },
    ("Bangalore", "Chennai"): {
        "distance_km": 350, "highway": "NH44",
        "waypoints": [
            {"name": "Hosur",       "km": 40,  "state": "tamil-nadu"},
            {"name": "Krishnagiri", "km": 95,  "state": "tamil-nadu"},
            {"name": "Vellore",     "km": 215, "state": "tamil-nadu"},
        ],
    },
    ("Bangalore", "Hyderabad"): {
        "distance_km": 570, "highway": "NH44",
        "waypoints": [
            {"name": "Kolar",     "km": 70,  "state": "karnataka"},
            {"name": "Anantapur", "km": 250, "state": "andhra-pradesh"},
            {"name": "Kurnool",   "km": 390, "state": "andhra-pradesh"},
            {"name": "Jadcherla", "km": 490, "state": "telangana"},
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
            {"name": "Jebel Ali",  "km": 40,  "state": "dubai"},
            {"name": "Yas Island", "km": 115, "state": "abu-dhabi"},
        ],
    },
    ("Dubai", "Sharjah"): {
        "distance_km": 35, "highway": "E11",
        "waypoints": [{"name": "Al Qusais", "km": 20, "state": "dubai"}],
    },
}

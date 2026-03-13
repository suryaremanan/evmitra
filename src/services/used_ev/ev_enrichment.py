"""
VoltSage — services/used_ev/ev_enrichment.py
EV specs and owner insights agent — TinyFish-powered.
Searches official manufacturer sources and owner forums for live spec data.
Falls back to car_profiles database if TinyFish finds nothing.
"""
from typing import Optional

from core.config import logger

from .agent_client import run_agent_async
from .models import EvEnrichment

# Lazy imports for fallback database
_car_profiles = None
_synthesis = None
_ALL_DATA: dict = {}


def set_all_data(data: dict) -> None:
    global _ALL_DATA
    _ALL_DATA = data


def _get_car_profiles():
    global _car_profiles
    if _car_profiles is None:
        import car_profiles as cp
        _car_profiles = cp
    return _car_profiles


def _get_synthesis():
    global _synthesis
    if _synthesis is None:
        import synthesis as s
        _synthesis = s
    return _synthesis


def _build_goal(make: str, model: str, year: str) -> str:
    return f"""\
You are an EV specifications researcher.

Vehicle: {year} {make} {model}

Perform ALL three steps:

STEP 1 — Official EV specifications:
  Google → "{make} {model} {year} battery capacity kWh specifications"
  Also search: "{make} {model} {year} WLTP range km DC fast charge kW specs site:ev-database.org OR site:insideevs.com OR site:electrek.co"
  Find the manufacturer's official specifications:
  - Battery capacity in kWh (usable or gross)
  - Official rated range in km (WLTP / ARAI / EPA — whichever is available)
  - DC fast charging speed in kW (maximum)

STEP 2 — Owner-reported issues and reliability:
  Google → "{make} {model} common problems OR issues site:reddit.com OR site:team-bhp.com OR site:forums.whichev.net"
  Also search: "{make} {model} reliability issues owner review"
  Find the top 3–5 most commonly reported problems from real owners.
  Look for: battery issues, software bugs, charging problems, build quality complaints.

STEP 3 — Owner satisfaction rating:
  Google → "{make} {model} owner rating OR satisfaction score"
  Find any numeric owner satisfaction rating (e.g. 4.2/5, 85/100).
  Convert everything to a 0–5 scale if needed.

CRITICAL ACCURACY RULES:
- Only report figures you actually found on pages you visited
- spec_battery_kwh must be a plain number (e.g. 30.2), not a string
- spec_range_km must be in kilometres (convert miles × 1.609 if needed)
- spec_dc_kw must be in kilowatts as a plain number
- Use 0 for any numeric field you could not find
- Source URLs MUST start with "https://"

Return ONLY this JSON:
{{
  "spec_battery_kwh": 30.2,
  "spec_range_km": 312,
  "spec_dc_kw": 50.0,
  "known_issues": [
    "Battery preconditioning not automatic in cold weather",
    "Regenerative braking paddle can feel abrupt at low speeds"
  ],
  "owner_rating": 4.1,
  "source_urls": ["https://..."]
}}"""


def _fuzzy_match_profile(make: str, model: str, year: str) -> Optional[dict]:
    try:
        cp = _get_car_profiles()
        profiles = cp.CAR_PROFILES
        search = f"{make} {model}".strip().lower()
        for name, profile in profiles.items():
            if name.lower() == search or search in name.lower() or name.lower() in search:
                return profile
    except Exception:
        pass
    return None


async def get_ev_enrichment(
    make: str,
    model: str,
    year: str = "",
    country: str = "india",
) -> EvEnrichment:
    """
    TinyFish-powered EV specs + owner insights.
    Falls back to car_profiles database if TinyFish returns no data.
    """
    if not make:
        return EvEnrichment(error="Insufficient vehicle data", source="none")

    agent_result = await run_agent_async(
        url="https://www.google.com",
        goal=_build_goal(make, model, year),
        label="EV Specs",
        profile="lite",
        timeout=90,
    )

    spec_battery_kwh: Optional[float] = None
    spec_range_city_km: Optional[int] = None
    spec_dc_kw: Optional[float] = None
    known_issues: list[str] = []
    owner_rating: Optional[float] = None
    source_urls: list[str] = [
        u for u in agent_result.get("source_urls", []) if str(u).startswith("http")
    ]

    raw_kwh = agent_result.get("spec_battery_kwh")
    try:
        val = float(raw_kwh or 0)
        if val > 0:
            spec_battery_kwh = val
    except (ValueError, TypeError):
        pass

    raw_range = agent_result.get("spec_range_km")
    try:
        val = int(raw_range or 0)
        if val > 0:
            spec_range_city_km = val
    except (ValueError, TypeError):
        pass

    raw_dc = agent_result.get("spec_dc_kw")
    try:
        val = float(raw_dc or 0)
        if val > 0:
            spec_dc_kw = val
    except (ValueError, TypeError):
        pass

    raw_issues = agent_result.get("known_issues", [])
    if isinstance(raw_issues, list):
        known_issues = [str(i) for i in raw_issues if i][:5]

    raw_rating = agent_result.get("owner_rating")
    if raw_rating:
        try:
            owner_rating = float(raw_rating)
        except (ValueError, TypeError):
            pass

    source = "live"

    # Fallback to database if TinyFish returned nothing useful
    if not spec_battery_kwh and not spec_range_city_km:
        profile = _fuzzy_match_profile(make, model, year)
        if profile:
            spec_battery_kwh = profile.get("battery_kwh")
            spec_range_city_km = profile.get("real_range_city_km")
            spec_dc_kw = spec_dc_kw or profile.get("dc_fast_charge_kw")
            source = "database"

            if _ALL_DATA and not known_issues:
                try:
                    syn = _get_synthesis()
                    search_key = profile.get("teambhp_search", f"{make} {model}")
                    insights = syn.extract_owner_insights(_ALL_DATA, search_key)
                    if insights:
                        known_issues = (
                            insights.get("bad", [])[:3] + insights.get("ugly", [])[:2]
                        )
                except Exception as exc:
                    logger.debug("extract_owner_insights fallback failed: %s", exc)

    return EvEnrichment(
        spec_battery_kwh=spec_battery_kwh,
        spec_range_city_km=spec_range_city_km,
        spec_range_highway_km=None,
        spec_dc_kw=spec_dc_kw,
        warranty_months=None,   # covered by battery_health agent
        known_issues=known_issues,
        owner_rating=owner_rating,
        source=source,
    )

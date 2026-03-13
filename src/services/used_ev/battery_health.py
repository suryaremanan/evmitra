"""
VoltSage — services/used_ev/battery_health.py
Battery health agent: asks TinyFish to find real-world SoH data from owner forums,
battery test databases, and manufacturer sources. No hardcoded degradation formulas.
"""
from .agent_client import run_agent_async
from .models import BatteryHealth, ListingFacts

_SOH_CONCERN_THRESHOLD = 80   # flag in scorer if SoH below this


def _build_goal(make: str, model: str, year: str, odometer_km: int, claimed_range_km: int) -> str:
    odo_str = f"{odometer_km:,} km" if odometer_km else "unknown"
    range_str = f"{claimed_range_km} km per charge" if claimed_range_km else "not stated by seller"
    return f"""\
You are a used EV battery health investigator.

Vehicle: {year} {make} {model}
Odometer: {odo_str}
Seller-claimed range: {range_str}

Perform ALL four steps:

STEP 1 — Real-world battery degradation data:
  Google → "{year} {make} {model} battery health {odo_str} owner report"
  Also search: "{make} {model} battery degradation real range site:reddit.com OR site:team-bhp.com OR site:insideevs.com"
  Find owner reports, battery health studies, or EV forum posts that show what
  real-world range or SoH owners report at around {odo_str}. Look for data points
  like "my {make} {model} still gives X km at Y km odometer".

STEP 2 — Official rated range:
  Google → "{make} {model} {year} official rated range WLTP OR ARAI OR EPA km"
  Find the manufacturer's certified rated range for this model. This is needed to
  compute how much range has been lost.

STEP 3 — Battery recall and service campaigns:
  Google → "{year} {make} {model} battery recall OR battery fire OR service campaign"
  Visit top results. Note any NHTSA/manufacturer recalls or battery issues.

STEP 4 — Battery warranty:
  Google → "{make} {model} battery warranty years km"
  Find the official battery warranty: years covered and km limit.

Based on all the above, estimate the battery State of Health (SoH) as a percentage:
- If seller states range AND you found official rated range: SoH ≈ (claimed / rated) × 100
- If you found owner reports of typical range at this mileage: use those as your reference
- If no data found: return estimated_soh_pct as 0 (do not guess)

CRITICAL ACCURACY RULES:
- Only report findings from pages you actually visited
- estimated_soh_pct must be based on real data you found, not a formula
- Source URLs MUST start with "https://"
- Use 0 for any numeric field you could not find

Return ONLY this JSON:
{{
  "estimated_soh_pct": 87,
  "soh_rationale": "Owner reports on TeamBHP show Nexon EV Max retains ~87% range at 50,000 km",
  "rated_range_km": 312,
  "typical_range_at_mileage_km": 270,
  "recall_found": false,
  "recall_details": "",
  "warranty_years": 8,
  "warranty_km": 160000,
  "dc_charge_limited": false,
  "source_urls": ["https://..."],
  "notes": []
}}"""


async def assess_battery(
    facts: ListingFacts,
) -> BatteryHealth:
    make = facts.make or "Unknown"
    model = facts.model or "EV"
    year = facts.year or "2020"
    odometer_km = facts.odometer_km or 0
    claimed_range_km = facts.claimed_range_km or 0

    try:
        vehicle_age = max(0, 2025 - int(year))
    except (ValueError, TypeError):
        vehicle_age = 3

    agent_result = await run_agent_async(
        url="https://www.google.com",
        goal=_build_goal(make, model, year, odometer_km, claimed_range_km),
        label="Battery",
        profile="stealth",
        timeout=120,
    )

    # SoH from TinyFish live data
    estimated_soh = int(agent_result.get("estimated_soh_pct") or 0)

    # If TinyFish couldn't find data and seller stated range, compute ratio
    if not estimated_soh and claimed_range_km:
        rated_range = int(agent_result.get("rated_range_km") or 0)
        if rated_range > 0:
            estimated_soh = min(100, max(0, round((claimed_range_km / rated_range) * 100)))

    degradation_flag = bool(estimated_soh) and estimated_soh < _SOH_CONCERN_THRESHOLD

    if not estimated_soh:
        assessment = "UNKNOWN"
    elif estimated_soh >= 90:
        assessment = "EXCELLENT"
    elif estimated_soh >= 80:
        assessment = "GOOD"
    elif estimated_soh >= 70:
        assessment = "FAIR"
    else:
        assessment = "POOR"

    recall_found = bool(agent_result.get("recall_found"))
    recall_details = agent_result.get("recall_details", "") or ""
    dc_charge_limited = bool(agent_result.get("dc_charge_limited"))
    source_urls = [u for u in agent_result.get("source_urls", []) if str(u).startswith("http")]
    notes: list[str] = [n for n in agent_result.get("notes", []) if isinstance(n, str) and n]
    soh_rationale = agent_result.get("soh_rationale", "")
    if soh_rationale:
        notes = [soh_rationale] + notes

    warranty_years = int(agent_result.get("warranty_years") or 0)
    warranty_km = int(agent_result.get("warranty_km") or 0)
    warranty_remaining = ""
    if warranty_years or warranty_km:
        in_time = vehicle_age < warranty_years
        in_km = odometer_km < warranty_km
        if in_time and in_km:
            warranty_remaining = f"In warranty ({warranty_years}yr / {warranty_km:,}km)"
        elif not in_time:
            warranty_remaining = f"Expired (>{warranty_years}yr)"
        else:
            warranty_remaining = f"Expired (>{warranty_km:,}km)"

    return BatteryHealth(
        estimated_soh_pct=estimated_soh if estimated_soh else None,
        degradation_flag=degradation_flag,
        warranty_remaining=warranty_remaining,
        recall_found=recall_found,
        recall_details=recall_details,
        dc_charge_limited=dc_charge_limited,
        assessment=assessment,
        notes=notes,
        source_urls=source_urls,
    )

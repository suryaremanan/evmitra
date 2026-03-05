"""
EV Mitra — synthesis.py
The complete pipeline: load all data → score → prompt → verdict
"""

import json
import logging
import math
import os
import requests
from pathlib import Path

from car_profiles import CAR_PROFILES, get_profile

logger = logging.getLogger("evmitra")


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent if (BASE_DIR.parent / "data").exists() else BASE_DIR
DATA_DIR = PROJECT_ROOT / "data"


# ─────────────────────────────────────────────────────────
# 1. DATA LOADER
# ─────────────────────────────────────────────────────────

def load_json(filename):
    file_path = DATA_DIR / filename
    if not file_path.exists():
        # Backward compatibility: support legacy root-level data files.
        file_path = PROJECT_ROOT / filename

    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("%s not found — using empty dict", filename)
        return {}
    except json.JSONDecodeError as e:
        logger.warning("%s has bad JSON: %s", filename, e)
        return {}


def load_all_data():
    """Load all scraped data files."""
    data = {
        "chargers_nagpur":  load_json("statiq_nagpur.json"),
        "chargers_pune":    load_json("statiq_pune.json"),
        "teambhp_thread1":  load_json("teambhp_nexon_ev.json"),
        "teambhp_thread2":  load_json("teambhp_thread2.json"),
        "teambhp_thread3":  load_json("teambhp_thread3.json"),
        "subsidy":          load_json("subsidy_data.json"),
        "ocm_nagpur":       load_json("ocm_nagpur.json"),
    }

    for name, content in data.items():
        if content:
            extra = ""
            if isinstance(content, dict) and "stations" in content:
                extra = f" ({content.get('total_found', len(content['stations']))} stations)"
            logger.info("  loaded %s%s", name, extra)
        else:
            logger.warning("  empty %s", name)

    return data


# ─────────────────────────────────────────────────────────
# 2. SUBSIDY DATA
# ─────────────────────────────────────────────────────────

MAHARASHTRA_SUBSIDY = {
    "state_name": "Maharashtra",
    "fame2_status": "FAME II ended March 2024. FAME III under discussion.",
    "state_road_tax_exemption_inr": 150000,
    "state_registration_fee_waiver_inr": 60000,
    "scrappage_incentive_inr": 25000,
    "total_estimated_saving_inr": 235000,
    "note": "No direct purchase subsidy for 4-wheelers currently. "
            "Savings are via tax/fee exemptions. Verify at time of purchase.",
    "source": "Maharashtra EV Policy 2021 (public)",
}


# ─────────────────────────────────────────────────────────
# 3. CALIBRATED ANXIETY SCORE CALCULATOR
#
# Formula is fully documented and defensible in Q&A.
#
# Daily score:
#   range_buffer = real_range × 0.85        (15% safety margin)
#   daily_ratio  = daily_km / range_buffer  (0→1 where 1 = full buffer)
#   daily_base   = daily_ratio × 10         (linear km use)
#   daily_infra  = max(0, (5 - fast_dc) × 0.4)  (penalty < 5 fast chargers)
#   daily_score  = min(10, daily_base + daily_infra)
#
# Occasional score:
#   trips_needed    = ceil(occasional_km / real_range)
#   coverage_score  = min(10, (trips_needed - 1) × 3)
#   gap_penalty     = max(0, 5 - high_power_count) × 0.6
#   occasional_score = min(10, coverage_score + gap_penalty)
# ─────────────────────────────────────────────────────────

def calculate_anxiety_scores(charger_data, daily_km, occasional_km,
                              car_profile: dict = None,
                              car_real_range_km: int = None):
    """
    Scores 1–10 where 1 = relaxed, 10 = very anxious.
    car_profile takes precedence over the legacy car_real_range_km param.
    """
    if car_profile is None:
        car_profile = get_profile("Tata Nexon EV Max")

    # Use profile's city range (Team-BHP confirmed, not manufacturer claim)
    real_range = car_real_range_km or car_profile.get("real_range_city_km", 180)

    stations = charger_data.get("stations", [])
    fast_dc = [
        s for s in stations
        if "DC" in s.get("connector_types", [])
        and s.get("power_kw") != 0     # exclude broken/inactive
    ]
    high_power = [
        s for s in fast_dc
        if s.get("power_kw") and s.get("power_kw") >= 50
    ]
    total = len(stations)
    fast_count = len(fast_dc)
    high_power_count = len(high_power)

    # ── Daily score ──
    range_buffer = real_range * 0.85   # 15% safety margin: conservative driving
    daily_ratio = min(1.0, daily_km / max(range_buffer, 1))
    daily_base = daily_ratio * 10
    daily_infra = max(0.0, (5 - fast_count) * 0.4)  # infra penalty if < 5 fast chargers
    daily_score = round(min(10, daily_base + daily_infra))

    if daily_ratio < 0.25:
        daily_rationale = (f"Your {daily_km}km commute is only {daily_ratio*100:.0f}% of "
                           f"safe range ({range_buffer:.0f}km). Very comfortable.")
    elif daily_ratio < 0.55:
        daily_rationale = (f"Your {daily_km}km commute uses {daily_ratio*100:.0f}% of "
                           f"safe range. Manageable with occasional public top-ups.")
    else:
        daily_rationale = (f"Your {daily_km}km commute is {daily_ratio*100:.0f}% of "
                           f"safe range ({range_buffer:.0f}km). Frequent charging needed.")

    if fast_count < 5:
        daily_rationale += (f" Only {fast_count} DC fast chargers in city "
                            "adds real infrastructure risk.")

    # ── Occasional score ──
    trips_needed = math.ceil(occasional_km / max(real_range, 1))
    coverage_score = min(10, (trips_needed - 1) * 3)
    gap_penalty = max(0.0, (5 - high_power_count) * 0.6)
    occasional_score = round(min(10, coverage_score + gap_penalty))

    if trips_needed <= 1:
        occasional_rationale = (f"Your {occasional_km}km trip fits within a single "
                                f"charge ({real_range}km real range). No stop needed.")
    elif trips_needed == 2:
        occasional_rationale = (
            f"Your {occasional_km}km trip needs 1 charge stop. "
            f"{high_power_count} fast charger(s) ≥50kW "
            f"{'available' if high_power_count >= 1 else 'NOT found'} in city — "
            f"highway coverage is the key risk."
        )
    else:
        occasional_rationale = (
            f"Your {occasional_km}km trip needs {trips_needed - 1} charge stops "
            f"with real range of {real_range}km. Significant planning required."
        )

    # Confidence: based on whether charger data came from a live scrape
    source_type = charger_data.get("source_type", "static_fallback")
    confidence = {"live": "high", "cache": "medium"}.get(source_type, "low")

    return {
        "daily_score": min(10, max(1, daily_score)),
        "occasional_score": min(10, max(1, occasional_score)),
        "daily_rationale": daily_rationale,
        "occasional_rationale": occasional_rationale,
        "total_stations": total,
        "fast_dc_chargers": fast_count,
        "high_power_chargers_50kw_plus": high_power_count,
        "real_range_used_km": real_range,
        "daily_km": daily_km,
        "occasional_km": occasional_km,
        "confidence": confidence,
    }


# ─────────────────────────────────────────────────────────
# 4. DATA EXTRACTOR
# Pull the most useful fields from Team-BHP files.
# Falls back gracefully when data is missing.
# ─────────────────────────────────────────────────────────

def extract_owner_insights(t1, t2, t3):
    """Extract and consolidate the most powerful data points."""
    # Thread 1
    verdict_1     = t1.get("honest_verdict", "")
    range_data    = t1.get("real_world_range", {})
    city_range    = range_data.get("city_ac_on_km", 180)
    highway_range = range_data.get("highway_kmph_100", 230)
    worst_range   = range_data.get("worst_case_km", 120)
    issues_1      = t1.get("long_term_issues", [])
    positives_1   = t1.get("things_owners_love", [])
    charging_exp  = t1.get("charging_network_experiences", [])
    charge_quote  = charging_exp[0].get("quote", "") if charging_exp else ""

    # Thread 2
    details_2       = t2.get("details", t2)
    honest_quote_2  = details_2.get("most_honest_quote", "")
    would_buy_again = details_2.get("would_buy_again", None)
    charge_verdict  = details_2.get("charging_reliability_verdict", "")
    cost_per_km     = details_2.get("cost_per_km_inr", 1.4)
    biggest_regret  = details_2.get("biggest_regret", "")

    # Thread 3
    honest_quote_3 = t3.get("most_honest_quote", "")
    discoveries    = t3.get("unexpected_discoveries", [])

    return {
        "city_range_km": city_range,
        "highway_range_km": highway_range,
        "worst_case_range_km": worst_range,
        "verdict_1": verdict_1,
        "charging_quote": charge_quote,
        "long_term_issues": issues_1,
        "things_owners_love": positives_1,
        "honest_quote_unicorn": honest_quote_2,
        "would_buy_again": would_buy_again,
        "charging_time_wasted": charge_verdict,
        "cost_per_km_inr": cost_per_km,
        "biggest_regret": biggest_regret,
        "range_lie_quote": honest_quote_3,
        "unexpected_discoveries": discoveries,
    }


# ─────────────────────────────────────────────────────────
# 5. SYNTHESIS PROMPT BUILDER
# car_profile drives all financial and range figures.
# ─────────────────────────────────────────────────────────

def build_prompt(user_input, scores, insights, subsidy, car_profile: dict = None, country: str = "india"):
    """Build the LLM synthesis prompt with car-specific data."""
    if car_profile is None:
        car_profile = get_profile("Tata Nexon EV Max")

    country_lower = (country or "india").lower()
    is_india = country_lower == "india"

    # ── Currency and locale config ──
    _LOCALE = {
        "india":   {"sym": "₹",  "unit": "lakhs", "divisor": 100_000, "petrol_per_km": 7.0,  "fuel_label": "petrol"},
        "uae":     {"sym": "AED","unit": "k",      "divisor": 1_000,   "petrol_per_km": 0.35, "fuel_label": "petrol"},
        "uk":      {"sym": "£",  "unit": "k",      "divisor": 1_000,   "petrol_per_km": 0.18, "fuel_label": "petrol"},
        "usa":     {"sym": "$",  "unit": "k",      "divisor": 1_000,   "petrol_per_km": 0.12, "fuel_label": "gas"},
        "germany": {"sym": "€",  "unit": "k",      "divisor": 1_000,   "petrol_per_km": 0.18, "fuel_label": "petrol"},
    }
    loc = _LOCALE.get(country_lower, {"sym": "",  "unit": "",  "divisor": 1, "petrol_per_km": 0.15, "fuel_label": "fuel"})
    sym = loc["sym"]
    fuel_label = loc["fuel_label"]

    issues_text      = "\n".join(f"  - {i}" for i in insights["long_term_issues"][:4])
    positives_text   = "\n".join(f"  - {p}" for p in insights["things_owners_love"][:3])
    discoveries_text = "\n".join(f"  - {d}" for d in insights["unexpected_discoveries"][:3])
    has_owner_data   = bool(insights.get("verdict_1") or issues_text or positives_text)

    # ── Subsidy / incentive text ──
    if is_india:
        total_saving = subsidy.get("total_estimated_saving_inr", 0)
        saving_display = total_saving / 100_000
        incentive_line = (
            f"{subsidy.get('state_name', 'State')} tax/fee exemptions: "
            f"~{sym}{saving_display:.1f} lakhs\n"
            f"  FAME II: Ended March 2024 — no direct purchase subsidy currently"
        )
    else:
        incentive_notes = [i.get("description", "") for i in (subsidy.get("incentives") or []) if i.get("description")]
        if incentive_notes:
            incentive_line = "Government incentives available:\n" + "\n".join(f"  - {n}" for n in incentive_notes[:3])
        else:
            incentive_line = subsidy.get("note", "Check local government website for current EV incentives.")

    # ── Financial figures ──
    ev_cost_per_km = car_profile.get("running_cost_per_km_inr", 1.4)
    ex_showroom    = car_profile.get("ex_showroom_inr", 2_000_000)
    mfr_claim_km   = car_profile.get("manufacturer_range_claim_km", 312)
    real_range     = car_profile.get("real_range_city_km", 180)
    charge_time    = car_profile.get("full_charge_min_dc", 57)
    charge_kw      = car_profile.get("dc_fast_charge_kw", 50)

    petrol_cost_per_km = loc["petrol_per_km"]
    saving_per_km  = petrol_cost_per_km - ev_cost_per_km
    annual_km      = scores["daily_km"] * 300
    annual_saving  = annual_km * saving_per_km

    # Format price for display — keep INR in lakhs, others as raw number
    if is_india:
        price_str = f"{sym}{ex_showroom / 100_000:.1f} lakhs ex-showroom"
    else:
        price_str = f"approx. {sym}{ex_showroom / 100_000:.0f}k (India price reference; verify local pricing)"

    # ── Owner source label ──
    owner_source = "Team-BHP (India's largest owner forum)" if is_india else "owner forums / press long-term reviews"

    # ── Owner data section ──
    if has_owner_data:
        owner_section = f"""REAL OWNER EXPERIENCES ({owner_source}):
  Overall verdict: "{insights['verdict_1']}"
  On charging reliability: "{insights['charging_quote']}"
  On manufacturer range claims: "{insights['range_lie_quote']}"
  Long-term owner (2 years): "{insights['honest_quote_unicorn']}"
  Would buy again: {'Yes' if insights['would_buy_again'] else 'NO'}
  Biggest regret: {insights['biggest_regret']}

  Long-term issues (multiple owners):
{issues_text}

  Unexpected discoveries owners wished they knew:
{discoveries_text}

  What owners genuinely love:
{positives_text}"""
    else:
        owner_section = f"""OWNER DATA NOTE:
  No localised owner forum data available for {country.title()} yet.
  Base your CHARGING INFRASTRUCTURE and SCORES sections on the scraped charger data.
  For owner experience: use your general knowledge of this car model's reliability,
  known issues, and user sentiment from global reviews. Be honest about data gaps."""

    prompt = f"""
You are EV Mitra — the most honest EV advisor for {country.title()}.
You are a knowledgeable friend, not a salesperson.
Your job: give the user honest, specific, actionable advice.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USER SITUATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{user_input}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REAL DATA (gathered live, not from brochures)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CAR SPECS (real-world data):
  Model: {car_profile.get("segment", "EV")} — {price_str}
  Real range (city, AC on): {real_range}km  ← NOT the {mfr_claim_km}km manufacturer claim
  DC fast charge: {charge_kw}kW — {charge_time} min for 10→80%

CHARGING INFRASTRUCTURE (live-scraped):
  Total stations in city: {scores['total_stations']}
  DC fast chargers (actually useful): {scores['fast_dc_chargers']}
  High-power ≥50kW chargers: {scores['high_power_chargers_50kw_plus']}
  Data confidence: {scores['confidence'].upper()}

ANXIETY SCORES (calibrated formula):
  Daily commute ({scores['daily_km']}km): {scores['daily_score']}/10 — {scores['daily_rationale']}
  Long trip ({scores['occasional_km']}km): {scores['occasional_score']}/10 — {scores['occasional_rationale']}

{owner_section}

FINANCIAL DATA:
  Running cost: {sym}{ev_cost_per_km}/km (EV) vs {sym}{petrol_cost_per_km}/km ({fuel_label})
  Annual saving: {sym}{annual_saving:,.0f} at {annual_km}km/year
  {incentive_line}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR RESPONSE FORMAT — follow exactly
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔋 CHARGING ANXIETY SCORE
Daily commute: {scores['daily_score']}/10
[One sentence — specific to their km and charger count]

Long trips: {scores['occasional_score']}/10
[One sentence — specific to their trip distance vs real range]

📊 WHAT REAL OWNERS ACTUALLY EXPERIENCE
[3-4 sentences using the owner data above. Quote naturally. Include real vs claimed range.
Feel like a friend sharing research, not a bullet list.
If no owner data: use your general knowledge and explicitly say it's based on global reviews.]

⚠️  THINGS NOBODY TELLS YOU BEFORE BUYING
[Exactly 3 specific issues from owner data or global knowledge. Direct. No softening.]

💚 WHAT'S GENUINELY GREAT
[2-3 things owners actually love. No marketing language.]

💰 YOUR ACTUAL NUMBERS
Running cost: {sym}{ev_cost_per_km}/km vs {sym}{petrol_cost_per_km}/km {fuel_label}
Annual saving: {sym}{annual_saving:,.0f} at your usage
[Incentive/policy note in one sentence]

🎯 HONEST VERDICT
[2-3 sentences. Most important part. Specific to their city, routes, situation.
If they shouldn't buy — say so and say why.
If they should — say so and what to watch for.
Do NOT hedge. Real friend, real answer. End with one actionable recommendation.]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRICT RULES:
- Never use "exciting", "revolutionary", "game-changer", "seamless"
- Never say "it depends" without immediately saying what it depends on
- Use the correct local currency ({sym}) — do NOT use {"₹" if sym != "₹" else "$ or £"}
- State problems seriously if data shows serious problems
- Name the user's city specifically in the verdict
- Max 400 words total
- OUTPUT FORMAT: Start each section DIRECTLY with the emoji (🔋, 📊, ⚠️, 💚, 💰, 🎯). No # ## headers. No title before first section. No --- dividers.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return prompt


# ─────────────────────────────────────────────────────────
# 6. LLM CALLER
# ─────────────────────────────────────────────────────────

def call_llm(prompt):
    """Call LLM — Anthropic first, Fireworks fallback."""
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}]
            )
            logger.info("LLM: Anthropic Claude")
            return msg.content[0].text
        except ImportError:
            logger.warning("anthropic package not installed — pip install anthropic")
        except Exception as e:
            logger.warning("Anthropic failed: %s", e)

    fireworks_key = os.environ.get("FIREWORKS_API_KEY")
    if fireworks_key:
        try:
            resp = requests.post(
                "https://api.fireworks.ai/inference/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {fireworks_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "accounts/fireworks/models/llama-v3p3-70b-instruct",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 800,
                    "temperature": 0.3,
                },
                timeout=30,
            )
            data = resp.json()
            if "choices" not in data:
                logger.warning("Fireworks non-chat response: %s", str(data)[:300])
                return None
            logger.info("LLM: Fireworks.ai (LLaMA 3.1)")
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning("Fireworks failed: %s", e)

    logger.error("No LLM API key found. Set ANTHROPIC_API_KEY or FIREWORKS_API_KEY.")
    return None


# ─────────────────────────────────────────────────────────
# 7. CLI TEST PIPELINE
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    from car_profiles import CAR_PROFILES

    all_data = load_all_data()
    charger_data = all_data.get("chargers_nagpur", {"stations": [], "total_found": 0})
    profile = CAR_PROFILES["Tata Nexon EV Max"]

    scores = calculate_anxiety_scores(charger_data, 25, 230, car_profile=profile)
    print(f"\n📊 Daily: {scores['daily_score']}/10 | Occasional: {scores['occasional_score']}/10")
    print(f"   Confidence: {scores['confidence']}")
    print(f"   Daily rationale: {scores['daily_rationale']}")

    insights = extract_owner_insights(
        all_data["teambhp_thread1"],
        all_data["teambhp_thread2"],
        all_data["teambhp_thread3"],
    )

    subsidy = MAHARASHTRA_SUBSIDY
    prompt = build_prompt(
        "I live in Nagpur. Daily 25km. Occasional 230km. No home charging.",
        scores, insights, subsidy, car_profile=profile
    )
    verdict = call_llm(prompt)
    if verdict:
        print("\n" + "="*60)
        print(verdict)

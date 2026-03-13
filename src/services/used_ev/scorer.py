"""
VoltSage — services/used_ev/scorer.py
Converts all agent results into a split risk score:
  fraud_risk      — price / duplicate / photo / identity signals
  ev_condition_risk — battery / odometer / warranty / recall
  overall_risk    — weighted combination (60% fraud + 40% condition)
"""
import re
from typing import Optional

from .models import (
    BatteryHealth,
    CrossCheckResult,
    EvEnrichment,
    ListingFacts,
    MarketData,
    RiskScore,
)

_CURRENT_YEAR = 2025

# VIN: 17 alphanum excluding I/O/Q
_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$", re.IGNORECASE)

# Price delta thresholds (% below market median)
_PRICE_EXTREME_LOW = -40.0
_PRICE_VERY_LOW    = -25.0
_PRICE_LOW         = -10.0

# Odometer anomaly: km per year below which we suspect tampering
_AVG_ANNUAL_KM          = 12_000
_MILEAGE_LOW_FRACTION   = 0.12
_MILEAGE_CHECK_MIN_AGE  = 3     # years

_BANDS = [
    (81, 100, "WALK AWAY", "red"),
    (56, 80,  "HIGH RISK", "orange"),
    (26, 55,  "CAUTION",   "yellow"),
    (0,  25,  "LOW RISK",  "green"),
]


def _band(score: int) -> tuple[str, str]:
    for lo, hi, name, color in _BANDS:
        if lo <= score <= hi:
            return name, color
    return "UNKNOWN", "grey"


def _vehicle_age(year_str: str) -> Optional[int]:
    try:
        year = int(year_str)
        return _CURRENT_YEAR - year if 1990 <= year <= _CURRENT_YEAR else None
    except (ValueError, TypeError):
        return None


def score_risk(
    facts: ListingFacts,
    cross_check: CrossCheckResult,
    market_data: MarketData,
    battery: BatteryHealth,
    enrichment: EvEnrichment,
) -> RiskScore:
    fraud_penalties: dict[str, int] = {}
    condition_penalties: dict[str, int] = {}
    flags: list[str] = []

    # ══════════════════════════════════════════════════════════════════════════
    # FRAUD RISK
    # ══════════════════════════════════════════════════════════════════════════

    # Price vs. market ────────────────────────────────────────────────────────
    if market_data and market_data.price_delta_pct is not None:
        delta = market_data.price_delta_pct
        if delta < _PRICE_EXTREME_LOW:
            fraud_penalties["price_extreme_low"] = 30
            flags.append(f"Price is {abs(delta):.0f}% below market median — extremely suspicious")
        elif delta < _PRICE_VERY_LOW:
            fraud_penalties["price_very_low"] = 20
            flags.append(f"Price is {abs(delta):.0f}% below market median")
        elif delta < _PRICE_LOW:
            fraud_penalties["price_low"] = 10
            flags.append(f"Price is {abs(delta):.0f}% below market median")

    # Duplicate listings ──────────────────────────────────────────────────────
    if cross_check:
        dup_count = len(cross_check.duplicates)
        if dup_count >= 3:
            fraud_penalties["many_duplicates"] = 25
            flags.append(f"Listing duplicated across {dup_count} platforms or identities")
        elif dup_count >= 1:
            fraud_penalties["some_duplicates"] = 15
            flags.append(f"{dup_count} duplicate listing(s) found on other platforms")

        # Photo reuse ─────────────────────────────────────────────────────────
        reuse_count = len(cross_check.image_reuses)
        if reuse_count >= 2:
            fraud_penalties["photo_reuse_severe"] = 18
            flags.append(f"Listing photos reused on {reuse_count} other web pages")
        elif reuse_count == 1:
            fraud_penalties["photo_reuse_minor"] = 10
            flags.append("Listing photo found reused on another web page")

        # Identity flags ──────────────────────────────────────────────────────
        id_count = len(cross_check.identity_flags)
        if id_count >= 2:
            fraud_penalties["identity_multiple"] = 18
            flags.extend(cross_check.identity_flags)
        elif id_count == 1:
            fraud_penalties["identity_single"] = 8
            flags.append(cross_check.identity_flags[0])

    # VIN checks ──────────────────────────────────────────────────────────────
    if facts:
        if not facts.vin:
            fraud_penalties["no_vin"] = 6
            flags.append("VIN not visible — seller may be hiding vehicle history")
        elif not _VIN_RE.match(facts.vin):
            fraud_penalties["invalid_vin"] = 8
            flags.append(f"VIN '{facts.vin}' has an invalid format — may be fabricated")

    # No photos ───────────────────────────────────────────────────────────────
    if facts and not facts.photo_urls:
        fraud_penalties["no_photos"] = 5
        flags.append("Listing has no photos — unusual for a legitimate private sale")

    # Extraction error ────────────────────────────────────────────────────────
    if facts and facts.error:
        fraud_penalties["extraction_error"] = 5
        flags.append("Could not fully load listing — page may be removed or access-blocked")

    # ══════════════════════════════════════════════════════════════════════════
    # EV CONDITION RISK
    # ══════════════════════════════════════════════════════════════════════════

    # Battery SoH ─────────────────────────────────────────────────────────────
    if battery:
        soh = battery.estimated_soh_pct
        if soh is not None:
            if soh < 70:
                condition_penalties["battery_poor"] = 25
                flags.append(f"Estimated battery SoH ~{soh}% — significant degradation")
            elif soh < 80:
                condition_penalties["battery_fair"] = 12
                flags.append(f"Estimated battery SoH ~{soh}% — noticeable degradation")
            elif soh < 88:
                condition_penalties["battery_moderate"] = 5
                flags.append(f"Estimated battery SoH ~{soh}% — some degradation")

        if battery.recall_found:
            condition_penalties["recall"] = 20
            flags.append(f"Battery recall found: {battery.recall_details or 'see manufacturer advisory'}")

        if battery.dc_charge_limited:
            condition_penalties["dc_limit"] = 8
            flags.append("DC fast charging may be limited due to battery condition")

    # Odometer anomaly ────────────────────────────────────────────────────────
    if facts and facts.odometer_km is not None:
        age = _vehicle_age(facts.year)
        if age and age >= _MILEAGE_CHECK_MIN_AGE:
            expected_min = age * _AVG_ANNUAL_KM * _MILEAGE_LOW_FRACTION
            if facts.odometer_km < expected_min:
                condition_penalties["odometer_suspiciously_low"] = 8
                flags.append(
                    f"Odometer ({facts.odometer_km:,} km) is suspiciously low for a "
                    f"{age}-year-old vehicle — possible tampering"
                )

    # Warranty expired ────────────────────────────────────────────────────────
    if battery and battery.warranty_remaining and "Expired" in battery.warranty_remaining:
        condition_penalties["warranty_expired"] = 5
        flags.append(f"Battery warranty: {battery.warranty_remaining}")

    # Known model issues ──────────────────────────────────────────────────────
    if enrichment and enrichment.known_issues:
        condition_penalties["known_issues"] = min(5 * len(enrichment.known_issues), 10)
        flags.append(f"Model has {len(enrichment.known_issues)} known owner-reported issue(s)")

    # ══════════════════════════════════════════════════════════════════════════
    # COMBINE
    # ══════════════════════════════════════════════════════════════════════════
    fraud_risk = min(sum(fraud_penalties.values()), 100)
    ev_condition_risk = min(sum(condition_penalties.values()), 100)
    overall_risk = min(round(0.60 * fraud_risk + 0.40 * ev_condition_risk), 100)

    band, color = _band(overall_risk)

    return RiskScore(
        fraud_risk=fraud_risk,
        ev_condition_risk=ev_condition_risk,
        overall_risk=overall_risk,
        band=band,
        band_color=color,
        flags=flags,
        fraud_penalties=fraud_penalties,
        condition_penalties=condition_penalties,
    )

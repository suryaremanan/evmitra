"""
VoltSage — services/used_ev/models.py
Shared dataclasses and Pydantic models for Used EV due diligence.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel



# ── Request / Response models ────────────────────────────────────────────────

class UsedEvRequest(BaseModel):
    listing_url: str
    country: str = "india"
    city: str = ""
    vin_hint: str = ""
    phone_hint: str = ""


# ── Agent result dataclasses ─────────────────────────────────────────────────

@dataclass
class ListingFacts:
    make: str = ""
    model: str = ""
    year: str = ""
    trim: str = ""
    odometer_km: Optional[int] = None      # plain integer km
    odometer_mi: Optional[int] = None      # original miles if applicable
    price: str = ""                        # as shown, e.g. "₹12,50,000"
    price_numeric: Optional[float] = None  # cleaned number
    seller_name: str = ""
    seller_phone: str = ""
    seller_location: str = ""
    vin: str = ""
    listed_date: str = ""
    description: str = ""
    photo_urls: list = field(default_factory=list)
    claimed_range_km: Optional[int] = None
    battery_kwh: Optional[float] = None
    listing_url: str = ""
    raw: dict = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class CrossCheckResult:
    duplicates: list = field(default_factory=list)    # [{url, platform, price, date, seller, note}]
    image_reuses: list = field(default_factory=list)  # [{page_title, source_url, match_type}]
    identity_flags: list = field(default_factory=list)
    identity_source_url: str = ""
    error: Optional[str] = None


@dataclass
class MarketData:
    median_price: Optional[float] = None
    low_price: Optional[float] = None
    high_price: Optional[float] = None
    avg_odometer_km: Optional[int] = None
    sample_count: int = 0
    listing_price: Optional[float] = None
    price_delta_pct: Optional[float] = None
    market_verdict: str = ""          # FAIR | BELOW_MARKET | SUSPICIOUSLY_LOW | ABOVE_MARKET
    comparables: list = field(default_factory=list)
    currency: str = "USD"
    source_urls: list = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class BatteryHealth:
    estimated_soh_pct: Optional[int] = None   # state of health 0–100%
    degradation_flag: bool = False
    warranty_remaining: str = ""
    recall_found: bool = False
    recall_details: str = ""
    dc_charge_limited: bool = False
    assessment: str = ""               # SHORT | FAIR | GOOD | EXCELLENT
    notes: list = field(default_factory=list)
    source_urls: list = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class EvEnrichment:
    spec_battery_kwh: Optional[float] = None
    spec_range_city_km: Optional[int] = None
    spec_range_highway_km: Optional[int] = None
    spec_dc_kw: Optional[float] = None
    warranty_months: Optional[int] = None
    known_issues: list = field(default_factory=list)   # from owner reviews
    owner_rating: Optional[float] = None
    source: str = "database"    # "database" | "live"
    error: Optional[str] = None


@dataclass
class RiskScore:
    fraud_risk: int = 0          # 0–100, from cross-check / price / identity
    ev_condition_risk: int = 0   # 0–100, from battery / odometer / warranty
    overall_risk: int = 0        # weighted combination
    band: str = ""               # LOW RISK | CAUTION | HIGH RISK | WALK AWAY
    band_color: str = ""         # green | yellow | orange | red
    flags: list = field(default_factory=list)
    fraud_penalties: dict = field(default_factory=dict)
    condition_penalties: dict = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────────────

def parse_numeric(val) -> Optional[float]:
    """Extract a positive float from any representation, or None."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if val > 0 else None
    cleaned = re.sub(r"[^\d.]", "", str(val))
    try:
        result = float(cleaned) if cleaned else None
        return result if result and result > 0 else None
    except ValueError:
        return None


def parse_odometer(raw) -> Optional[int]:
    """Convert any odometer string to a plain integer km, or None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw) if raw > 0 else None
    cleaned = re.sub(r"[^\d]", "", str(raw))
    if not cleaned:
        return None
    val = int(cleaned)
    return val if val > 0 else None



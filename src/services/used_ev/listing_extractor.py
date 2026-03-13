"""
VoltSage — services/used_ev/listing_extractor.py
Agent 1: Navigate to a used EV listing and extract all facts.
"""
from .agent_client import run_agent_async
from .models import ListingFacts, parse_numeric, parse_odometer

_GOAL = """\
You are visiting a used electric vehicle (EV) listing page. Extract every visible fact
about the vehicle and seller, then return them as a single JSON object.

REQUIRED JSON SHAPE (use exact keys — empty string or 0 for unknowns):
{{
  "make": "",              // brand, e.g. "Tata", "Tesla", "Hyundai"
  "model": "",             // model, e.g. "Nexon EV", "Model 3", "Kona Electric"
  "year": "",              // 4-digit string, e.g. "2021"
  "trim": "",              // trim/variant if shown, e.g. "Max", "Long Range"
  "odometer_km": 0,        // INTEGER km — strip commas; if shown in miles multiply by 1.609
  "price": "",             // as displayed, e.g. "₹12,50,000" or "$18,500"
  "seller_name": "",       // display name of the seller
  "seller_phone": "",      // phone exactly as shown, or ""
  "seller_location": "",   // city/region as shown, e.g. "Mumbai" or "Austin, TX"
  "vin": "",               // VIN if visible (click "Show VIN" if needed)
  "listed_date": "",       // posting date if shown
  "description": "",       // first 500 chars of the listing description
  "photo_urls": [],        // up to 5 full-size image URLs (.jpg/.png/.webp)
  "claimed_range_km": 0,   // seller-claimed range per charge in km (0 if not stated)
  "battery_kwh": 0.0       // battery capacity in kWh if stated (0 if not stated)
}}

Rules:
- odometer_km MUST be a plain integer — never a string with units
- claimed_range_km: only fill if the seller explicitly states range in the listing
- photo_urls: full-size images only, skip thumbnails and banners
- Never invent data; use "" or 0 for anything not visible
- If VIN is behind a reveal button — click it
{hints}\
"""


async def extract_listing(
    listing_url: str,
    vin_hint: str = "",
    phone_hint: str = "",
) -> ListingFacts:
    hints = ""
    if vin_hint:
        hints += f"\n- User provided VIN {vin_hint} — verify it matches the page."
    if phone_hint:
        hints += f"\n- User provided phone {phone_hint} — verify it appears on the page."

    result = await run_agent_async(
        url=listing_url,
        goal=_GOAL.format(hints=hints),
        label="Listing",
        profile="stealth",
        timeout=120,
    )

    if result.get("error"):
        return ListingFacts(listing_url=listing_url, error=result["error"])
    if not result:
        return ListingFacts(listing_url=listing_url, error="Agent returned no data")

    price_str = result.get("price", "") or ""
    price_numeric = parse_numeric(price_str)

    return ListingFacts(
        make=result.get("make", ""),
        model=result.get("model", ""),
        year=result.get("year", ""),
        trim=result.get("trim", ""),
        odometer_km=parse_odometer(result.get("odometer_km")),
        price=price_str,
        price_numeric=price_numeric,
        seller_name=result.get("seller_name", ""),
        seller_phone=result.get("seller_phone", "") or phone_hint,
        seller_location=result.get("seller_location", ""),
        vin=result.get("vin", "") or vin_hint,
        listed_date=result.get("listed_date", ""),
        description=result.get("description", ""),
        photo_urls=result.get("photo_urls", []),
        claimed_range_km=parse_odometer(result.get("claimed_range_km")),
        battery_kwh=parse_numeric(result.get("battery_kwh")),
        listing_url=listing_url,
        raw=result,
    )

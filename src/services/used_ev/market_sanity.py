"""
VoltSage — services/used_ev/market_sanity.py
Agent 2d: Compare listing price to market median for the same EV model & country.
Country-aware market sources.
"""
import statistics
from typing import Optional

from .agent_client import run_agent_async
from .models import ListingFacts, MarketData, parse_numeric

_VERY_LOW_THRESHOLD = -30.0
_LOW_THRESHOLD      = -10.0
_HIGH_THRESHOLD     =  20.0


def _market_sources_for_country(country: str) -> list[dict]:
    _SOURCES = {
        "india": [
            {"name": "Cars24",   "url": "https://www.cars24.com/",   "profile": "lite"},
            {"name": "Spinny",   "url": "https://www.spinny.com/",    "profile": "lite"},
            {"name": "CarDekho", "url": "https://www.cardekho.com/",  "profile": "lite"},
        ],
        "usa": [
            {"name": "CarGurus",   "url": "https://www.cargurus.com/",   "profile": "lite"},
            {"name": "AutoTrader", "url": "https://www.autotrader.com/", "profile": "lite"},
        ],
        "uk": [
            {"name": "AutoTrader UK", "url": "https://www.autotrader.co.uk/", "profile": "lite"},
            {"name": "eBay Motors",   "url": "https://www.ebay.co.uk/",       "profile": "lite"},
        ],
        "uae": [
            {"name": "dubizzle",  "url": "https://dubai.dubizzle.com/motors/used-cars/", "profile": "lite"},
            {"name": "YallaMotor","url": "https://www.yallamotor.com/used-cars/",         "profile": "lite"},
        ],
        "germany": [
            {"name": "Mobile.de",   "url": "https://www.mobile.de/",     "profile": "lite"},
            {"name": "AutoScout24", "url": "https://www.autoscout24.de/","profile": "lite"},
        ],
        "australia": [
            {"name": "CarsGuide", "url": "https://www.carsguide.com.au/", "profile": "lite"},
            {"name": "CarSales",  "url": "https://www.carsales.com.au/",  "profile": "lite"},
        ],
    }
    return _SOURCES.get(country, [
        {"name": "Google Market", "url": "https://www.google.com/", "profile": "lite"},
    ])


def _build_goal(make: str, model: str, year: str, location: str, country: str) -> str:
    search_term = f"{year} {make} {model}".strip()
    sources = _market_sources_for_country(country)
    source_names = ", ".join(s["name"] for s in sources)

    return f"""\
Research used EV market prices for: "{search_term}" near "{location}".

Search on: {source_names}

Steps:
1. Search each available marketplace for "{search_term}" listings in or near "{location}"
2. Collect prices and odometer readings from the first 8+ listings
3. Only include listings for the same year/model

CRITICAL RULES:
- ONLY report prices you ACTUALLY SEE on the page — never estimate or fabricate
- ALL price and odometer values MUST be plain numbers (no currency symbols, no commas, no units)
- Prices in local currency (INR, AED, GBP) — use as-is without converting
- Compute median_price, low_price, high_price from the prices you collected
- avg_odometer_km = average odometer in km (convert mi×1.609 if needed)
- sample_count = total number of listings found
- Include the listing URL for each comparable where available

Return ONLY this JSON:
{{
  "median_price": 1250000,
  "low_price": 950000,
  "high_price": 1600000,
  "avg_odometer_km": 42000,
  "sample_count": 8,
  "currency": "INR",
  "comparables": [
    {{
      "price": 1150000,
      "odometer_km": 38000,
      "year": "2021",
      "trim": "Max",
      "source": "Cars24",
      "url": "https://www.cars24.com/buy-used-tata-nexon-ev-..."
    }}
  ]
}}"""


def _currency_for_country(country: str) -> str:
    _MAP = {
        "india": "INR", "usa": "USD", "uk": "GBP",
        "germany": "EUR", "uae": "AED", "australia": "AUD",
        "france": "EUR", "norway": "NOK", "singapore": "SGD",
    }
    return _MAP.get(country, "USD")


async def check_market(
    facts: ListingFacts,
    country: str = "india",
) -> MarketData:
    make = facts.make or ""
    model = facts.model or ""
    year = facts.year or ""
    currency = _currency_for_country(country)

    if not make:
        return MarketData(error="Insufficient vehicle data to search market prices", currency=currency)

    location = facts.seller_location or country.title()
    sources = _market_sources_for_country(country)
    primary = sources[0]

    result = await run_agent_async(
        url=primary["url"],
        goal=_build_goal(make, model, year, location, country),
        label="Market",
        profile=primary.get("profile", "lite"),
        timeout=120,
    )

    if result.get("error") or not result:
        return MarketData(error=result.get("error", "No market data returned"), currency=currency)

    comparables = result.get("comparables", [])

    median_price = parse_numeric(result.get("median_price"))
    low_price    = parse_numeric(result.get("low_price"))
    high_price   = parse_numeric(result.get("high_price"))

    if comparables and not all([median_price, low_price, high_price]):
        prices = [parse_numeric(c.get("price")) for c in comparables]
        prices = [p for p in prices if p and p > 0]
        if prices:
            median_price = median_price or statistics.median(prices)
            low_price    = low_price    or min(prices)
            high_price   = high_price   or max(prices)

    avg_odometer_km: Optional[int] = None
    raw_avg = parse_numeric(result.get("avg_odometer_km"))
    if raw_avg and raw_avg > 0:
        avg_odometer_km = int(raw_avg)
    elif comparables:
        odos = [parse_numeric(c.get("odometer_km")) for c in comparables]
        odos = [o for o in odos if o and o > 0]
        if odos:
            avg_odometer_km = int(sum(odos) / len(odos))

    listing_price = facts.price_numeric
    price_delta_pct: Optional[float] = None
    market_verdict = "UNKNOWN"

    if listing_price and median_price and median_price > 0:
        price_delta_pct = round(
            ((listing_price - median_price) / median_price) * 100, 1
        )
        if price_delta_pct < _VERY_LOW_THRESHOLD:
            market_verdict = "SUSPICIOUSLY_LOW"
        elif price_delta_pct < _LOW_THRESHOLD:
            market_verdict = "BELOW_MARKET"
        elif price_delta_pct > _HIGH_THRESHOLD:
            market_verdict = "ABOVE_MARKET"
        else:
            market_verdict = "FAIR"

    currency = result.get("currency") or currency
    source_urls = [c["url"] for c in comparables if c.get("url", "").startswith("http")]

    return MarketData(
        median_price=median_price,
        low_price=low_price,
        high_price=high_price,
        avg_odometer_km=avg_odometer_km,
        sample_count=int(result.get("sample_count", len(comparables))),
        listing_price=listing_price,
        price_delta_pct=price_delta_pct,
        market_verdict=market_verdict,
        comparables=comparables[:6],
        currency=currency,
        source_urls=source_urls[:3],
    )

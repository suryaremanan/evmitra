"""
VoltSage — global_config.py
Country, currency, and charging network registry for all supported markets.
All charging network URLs are consumed by the TinyFish scraping engine.
"""

from typing import Optional

# ─────────────────────────────────────────────────────────
# CURRENCY REGISTRY
# ─────────────────────────────────────────────────────────

CURRENCIES: dict[str, dict] = {
    "USD": {"symbol": "$",  "name": "US Dollar",         "petrol_per_km": 0.14, "locale": "en-US"},
    "EUR": {"symbol": "€",  "name": "Euro",               "petrol_per_km": 0.16, "locale": "de-DE"},
    "GBP": {"symbol": "£",  "name": "British Pound",      "petrol_per_km": 0.18, "locale": "en-GB"},
    "AUD": {"symbol": "A$", "name": "Australian Dollar",  "petrol_per_km": 0.17, "locale": "en-AU"},
    "CAD": {"symbol": "C$", "name": "Canadian Dollar",    "petrol_per_km": 0.13, "locale": "en-CA"},
    "JPY": {"symbol": "¥",  "name": "Japanese Yen",       "petrol_per_km": 22.0, "locale": "ja-JP"},
    "INR": {"symbol": "₹",  "name": "Indian Rupee",       "petrol_per_km": 7.0,  "locale": "en-IN"},
    "NOK": {"symbol": "kr", "name": "Norwegian Krone",    "petrol_per_km": 1.8,  "locale": "nb-NO"},
    "SEK": {"symbol": "kr", "name": "Swedish Krona",      "petrol_per_km": 1.9,  "locale": "sv-SE"},
    "CNY": {"symbol": "¥",  "name": "Chinese Yuan",       "petrol_per_km": 0.95, "locale": "zh-CN"},
    "SGD": {"symbol": "S$", "name": "Singapore Dollar",   "petrol_per_km": 0.19, "locale": "en-SG"},
    "AED": {"symbol": "د.إ","name": "UAE Dirham",         "petrol_per_km": 0.08, "locale": "ar-AE"},
    "KRW": {"symbol": "₩",  "name": "South Korean Won",   "petrol_per_km": 180,  "locale": "ko-KR"},
    "NZD": {"symbol": "NZ$","name": "New Zealand Dollar", "petrol_per_km": 0.20, "locale": "en-NZ"},
    "CHF": {"symbol": "Fr", "name": "Swiss Franc",        "petrol_per_km": 0.22, "locale": "de-CH"},
}


# ─────────────────────────────────────────────────────────
# CHARGING NETWORK REGISTRY
# key = country code, value = list of network dicts:
#   { name, url_template (with {city} placeholder), profile }
# ─────────────────────────────────────────────────────────

CHARGING_NETWORKS: dict[str, list[dict]] = {
    "US": [
        {"name": "ChargePoint",        "url_template": "https://www.chargepoint.com/find#/filter%5Bcommunity%5D=false&filter%5Bnetwork_id%5D=1&search={city}", "profile": "lite"},
        {"name": "Electrify America",  "url_template": "https://www.electrifyamerica.com/locate-charger/?filters=LocationDetails&filterValues={city}", "profile": "lite"},
        {"name": "PlugShare",          "url_template": "https://www.plugshare.com/location/{city}", "profile": "stealth"},
    ],
    "GB": [
        {"name": "Zap-Map",            "url_template": "https://www.zap-map.com/find/?postcode={city}", "profile": "stealth"},
        {"name": "Pod Point",          "url_template": "https://pod-point.com/find-a-charge-point?location={city}", "profile": "lite"},
        {"name": "BP Pulse",           "url_template": "https://www.bppulse.co.uk/find-a-charge-point?location={city}", "profile": "lite"},
    ],
    "DE": [
        {"name": "IONITY",             "url_template": "https://ionity.eu/de/find-hpc.html?location={city}", "profile": "lite"},
        {"name": "EnBW",               "url_template": "https://www.enbw.com/elektromobilitaet/laden/e-mobility-finder/?city={city}", "profile": "lite"},
        {"name": "Charge&Drive",       "url_template": "https://chargeanddrive.com/charging-stations?city={city}", "profile": "lite"},
    ],
    "FR": [
        {"name": "IONITY",             "url_template": "https://ionity.eu/fr/find-hpc.html?location={city}", "profile": "lite"},
        {"name": "Freshmile",          "url_template": "https://freshmile.com/stations?city={city}", "profile": "lite"},
        {"name": "TotalEnergies",      "url_template": "https://charge.totalenergies.com/en/find-a-charging-station?location={city}", "profile": "lite"},
    ],
    "NO": [
        {"name": "Recharge",           "url_template": "https://rechargeinfra.com/find-charger?location={city}", "profile": "lite"},
        {"name": "IONITY",             "url_template": "https://ionity.eu/no/find-hpc.html?location={city}", "profile": "lite"},
        {"name": "PlugShare",          "url_template": "https://www.plugshare.com/location/{city}", "profile": "stealth"},
    ],
    "AU": [
        {"name": "Chargefox",          "url_template": "https://www.chargefox.com/chargers/?lat=-33.87&lng=151.21&radius=50&suburb={city}", "profile": "stealth"},
        {"name": "ChargePoint AU",     "url_template": "https://www.chargepoint.com/au/find/#/filter%5Bcountry%5D=AU&search={city}", "profile": "lite"},
        {"name": "NRMA Electric",      "url_template": "https://www.mynrma.com.au/electric-vehicles/charging/find-a-charger?location={city}", "profile": "lite"},
    ],
    "JP": [
        {"name": "CHAdeMO",            "url_template": "https://www.chademo.com/ev-charging/quick-charger-map/?city={city}", "profile": "lite"},
        {"name": "NissanConnect",      "url_template": "https://www.nissan.co.jp/SUPPORT/EVMAP/?city={city}", "profile": "stealth"},
        {"name": "PlugShare",          "url_template": "https://www.plugshare.com/location/{city}", "profile": "stealth"},
    ],
    "IN": [
        {"name": "PlugShare India",    "url_template": "https://www.plugshare.com/location/{city}+India", "profile": "stealth"},
        {"name": "Statiq",             "url_template": "https://www.statiq.in/charging-stations/{city_lower}", "profile": "stealth"},
        {"name": "ChargeZone",         "url_template": "https://chargezone.in/charging-stations/{city_lower}", "profile": "lite"},
    ],
    "CA": [
        {"name": "ChargePoint CA",     "url_template": "https://www.chargepoint.com/ca/find/#/filter%5Bcountry%5D=CA&search={city}", "profile": "lite"},
        {"name": "FLO",                "url_template": "https://onflo.com/en/charging-stations/?city={city}", "profile": "lite"},
        {"name": "Circuit ÉlectriQC",  "url_template": "https://www.tesla.com/en_CA/find-us/supercharger?filters=supercharger&city={city}", "profile": "lite"},
    ],
    "CN": [
        {"name": "State Grid",         "url_template": "https://www.plugshare.com/location/{city}+China", "profile": "stealth"},
        {"name": "BYD Charge",         "url_template": "https://www.plugshare.com/location/{city}+China", "profile": "stealth"},
    ],
    "SG": [
        {"name": "SP Mobility",        "url_template": "https://www.spmobility.com.sg/ev-charging-stations?location={city}", "profile": "lite"},
        {"name": "PlugShare SG",       "url_template": "https://www.plugshare.com/location/{city}+Singapore", "profile": "stealth"},
    ],
    "AE": [
        {"name": "DEWA EV Green",      "url_template": "https://www.dewa.gov.ae/en/consumer/innovation/electric-vehicles/ev-green-charger", "profile": "lite"},
        {"name": "PlugShare AE",       "url_template": "https://www.plugshare.com/location/{city}+UAE", "profile": "stealth"},
    ],
    "KR": [
        {"name": "KEPCO EV",           "url_template": "https://www.plugshare.com/location/{city}+Korea", "profile": "stealth"},
        {"name": "Hyundai E-pit",      "url_template": "https://www.plugshare.com/location/{city}+Korea", "profile": "stealth"},
    ],
    "NZ": [
        {"name": "ChargeNet NZ",       "url_template": "https://www.chargenet.nz/map/?location={city}", "profile": "lite"},
        {"name": "PlugShare NZ",       "url_template": "https://www.plugshare.com/location/{city}+New+Zealand", "profile": "stealth"},
    ],
    "CH": [
        {"name": "EnPos CH",           "url_template": "https://www.plugshare.com/location/{city}+Switzerland", "profile": "stealth"},
        {"name": "IONITY CH",          "url_template": "https://ionity.eu/de/find-hpc.html?location={city}+Switzerland", "profile": "lite"},
    ],
    "SE": [
        {"name": "IONITY SE",          "url_template": "https://ionity.eu/sv/find-hpc.html?location={city}", "profile": "lite"},
        {"name": "Vattenfall InCharge","url_template": "https://incharge.vattenfall.se/ladda/hitta-en-laddstation/?city={city}", "profile": "lite"},
    ],
}

# ─────────────────────────────────────────────────────────
# COUNTRY REGISTRY — supported markets
# ─────────────────────────────────────────────────────────

COUNTRIES: dict[str, dict] = {
    "US": {
        "name": "United States", "flag": "🇺🇸", "currency": "USD",
        "cities": ["Los Angeles", "New York", "San Francisco", "Chicago", "Austin",
                   "Seattle", "Boston", "Miami", "Denver", "Portland",
                   "Phoenix", "Atlanta", "Dallas", "San Diego", "Nashville"],
        "ev_review_url": "https://electrek.co",
        "review_search_url": "https://electrek.co/search/?search={model}+review+owner",
        "region_label": "State",
    },
    "GB": {
        "name": "United Kingdom", "flag": "🇬🇧", "currency": "GBP",
        "cities": ["London", "Manchester", "Birmingham", "Edinburgh", "Bristol",
                   "Leeds", "Liverpool", "Glasgow", "Sheffield", "Cardiff",
                   "Newcastle", "Nottingham", "Brighton", "Oxford", "Cambridge"],
        "ev_review_url": "https://www.autoexpress.co.uk",
        "review_search_url": "https://www.autoexpress.co.uk/search/q/{model}+long+term+test",
        "region_label": "Region",
    },
    "DE": {
        "name": "Germany", "flag": "🇩🇪", "currency": "EUR",
        "cities": ["Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne",
                   "Stuttgart", "Düsseldorf", "Leipzig", "Hanover", "Nuremberg",
                   "Dresden", "Bremen", "Dortmund", "Essen", "Bochum"],
        "ev_review_url": "https://www.adac.de",
        "review_search_url": "https://www.adac.de/suche/?query={model}+Erfahrungsbericht",
        "region_label": "State",
    },
    "FR": {
        "name": "France", "flag": "🇫🇷", "currency": "EUR",
        "cities": ["Paris", "Lyon", "Marseille", "Bordeaux", "Toulouse",
                   "Nice", "Nantes", "Strasbourg", "Montpellier", "Lille",
                   "Rennes", "Reims", "Toulon", "Grenoble", "Dijon"],
        "ev_review_url": "https://www.autoplus.fr",
        "review_search_url": "https://www.autoplus.fr/recherche?q={model}+essai+proprietaires",
        "region_label": "Region",
    },
    "NO": {
        "name": "Norway", "flag": "🇳🇴", "currency": "NOK",
        "cities": ["Oslo", "Bergen", "Trondheim", "Stavanger", "Kristiansand",
                   "Drammen", "Fredrikstad", "Tromsø", "Sandnes", "Skien"],
        "ev_review_url": "https://elbil.no",
        "review_search_url": "https://elbil.no/sok/?q={model}",
        "region_label": "Region",
    },
    "AU": {
        "name": "Australia", "flag": "🇦🇺", "currency": "AUD",
        "cities": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide",
                   "Canberra", "Hobart", "Darwin", "Gold Coast", "Newcastle",
                   "Wollongong", "Cairns", "Toowoomba", "Ballarat"],
        "ev_review_url": "https://www.drive.com.au",
        "review_search_url": "https://www.drive.com.au/news/search/?q={model}+review+owners",
        "region_label": "State",
    },
    "JP": {
        "name": "Japan", "flag": "🇯🇵", "currency": "JPY",
        "cities": ["Tokyo", "Osaka", "Kyoto", "Yokohama", "Nagoya",
                   "Sapporo", "Fukuoka", "Kobe", "Sendai", "Hiroshima",
                   "Nara", "Kawasaki", "Chiba", "Saitama"],
        "ev_review_url": "https://motor-fan.jp",
        "review_search_url": "https://motor-fan.jp/search/{model}",
        "region_label": "Prefecture",
    },
    "IN": {
        "name": "India", "flag": "🇮🇳", "currency": "INR",
        "cities": ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
                   "Pune", "Ahmedabad", "Kolkata", "Jaipur", "Nagpur",
                   "Chandigarh", "Kochi", "Lucknow", "Indore", "Bhopal"],
        "ev_review_url": "https://www.team-bhp.com",
        "review_search_url": "https://www.team-bhp.com/forum/search.php?searchid=0&q={model}+review+ownership&submit=Search",
        "region_label": "State",
    },
    "CA": {
        "name": "Canada", "flag": "🇨🇦", "currency": "CAD",
        "cities": ["Toronto", "Vancouver", "Montreal", "Calgary", "Ottawa",
                   "Edmonton", "Winnipeg", "Quebec City", "Hamilton", "Halifax",
                   "London", "Saskatoon", "Regina", "Victoria"],
        "ev_review_url": "https://driving.ca",
        "review_search_url": "https://driving.ca/search/q/{model}+review",
        "region_label": "Province",
    },
    "CN": {
        "name": "China", "flag": "🇨🇳", "currency": "CNY",
        "cities": ["Beijing", "Shanghai", "Shenzhen", "Guangzhou", "Chengdu",
                   "Hangzhou", "Wuhan", "Nanjing", "Xi'an", "Tianjin",
                   "Chongqing", "Suzhou", "Dongguan"],
        "ev_review_url": "https://www.autohome.com.cn",
        "review_search_url": "https://www.autohome.com.cn/car/search/?keywords={model}",
        "region_label": "Province",
    },
    "SG": {
        "name": "Singapore", "flag": "🇸🇬", "currency": "SGD",
        "cities": ["Singapore Central", "Jurong", "Tampines", "Woodlands",
                   "Bedok", "Bishan", "Clementi", "Toa Payoh"],
        "ev_review_url": "https://www.sgcarmart.com",
        "review_search_url": "https://www.sgcarmart.com/used_cars/search.php?QS={model}",
        "region_label": "District",
    },
    "AE": {
        "name": "UAE", "flag": "🇦🇪", "currency": "AED",
        "cities": ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah",
                   "Fujairah", "Umm Al Quwain"],
        "ev_review_url": "https://www.dubicars.com",
        "review_search_url": "https://www.dubicars.com/search/?q={model}",
        "region_label": "Emirate",
    },
    "KR": {
        "name": "South Korea", "flag": "🇰🇷", "currency": "KRW",
        "cities": ["Seoul", "Busan", "Incheon", "Daegu", "Daejeon",
                   "Gwangju", "Suwon", "Ulsan", "Changwon", "Goyang"],
        "ev_review_url": "https://www.bobaedream.co.kr",
        "review_search_url": "https://www.bobaedream.co.kr/search?keyword={model}",
        "region_label": "Province",
    },
    "NZ": {
        "name": "New Zealand", "flag": "🇳🇿", "currency": "NZD",
        "cities": ["Auckland", "Wellington", "Christchurch", "Hamilton",
                   "Tauranga", "Dunedin", "Napier", "Palmerston North"],
        "ev_review_url": "https://www.stuff.co.nz",
        "review_search_url": "https://www.stuff.co.nz/search?q={model}+electric+review",
        "region_label": "Region",
    },
    "SE": {
        "name": "Sweden", "flag": "🇸🇪", "currency": "SEK",
        "cities": ["Stockholm", "Gothenburg", "Malmö", "Uppsala", "Linköping",
                   "Örebro", "Västerås", "Helsingborg", "Norrköping", "Jönköping"],
        "ev_review_url": "https://www.automotorsport.se",
        "review_search_url": "https://www.automotorsport.se/sok/?q={model}",
        "region_label": "County",
    },
    "CH": {
        "name": "Switzerland", "flag": "🇨🇭", "currency": "CHF",
        "cities": ["Zurich", "Geneva", "Basel", "Bern", "Lausanne",
                   "Winterthur", "Lucerne", "St. Gallen", "Lugano", "Biel"],
        "ev_review_url": "https://www.auto-illustrierte.ch",
        "review_search_url": "https://www.auto-illustrierte.ch/suche?q={model}",
        "region_label": "Canton",
    },
}


# ─────────────────────────────────────────────────────────
# GOVERNMENT INCENTIVE TEMPLATES
# (generic — TinyFish scrapes the live amounts at query time)
# ─────────────────────────────────────────────────────────

INCENTIVE_TEMPLATES: dict[str, dict] = {
    "US": {
        "headline": "Federal EV Tax Credit",
        "detail": "Up to $7,500 federal tax credit (IRA 2022) + state-level rebates",
        "source": "IRS Form 8936 / AFDC",
        "live_search_url": "https://afdc.energy.gov/laws/electric-vehicles?state={region}",
    },
    "GB": {
        "headline": "UK Plug-in Vehicle Grant (ended 2022)",
        "detail": "No federal grant currently. Scotland has interest-free EV loans. Check local authority.",
        "source": "UK Office for Zero Emission Vehicles",
        "live_search_url": "https://www.gov.uk/electric-vehicle-grants",
    },
    "DE": {
        "headline": "Umweltbonus (ended 2023)",
        "detail": "Germany's Umweltbonus subsidy ended Dec 2023. KfW EV financing available.",
        "source": "Bundesamt für Wirtschaft und Ausfuhrkontrolle",
        "live_search_url": "https://www.bafa.de/DE/Energie/Elektromobilitaet/elektromobilitaet_node.html",
    },
    "FR": {
        "headline": "Bonus Écologique",
        "detail": "Up to €5,000 bonus for new EVs meeting criteria. Leasing supplement for low-income.",
        "source": "Service Public France",
        "live_search_url": "https://www.service-public.fr/particuliers/vosdroits/F34014",
    },
    "NO": {
        "headline": "Norway EV Incentives",
        "detail": "Low VAT, reduced tolls, free/discounted ferries, company car tax benefits. World-leading.",
        "source": "Norsk elbilforening",
        "live_search_url": "https://elbil.no/elbilstatistikk/",
    },
    "AU": {
        "headline": "Australia EV Fringe Benefits Tax Exemption",
        "detail": "FBT exemption for EVs under luxury car tax threshold. State-specific stamp duty waivers.",
        "source": "Australian Tax Office / State Revenue Offices",
        "live_search_url": "https://www.ato.gov.au/businesses-and-organisations/hiring-and-paying-your-workers/fringe-benefits-tax",
    },
    "JP": {
        "headline": "CEV Subsidy (Next Generation Vehicle)",
        "detail": "Up to ¥850,000 subsidy for qualifying EVs. Check CEV subsidy database.",
        "source": "METI / CEV Subsidy",
        "live_search_url": "https://www.cev-pc.or.jp/hojo/cej.html",
    },
    "IN": {
        "headline": "FAME III (Under Discussion) + State Subsidies",
        "detail": "FAME II ended March 2024. State-level road tax / registration exemptions active.",
        "source": "Ministry of Heavy Industries / State EV Policy",
        "live_search_url": "https://fame2.heavyindustries.gov.in/",
    },
    "CA": {
        "headline": "Canada iZEV Program",
        "detail": "Up to C$5,000 for eligible ZEVs. Province-specific top-ups (Quebec up to C$7,000).",
        "source": "Transport Canada",
        "live_search_url": "https://tc.canada.ca/en/road-transportation/innovative-technologies/zero-emission-vehicles",
    },
    "CN": {
        "headline": "China NEV Subsidies & Tax Exemptions",
        "detail": "Purchase tax exemption for NEVs. Local government subsidies vary by city.",
        "source": "Ministry of Finance China",
        "live_search_url": "https://www.mof.gov.cn",
    },
    "SG": {
        "headline": "Singapore EV Early Adoption Incentive",
        "detail": "EEAI rebate off ARF for BEVs. VES rebates based on emissions band.",
        "source": "Land Transport Authority Singapore",
        "live_search_url": "https://www.lta.gov.sg/content/ltagov/en/getting_around/vehicles/vehicle_registration/electric_vehicle.html",
    },
    "AE": {
        "headline": "UAE EV Incentives",
        "detail": "Free salik/toll passes, discounted parking, DEWA free charging at public stations.",
        "source": "Dubai RTA / DEWA",
        "live_search_url": "https://www.rta.ae",
    },
    "KR": {
        "headline": "South Korea EV Subsidy",
        "detail": "Up to KRW 6.8M national subsidy + local government top-up. Varies by model.",
        "source": "Korean Ministry of Environment",
        "live_search_url": "https://www.ev.or.kr",
    },
    "NZ": {
        "headline": "NZ Clean Car Discount (ended 2023)",
        "detail": "Clean Car Discount ended December 2023. ACC discount and road user charge exemption remain.",
        "source": "Waka Kotahi NZ Transport Agency",
        "live_search_url": "https://www.nzta.govt.nz/vehicles/electric-vehicles/",
    },
    "SE": {
        "headline": "Sweden Klimatbonus",
        "detail": "Klimatbonus (green bonus) was abolished Jan 2023. VAT exemption for company EVs remains.",
        "source": "Transportstyrelsen",
        "live_search_url": "https://www.transportstyrelsen.se",
    },
    "CH": {
        "headline": "Switzerland Cantonal EV Incentives",
        "detail": "No federal subsidy. Cantons offer varying rebates (Geneva: CHF 3,000). Check locally.",
        "source": "Bundesamt für Energie",
        "live_search_url": "https://www.bfe.admin.ch/bfe/de/home/effizienz/mobilitaet/elektromobilitaet.html",
    },
}


def get_country(country_code: str) -> dict:
    """Return country config, falling back to US."""
    return COUNTRIES.get(country_code.upper(), COUNTRIES["US"])


def get_incentives(country_code: str) -> dict:
    """Return incentive template for a country."""
    return INCENTIVE_TEMPLATES.get(country_code.upper(), {
        "headline": "Government EV Incentives",
        "detail": "Check your local government website for current EV purchase incentives and tax credits.",
        "source": "Local Government EV Policy",
        "live_search_url": "",
    })


def get_currency(currency_code: str) -> dict:
    """Return currency config, falling back to USD."""
    return CURRENCIES.get(currency_code.upper(), CURRENCIES["USD"])


def get_charging_networks(country_code: str) -> list[dict]:
    """Return charging network sources for a country, falling back to PlugShare global."""
    networks = CHARGING_NETWORKS.get(country_code.upper(), [])
    if not networks:
        # Global fallback: PlugShare works everywhere
        networks = [
            {"name": "PlugShare", "url_template": "https://www.plugshare.com/location/{city}", "profile": "stealth"},
        ]
    return networks

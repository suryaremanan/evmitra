"""
EV Mitra — car_profiles.py
Single source of truth for all supported EV models.
Replaces every hardcoded Nexon constant in synthesis.py / backend.py.

Range figures are from Team-BHP owner reports, not manufacturer claims.
Prices are ex-showroom approximations — verify with dealer.
"""

CAR_PROFILES: dict[str, dict] = {
    "Tata Nexon EV Max": {
        "real_range_city_km": 180,      # Team-BHP confirmed (AC on)
        "real_range_highway_km": 230,   # at 100kmph
        "worst_case_km": 120,
        "battery_kwh": 40.5,
        "dc_fast_charge_kw": 50,
        "full_charge_min_dc": 57,       # 10→80% at 50kW
        "ex_showroom_inr": 2000000,
        "running_cost_per_km_inr": 1.4,
        "manufacturer_range_claim_km": 312,
        "segment": "compact SUV",
        "teambhp_search": "Nexon EV Max ownership review",
        "markets": ["india"],
    },
    "Tata Nexon EV": {
        "real_range_city_km": 150,
        "real_range_highway_km": 190,
        "worst_case_km": 100,
        "battery_kwh": 30.2,
        "dc_fast_charge_kw": 25,
        "full_charge_min_dc": 60,
        "ex_showroom_inr": 1450000,
        "running_cost_per_km_inr": 1.2,
        "manufacturer_range_claim_km": 250,
        "segment": "compact SUV",
        "teambhp_search": "Nexon EV ownership review India",
        "markets": ["india"],
    },
    "Tata Tiago EV": {
        "real_range_city_km": 200,
        "real_range_highway_km": 240,
        "worst_case_km": 150,
        "battery_kwh": 24.0,
        "dc_fast_charge_kw": 25,
        "full_charge_min_dc": 58,
        "ex_showroom_inr": 850000,
        "running_cost_per_km_inr": 1.0,
        "manufacturer_range_claim_km": 315,
        "segment": "hatchback",
        "teambhp_search": "Tata Tiago EV ownership review",
        "markets": ["india"],
    },
    "MG ZS EV": {
        "real_range_city_km": 280,
        "real_range_highway_km": 330,
        "worst_case_km": 210,
        "battery_kwh": 50.3,
        "dc_fast_charge_kw": 76,
        "full_charge_min_dc": 40,
        "ex_showroom_inr": 2200000,
        "running_cost_per_km_inr": 1.3,
        "manufacturer_range_claim_km": 461,
        "segment": "mid-size SUV",
        "teambhp_search": "MG ZS EV ownership review India",
        "markets": ["global"],
    },
    "MG Windsor EV": {
        "real_range_city_km": 270,
        "real_range_highway_km": 320,
        "worst_case_km": 200,
        "battery_kwh": 38.0,
        "dc_fast_charge_kw": 40,
        "full_charge_min_dc": 75,
        "ex_showroom_inr": 1399000,
        "running_cost_per_km_inr": 1.1,
        "manufacturer_range_claim_km": 332,
        "segment": "crossover",
        "teambhp_search": "MG Windsor EV ownership review",
        "markets": ["india"],
    },
    "Hyundai Ioniq 5": {
        "real_range_city_km": 380,
        "real_range_highway_km": 430,
        "worst_case_km": 300,
        "battery_kwh": 72.6,
        "dc_fast_charge_kw": 220,
        "full_charge_min_dc": 18,       # 10→80% at 220kW
        "ex_showroom_inr": 4600000,
        "running_cost_per_km_inr": 1.5,
        "manufacturer_range_claim_km": 631,
        "segment": "premium crossover",
        "teambhp_search": "Hyundai Ioniq 5 ownership India review",
        "markets": ["global"],
    },
    "Hyundai Creta Electric": {
        "real_range_city_km": 400,
        "real_range_highway_km": 460,
        "worst_case_km": 320,
        "battery_kwh": 51.4,
        "dc_fast_charge_kw": 50,
        "full_charge_min_dc": 58,
        "ex_showroom_inr": 1700000,
        "running_cost_per_km_inr": 0.95,
        "manufacturer_range_claim_km": 473,
        "segment": "compact SUV",
        "teambhp_search": "Hyundai Creta Electric ownership India",
        "markets": ["india"],
    },
    "Kia EV6": {
        "real_range_city_km": 350,
        "real_range_highway_km": 400,
        "worst_case_km": 270,
        "battery_kwh": 77.4,
        "dc_fast_charge_kw": 240,
        "full_charge_min_dc": 18,
        "ex_showroom_inr": 6095000,
        "running_cost_per_km_inr": 1.6,
        "manufacturer_range_claim_km": 528,
        "segment": "premium crossover",
        "teambhp_search": "Kia EV6 ownership review India",
        "markets": ["global"],
    },
    "BYD Atto 3": {
        "real_range_city_km": 360,
        "real_range_highway_km": 400,
        "worst_case_km": 280,
        "battery_kwh": 60.48,
        "dc_fast_charge_kw": 70,
        "full_charge_min_dc": 50,
        "ex_showroom_inr": 3399000,
        "running_cost_per_km_inr": 1.3,
        "manufacturer_range_claim_km": 521,
        "segment": "mid-size SUV",
        "teambhp_search": "BYD Atto 3 ownership review India",
        "markets": ["global"],
    },
    "Mahindra BE 6": {
        "real_range_city_km": 450,
        "real_range_highway_km": 500,
        "worst_case_km": 370,
        "battery_kwh": 79.0,
        "dc_fast_charge_kw": 175,
        "full_charge_min_dc": 20,       # 20→80% at 175kW
        "ex_showroom_inr": 2145000,
        "running_cost_per_km_inr": 1.2,
        "manufacturer_range_claim_km": 682,
        "segment": "electric SUV",
        "teambhp_search": "Mahindra BE 6 ownership review",
        "markets": ["india"],
    },
}

# Ordered list for dropdown menus
CAR_MODEL_LIST = list(CAR_PROFILES.keys())


def get_profile(car_model: str) -> dict:
    """Return car profile, falling back to Nexon EV Max if unknown."""
    return CAR_PROFILES.get(car_model, CAR_PROFILES["Tata Nexon EV Max"])


def get_models_for_country(country: str) -> list[str]:
    """Return car models available for a given country.
    India gets all models; all other markets get only 'global' models.
    """
    if country.lower() == "india":
        return CAR_MODEL_LIST
    return [name for name, p in CAR_PROFILES.items() if "global" in p.get("markets", [])]

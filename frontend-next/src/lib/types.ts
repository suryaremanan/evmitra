// VoltSage — global TypeScript interfaces

export interface Country {
    code: string
    name: string
    flag: string
    currency: string
    currency_symbol: string
    cities: string[]
    region_label: string
}

export interface EvModel {
    name: string
    brand: string
    segment: string
    real_range_city_km: number
    real_range_highway_km?: number
    battery_kwh: number
    dc_fast_charge_kw: number
    base_price_usd: number
    source?: 'database' | 'live'
}

export interface AnxietyScores {
    daily_score: number
    occasional_score: number
    daily_rationale: string
    occasional_rationale: string
    total_stations: number
    fast_dc_chargers: number
    high_power_chargers_50kw_plus: number
    real_range_used_km: number
    daily_km: number
    occasional_km: number
    confidence: 'high' | 'medium' | 'low'
}

export interface ChargerStation {
    name: string
    address: string
    connector_types: string[]
    power_kw: number
    status: string
}

export interface VehicleDetails {
    price_formatted: string | null
    battery_kwh: number
    dc_fast_charge_kw: number
    is_fast_charging: boolean
    charger_type: string | null
    battery_warranty: string | null
    iot_map_available: boolean | null
    showrooms: { name: string; address: string }[]
    distributors: { name: string; address: string }[]
}

export interface VerdictResult {
    country: string
    city: string
    car: string
    currency: string
    currency_symbol: string
    daily_km: number
    occasional_km: number
    scores: AnxietyScores
    stations: ChargerStation[]
    verdict: string
    data_freshness: {
        chargers: { source_type: string; fetched_at: string | null }
        owner_reviews: { source_type: string; fetched_at: string | null }
    }
    vehicle_details: VehicleDetails
    incentives: { headline: string; source: string }
    sources_used: string[]
}

export type SseEventType =
    | 'SCRAPING_CHARGERS'
    | 'CHARGERS_DONE'
    | 'SCRAPING_OWNERS'
    | 'OWNERS_DONE'
    | 'SCRAPING_SPECS'
    | 'SPECS_DONE'
    | 'SCORING'
    | 'LLM'
    | 'COMPLETE'
    | 'ERROR'

export interface SseEvent {
    type: SseEventType
    message?: string
    data?: VerdictResult
}

export interface FormState {
    country: string
    city: string
    carModel: string
    dailyKm: number
    occasionalKm: number
    hasHomeCharging: boolean
    currency: string
}

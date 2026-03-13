// VoltSage — Used EV Due Diligence TypeScript types

export interface UsedEvRequest {
    listing_url: string
    country: string
    city?: string
    vin_hint?: string
    phone_hint?: string
}

export interface VehicleFacts {
    make: string
    model: string
    year: string
    trim: string
    odometer_km: number | null
    asking_price: string
    seller_name: string
    seller_phone: string
    seller_location: string
    vin: string
    listed_date: string
    listing_url: string
    claimed_range_km: number | null
}

export interface EvSpecs {
    spec_battery_kwh: number | null
    spec_range_city_km: number | null
    spec_range_highway_km: number | null
    spec_dc_kw: number | null
    warranty_months: number | null
    known_issues: string[]
    source: 'database' | 'live'
}

export interface BatteryAssessment {
    estimated_soh_pct: number | null
    degradation_flag: boolean
    warranty_remaining: string
    recall_found: boolean
    recall_details: string
    dc_charge_limited: boolean
    assessment: 'EXCELLENT' | 'GOOD' | 'FAIR' | 'POOR' | 'UNKNOWN'
    notes: string[]
    source_urls: string[]
}

export interface Comparable {
    price: number
    odometer_km: number
    year: string
    trim: string
    source: string
    url?: string
}

export interface MarketComparison {
    median_market_price: number | null
    low_price: number | null
    high_price: number | null
    listing_price: number | null
    price_delta_pct: number | null
    market_verdict: 'FAIR' | 'BELOW_MARKET' | 'SUSPICIOUSLY_LOW' | 'ABOVE_MARKET' | 'UNKNOWN'
    avg_odometer_km: number | null
    sample_count: number
    currency: string
    comparables: Comparable[]
    source_urls: string[]
}

export interface DuplicateListing {
    platform: string
    url: string
    price?: string
    date?: string
    seller?: string
    note?: string
}

export interface PhotoReuse {
    page_title: string
    source_url: string
    match_type: 'exact' | 'similar'
}

export interface Evidence {
    duplicate_listings: DuplicateListing[]
    photo_reuse: PhotoReuse[]
    identity_flags: string[]
    identity_source_url?: string
}

export interface InvestigationTiming {
    elapsed_seconds: number
    agents_run: number
    parallel_agents: number
}

export interface UsedEvReport {
    generated_at: string
    country: string
    investigation_timing: InvestigationTiming
    fraud_risk: number
    ev_condition_risk: number
    overall_risk: number
    risk_band: 'LOW RISK' | 'CAUTION' | 'HIGH RISK' | 'WALK AWAY'
    risk_band_color: 'green' | 'yellow' | 'orange' | 'red'
    recommendation: {
        action: string
        detail: string
        icon: string
    }
    vehicle_facts: VehicleFacts
    ev_specs: EvSpecs
    battery_assessment: BatteryAssessment
    market_comparison: MarketComparison
    red_flags: string[]
    questions_to_ask: string[]
    evidence: Evidence
    penalty_breakdown: {
        fraud: Record<string, number>
        condition: Record<string, number>
    }
}

export type UsedEvEventType =
    | 'STAGE'
    | 'PROGRESS'
    | 'AGENT_COMPLETE'
    | 'WARNING'
    | 'COMPLETE'
    | 'ERROR'

export interface UsedEvSseEvent {
    type: UsedEvEventType
    stage?: number
    agent?: string
    message?: string
    report?: UsedEvReport
    elapsed_seconds?: number
}

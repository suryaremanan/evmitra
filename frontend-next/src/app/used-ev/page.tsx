'use client'

import { useState, useEffect, useCallback } from 'react'
import {
    Search, Globe2, AlertTriangle, CheckCircle2, XCircle,
    Loader2, Battery, ShieldAlert, TrendingDown, ChevronRight,
    ExternalLink, Zap, Clock, Users, Car,
} from 'lucide-react'
import Link from 'next/link'
import { useUsedEvStream } from '@/hooks/useUsedEvStream'
import type { UsedEvReport, BatteryAssessment } from '@/lib/used-ev-types'

// ── Constants ────────────────────────────────────────────────────────────────

const COUNTRIES = [
    { code: 'india',     label: 'India',         flag: '🇮🇳' },
    { code: 'usa',       label: 'United States',  flag: '🇺🇸' },
    { code: 'uk',        label: 'United Kingdom', flag: '🇬🇧' },
    { code: 'germany',   label: 'Germany',        flag: '🇩🇪' },
    { code: 'uae',       label: 'UAE',            flag: '🇦🇪' },
    { code: 'australia', label: 'Australia',      flag: '🇦🇺' },
    { code: 'canada',    label: 'Canada',         flag: '🇨🇦' },
    { code: 'france',    label: 'France',         flag: '🇫🇷' },
    { code: 'norway',    label: 'Norway',         flag: '🇳🇴' },
    { code: 'singapore', label: 'Singapore',      flag: '🇸🇬' },
]

const BAND_CONFIG = {
    'LOW RISK':  { bg: '#0d1f14', border: '#1a4428', text: '#22c55e', label: 'LOW RISK' },
    'CAUTION':   { bg: '#1a1506', border: '#44380a', text: '#facc15', label: 'CAUTION' },
    'HIGH RISK': { bg: '#1a0e06', border: '#7c2d12', text: '#f97316', label: 'HIGH RISK' },
    'WALK AWAY': { bg: '#1a0608', border: '#7f1d1d', text: '#ef4444', label: 'WALK AWAY' },
}

const STAGE_LABELS: Record<number, string> = {
    1: 'Extracting listing',
    2: 'Parallel agent scan',
    3: 'Scoring & report',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function safeHost(url: string): string {
    try { return new URL(url).hostname.replace(/^www\./, '') }
    catch { return url.slice(0, 30) }
}

function fmtCurrency(val: number | null | undefined, currency: string): string {
    if (val == null) return '—'
    const symbols: Record<string, string> = {
        INR: '₹', USD: '$', GBP: '£', EUR: '€', AED: 'د.إ',
        AUD: 'A$', CAD: 'C$', NOK: 'kr', SGD: 'S$',
    }
    const sym = symbols[currency] ?? currency + ' '
    if (val >= 1_00_000 && currency === 'INR') {
        return `${sym}${(val / 1_00_000).toFixed(1)}L`
    }
    return `${sym}${val.toLocaleString()}`
}

// ── Sub-components ────────────────────────────────────────────────────────────

function RiskRing({ score, label, color }: { score: number; label: string; color: string }) {
    const [anim, setAnim] = useState(false)
    useEffect(() => {
        const t = setTimeout(() => setAnim(true), 100)
        return () => clearTimeout(t)
    }, [score])

    const r = 52
    const sw = 10
    const C = 2 * Math.PI * r
    const offset = anim ? C * (1 - score / 100) : C

    return (
        <div className="flex flex-col items-center gap-1">
            <svg width={130} height={130} viewBox="0 0 130 130">
                <circle cx={65} cy={65} r={r} fill="none" stroke="#1e2d42" strokeWidth={sw} />
                <circle
                    cx={65} cy={65} r={r} fill="none"
                    stroke={color} strokeWidth={sw}
                    strokeLinecap="round"
                    strokeDasharray={C}
                    strokeDashoffset={offset}
                    strokeLinejoin="round"
                    transform="rotate(-90 65 65)"
                    style={{ transition: 'stroke-dashoffset 0.9s cubic-bezier(0.4,0,0.2,1)' }}
                />
                <text x="65" y="62" textAnchor="middle" fill="white" fontSize="26" fontWeight="700" fontFamily="monospace">
                    {score}
                </text>
                <text x="65" y="79" textAnchor="middle" fill="#8ba3c7" fontSize="9" fontFamily="system-ui">
                    / 100
                </text>
            </svg>
            <span className="text-xs font-semibold tracking-wider" style={{ color }}>{label}</span>
        </div>
    )
}

function ScoreBar({ label, value, color, max = 100 }: { label: string; value: number; color: string; max?: number }) {
    const [anim, setAnim] = useState(false)
    useEffect(() => {
        const t = setTimeout(() => setAnim(true), 200)
        return () => clearTimeout(t)
    }, [value])

    const pct = (value / max) * 100

    return (
        <div className="space-y-1">
            <div className="flex justify-between text-xs">
                <span className="text-[#8ba3c7]">{label}</span>
                <span className="font-mono font-semibold" style={{ color }}>{value}</span>
            </div>
            <div className="h-1.5 rounded-full bg-[#1e2d42] overflow-hidden">
                <div
                    className="h-full rounded-full"
                    style={{
                        width: anim ? `${pct}%` : '0%',
                        backgroundColor: color,
                        transition: 'width 0.8s cubic-bezier(0.4,0,0.2,1)',
                        boxShadow: `0 0 8px ${color}66`,
                    }}
                />
            </div>
        </div>
    )
}

function BatterySoH({ battery }: { battery: BatteryAssessment }) {
    const [anim, setAnim] = useState(false)
    useEffect(() => {
        const t = setTimeout(() => setAnim(true), 300)
        return () => clearTimeout(t)
    }, [battery.estimated_soh_pct])

    const soh = battery.estimated_soh_pct ?? 0
    const color = soh >= 90 ? '#22c55e' : soh >= 80 ? '#a3e635' : soh >= 70 ? '#facc15' : '#ef4444'
    const assessColor = battery.assessment === 'EXCELLENT' ? '#22c55e'
        : battery.assessment === 'GOOD' ? '#a3e635'
        : battery.assessment === 'FAIR' ? '#facc15' : '#ef4444'

    return (
        <div className="rounded-xl border border-[#1e2d42] bg-[#0d1220] p-5 space-y-4">
            <div className="flex items-center gap-2">
                <Battery size={16} className="text-[#3b82f6]" />
                <span className="text-sm font-semibold text-white">Battery Health</span>
                <span
                    className="ml-auto text-xs font-bold tracking-wider px-2 py-0.5 rounded"
                    style={{ backgroundColor: `${assessColor}22`, color: assessColor, border: `1px solid ${assessColor}44` }}
                >
                    {battery.assessment}
                </span>
            </div>

            {/* SoH bar */}
            <div className="space-y-1">
                <div className="flex justify-between text-xs">
                    <span className="text-[#8ba3c7]">Estimated State of Health</span>
                    <span className="font-mono font-semibold" style={{ color }}>{soh}%</span>
                </div>
                <div className="h-3 rounded-full bg-[#1e2d42] overflow-hidden relative">
                    <div
                        className="h-full rounded-full"
                        style={{
                            width: anim ? `${soh}%` : '0%',
                            background: `linear-gradient(90deg, ${color}88, ${color})`,
                            transition: 'width 1s cubic-bezier(0.4,0,0.2,1)',
                            boxShadow: `0 0 12px ${color}66`,
                        }}
                    />
                    {/* Benchmark lines */}
                    {[70, 80, 90].map(mark => (
                        <div
                            key={mark}
                            className="absolute top-0 bottom-0 w-px opacity-40"
                            style={{ left: `${mark}%`, backgroundColor: '#8ba3c7' }}
                        />
                    ))}
                </div>
                <div className="flex justify-between text-[10px] text-[#4a6680] px-0.5">
                    <span>Poor</span>
                    <span>Fair</span>
                    <span>Good</span>
                    <span>Excellent</span>
                </div>
            </div>

            {/* Status pills */}
            <div className="flex flex-wrap gap-2">
                {battery.recall_found && (
                    <span className="text-xs px-2 py-0.5 rounded bg-[#7f1d1d44] border border-[#7f1d1d] text-[#ef4444]">
                        ⚠ Recall Found
                    </span>
                )}
                {battery.dc_charge_limited && (
                    <span className="text-xs px-2 py-0.5 rounded bg-[#7c2d1244] border border-[#7c2d12] text-[#f97316]">
                        DC Limit
                    </span>
                )}
                {battery.warranty_remaining && (
                    <span className={`text-xs px-2 py-0.5 rounded border ${
                        battery.warranty_remaining.includes('Expired')
                            ? 'bg-[#44380a44] border-[#44380a] text-[#facc15]'
                            : 'bg-[#1a4428] border-[#166534] text-[#22c55e]'
                    }`}>
                        {battery.warranty_remaining}
                    </span>
                )}
            </div>

            {battery.notes.length > 0 && (
                <ul className="space-y-1">
                    {battery.notes.map((note, i) => (
                        <li key={i} className="text-xs text-[#8ba3c7] flex gap-2">
                            <span className="text-[#3b82f6] mt-0.5">›</span>{note}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    )
}

function EvidenceCard({ title, items, urlKey }: {
    title: string
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    items: any[]
    urlKey: string
}) {
    if (items.length === 0) return null
    return (
        <div className="rounded-xl border border-[#7f1d1d] bg-[#1a060844] p-4 space-y-3">
            <div className="flex items-center gap-2">
                <AlertTriangle size={14} className="text-[#ef4444]" />
                <span className="text-sm font-semibold text-[#ef4444]">{title}</span>
                <span className="ml-auto text-xs font-mono text-[#ef4444] bg-[#7f1d1d44] px-2 py-0.5 rounded">
                    {items.length} found
                </span>
            </div>
            <div className="space-y-2">
                {items.map((item, i) => {
                    const url = item[urlKey] as string | undefined
                    return (
                        <div key={i} className="text-xs space-y-1 bg-[#0d1220] rounded p-3">
                            {url && url.startsWith('http') && (
                                <div className="flex items-center gap-1.5">
                                    <span className="text-[10px] font-bold tracking-widest text-[#22c55e] bg-[#0d1f1444] border border-[#1a4428] px-1.5 py-0.5 rounded">
                                        ✓ VERIFIED
                                    </span>
                                    <a href={url} target="_blank" rel="noopener noreferrer"
                                        className="text-[#3b82f6] hover:text-[#60a5fa] flex items-center gap-1">
                                        {safeHost(url)} <ExternalLink size={10} />
                                    </a>
                                </div>
                            )}
                            {Object.entries(item).filter(([k]) => k !== urlKey && k !== 'match_type').map(([k, v]) => (
                                typeof v === 'string' && v ? (
                                    <div key={k} className="flex gap-2">
                                        <span className="text-[#4a6680] capitalize min-w-[60px]">{k.replace(/_/g, ' ')}:</span>
                                        <span className="text-[#8ba3c7] flex-1">{v}</span>
                                    </div>
                                ) : null
                            ))}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function UsedEvPage() {
    const { state, start, reset } = useUsedEvStream()

    const [formData, setFormData] = useState({
        listing_url: '',
        country: 'india',
        city: '',
        vin_hint: '',
        phone_hint: '',
        showAdvanced: false,
    })

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        if (!formData.listing_url.trim()) return
        start({
            listing_url: formData.listing_url.trim(),
            country: formData.country,
            city: formData.city || undefined,
            vin_hint: formData.vin_hint || undefined,
            phone_hint: formData.phone_hint || undefined,
        })
    }

    const report = state.report as UsedEvReport | null
    const bandCfg = report ? (BAND_CONFIG[report.risk_band] ?? BAND_CONFIG['CAUTION']) : null

    if (state.status === 'streaming') {
        return (
            <div className="min-h-screen bg-[#07090f] text-white">
                {/* Nav */}
                <nav className="border-b border-[#1e2d42] px-6 py-4 flex items-center gap-4">
                    <Link href="/" className="text-[#8ba3c7] hover:text-white text-sm flex items-center gap-1">
                        ← VoltSage
                    </Link>
                    <span className="text-[#1e2d42]">/</span>
                    <span className="text-white text-sm font-medium">Used EV Inspect</span>
                </nav>

                <div className="max-w-2xl mx-auto px-6 py-16">
                    {/* Header */}
                    <div className="text-center mb-12">
                        <div className="inline-flex items-center gap-2 mb-4">
                            <div className="w-2 h-2 rounded-full bg-[#3b82f6] animate-pulse" />
                            <span className="text-xs text-[#3b82f6] tracking-widest font-semibold uppercase">
                                Investigation in progress
                            </span>
                        </div>
                        <h2 className="text-2xl font-bold text-white">
                            Scanning {state.messages.find(m => m.includes('extracted:'))?.split('extracted:')[1]?.split(',')[0]?.trim() || 'listing'}
                        </h2>
                    </div>

                    {/* Stage progress */}
                    <div className="flex items-center justify-center gap-0 mb-10">
                        {[1, 2, 3].map((s, i) => (
                            <div key={s} className="flex items-center">
                                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border ${
                                    s < state.stage ? 'bg-[#1a4428] border-[#22c55e] text-[#22c55e]'
                                    : s === state.stage ? 'bg-[#1e3a5f] border-[#3b82f6] text-[#3b82f6] animate-pulse'
                                    : 'bg-[#0d1220] border-[#1e2d42] text-[#4a6680]'
                                }`}>
                                    {s < state.stage ? '✓' : s}
                                </div>
                                <div className="flex flex-col mx-2 w-24 text-center">
                                    <span className={`text-[10px] tracking-wide ${s <= state.stage ? 'text-[#8ba3c7]' : 'text-[#4a6680]'}`}>
                                        {STAGE_LABELS[s]}
                                    </span>
                                </div>
                                {i < 2 && (
                                    <div className={`w-8 h-px ${s < state.stage ? 'bg-[#22c55e]' : 'bg-[#1e2d42]'}`} />
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Log */}
                    <div className="rounded-xl border border-[#1e2d42] bg-[#0d1220] p-5 font-mono text-xs space-y-2 max-h-72 overflow-y-auto">
                        {state.messages.length === 0 && (
                            <div className="text-[#4a6680]">Connecting…</div>
                        )}
                        {state.messages.map((msg, i) => (
                            <div key={i} className={`flex gap-2 ${i === state.messages.length - 1 ? 'text-white' : 'text-[#8ba3c7]'}`}>
                                <span className="text-[#4a6680] select-none">{String(i + 1).padStart(2, '0')}</span>
                                <span>{msg}</span>
                            </div>
                        ))}
                        {state.status === 'streaming' && (
                            <div className="flex items-center gap-2 text-[#3b82f6]">
                                <Loader2 size={12} className="animate-spin" />
                                <span>Running…</span>
                            </div>
                        )}
                    </div>

                    <p className="text-center text-xs text-[#4a6680] mt-6">
                        3 agents run in parallel · every finding includes a verified source URL
                    </p>
                </div>
            </div>
        )
    }

    if (state.status === 'error') {
        return (
            <div className="min-h-screen bg-[#07090f] text-white flex items-center justify-center">
                <div className="text-center space-y-4">
                    <XCircle size={48} className="text-[#ef4444] mx-auto" />
                    <h2 className="text-xl font-bold">Investigation failed</h2>
                    <p className="text-[#8ba3c7]">{state.error}</p>
                    <button onClick={reset} className="px-4 py-2 rounded-lg bg-[#1e2d42] text-white hover:bg-[#263d5a] text-sm">
                        Try again
                    </button>
                </div>
            </div>
        )
    }

    if (state.status === 'complete' && report && bandCfg) {
        return (
            <div className="min-h-screen bg-[#07090f] text-white">
                {/* Nav */}
                <nav className="border-b border-[#1e2d42] px-6 py-4 flex items-center gap-4">
                    <Link href="/" className="text-[#8ba3c7] hover:text-white text-sm flex items-center gap-1">
                        ← VoltSage
                    </Link>
                    <span className="text-[#1e2d42]">/</span>
                    <Link href="/used-ev" onClick={reset} className="text-[#8ba3c7] hover:text-white text-sm">
                        Used EV Inspect
                    </Link>
                    <span className="text-[#1e2d42]">/</span>
                    <span className="text-white text-sm">
                        {report.vehicle_facts.year} {report.vehicle_facts.make} {report.vehicle_facts.model}
                    </span>
                    <div className="ml-auto flex items-center gap-3">
                        <span className="text-xs text-[#4a6680] flex items-center gap-1">
                            <Clock size={11} />
                            {report.investigation_timing.elapsed_seconds}s
                        </span>
                        <span className="text-xs text-[#4a6680]">·</span>
                        <span className="text-xs text-[#4a6680]">
                            {report.investigation_timing.parallel_agents} parallel agents
                        </span>
                        <button
                            onClick={reset}
                            className="text-xs px-3 py-1.5 rounded-lg bg-[#1e2d42] text-[#8ba3c7] hover:bg-[#263d5a] hover:text-white"
                        >
                            New inspection
                        </button>
                    </div>
                </nav>

                <div className="max-w-5xl mx-auto px-6 py-10 space-y-8">

                    {/* ── Verdict hero ──────────────────────────────────────────── */}
                    <div
                        className="rounded-2xl p-8 border text-center"
                        style={{
                            backgroundColor: bandCfg.bg,
                            borderColor: bandCfg.border,
                            background: `radial-gradient(ellipse at top, ${bandCfg.text}08 0%, ${bandCfg.bg} 70%)`,
                        }}
                    >
                        <div
                            className="inline-block text-sm font-bold tracking-[0.2em] px-4 py-1 rounded mb-4 border"
                            style={{ color: bandCfg.text, borderColor: `${bandCfg.text}44`, backgroundColor: `${bandCfg.text}11` }}
                        >
                            {bandCfg.label}
                        </div>
                        <h1 className="text-3xl font-bold text-white mb-2">
                            {report.recommendation.icon} {report.recommendation.action}
                        </h1>
                        <p className="text-[#8ba3c7] max-w-xl mx-auto">{report.recommendation.detail}</p>
                        <div className="mt-6 flex justify-center gap-6 text-sm">
                            <div className="text-center">
                                <div className="font-mono text-2xl font-bold" style={{ color: bandCfg.text }}>
                                    {report.overall_risk}
                                </div>
                                <div className="text-[#4a6680] text-xs mt-1">Overall Risk</div>
                            </div>
                            <div className="w-px bg-[#1e2d42]" />
                            <div className="text-center">
                                <div className="font-mono text-2xl font-bold text-[#f97316]">
                                    {report.fraud_risk}
                                </div>
                                <div className="text-[#4a6680] text-xs mt-1">Fraud Risk</div>
                            </div>
                            <div className="w-px bg-[#1e2d42]" />
                            <div className="text-center">
                                <div className="font-mono text-2xl font-bold text-[#3b82f6]">
                                    {report.ev_condition_risk}
                                </div>
                                <div className="text-[#4a6680] text-xs mt-1">EV Condition Risk</div>
                            </div>
                        </div>
                    </div>

                    {/* ── Main dashboard grid ──────────────────────────────────── */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                        {/* Risk rings column */}
                        <div className="rounded-xl border border-[#1e2d42] bg-[#0d1220] p-6 flex flex-col items-center gap-6">
                            <h3 className="text-sm font-semibold text-[#8ba3c7] tracking-wide w-full">RISK BREAKDOWN</h3>
                            <RiskRing score={report.overall_risk} label="OVERALL" color={bandCfg.text} />
                            <div className="w-full space-y-3">
                                <ScoreBar label="Fraud Risk" value={report.fraud_risk} color="#f97316" />
                                <ScoreBar label="EV Condition Risk" value={report.ev_condition_risk} color="#3b82f6" />
                            </div>
                        </div>

                        {/* Vehicle facts + red flags */}
                        <div className="lg:col-span-2 space-y-4">
                            {/* Vehicle facts */}
                            <div className="rounded-xl border border-[#1e2d42] bg-[#0d1220] p-5">
                                <div className="flex items-center gap-2 mb-4">
                                    <Car size={14} className="text-[#3b82f6]" />
                                    <span className="text-sm font-semibold text-white">Vehicle</span>
                                </div>
                                <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                                    {[
                                        ['Make', report.vehicle_facts.make],
                                        ['Model', report.vehicle_facts.model],
                                        ['Year', report.vehicle_facts.year],
                                        ['Trim', report.vehicle_facts.trim],
                                        ['Odometer', report.vehicle_facts.odometer_km ? `${report.vehicle_facts.odometer_km.toLocaleString()} km` : '—'],
                                        ['Asking Price', report.vehicle_facts.asking_price || '—'],
                                        ['VIN', report.vehicle_facts.vin || 'Not provided'],
                                        ['Seller', report.vehicle_facts.seller_name || '—'],
                                    ].map(([label, value]) => (
                                        <div key={label} className="flex gap-2">
                                            <span className="text-[#4a6680] min-w-[80px]">{label}</span>
                                            <span className="text-[#c3d4e8] font-medium">{value}</span>
                                        </div>
                                    ))}
                                </div>
                                {report.vehicle_facts.listing_url && (
                                    <a
                                        href={report.vehicle_facts.listing_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="mt-3 flex items-center gap-1 text-xs text-[#3b82f6] hover:text-[#60a5fa]"
                                    >
                                        {safeHost(report.vehicle_facts.listing_url)} <ExternalLink size={10} />
                                    </a>
                                )}
                            </div>

                            {/* Red flags */}
                            {report.red_flags.length > 0 && (
                                <div className="rounded-xl border border-[#7f1d1d] bg-[#1a060811] p-5">
                                    <div className="flex items-center gap-2 mb-3">
                                        <ShieldAlert size={14} className="text-[#ef4444]" />
                                        <span className="text-sm font-semibold text-[#ef4444]">Red Flags</span>
                                        <span className="ml-auto text-xs text-[#ef4444] bg-[#7f1d1d44] px-2 py-0.5 rounded">
                                            {report.red_flags.length}
                                        </span>
                                    </div>
                                    <ul className="space-y-2">
                                        {report.red_flags.map((flag, i) => (
                                            <li key={i} className="text-sm text-[#fca5a5] flex gap-2">
                                                <span className="text-[#ef4444] mt-0.5 shrink-0">→</span>
                                                {flag}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* ── Battery health ───────────────────────────────────────── */}
                    {report.battery_assessment?.estimated_soh_pct != null && (
                        <BatterySoH battery={report.battery_assessment} />
                    )}

                    {/* ── EV specs from VoltSage DB ────────────────────────────── */}
                    {report.ev_specs?.spec_range_city_km && (
                        <div className="rounded-xl border border-[#1e2d42] bg-[#0d1220] p-5">
                            <div className="flex items-center gap-2 mb-4">
                                <Zap size={14} className="text-[#facc15]" />
                                <span className="text-sm font-semibold text-white">EV Specs (VoltSage database)</span>
                                <span className="ml-auto text-xs text-[#4a6680]">{report.ev_specs.source}</span>
                            </div>
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                                {[
                                    ['Battery', report.ev_specs.spec_battery_kwh ? `${report.ev_specs.spec_battery_kwh} kWh` : '—'],
                                    ['City Range', report.ev_specs.spec_range_city_km ? `${report.ev_specs.spec_range_city_km} km` : '—'],
                                    ['Highway Range', report.ev_specs.spec_range_highway_km ? `${report.ev_specs.spec_range_highway_km} km` : '—'],
                                    ['DC Fast Charge', report.ev_specs.spec_dc_kw ? `${report.ev_specs.spec_dc_kw} kW` : '—'],
                                ].map(([label, value]) => (
                                    <div key={label} className="text-center bg-[#07090f] rounded-lg p-3">
                                        <div className="text-lg font-bold text-white font-mono">{value}</div>
                                        <div className="text-xs text-[#4a6680] mt-1">{label}</div>
                                    </div>
                                ))}
                            </div>
                            {report.ev_specs.known_issues.length > 0 && (
                                <div className="mt-4 pt-4 border-t border-[#1e2d42]">
                                    <p className="text-xs text-[#8ba3c7] font-semibold mb-2">Known owner-reported issues:</p>
                                    <ul className="space-y-1">
                                        {report.ev_specs.known_issues.map((issue, i) => (
                                            <li key={i} className="text-xs text-[#8ba3c7] flex gap-2">
                                                <span className="text-[#f97316]">›</span>{issue}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    )}

                    {/* ── Market pricing ──────────────────────────────────────── */}
                    {report.market_comparison?.median_market_price && (
                        <div className="rounded-xl border border-[#1e2d42] bg-[#0d1220] p-5">
                            <div className="flex items-center gap-2 mb-5">
                                <TrendingDown size={14} className="text-[#a3e635]" />
                                <span className="text-sm font-semibold text-white">Market Price Analysis</span>
                                {report.market_comparison.market_verdict && (
                                    <span className={`ml-auto text-xs font-bold px-2 py-0.5 rounded border ${
                                        report.market_comparison.market_verdict === 'FAIR' ? 'text-[#22c55e] border-[#166534] bg-[#1a4428]'
                                        : report.market_comparison.market_verdict === 'ABOVE_MARKET' ? 'text-[#60a5fa] border-[#1d4ed8] bg-[#1e3a5f]'
                                        : 'text-[#facc15] border-[#44380a] bg-[#44380a44]'
                                    }`}>
                                        {report.market_comparison.market_verdict.replace('_', ' ')}
                                    </span>
                                )}
                            </div>

                            {/* Price bar */}
                            <PriceBar
                                low={report.market_comparison.low_price ?? 0}
                                median={report.market_comparison.median_market_price ?? 0}
                                high={report.market_comparison.high_price ?? 0}
                                listing={report.market_comparison.listing_price}
                                currency={report.market_comparison.currency}
                            />

                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5">
                                {[
                                    ['Median', fmtCurrency(report.market_comparison.median_market_price, report.market_comparison.currency)],
                                    ['Low', fmtCurrency(report.market_comparison.low_price, report.market_comparison.currency)],
                                    ['High', fmtCurrency(report.market_comparison.high_price, report.market_comparison.currency)],
                                    ['Sample', `${report.market_comparison.sample_count} listings`],
                                ].map(([label, value]) => (
                                    <div key={label} className="bg-[#07090f] rounded-lg p-3 text-center">
                                        <div className="font-mono font-bold text-white">{value}</div>
                                        <div className="text-xs text-[#4a6680] mt-0.5">{label}</div>
                                    </div>
                                ))}
                            </div>

                            {report.market_comparison.comparables.length > 0 && (
                                <div className="mt-4 pt-4 border-t border-[#1e2d42]">
                                    <p className="text-xs text-[#8ba3c7] font-semibold mb-2">Comparable listings:</p>
                                    <div className="space-y-1.5">
                                        {report.market_comparison.comparables.slice(0, 4).map((c, i) => (
                                            <div key={i} className="flex items-center gap-3 text-xs text-[#8ba3c7]">
                                                <span className="text-white font-mono font-semibold min-w-[80px]">
                                                    {fmtCurrency(c.price, report.market_comparison.currency)}
                                                </span>
                                                <span className="text-[#4a6680]">
                                                    {c.odometer_km ? `${c.odometer_km.toLocaleString()} km` : ''}{c.trim ? ` · ${c.trim}` : ''}
                                                </span>
                                                <span className="text-[#4a6680]">{c.source}</span>
                                                {c.url && c.url.startsWith('http') && (
                                                    <a href={c.url} target="_blank" rel="noopener noreferrer"
                                                        className="ml-auto text-[#3b82f6] hover:text-[#60a5fa]">
                                                        <ExternalLink size={10} />
                                                    </a>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* ── Evidence board ──────────────────────────────────────── */}
                    {(report.evidence.duplicate_listings?.length > 0 ||
                        report.evidence.photo_reuse?.length > 0 ||
                        report.evidence.identity_flags?.length > 0) && (
                        <div className="space-y-4">
                            <h3 className="text-sm font-semibold text-[#8ba3c7] tracking-wide">EVIDENCE BOARD</h3>
                            <EvidenceCard
                                title="Duplicate Listings"
                                items={report.evidence.duplicate_listings ?? []}
                                urlKey="url"
                            />
                            <EvidenceCard
                                title="Photo Reuse"
                                items={report.evidence.photo_reuse ?? []}
                                urlKey="source_url"
                            />
                            {report.evidence.identity_flags?.length > 0 && (
                                <div className="rounded-xl border border-[#7c2d12] bg-[#1a0e0611] p-4">
                                    <div className="flex items-center gap-2 mb-3">
                                        <AlertTriangle size={14} className="text-[#f97316]" />
                                        <span className="text-sm font-semibold text-[#f97316]">Identity Flags</span>
                                    </div>
                                    <ul className="space-y-2">
                                        {report.evidence.identity_flags.map((flag, i) => (
                                            <li key={i} className="text-sm text-[#fdba74] flex gap-2">
                                                <span className="text-[#f97316] shrink-0">→</span>{flag}
                                            </li>
                                        ))}
                                    </ul>
                                    {report.evidence.identity_source_url && (
                                        <a
                                            href={report.evidence.identity_source_url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="mt-2 flex items-center gap-1 text-xs text-[#3b82f6] hover:text-[#60a5fa]"
                                        >
                                            <span className="text-[10px] font-bold text-[#22c55e] bg-[#0d1f1444] border border-[#1a4428] px-1 py-0.5 rounded mr-1">✓ VERIFIED</span>
                                            {safeHost(report.evidence.identity_source_url)} <ExternalLink size={10} />
                                        </a>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {/* ── Questions to ask ───────────────────────────────────── */}
                    {report.questions_to_ask.length > 0 && (
                        <div className="rounded-xl border border-[#1e2d42] bg-[#0d1220] p-5">
                            <div className="flex items-center gap-2 mb-4">
                                <Users size={14} className="text-[#a78bfa]" />
                                <span className="text-sm font-semibold text-white">Ask the Seller</span>
                            </div>
                            <ol className="space-y-2">
                                {report.questions_to_ask.map((q, i) => (
                                    <li key={i} className="flex gap-3 text-sm text-[#8ba3c7]">
                                        <span className="font-mono text-[#a78bfa] font-bold shrink-0">{i + 1}.</span>
                                        {q}
                                    </li>
                                ))}
                            </ol>
                        </div>
                    )}

                    {/* Footer */}
                    <p className="text-center text-xs text-[#4a6680] pb-8">
                        Powered by VoltSage · TinyFish browser agents · {report.investigation_timing.elapsed_seconds}s investigation
                    </p>
                </div>
            </div>
        )
    }

    // ── Form (idle) ──────────────────────────────────────────────────────────
    return (
        <div className="min-h-screen bg-[#07090f] text-white">
            {/* Nav */}
            <nav className="border-b border-[#1e2d42] px-6 py-4 flex items-center gap-4">
                <Link href="/" className="text-[#8ba3c7] hover:text-white text-sm flex items-center gap-1">
                    ← VoltSage
                </Link>
                <span className="text-[#1e2d42]">/</span>
                <span className="text-white text-sm font-medium">Used EV Inspect</span>
            </nav>

            <div className="max-w-2xl mx-auto px-6 py-16">
                {/* Header */}
                <div className="text-center mb-12">
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#1e3a5f] border border-[#1d4ed8] text-[#60a5fa] text-xs font-semibold mb-5">
                        <Zap size={12} />
                        5 AI agents · 3 run in parallel · ~90 seconds
                    </div>
                    <h1 className="text-4xl font-bold text-white mb-4">
                        Used EV Due Diligence
                    </h1>
                    <p className="text-[#8ba3c7] text-lg">
                        Paste any used EV listing. We check for fraud, battery health,
                        and market pricing — every finding backed by a verified URL.
                    </p>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="space-y-5">
                    <div>
                        <label className="block text-sm text-[#8ba3c7] mb-2">Listing URL *</label>
                        <div className="relative">
                            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#4a6680]" />
                            <input
                                type="url"
                                required
                                placeholder="https://www.cars24.com/buy-used-..."
                                value={formData.listing_url}
                                onChange={e => setFormData(f => ({ ...f, listing_url: e.target.value }))}
                                className="w-full pl-10 pr-4 py-3 bg-[#0d1220] border border-[#1e2d42] rounded-xl text-white placeholder-[#4a6680] focus:outline-none focus:border-[#3b82f6] focus:ring-1 focus:ring-[#3b82f655]"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm text-[#8ba3c7] mb-2">Country</label>
                        <div className="relative">
                            <Globe2 size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#4a6680]" />
                            <select
                                value={formData.country}
                                onChange={e => setFormData(f => ({ ...f, country: e.target.value }))}
                                className="w-full pl-10 pr-4 py-3 bg-[#0d1220] border border-[#1e2d42] rounded-xl text-white focus:outline-none focus:border-[#3b82f6] appearance-none"
                            >
                                {COUNTRIES.map(c => (
                                    <option key={c.code} value={c.code}>
                                        {c.flag} {c.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                    </div>

                    {/* Advanced toggle */}
                    <button
                        type="button"
                        onClick={() => setFormData(f => ({ ...f, showAdvanced: !f.showAdvanced }))}
                        className="text-xs text-[#4a6680] hover:text-[#8ba3c7] flex items-center gap-1"
                    >
                        <ChevronRight size={12} className={`transition-transform ${formData.showAdvanced ? 'rotate-90' : ''}`} />
                        Optional hints (VIN / seller phone)
                    </button>

                    {formData.showAdvanced && (
                        <div className="space-y-4 pl-4 border-l border-[#1e2d42]">
                            <div>
                                <label className="block text-xs text-[#4a6680] mb-1">VIN (if you have it)</label>
                                <input
                                    type="text"
                                    placeholder="17-character VIN"
                                    value={formData.vin_hint}
                                    onChange={e => setFormData(f => ({ ...f, vin_hint: e.target.value }))}
                                    className="w-full px-3 py-2 bg-[#0d1220] border border-[#1e2d42] rounded-lg text-white placeholder-[#4a6680] focus:outline-none focus:border-[#3b82f6] text-sm"
                                />
                            </div>
                            <div>
                                <label className="block text-xs text-[#4a6680] mb-1">Seller phone (if visible)</label>
                                <input
                                    type="text"
                                    placeholder="+91 98765 43210"
                                    value={formData.phone_hint}
                                    onChange={e => setFormData(f => ({ ...f, phone_hint: e.target.value }))}
                                    className="w-full px-3 py-2 bg-[#0d1220] border border-[#1e2d42] rounded-lg text-white placeholder-[#4a6680] focus:outline-none focus:border-[#3b82f6] text-sm"
                                />
                            </div>
                        </div>
                    )}

                    <button
                        type="submit"
                        className="w-full py-4 rounded-xl bg-[#3b82f6] hover:bg-[#2563eb] text-white font-semibold text-base flex items-center justify-center gap-2 transition-colors"
                    >
                        <Search size={18} />
                        Inspect this EV
                    </button>

                    <p className="text-center text-xs text-[#4a6680]">
                        Fraud check · Battery SoH · Market pricing · All with verified source URLs
                    </p>
                </form>

                {/* What we check */}
                <div className="mt-16 grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {[
                        { icon: <ShieldAlert size={16} className="text-[#ef4444]" />, label: 'Duplicate listing scan', detail: 'Cross-platform search with verified URLs' },
                        { icon: <Search size={16} className="text-[#a78bfa]" />, label: 'Photo reverse-search', detail: 'Google Lens + TinEye confirmation' },
                        { icon: <AlertTriangle size={16} className="text-[#f97316]" />, label: 'Seller identity check', detail: 'Fraud databases · scam report sites' },
                        { icon: <Battery size={16} className="text-[#3b82f6]" />, label: 'Battery health estimate', detail: 'SoH from odometer · recall search · warranty' },
                        { icon: <TrendingDown size={16} className="text-[#a3e635]" />, label: 'Market pricing', detail: 'Country-aware comparable listings' },
                        { icon: <Zap size={16} className="text-[#facc15]" />, label: 'EV spec enrichment', detail: 'VoltSage database + owner review insights' },
                    ].map(({ icon, label, detail }) => (
                        <div key={label} className="flex gap-3 p-4 rounded-xl bg-[#0d1220] border border-[#1e2d42]">
                            <div className="mt-0.5 shrink-0">{icon}</div>
                            <div>
                                <div className="text-sm font-medium text-white">{label}</div>
                                <div className="text-xs text-[#4a6680] mt-0.5">{detail}</div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}

// ── Price Bar component ──────────────────────────────────────────────────────

function PriceBar({ low, median, high, listing, currency }: {
    low: number; median: number; high: number; listing: number | null; currency: string
}) {
    if (!low || !high || low === high) return null

    const range = high - low
    const medianPct = ((median - low) / range) * 100
    const listingPct = listing ? Math.max(0, Math.min(100, ((listing - low) / range) * 100)) : null

    return (
        <div className="space-y-2">
            <div className="relative h-6 rounded-full bg-[#1e2d42] overflow-visible">
                {/* Range fill */}
                <div className="absolute inset-0 rounded-full bg-gradient-to-r from-[#1e3a5f] via-[#1a4428] to-[#1e3a5f]" />
                {/* Median marker */}
                <div
                    className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-1.5 h-4 rounded-full bg-[#22c55e]"
                    style={{ left: `${medianPct}%` }}
                />
                {/* Listing price marker */}
                {listingPct !== null && (
                    <div
                        className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 bg-white"
                        style={{
                            left: `${listingPct}%`,
                            borderColor: listingPct < medianPct - 10 ? '#ef4444' : listingPct > medianPct + 10 ? '#60a5fa' : '#facc15',
                            boxShadow: `0 0 8px ${listingPct < medianPct - 10 ? '#ef444488' : '#facc1588'}`,
                        }}
                    />
                )}
            </div>
            <div className="flex justify-between text-xs text-[#4a6680] px-0.5">
                <span>{fmtCurrency(low, currency)}</span>
                <span className="text-[#22c55e]">median {fmtCurrency(median, currency)}</span>
                {listing && <span className="text-white">● listing {fmtCurrency(listing, currency)}</span>}
                <span>{fmtCurrency(high, currency)}</span>
            </div>
        </div>
    )
}

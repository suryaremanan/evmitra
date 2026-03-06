'use client'

import { useState, useEffect, useCallback } from 'react'
import {
    Globe2, Zap, MapPin, ChevronDown, Home, Search,
    Loader2, CheckCircle2, AlertCircle, RefreshCw, ArrowRight,
    Battery, Shield, TrendingDown, Download,
} from 'lucide-react'
import { fetchCountries, fetchEVDatabase, streamEVDatabase, streamVerdict } from '@/lib/api'
import type { Country, EvModel, VerdictResult, VehicleDetails, ChargerStation, FormState } from '@/lib/types'

// ─────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────

function generateUserId(): string {
    if (typeof window === 'undefined') return ''
    const stored = localStorage.getItem('voltsage_user_id')
    if (stored) return stored
    const id = `vs_${Math.random().toString(36).slice(2, 10)}`
    localStorage.setItem('voltsage_user_id', id)
    return id
}

function scoreColor(score: number): string {
    if (score <= 3) return '#10b981'
    if (score <= 6) return '#f59e0b'
    return '#f43f5e'
}

function scoreColorClass(score: number): string {
    if (score <= 3) return 'score-green'
    if (score <= 6) return 'score-amber'
    return 'score-red'
}

function scoreLabel(score: number): string {
    if (score <= 3) return 'Low anxiety'
    if (score <= 6) return 'Moderate'
    return 'High anxiety'
}

function gaugeArcClass(score: number): string {
    if (score <= 3) return 'gauge-arc-green'
    if (score <= 6) return 'gauge-arc-amber'
    return 'gauge-arc-red'
}

// ─────────────────────────────────────────────────────────
// CIRCULAR GAUGE — animated SVG arc
// ─────────────────────────────────────────────────────────

function CircularGauge({
    score,
    label,
    rationale,
    delay = 0,
}: {
    score: number
    label: string
    rationale: string
    delay?: number
}) {
    const [animated, setAnimated] = useState(false)

    useEffect(() => {
        setAnimated(false)
        const t = setTimeout(() => setAnimated(true), delay + 80)
        return () => clearTimeout(t)
    }, [score, delay])

    const r = 44
    const sw = 7
    const C = 2 * Math.PI * r
    const targetOffset = C * (1 - score / 10)
    const offset = animated ? targetOffset : C
    const color = scoreColor(score)

    return (
        <div className="bento-item bg-[#0d1220] border border-[#1e2d42] rounded-xl p-5">
            <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#22d3ee] mb-4">{label}</div>
            <div className="flex items-center gap-5">
                {/* SVG Gauge */}
                <div className="relative flex-shrink-0" style={{ width: 116, height: 116 }}>
                    <svg width="116" height="116" viewBox="0 0 110 110" style={{ overflow: 'visible' }}>
                        {/* Track */}
                        <circle cx="55" cy="55" r={r} fill="none" stroke="#1e2d42" strokeWidth={sw} />
                        {/* Glow track (subtle) */}
                        <circle
                            cx="55" cy="55" r={r}
                            fill="none"
                            stroke={color}
                            strokeWidth={sw + 4}
                            strokeLinecap="round"
                            strokeDasharray={C}
                            strokeDashoffset={offset}
                            transform="rotate(-90 55 55)"
                            opacity="0.08"
                            style={{ transition: 'stroke-dashoffset 1.5s cubic-bezier(0.4, 0, 0.2, 1)' }}
                        />
                        {/* Main arc */}
                        <circle
                            cx="55" cy="55" r={r}
                            fill="none"
                            stroke={color}
                            strokeWidth={sw}
                            strokeLinecap="round"
                            strokeDasharray={C}
                            strokeDashoffset={offset}
                            transform="rotate(-90 55 55)"
                            className={gaugeArcClass(score)}
                            style={{
                                transition: 'stroke-dashoffset 1.5s cubic-bezier(0.4, 0, 0.2, 1)',
                                filter: `drop-shadow(0 0 5px ${color})`,
                            }}
                        />
                        {/* End dot */}
                        {animated && (
                            <circle
                                cx={55 + r * Math.cos(((-90 + (score / 10) * 360 - 360) * Math.PI) / 180)}
                                cy={55 + r * Math.sin(((-90 + (score / 10) * 360 - 360) * Math.PI) / 180)}
                                r="4"
                                fill={color}
                                style={{ filter: `drop-shadow(0 0 4px ${color})` }}
                            />
                        )}
                    </svg>
                    {/* Score in center */}
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span
                            className={`text-[40px] font-bold tabular-nums leading-none ${scoreColorClass(score)}`}
                            style={{ fontFamily: "'Space Mono', monospace" }}
                        >
                            {score}
                        </span>
                        <span className="text-[10px] text-slate-600 font-mono mt-0.5">/10</span>
                    </div>
                </div>

                {/* Details */}
                <div className="flex-1 min-w-0">
                    <div className={`text-sm font-semibold mb-2 ${scoreColorClass(score)}`} style={{ color }}>
                        {scoreLabel(score)}
                    </div>
                    <p className="text-xs text-slate-400 leading-relaxed">{rationale}</p>
                </div>
            </div>
        </div>
    )
}

// ─────────────────────────────────────────────────────────
// ANIMATED COUNTER
// ─────────────────────────────────────────────────────────

function AnimatedCounter({ value, delay = 0 }: { value: number; delay?: number }) {
    const [display, setDisplay] = useState(0)

    useEffect(() => {
        const t = setTimeout(() => {
            const duration = 1200
            const start = performance.now()
            const tick = (now: number) => {
                const progress = Math.min((now - start) / duration, 1)
                const eased = 1 - Math.pow(1 - progress, 3)
                setDisplay(Math.round(eased * value))
                if (progress < 1) requestAnimationFrame(tick)
            }
            requestAnimationFrame(tick)
        }, delay)
        return () => clearTimeout(t)
    }, [value, delay])

    return <>{display}</>
}

// ─────────────────────────────────────────────────────────
// HEADER
// ─────────────────────────────────────────────────────────

function Header() {
    return (
        <header className="no-print relative z-20 bg-[#0a0d14]/95 border-b border-[#1e2d42] backdrop-blur-sm">
            <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 border border-[#22d3ee]/40 bg-[#22d3ee]/8 flex items-center justify-center">
                        <Zap size={16} className="text-[#22d3ee]" fill="currentColor" />
                    </div>
                    <div>
                        <div
                            className="text-[20px] text-white leading-none"
                            style={{ fontFamily: "'Syne', sans-serif", fontWeight: 800 }}
                        >
                            Volt<span style={{ color: '#22d3ee' }}>Sage</span>
                        </div>
                        <div className="font-mono text-[9px] tracking-[0.25em] uppercase text-slate-600 mt-0.5">
                            Global EV Advisor
                        </div>
                    </div>
                </div>
                <div className="hidden sm:flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-[#22d3ee] animate-pulse" />
                    <span className="font-mono text-[11px] text-slate-500 tracking-widest">Live · TinyFish Agent</span>
                </div>
            </div>
        </header>
    )
}

// ─────────────────────────────────────────────────────────
// COUNTRY SELECTOR
// ─────────────────────────────────────────────────────────

function CountrySelector({
    countries, selected, onSelect,
}: {
    countries: Country[]
    selected: Country | null
    onSelect: (c: Country) => void
}) {
    const [open, setOpen] = useState(false)
    const [search, setSearch] = useState('')

    const filtered = countries.filter(c =>
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        c.code.toLowerCase().includes(search.toLowerCase())
    )

    return (
        <div className="relative">
            <button
                id="country-selector"
                onClick={() => setOpen(o => !o)}
                className="w-full flex items-center justify-between gap-3 px-4 py-3 bg-[#0d1220] border border-[#1e2d42] hover:border-[#22d3ee]/50 transition-colors group"
            >
                <div className="flex items-center gap-3">
                    <Globe2 size={15} className="text-slate-500 group-hover:text-[#22d3ee] transition-colors flex-shrink-0" />
                    {selected ? (
                        <span className="flex items-center gap-2 text-sm text-white">
                            <span className="text-base">{selected.flag}</span>
                            {selected.name}
                            <span className="text-xs text-slate-500 font-mono ml-1">{selected.currency_symbol}</span>
                        </span>
                    ) : (
                        <span className="text-sm text-slate-500">Select country...</span>
                    )}
                </div>
                <ChevronDown size={14} className={`text-slate-500 transition-transform flex-shrink-0 ${open ? 'rotate-180' : ''}`} />
            </button>

            {open && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-[#0d1220] border border-[#1e2d42] shadow-2xl z-50 overflow-hidden">
                    <div className="p-2 border-b border-[#1e2d42]">
                        <div className="flex items-center gap-2 px-3 py-2 bg-[#07090f]">
                            <Search size={13} className="text-slate-500" />
                            <input
                                autoFocus
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                                placeholder="Search country..."
                                className="flex-1 bg-transparent text-sm text-white placeholder-slate-600 outline-none font-mono"
                            />
                        </div>
                    </div>
                    <div className="max-h-60 overflow-y-auto">
                        {filtered.map(c => (
                            <button
                                key={c.code}
                                onClick={() => { onSelect(c); setOpen(false); setSearch('') }}
                                className={`w-full flex items-center gap-3 px-4 py-2.5 hover:bg-[#111827] transition-colors text-left ${selected?.code === c.code ? 'bg-[#22d3ee]/5' : ''}`}
                            >
                                <span className="text-lg w-7 text-center">{c.flag}</span>
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm text-white">{c.name}</div>
                                    <div className="text-xs text-slate-500 font-mono">{c.currency} · {c.currency_symbol}</div>
                                </div>
                                {selected?.code === c.code && <CheckCircle2 size={13} className="text-[#22d3ee] flex-shrink-0" />}
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}

// ─────────────────────────────────────────────────────────
// RANGE SLIDER
// ─────────────────────────────────────────────────────────

function RangeSlider({
    id, label, value, min, max, step, unit, onChange,
}: {
    id: string; label: string; value: number
    min: number; max: number; step: number; unit: string
    onChange: (v: number) => void
}) {
    const pct = ((value - min) / (max - min)) * 100
    return (
        <div>
            <div className="flex justify-between items-baseline mb-2.5">
                <label htmlFor={id} className="font-mono text-[10px] tracking-[0.18em] uppercase text-slate-500">
                    {label}
                </label>
                <span
                    className="text-sm font-bold tabular-nums"
                    style={{ color: '#22d3ee', fontFamily: "'Space Mono', monospace" }}
                >
                    {value}{unit}
                </span>
            </div>
            <input
                id={id}
                type="range"
                min={min} max={max} step={step} value={value}
                onChange={e => onChange(Number(e.target.value))}
                className="w-full h-px appearance-none cursor-pointer"
                style={{ background: `linear-gradient(to right, #22d3ee ${pct}%, #1e2d42 ${pct}%)` }}
            />
            <div className="flex justify-between font-mono text-[10px] text-slate-700 mt-1.5">
                <span>{min}{unit}</span>
                <span>{max}{unit}</span>
            </div>
        </div>
    )
}

// ─────────────────────────────────────────────────────────
// LOADING PANEL — terminal style
// ─────────────────────────────────────────────────────────

interface LoadingStep {
    id: string; label: string; status: 'pending' | 'active' | 'done' | 'error'; message?: string
}

function LoadingPanel({ steps }: { steps: LoadingStep[] }) {
    const done = steps.filter(s => s.status === 'done').length
    const pct = (done / steps.length) * 100

    return (
        <div className="max-w-lg mx-auto bg-[#0a0d14] border border-[#1e2d42] p-6 animate-fade-up">
            {/* Terminal header bar */}
            <div className="flex items-center gap-2 pb-4 mb-5 border-b border-[#1e2d42]">
                <div className="flex gap-1.5">
                    <div className="w-3 h-3 rounded-full bg-[#f43f5e]/50" />
                    <div className="w-3 h-3 rounded-full bg-[#f59e0b]/50" />
                    <div className="w-3 h-3 rounded-full bg-[#10b981]/50" />
                </div>
                <span className="font-mono text-[10px] tracking-[0.2em] uppercase text-slate-600 ml-2">
                    VoltSage Analysis Engine
                </span>
                <Loader2 size={11} className="text-[#22d3ee] animate-spin ml-auto" />
            </div>

            {/* Steps */}
            <div className="space-y-3.5">
                {steps.map(step => (
                    <div key={step.id} className={`flex items-start gap-3 transition-opacity ${step.status === 'pending' ? 'opacity-20' : 'opacity-100'}`}>
                        <span className={`font-mono text-[11px] flex-shrink-0 mt-px ${step.status === 'done' ? 'text-[#10b981]' : step.status === 'active' ? 'text-[#22d3ee]' : step.status === 'error' ? 'text-[#f43f5e]' : 'text-slate-700'}`}>
                            {step.status === 'done' ? '[✓]' : step.status === 'active' ? '[▶]' : step.status === 'error' ? '[✗]' : '[ ]'}
                        </span>
                        <div className="flex-1 min-w-0">
                            <div className={`font-mono text-[12px] ${step.status === 'active' ? 'text-[#22d3ee]' : step.status === 'done' ? 'text-slate-500' : 'text-slate-700'}`}>
                                {step.label}
                                {step.status === 'active' && <span className="cursor-blink ml-1">_</span>}
                            </div>
                            {step.message && step.status !== 'pending' && (
                                <div className="font-mono text-[11px] text-slate-600 mt-0.5 truncate">{step.message}</div>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            {/* Progress */}
            <div className="mt-6 h-px bg-[#1e2d42] overflow-hidden">
                <div
                    className="h-full transition-all duration-700 ease-out"
                    style={{ width: `${pct}%`, background: '#22d3ee', boxShadow: '0 0 8px #22d3ee88' }}
                />
            </div>
            <div className="mt-1.5 font-mono text-[10px] text-slate-600 flex justify-between">
                <span>Processing...</span>
                <span>{done} / {steps.length}</span>
            </div>
        </div>
    )
}

// ─────────────────────────────────────────────────────────
// BENTO CARD
// ─────────────────────────────────────────────────────────

const SECTION_CONFIG: Record<string, { accent: string; glow: string }> = {
    owners:   { accent: '#a78bfa', glow: 'rgba(167,139,250,0.08)' },
    warnings: { accent: '#f43f5e', glow: 'rgba(244,63,94,0.07)' },
    great:    { accent: '#10b981', glow: 'rgba(16,185,129,0.07)' },
    numbers:  { accent: '#f59e0b', glow: 'rgba(245,158,11,0.07)' },
    score:    { accent: '#22d3ee', glow: 'rgba(34,211,238,0.07)' },
}

function BentoCard({
    icon, title, content, sectionKey, colSpan = 1, delay = 0,
}: {
    icon: string; title: string; content: string
    sectionKey: string; colSpan?: 1 | 2; delay?: number
}) {
    const cfg = SECTION_CONFIG[sectionKey] ?? SECTION_CONFIG.score
    const spanClass = colSpan === 2 ? 'col-span-2' : ''

    return (
        <div
            className={`bento-item relative ${spanClass} bg-[#0d1220] border border-[#1e2d42] rounded-xl p-5 overflow-hidden animate-fade-up`}
            style={{
                animationDelay: `${delay}ms`,
                background: `linear-gradient(135deg, ${cfg.glow}, transparent 60%)`,
            }}
        >
            {/* Corner accent glow */}
            <div
                className="absolute -top-8 -left-8 w-28 h-28 rounded-full blur-2xl pointer-events-none opacity-30"
                style={{ background: cfg.accent }}
            />
            <div className="relative z-10">
                <div className="flex items-center gap-2 mb-3">
                    <span className="text-base leading-none">{icon}</span>
                    <span
                        className="font-mono text-[10px] tracking-[0.2em] uppercase"
                        style={{ color: cfg.accent }}
                    >
                        {title}
                    </span>
                </div>
                <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">{content}</p>
            </div>
        </div>
    )
}

// ─────────────────────────────────────────────────────────
// STATION DONUT — DC / HP / AC breakdown
// ─────────────────────────────────────────────────────────

function StationDonut({ scores, animated }: { scores: VerdictResult['scores']; animated: boolean }) {
    const total = scores.total_stations
    const r = 36, sw = 9
    const C = 2 * Math.PI * r

    const hp     = Math.min(scores.high_power_chargers_50kw_plus, total)
    const dcFast = Math.min(scores.fast_dc_chargers, total)
    const dcOnly = Math.max(0, dcFast - hp)
    const ac     = Math.max(0, total - dcFast)

    const hpLen  = animated && total > 0 ? (hp     / total) * C : 0
    const dcLen  = animated && total > 0 ? (dcOnly / total) * C : 0
    const acLen  = animated && total > 0 ? (ac     / total) * C : 0
    const hpDeg  = total > 0 ? (hp     / total) * 360 : 0
    const dcDeg  = total > 0 ? (dcOnly / total) * 360 : 0

    if (total === 0) {
        return (
            <div className="flex flex-col items-center justify-center gap-2 h-full py-4">
                <svg width="100" height="100" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r={r} fill="none" stroke="#1a2233" strokeWidth={sw} strokeDasharray="3 3" />
                    <text x="50" y="50" textAnchor="middle" dominantBaseline="middle" fill="#334155" fontFamily="monospace" fontSize="8">no stations</text>
                </svg>
            </div>
        )
    }

    return (
        <div className="flex flex-col items-center gap-3 h-full justify-center">
            <div className="relative" style={{ width: 110, height: 110 }}>
                <svg width="110" height="110" viewBox="0 0 100 100" style={{ overflow: 'visible' }}>
                    <circle cx="50" cy="50" r={r} fill="none" stroke="#111827" strokeWidth={sw} />
                    {ac > 0 && (
                        <circle cx="50" cy="50" r={r} fill="none" stroke="#22d3ee" strokeWidth={sw} strokeLinecap="butt"
                            strokeDasharray={`${acLen} ${C - acLen}`}
                            transform={`rotate(${-90 + hpDeg + dcDeg} 50 50)`}
                            style={{ transition: 'stroke-dasharray 1.4s cubic-bezier(0.4,0,0.2,1) 0.4s', filter: 'drop-shadow(0 0 3px #22d3ee50)' }} />
                    )}
                    {dcOnly > 0 && (
                        <circle cx="50" cy="50" r={r} fill="none" stroke="#10b981" strokeWidth={sw} strokeLinecap="butt"
                            strokeDasharray={`${dcLen} ${C - dcLen}`}
                            transform={`rotate(${-90 + hpDeg} 50 50)`}
                            style={{ transition: 'stroke-dasharray 1.2s cubic-bezier(0.4,0,0.2,1) 0.2s', filter: 'drop-shadow(0 0 3px #10b98150)' }} />
                    )}
                    {hp > 0 && (
                        <circle cx="50" cy="50" r={r} fill="none" stroke="#f59e0b" strokeWidth={sw} strokeLinecap="butt"
                            strokeDasharray={`${hpLen} ${C - hpLen}`}
                            transform="rotate(-90 50 50)"
                            style={{ transition: 'stroke-dasharray 1.0s cubic-bezier(0.4,0,0.2,1)', filter: 'drop-shadow(0 0 4px #f59e0b60)' }} />
                    )}
                    <text x="50" y="44" textAnchor="middle" dominantBaseline="middle" fill="white"
                        fontFamily="Space Mono, monospace" fontWeight="bold" fontSize="20">{total}</text>
                    <text x="50" y="58" textAnchor="middle" dominantBaseline="middle" fill="#475569"
                        fontFamily="monospace" fontSize="7.5">STATIONS</text>
                </svg>
            </div>
            <div className="w-full space-y-1.5">
                {([
                    { label: '50kW+ Rapid', count: hp,     color: '#f59e0b' },
                    { label: 'DC Fast',     count: dcOnly, color: '#10b981' },
                    { label: 'AC',          count: ac,     color: '#22d3ee' },
                ] as { label: string; count: number; color: string }[]).filter(s => s.count > 0).map(seg => (
                    <div key={seg.label} className="flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-sm flex-shrink-0" style={{ background: seg.color }} />
                        <span className="font-mono text-[10px] text-slate-500 flex-1">{seg.label}</span>
                        <span className="font-mono text-[10px] font-bold" style={{ color: seg.color }}>{seg.count}</span>
                    </div>
                ))}
            </div>
        </div>
    )
}

// ─────────────────────────────────────────────────────────
// RANGE DEGRADATION CURVE — smooth bezier
// ─────────────────────────────────────────────────────────

function RangeDegradationCurve({ scores, animated }: { scores: VerdictResult['scores']; animated: boolean }) {
    const base  = scores.real_range_used_km
    const city  = Math.round(base * 1.14)
    const hway  = base
    const worst = Math.round(base * 0.72)

    const W = 220, H = 110, PL = 32, PR = 12, PT = 16, PB = 20
    const drawW = W - PL - PR
    const drawH = H - PT - PB
    const maxKm = city * 1.08

    const toY = (km: number) => H - PB - (km / maxKm) * drawH
    const toX = (frac: number) => PL + frac * drawW

    const pts = [
        { x: toX(0),   y: toY(city),  label: 'City',    value: city,  color: '#10b981' },
        { x: toX(0.5), y: toY(hway),  label: 'Highway', value: hway,  color: '#22d3ee' },
        { x: toX(1),   y: toY(worst), label: 'Worst',   value: worst, color: '#f59e0b' },
    ]
    const [p0, p1, p2] = pts
    const bezier = `M${p0.x},${p0.y} C${(p0.x+p1.x)/2},${p0.y} ${(p0.x+p1.x)/2},${p1.y} ${p1.x},${p1.y} C${(p1.x+p2.x)/2},${p1.y} ${(p1.x+p2.x)/2},${p2.y} ${p2.x},${p2.y}`
    const area   = `${bezier} L${p2.x},${H-PB} L${p0.x},${H-PB} Z`

    const dailyX = Math.min(toX(scores.daily_km / city), toX(0.92))
    const occX   = Math.min(toX(scores.occasional_km / city), toX(0.99))

    return (
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: 'visible' }}>
            <defs>
                <linearGradient id="rFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.12" />
                    <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
                </linearGradient>
                <linearGradient id="rStroke" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%"   stopColor="#10b981" />
                    <stop offset="50%"  stopColor="#22d3ee" />
                    <stop offset="100%" stopColor="#f59e0b" />
                </linearGradient>
            </defs>

            {/* Grid */}
            {[0.33, 0.66, 1].map((f, i) => {
                const y = H - PB - f * drawH
                const km = Math.round(maxKm * f)
                return (
                    <g key={i}>
                        <line x1={PL} y1={y} x2={W-PR} y2={y} stroke="#1e2d42" strokeWidth="0.5" />
                        <text x={PL-4} y={y} textAnchor="end" dominantBaseline="middle" fill="#334155" fontFamily="monospace" fontSize="6">{km}</text>
                    </g>
                )
            })}
            <line x1={PL} y1={PT} x2={PL} y2={H-PB} stroke="#1e2d42" strokeWidth="0.5" />

            {/* Area + curve */}
            {animated && <path d={area} fill="url(#rFill)" style={{ transition: 'opacity 0.8s ease' }} />}
            <path d={bezier} fill="none" stroke="url(#rStroke)" strokeWidth="2" strokeLinecap="round"
                style={{ opacity: animated ? 1 : 0, transition: 'opacity 0.8s ease 0.3s', filter: 'drop-shadow(0 0 4px #22d3ee35)' }} />

            {/* Markers: daily */}
            {scores.daily_km < city && (
                <g>
                    <line x1={dailyX} y1={PT} x2={dailyX} y2={H-PB} stroke="#10b981" strokeWidth="1" strokeDasharray="2 2" opacity="0.6" />
                    <text x={dailyX} y={PT-4} textAnchor="middle" fill="#10b981" fontFamily="monospace" fontSize="6.5">daily</text>
                </g>
            )}
            {scores.occasional_km < city * 1.05 && (
                <g>
                    <line x1={occX} y1={PT} x2={occX} y2={H-PB} stroke="#f59e0b" strokeWidth="1" strokeDasharray="2 2" opacity="0.6" />
                    <text x={occX} y={PT-4} textAnchor="middle" fill="#f59e0b" fontFamily="monospace" fontSize="6.5">trip</text>
                </g>
            )}

            {/* Points */}
            {pts.map((p, i) => (
                <g key={i} style={{ opacity: animated ? 1 : 0, transition: `opacity 0.5s ease ${0.3 + i * 0.1}s` }}>
                    <circle cx={p.x} cy={p.y} r="4" fill="#0d1220" stroke={p.color} strokeWidth="1.5" />
                    <text x={p.x} y={p.y - 8} textAnchor="middle" fill="white" fontFamily="monospace" fontSize="8" fontWeight="bold">{p.value}km</text>
                    <text x={p.x} y={H-PB+10} textAnchor="middle" fill={p.color} fontFamily="monospace" fontSize="7">{p.label}</text>
                </g>
            ))}
        </svg>
    )
}

// ─────────────────────────────────────────────────────────
// BATTERY SEMI-ARC
// ─────────────────────────────────────────────────────────

function BatteryArcMini({ kwh, animated }: { kwh: number; animated: boolean }) {
    const r = 30
    const fullC = 2 * Math.PI * r
    const halfC = Math.PI * r
    const pct   = Math.min(1, kwh / 110)
    const fillLen = animated ? halfC * pct : 0
    const color = kwh >= 75 ? '#10b981' : kwh >= 50 ? '#22d3ee' : '#f59e0b'

    return (
        <svg width="80" height="46" viewBox="-6 -6 92 52" style={{ overflow: 'visible' }}>
            {/* Track: top half */}
            <circle cx="40" cy="44" r={r} fill="none" stroke="#1a2233" strokeWidth="8"
                strokeDasharray={`${halfC} ${fullC - halfC}`} strokeDashoffset={halfC / 2}
                transform="rotate(180 40 44)" />
            {/* Fill */}
            <circle cx="40" cy="44" r={r} fill="none" stroke={color} strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={`${fillLen} ${fullC - fillLen}`} strokeDashoffset={halfC / 2}
                transform="rotate(180 40 44)"
                style={{ transition: 'stroke-dasharray 1.3s cubic-bezier(0.4,0,0.2,1)', filter: `drop-shadow(0 0 6px ${color}70)` }} />
            <text x="40" y="32" textAnchor="middle" dominantBaseline="middle" fill="white"
                fontFamily="Space Mono, monospace" fontWeight="bold" fontSize="15">{kwh}</text>
            <text x="40" y="43" textAnchor="middle" dominantBaseline="middle" fill="#475569"
                fontFamily="monospace" fontSize="7.5">kWh</text>
        </svg>
    )
}

// ─────────────────────────────────────────────────────────
// CHARGING SPEED SPECTRUM BAR
// ─────────────────────────────────────────────────────────

function ChargingSpeedSpectrum({ kw, animated }: { kw: number; animated: boolean }) {
    const MAX = 350
    const pct = Math.min(98, (kw / MAX) * 100)
    const zones = [
        { label: 'AC ≤22kW',      start: 0,   end: 22,  color: '#334155' },
        { label: 'DC Fast',        start: 22,  end: 100, color: '#22d3ee' },
        { label: 'Rapid 100–200', start: 100, end: 200, color: '#10b981' },
        { label: 'Hyper 200+',    start: 200, end: 350, color: '#f59e0b' },
    ]
    const carColor = kw <= 22 ? '#64748b' : kw <= 100 ? '#22d3ee' : kw <= 200 ? '#10b981' : '#f59e0b'
    const carLabel = kw <= 22 ? 'Level 2 AC' : kw <= 100 ? 'DC Fast' : kw <= 200 ? 'Rapid DC' : 'Hyper DC'

    return (
        <div>
            <div className="flex items-center justify-between mb-2">
                <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#22d3ee]">Charging Speed Spectrum</div>
                <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px]" style={{ color: carColor }}>{carLabel}</span>
                    <span className="font-mono text-[13px] font-bold" style={{ color: carColor, fontFamily: "'Space Mono', monospace" }}>{kw} kW</span>
                </div>
            </div>
            <div className="relative h-7 rounded overflow-hidden border border-[#1e2d42]">
                {zones.map(z => (
                    <div key={z.label} style={{
                        position: 'absolute', top: 0, bottom: 0,
                        left: `${(z.start / MAX) * 100}%`,
                        width: `${((z.end - z.start) / MAX) * 100}%`,
                        background: z.color, opacity: 0.18,
                        borderRight: '1px solid #1e2d4260',
                    }} />
                ))}
                <div style={{
                    position: 'absolute', top: 0, bottom: 0, width: 3,
                    left: `${animated ? pct : 0}%`,
                    background: carColor,
                    boxShadow: `0 0 12px ${carColor}`,
                    transform: 'translateX(-50%)',
                    transition: 'left 1.5s cubic-bezier(0.4,0,0.2,1)',
                    zIndex: 10,
                }} />
                <div style={{
                    position: 'absolute', top: 0, bottom: 0, left: 0,
                    width: `${animated ? pct : 0}%`,
                    background: `linear-gradient(90deg, transparent, ${carColor}15)`,
                    transition: 'width 1.5s cubic-bezier(0.4,0,0.2,1)',
                }} />
            </div>
            <div className="flex justify-between font-mono text-[9px] text-slate-700 mt-1.5">
                {zones.map(z => <span key={z.label}>{z.label}</span>)}
            </div>
        </div>
    )
}

// ─────────────────────────────────────────────────────────
// VISUALIZATION PANEL
// ─────────────────────────────────────────────────────────

function VisualizationPanel({ result }: { result: VerdictResult }) {
    const { scores } = result
    const [animated, setAnimated] = useState(false)
    const [hoveredAxis, setHoveredAxis] = useState<number | null>(null)
    const [hoveredBar, setHoveredBar] = useState<string | null>(null)

    useEffect(() => {
        setAnimated(false)
        const t = setTimeout(() => setAnimated(true), 350)
        return () => clearTimeout(t)
    }, [result])

    // ── Radar chart ──
    const radarAxes = [
        { label: 'Range',      sub: `${scores.real_range_used_km}km`, value: Math.min(1, scores.real_range_used_km / Math.max(scores.occasional_km * 1.2, 200)) },
        { label: 'Daily Ease', sub: `${10 - scores.daily_score}/10`,  value: (10 - scores.daily_score) / 10 },
        { label: 'Long Trips', sub: `${10 - scores.occasional_score}/10`, value: (10 - scores.occasional_score) / 10 },
        { label: 'Chargers',   sub: `${scores.total_stations}`,        value: Math.min(1, scores.total_stations / 20) },
        { label: 'DC Fast',    sub: `${scores.fast_dc_chargers}`,      value: scores.total_stations > 0 ? Math.min(1, scores.fast_dc_chargers / scores.total_stations) : 0 },
        { label: 'Confidence', sub: scores.confidence,                 value: scores.confidence === 'high' ? 1 : scores.confidence === 'medium' ? 0.6 : 0.3 },
    ]
    const NUM = 6, CX = 90, CY = 90, R = 62

    function axisXY(i: number, r: number) {
        const a = (i * 2 * Math.PI / NUM) - Math.PI / 2
        return { x: CX + r * Math.cos(a), y: CY + r * Math.sin(a) }
    }
    function polyPath(fracs: number[]) {
        return fracs.map((f, i) => { const p = axisXY(i, R * f); return `${i === 0 ? 'M' : 'L'}${p.x},${p.y}` }).join(' ') + 'Z'
    }

    const dataPath   = polyPath(radarAxes.map(ax => animated ? ax.value : 0))
    const dataPoints = radarAxes.map((ax, i) => axisXY(i, R * (animated ? ax.value : 0)))

    // ── Range bars ──
    const maxDist = Math.max(scores.real_range_used_km, scores.occasional_km, scores.daily_km * 3, 50) * 1.1
    const rangeBars = [
        { id: 'range', label: 'Car Range',     value: scores.real_range_used_km, color: '#22d3ee', delay: 0 },
        { id: 'occ',   label: 'Longest Trip',  value: scores.occasional_km,      color: '#f59e0b', delay: 150 },
        { id: 'daily', label: 'Daily Commute', value: scores.daily_km,           color: '#10b981', delay: 300 },
    ]

    // ── Dual rings ──
    const oR = 50, iR = 34
    const oC = 2 * Math.PI * oR, iC = 2 * Math.PI * iR
    const dailyOffset      = animated ? oC * (1 - scores.daily_score / 10) : oC
    const occasionalOffset = animated ? iC * (1 - scores.occasional_score / 10) : iC
    const dailyCol = scoreColor(scores.daily_score)
    const occCol   = scoreColor(scores.occasional_score)

    return (
        <div className="animate-fade-up no-print space-y-3" style={{ animationDelay: '280ms' }}>
            <div className="flex items-center gap-3">
                <span className="font-mono text-[10px] tracking-[0.25em] uppercase text-slate-600">Data Observatory</span>
                <div className="flex-1 h-px bg-[#1e2d42]" />
                <span className="font-mono text-[9px] text-slate-700 tracking-[0.2em]">INTERACTIVE</span>
            </div>

            {/* Row 1: Radar | Anxiety Rings | Station Donut */}
            <div className="grid grid-cols-3 gap-3">

                {/* Radar */}
                <div className="bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4 overflow-hidden">
                    <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#22d3ee] mb-1">Suitability Radar</div>
                    <div className="font-mono text-[9px] text-slate-700 mb-2">hover axes</div>
                    <svg width="100%" viewBox="0 0 180 180">
                        {[0.33, 0.66, 1].map((f, ri) => (
                            <path key={ri} d={polyPath([f,f,f,f,f,f])} fill="none" stroke="#1e2d42" strokeWidth="1" opacity={f === 1 ? 0.7 : 0.35} />
                        ))}
                        {radarAxes.map((_, i) => {
                            const outer = axisXY(i, R)
                            return <line key={i} x1={CX} y1={CY} x2={outer.x} y2={outer.y} stroke="#1e2d42" strokeWidth="1" opacity="0.5" />
                        })}
                        <path d={dataPath} fill="#22d3ee" fillOpacity="0.07" style={{ transition: 'all 1.3s cubic-bezier(0.4,0,0.2,1)' }} />
                        <path d={dataPath} fill="none" stroke="#22d3ee" strokeWidth="1.5"
                            style={{ transition: 'all 1.3s cubic-bezier(0.4,0,0.2,1)', filter: 'drop-shadow(0 0 4px #22d3ee55)' }} />
                        {dataPoints.map((p, i) => (
                            <g key={i} style={{ cursor: 'pointer' }} onMouseEnter={() => setHoveredAxis(i)} onMouseLeave={() => setHoveredAxis(null)}>
                                <circle cx={p.x} cy={p.y} r="10" fill="transparent" />
                                <circle cx={p.x} cy={p.y} r={hoveredAxis === i ? 5 : 3.5}
                                    fill="#0d1220" stroke="#22d3ee" strokeWidth="1.5"
                                    style={{ transition: 'all 1.3s cubic-bezier(0.4,0,0.2,1)', filter: hoveredAxis === i ? 'drop-shadow(0 0 6px #22d3ee)' : 'none' }} />
                            </g>
                        ))}
                        {radarAxes.map((ax, i) => {
                            const lp = axisXY(i, R + 16)
                            const hovered = hoveredAxis === i
                            return (
                                <g key={i}>
                                    <text x={lp.x} y={lp.y} textAnchor="middle" dominantBaseline="middle"
                                        fontSize="7.5" fontFamily="monospace" fill={hovered ? '#22d3ee' : '#475569'}
                                        style={{ transition: 'fill 0.2s' }}>{ax.label}</text>
                                    {hovered && (
                                        <text x={lp.x} y={lp.y + 10} textAnchor="middle" dominantBaseline="middle"
                                            fontSize="7" fontFamily="monospace" fill="#22d3ee" opacity="0.75">{ax.sub}</text>
                                    )}
                                </g>
                            )
                        })}
                    </svg>
                </div>

                {/* Anxiety Rings */}
                <div className="bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4 flex flex-col items-center">
                    <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#22d3ee] mb-3 self-start">Anxiety Rings</div>
                    <div className="relative flex-1 flex items-center justify-center" style={{ minHeight: 130 }}>
                        <svg width="130" height="130" viewBox="0 0 120 120" style={{ overflow: 'visible' }}>
                            <circle cx="60" cy="60" r={oR} fill="none" stroke="#1e2d42" strokeWidth="6" />
                            <circle cx="60" cy="60" r={oR} fill="none" stroke={dailyCol} strokeWidth="6"
                                strokeLinecap="round" strokeDasharray={oC} strokeDashoffset={dailyOffset}
                                transform="rotate(-90 60 60)"
                                style={{ transition: 'stroke-dashoffset 1.4s cubic-bezier(0.4,0,0.2,1)', filter: `drop-shadow(0 0 5px ${dailyCol})` }} />
                            <circle cx="60" cy="60" r={iR} fill="none" stroke="#1e2d42" strokeWidth="6" />
                            <circle cx="60" cy="60" r={iR} fill="none" stroke={occCol} strokeWidth="6"
                                strokeLinecap="round" strokeDasharray={iC} strokeDashoffset={occasionalOffset}
                                transform="rotate(-90 60 60)"
                                style={{ transition: 'stroke-dashoffset 1.4s cubic-bezier(0.4,0,0.2,1) 0.25s', filter: `drop-shadow(0 0 5px ${occCol})` }} />
                        </svg>
                        <div className="absolute inset-0 flex flex-col items-center justify-center gap-0.5">
                            <span className="font-mono text-[18px] font-bold leading-none" style={{ color: dailyCol }}>{scores.daily_score}</span>
                            <span className="font-mono text-[9px] text-slate-700">·</span>
                            <span className="font-mono text-[18px] font-bold leading-none" style={{ color: occCol }}>{scores.occasional_score}</span>
                        </div>
                    </div>
                    <div className="w-full mt-3 space-y-1.5">
                        {[
                            { label: 'Daily commute', score: scores.daily_score, color: dailyCol },
                            { label: 'Long trips',    score: scores.occasional_score, color: occCol },
                        ].map(row => (
                            <div key={row.label} className="flex items-center gap-2">
                                <div className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: row.color }} />
                                <span className="font-mono text-[10px] text-slate-500 flex-1">{row.label}</span>
                                <span className="font-mono text-[10px]" style={{ color: row.color }}>{scoreLabel(row.score)}</span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Station Donut */}
                <div className="bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4">
                    <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#22d3ee] mb-3">Station Breakdown</div>
                    <StationDonut scores={scores} animated={animated} />
                </div>
            </div>

            {/* Row 2: Range Bars | Range Degradation Curve */}
            <div className="grid grid-cols-2 gap-3">

                {/* Range Bars */}
                <div className="bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4">
                    <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#22d3ee] mb-1">Range vs Trips</div>
                    <div className="font-mono text-[9px] text-slate-700 mb-4">hover bars</div>
                    <div className="space-y-4">
                        {rangeBars.map(bar => {
                            const pct = animated ? Math.min(100, (bar.value / maxDist) * 100) : 0
                            const isOver = bar.id === 'occ' && bar.value > scores.real_range_used_km
                            const col = isOver ? '#f43f5e' : bar.color
                            const isHov = hoveredBar === bar.id
                            return (
                                <div key={bar.id} onMouseEnter={() => setHoveredBar(bar.id)} onMouseLeave={() => setHoveredBar(null)}>
                                    <div className="flex justify-between mb-1.5">
                                        <span className="font-mono text-[10px] text-slate-500">{bar.label}</span>
                                        <span className="font-mono text-[10px] tabular-nums" style={{ color: col }}>{bar.value}km</span>
                                    </div>
                                    <div className="h-2 bg-[#070910] border border-[#1e2d42] overflow-hidden relative">
                                        <div style={{
                                            position: 'absolute', inset: '0 auto 0 0', width: `${pct}%`,
                                            background: col,
                                            boxShadow: isHov ? `0 0 10px ${col}` : `0 0 4px ${col}60`,
                                            transition: `width 1s cubic-bezier(0.4,0,0.2,1) ${bar.delay}ms, box-shadow 0.2s`,
                                        }} />
                                    </div>
                                    {isHov && <div className="font-mono text-[9px] mt-1" style={{ color: col }}>{Math.round(pct)}% of scale · {bar.value}km</div>}
                                </div>
                            )
                        })}
                    </div>
                    <div className="mt-5 pt-3 border-t border-[#1e2d42] font-mono text-[10px]"
                        style={{ color: scores.real_range_used_km >= scores.occasional_km ? '#10b981' : '#f59e0b' }}>
                        {scores.real_range_used_km >= scores.occasional_km
                            ? `✓ Range covers all trips`
                            : `⚠ ${scores.occasional_km - scores.real_range_used_km}km gap on longest trip`}
                    </div>
                </div>

                {/* Range Degradation Curve */}
                <div className="bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4">
                    <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#22d3ee] mb-1">Range Degradation</div>
                    <div className="font-mono text-[9px] text-slate-700 mb-3">city → highway → worst case</div>
                    <RangeDegradationCurve scores={scores} animated={animated} />
                </div>
            </div>

            {/* Row 3: Charging Speed Spectrum (full width) */}
            <div className="bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4">
                <ChargingSpeedSpectrum
                    kw={result.vehicle_details?.dc_fast_charge_kw ?? scores.fast_dc_chargers}
                    animated={animated}
                />
            </div>

            {/* Row 4: Live Stations */}
            {result.stations && result.stations.length > 0 && (
                <div className="bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4">
                    <div className="flex items-center gap-3 mb-3">
                        <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#22d3ee]">
                            Live Charging Stations · {result.city}
                        </div>
                        <div className="flex items-center gap-1.5 ml-auto">
                            <div className="w-1.5 h-1.5 rounded-full bg-[#10b981] animate-pulse" />
                            <span className="font-mono text-[9px] text-[#10b981]">{result.stations.length} found via TinyFish</span>
                        </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 max-h-52 overflow-y-auto pr-1"
                        style={{ scrollbarWidth: 'thin', scrollbarColor: '#1e2d42 transparent' }}>
                        {result.stations.map((s: ChargerStation, i: number) => {
                            const isDC = s.connector_types.some(ct => ct.toUpperCase().includes('DC'))
                            const accentColor = isDC ? '#10b981' : '#22d3ee'
                            return (
                                <div key={i}
                                    className="flex items-start gap-2.5 p-2.5 border border-[#1e2d42] rounded-lg hover:border-[#22d3ee]/30 transition-colors"
                                    style={{ background: '#070910' }}>
                                    <div className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0"
                                        style={{ background: accentColor, boxShadow: `0 0 4px ${accentColor}` }} />
                                    <div className="min-w-0">
                                        <div className="font-mono text-[11px] text-slate-300 truncate leading-tight">{s.name}</div>
                                        <div className="font-mono text-[10px] text-slate-600 truncate mt-0.5">{s.address}</div>
                                        <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                                            {s.connector_types.map((ct, j) => (
                                                <span key={j} className="font-mono text-[9px] px-1.5 py-0.5 rounded"
                                                    style={{ background: isDC ? '#10b98115' : '#22d3ee15', color: accentColor, border: `1px solid ${accentColor}25` }}>
                                                    {ct}
                                                </span>
                                            ))}
                                            {s.connector_types.length === 0 && <span className="font-mono text-[9px] text-slate-700">AC</span>}
                                            {s.power_kw > 0 && <span className="font-mono text-[9px] text-slate-600">{s.power_kw}kW</span>}
                                        </div>
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                </div>
            )}
        </div>
    )
}

// ─────────────────────────────────────────────────────────
// VEHICLE SPECS PANEL — live vehicle intelligence
// ─────────────────────────────────────────────────────────

function VehicleSpecsPanel({ result }: { result: VerdictResult }) {
    const vd = result.vehicle_details as (VehicleDetails & { source_type?: string }) | undefined
    const [animated, setAnimated] = useState(false)

    useEffect(() => {
        const t = setTimeout(() => setAnimated(true), 300)
        return () => clearTimeout(t)
    }, [])

    const battery  = vd?.battery_kwh      ?? 0
    const dcKw     = vd?.dc_fast_charge_kw ?? 0
    const isFast   = vd?.is_fast_charging  ?? dcKw >= 50
    const dcColor  = dcKw > 150 ? '#10b981' : dcKw > 50 ? '#22d3ee' : '#f59e0b'

    return (
        <div className="animate-fade-up no-print space-y-3" style={{ animationDelay: '340ms' }}>
            <div className="flex items-center gap-3">
                <span className="font-mono text-[10px] tracking-[0.25em] uppercase text-slate-600">Vehicle Intelligence</span>
                <div className="flex-1 h-px bg-[#1e2d42]" />
                {vd?.source_type === 'live' ? (
                    <div className="flex items-center gap-1.5">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#10b981] animate-pulse" />
                        <span className="font-mono text-[9px] text-[#10b981]">Live scraped</span>
                    </div>
                ) : (
                    <span className="font-mono text-[9px] text-slate-700">Static profile</span>
                )}
            </div>

            {/* Row 1: Price | Battery Arc | DC Speed | IoT */}
            <div className="grid grid-cols-4 gap-3">

                {/* Price */}
                <div className="bg-[#0d1220] border border-[#22d3ee]/15 rounded-xl p-4 flex flex-col items-center justify-center text-center"
                    style={{ background: 'linear-gradient(135deg, rgba(34,211,238,0.05), transparent)' }}>
                    <div className="font-mono text-[9px] tracking-[0.2em] uppercase text-slate-600 mb-2">Local Price</div>
                    {vd?.price_formatted ? (
                        <div className="text-lg font-bold leading-tight" style={{ color: '#22d3ee', fontFamily: "'Space Mono', monospace" }}>
                            {vd.price_formatted}
                        </div>
                    ) : (
                        <div className="font-mono text-[11px] text-slate-700 italic">Fetching...</div>
                    )}
                    <div className="font-mono text-[9px] text-slate-700 mt-1">{result.city}</div>
                </div>

                {/* Battery Arc */}
                <div className="bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4 flex flex-col items-center justify-center">
                    <div className="font-mono text-[9px] tracking-[0.2em] uppercase text-slate-600 mb-2">Battery</div>
                    <BatteryArcMini kwh={battery} animated={animated} />
                </div>

                {/* DC Fast Charge */}
                <div className="bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4 flex flex-col items-center justify-center text-center">
                    <div className="font-mono text-[9px] tracking-[0.2em] uppercase text-slate-600 mb-2">Max Charge Rate</div>
                    <div className="text-[28px] font-bold leading-none tabular-nums"
                        style={{ color: dcColor, fontFamily: "'Space Mono', monospace" }}>
                        {dcKw}<span className="text-sm text-slate-600 ml-1">kW</span>
                    </div>
                    <div className="font-mono text-[9px] mt-1.5" style={{ color: isFast ? '#10b981' : '#64748b' }}>
                        {isFast ? 'DC Fast Capable' : 'AC Only'}
                    </div>
                </div>

                {/* IoT / Connected Car */}
                <div className="bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4 flex flex-col items-center justify-center text-center">
                    <div className="font-mono text-[9px] tracking-[0.2em] uppercase text-slate-600 mb-3">Connected Car</div>
                    {vd?.iot_map_available === true ? (
                        <div className="flex flex-col items-center gap-2">
                            <div className="w-10 h-10 rounded-full border border-[#22d3ee]/40 flex items-center justify-center"
                                style={{ boxShadow: '0 0 16px #22d3ee25', background: 'rgba(34,211,238,0.06)' }}>
                                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                                    <path d="M1 6 C1 6 4.5 2.5 9 2.5 C13.5 2.5 17 6 17 6" stroke="#22d3ee" strokeWidth="1.5" strokeLinecap="round" opacity="0.4" />
                                    <path d="M3.5 9 C3.5 9 5.8 7 9 7 C12.2 7 14.5 9 14.5 9" stroke="#22d3ee" strokeWidth="1.5" strokeLinecap="round" opacity="0.7" />
                                    <path d="M6.5 12 C6.5 12 7.6 11 9 11 C10.4 11 11.5 12 11.5 12" stroke="#22d3ee" strokeWidth="1.5" strokeLinecap="round" />
                                    <circle cx="9" cy="15" r="1.2" fill="#22d3ee" />
                                </svg>
                            </div>
                            <span className="font-mono text-[9px] text-[#22d3ee]">IoT Available</span>
                        </div>
                    ) : vd?.iot_map_available === false ? (
                        <div className="font-mono text-[11px] text-slate-700">Not Available</div>
                    ) : (
                        <div className="font-mono text-[11px] text-slate-700 italic">Unknown</div>
                    )}
                </div>
            </div>

            {/* Row 2: Charger Type + Warranty | Showrooms */}
            <div className="grid grid-cols-3 gap-3">

                {/* Connector + Warranty */}
                <div className="bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4 space-y-4">
                    <div>
                        <div className="font-mono text-[9px] tracking-[0.2em] uppercase text-slate-600 mb-2">Connector Standard</div>
                        {vd?.charger_type ? (
                            <div className="inline-block px-3 py-1 border border-[#22d3ee]/30 bg-[#22d3ee]/5 font-mono text-sm font-bold text-[#22d3ee]">
                                {vd.charger_type}
                            </div>
                        ) : (
                            <div className="font-mono text-[11px] text-slate-700">—</div>
                        )}
                    </div>
                    <div className="border-t border-[#1e2d42] pt-4">
                        <div className="font-mono text-[9px] tracking-[0.2em] uppercase text-slate-600 mb-2">Battery Warranty</div>
                        {vd?.battery_warranty ? (
                            <div className="font-mono text-[12px] text-[#10b981] leading-relaxed">{vd.battery_warranty}</div>
                        ) : (
                            <div className="font-mono text-[11px] text-slate-700">—</div>
                        )}
                    </div>
                </div>

                {/* Showrooms */}
                <div className="col-span-2 bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4">
                    <div className="flex items-center gap-2 mb-3">
                        <div className="font-mono text-[9px] tracking-[0.2em] uppercase text-slate-600">
                            Showrooms &amp; Dealers · {result.city}
                        </div>
                        {(vd?.showrooms?.length ?? 0) > 0 && (
                            <span className="font-mono text-[9px] text-[#10b981] ml-auto">{vd!.showrooms.length} found</span>
                        )}
                    </div>
                    {(vd?.showrooms?.length ?? 0) > 0 ? (
                        <div className="space-y-1.5 max-h-44 overflow-y-auto pr-1"
                            style={{ scrollbarWidth: 'thin', scrollbarColor: '#1e2d42 transparent' }}>
                            {vd!.showrooms.map((s, i) => (
                                <div key={i}
                                    className="flex items-start gap-2.5 p-2.5 border border-[#1e2d42] rounded-lg hover:border-[#22d3ee]/30 hover:bg-[#22d3ee]/3 transition-all cursor-default"
                                    style={{ background: '#070910' }}>
                                    <div className="w-5 h-5 flex-shrink-0 flex items-center justify-center border border-[#1e2d42] rounded font-mono text-[9px] text-slate-600 bg-[#0d1220]">
                                        {i + 1}
                                    </div>
                                    <div className="min-w-0">
                                        <div className="font-mono text-[11px] text-slate-300 leading-tight">{s.name || '—'}</div>
                                        {s.address && (
                                            <div className="font-mono text-[10px] text-slate-600 mt-0.5 truncate">{s.address}</div>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="font-mono text-[11px] text-slate-700 italic py-4 text-center">
                            No showroom data scraped for {result.city}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}

// ─────────────────────────────────────────────────────────
// RESULT DASHBOARD
// ─────────────────────────────────────────────────────────

function ResultDashboard({ result, onReset }: { result: VerdictResult; onReset: () => void }) {
    const { scores } = result

    // Parse verdict sections by emoji markers
    const markers = [
        { emoji: '🔋', title: 'Charging Anxiety Score', key: 'score' },
        { emoji: '📊', title: 'What Real Owners Experience', key: 'owners' },
        { emoji: '⚠️', title: 'Things Nobody Tells You', key: 'warnings' },
        { emoji: '💚', title: "What's Genuinely Great", key: 'great' },
        { emoji: '💰', title: 'Your Actual Numbers', key: 'numbers' },
        { emoji: '🎯', title: 'Honest Verdict', key: 'verdict' },
    ]

    type Section = { icon: string; title: string; content: string; key: string }
    const sections: Section[] = []
    let remaining = result.verdict.trim()

    for (let i = 0; i < markers.length; i++) {
        const m = markers[i], nextM = markers[i + 1]
        const startIdx = remaining.indexOf(m.emoji)
        if (startIdx === -1) continue
        const endIdx = nextM ? remaining.indexOf(nextM.emoji, startIdx + 1) : -1
        const content = endIdx > -1
            ? remaining.slice(startIdx + m.emoji.length, endIdx).trim()
            : remaining.slice(startIdx + m.emoji.length).trim()
        sections.push({ icon: m.emoji, title: m.title, content, key: m.key })
    }

    const sm = Object.fromEntries(sections.map(s => [s.key, s]))

    const handlePDF = () => {
        const prev = document.title
        document.title = `VoltSage Report — ${result.car} in ${result.city}`
        window.print()
        setTimeout(() => { document.title = prev }, 1500)
    }

    return (
        <div className="print-page space-y-4">
            {/* Print-only header (hidden on screen) */}
            <div className="print-only hidden border-b-2 border-gray-300 pb-4 mb-6">
                <div style={{ fontFamily: 'Syne, sans-serif', fontSize: '24pt', fontWeight: 800 }}>
                    VoltSage — EV Analysis Report
                </div>
                <div style={{ fontFamily: 'Space Mono, monospace', fontSize: '10pt', color: '#555', marginTop: '4pt' }}>
                    {result.car} · {result.city}, {result.country} · Generated {new Date().toLocaleDateString()}
                </div>
            </div>

            {/* Dashboard header */}
            <div className="flex items-start justify-between gap-4 no-print-layout">
                <div>
                    <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#22d3ee] mb-1.5">
                        Analysis Complete
                    </div>
                    <h2
                        className="text-2xl text-white tracking-tight leading-tight"
                        style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700 }}
                    >
                        {result.car}
                    </h2>
                    <div className="flex items-center gap-2 mt-1.5 text-sm text-slate-500">
                        <MapPin size={12} className="flex-shrink-0" />
                        <span>{result.city}, {result.country}</span>
                        <span className="text-slate-700">·</span>
                        <span className="font-mono">{result.currency_symbol} {result.currency}</span>
                    </div>
                </div>
                <div className="no-print flex items-center gap-2 flex-shrink-0">
                    <button
                        onClick={handlePDF}
                        className="flex items-center gap-1.5 px-3 py-2 font-mono text-[11px] text-slate-400 border border-[#1e2d42] hover:text-[#22d3ee] hover:border-[#22d3ee]/40 transition-colors"
                        title="Download as PDF"
                    >
                        <Download size={12} />
                        PDF
                    </button>
                    <button
                        onClick={onReset}
                        className="flex items-center gap-1.5 px-3 py-2 font-mono text-[11px] text-slate-400 border border-[#1e2d42] hover:text-[#22d3ee] hover:border-[#22d3ee]/40 transition-colors"
                    >
                        <RefreshCw size={11} />
                        New
                    </button>
                </div>
            </div>

            {/* ── Score Gauges ── */}
            <div className="grid grid-cols-2 gap-4">
                <CircularGauge
                    score={scores.daily_score}
                    label="Daily Commute"
                    rationale={scores.daily_rationale}
                    delay={0}
                />
                <CircularGauge
                    score={scores.occasional_score}
                    label="Long Trips"
                    rationale={scores.occasional_rationale}
                    delay={180}
                />
            </div>

            {/* ── Stats strip ── */}
            <div className="grid grid-cols-3 gap-3">
                {[
                    { label: 'Total Stations', value: scores.total_stations, icon: Battery, color: '#22d3ee', delay: 100 },
                    { label: 'DC Fast Chargers', value: scores.fast_dc_chargers, icon: Zap, color: '#10b981', delay: 180 },
                    { label: '50kW+ Rapid', value: scores.high_power_chargers_50kw_plus, icon: TrendingDown, color: '#f59e0b', delay: 260 },
                ].map((stat) => {
                    const Icon = stat.icon
                    return (
                        <div
                            key={stat.label}
                            className="bento-item bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4 text-center animate-fade-up"
                            style={{ animationDelay: `${stat.delay}ms` }}
                        >
                            <Icon size={14} className="mx-auto mb-2.5" style={{ color: stat.color }} />
                            <div
                                className="text-[32px] font-bold tabular-nums leading-none"
                                style={{ color: stat.color, fontFamily: "'Space Mono', monospace" }}
                            >
                                <AnimatedCounter value={stat.value} delay={stat.delay + 200} />
                            </div>
                            <div className="font-mono text-[10px] text-slate-600 mt-1.5 uppercase tracking-widest leading-tight">
                                {stat.label}
                            </div>
                        </div>
                    )
                })}
            </div>

            {/* ── Visualization Panel ── */}
            <VisualizationPanel result={result} />

            {/* ── Vehicle Specs Panel ── */}
            {result.vehicle_details && <VehicleSpecsPanel result={result} />}

            {/* ── Bento verdict grid ── */}
            {sections.length > 0 ? (
                <div className="bento-grid grid grid-cols-3 gap-3">
                    {/* Row 1: Owners (wide) + Warnings (narrow) */}
                    {sm.owners && (
                        <BentoCard icon={sm.owners.icon} title={sm.owners.title}
                            content={sm.owners.content} sectionKey="owners" colSpan={2} delay={80} />
                    )}
                    {sm.warnings && (
                        <BentoCard icon={sm.warnings.icon} title={sm.warnings.title}
                            content={sm.warnings.content} sectionKey="warnings" colSpan={1} delay={140} />
                    )}

                    {/* Row 2: What's great (narrow) + Numbers (wide) */}
                    {sm.great && (
                        <BentoCard icon={sm.great.icon} title={sm.great.title}
                            content={sm.great.content} sectionKey="great" colSpan={1} delay={200} />
                    )}
                    {sm.numbers && (
                        <BentoCard icon={sm.numbers.icon} title={sm.numbers.title}
                            content={sm.numbers.content} sectionKey="numbers" colSpan={2} delay={260} />
                    )}

                    {/* Row 3: Verdict — full width, special treatment */}
                    {sm.verdict && (
                        <div
                            className="verdict-card col-span-3 bento-item relative bg-[#0d1220] border border-[#22d3ee]/25 rounded-xl p-6 overflow-hidden animate-fade-up"
                            style={{
                                animationDelay: '360ms',
                                background: 'linear-gradient(135deg, rgba(34,211,238,0.07) 0%, rgba(34,211,238,0.02) 40%, transparent 70%)',
                            }}
                        >
                            {/* Background glow */}
                            <div className="absolute -top-16 -right-16 w-48 h-48 rounded-full bg-[#22d3ee]/6 blur-3xl pointer-events-none" />

                            <div className="relative z-10">
                                <div className="flex items-center gap-2.5 mb-4">
                                    <span className="text-lg leading-none">{sm.verdict.icon}</span>
                                    <span className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#22d3ee]">
                                        Honest Verdict
                                    </span>
                                    <div className="flex-1 h-px bg-[#22d3ee]/15 ml-2" />
                                </div>
                                <p
                                    className="text-[17px] text-slate-100 leading-relaxed"
                                    style={{ fontFamily: "'Outfit', sans-serif", fontStyle: 'italic', fontWeight: 500 }}
                                >
                                    {sm.verdict.content}
                                </p>
                            </div>
                        </div>
                    )}
                </div>
            ) : (
                /* Fallback if no emoji markers in verdict */
                <div className="bento-item bg-[#0d1220] border border-[#1e2d42] rounded-xl p-5">
                    <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">{result.verdict}</p>
                </div>
            )}

            {/* ── Incentives ── */}
            {result.incentives?.headline && (
                <div
                    className="bento-item bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4 flex items-start gap-3 animate-fade-up"
                    style={{ animationDelay: '460ms' }}
                >
                    <Shield size={14} className="text-[#22d3ee] mt-0.5 flex-shrink-0" />
                    <div>
                        <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#22d3ee] mb-1.5">
                            Government Incentives
                        </div>
                        <p className="text-sm text-slate-300">{result.incentives.headline}</p>
                        <p className="font-mono text-[11px] text-slate-600 mt-1">{result.incentives.source}</p>
                    </div>
                </div>
            )}

            {/* ── Sources & Freshness ── */}
            <div
                className="grid grid-cols-2 gap-3 animate-fade-up"
                style={{ animationDelay: '520ms' }}
            >
                <div className="bento-item bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4">
                    <div className="font-mono text-[10px] tracking-[0.18em] uppercase text-slate-600 mb-2">Data Sources</div>
                    <div className="flex flex-wrap gap-1.5">
                        {result.sources_used.map((s, i) => (
                            <span key={i} className="font-mono text-[10px] px-2 py-0.5 border border-[#1e2d42] text-slate-500">
                                {s}
                            </span>
                        ))}
                    </div>
                </div>
                <div className="bento-item bg-[#0d1220] border border-[#1e2d42] rounded-xl p-4">
                    <div className="font-mono text-[10px] tracking-[0.18em] uppercase text-slate-600 mb-2">Data Freshness</div>
                    <div className="space-y-0.5 font-mono text-[11px] text-slate-500">
                        <div>Chargers: {result.data_freshness.chargers.source_type} · {result.data_freshness.chargers.fetched_at ? new Date(result.data_freshness.chargers.fetched_at).toLocaleTimeString() : 'N/A'}</div>
                        <div>Reviews: {result.data_freshness.owner_reviews.source_type} · TinyFish</div>
                    </div>
                </div>
            </div>
        </div>
    )
}

// ─────────────────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────────────────

const INITIAL_STEPS = [
    { id: 'chargers', label: 'Scraping live charging stations',          status: 'pending' as const },
    { id: 'owners',   label: 'Reading owner forum reviews',              status: 'pending' as const },
    { id: 'specs',    label: 'Fetching local prices & showrooms',        status: 'pending' as const },
    { id: 'scoring',  label: 'Calculating anxiety scores',               status: 'pending' as const },
    { id: 'llm',      label: 'Synthesising honest verdict (AI)',         status: 'pending' as const },
]

export default function HomePage() {
    const [countries, setCountries]             = useState<Country[]>([])
    const [selectedCountry, setSelectedCountry] = useState<Country | null>(null)
    const [evModels, setEvModels]               = useState<EvModel[]>([])
    const [loadingCountries, setLoadingCountries] = useState(true)
    const [loadingModels, setLoadingModels]     = useState(false)
    const [form, setForm]                       = useState<FormState>({
        country: '', city: '',
        carModel: '',
        dailyKm: 40, occasionalKm: 300,
        hasHomeCharging: false, currency: '',
    })
    const [isStreaming, setIsStreaming]          = useState(false)
    const [loadingSteps, setLoadingSteps]       = useState<LoadingStep[]>(INITIAL_STEPS)
    const [result, setResult]                   = useState<VerdictResult | null>(null)
    const [error, setError]                     = useState<string | null>(null)
    const [userId]                              = useState(generateUserId)

    useEffect(() => {
        fetchCountries()
            .then(data => {
                setCountries(data.countries)
            })
            .catch(() => setError('Failed to load countries. Is the backend running?'))
            .finally(() => setLoadingCountries(false))
    }, [])

    useEffect(() => {
        if (!form.country) return
        setLoadingModels(true)
        setEvModels([])
        let streamClosed = false
        let gotAnyModels = false
        let didLiveFetchAfterStream = false

        const runLiveFetchIfNeeded = () => {
            if (didLiveFetchAfterStream || gotAnyModels) return
            didLiveFetchAfterStream = true
            fetchEVDatabase(form.country)
                .then(resp => {
                    const liveModels = (resp.models || []) as EvModel[]
                    if (liveModels.length > 0) {
                        gotAnyModels = true
                        setEvModels(liveModels)
                        setForm(prev => {
                            const hasCurrent = liveModels.some(m => m.name === prev.carModel)
                            if (hasCurrent) return prev
                            return { ...prev, carModel: liveModels[0].name }
                        })
                    }
                })
                .finally(() => setLoadingModels(false))
        }

        const cleanup = streamEVDatabase(form.country, (event) => {
            if (event.type === 'MODELS_PARTIAL' || event.type === 'COMPLETE') {
                const data = event.data as { models?: EvModel[]; data?: { models?: EvModel[] } } | undefined
                const models = data?.models || data?.data?.models || []
                if (models.length > 0) {
                    gotAnyModels = true
                    setEvModels(models)
                }
                setForm(prev => {
                    if (!models.length) return prev
                    const hasCurrent = models.some(m => m.name === prev.carModel)
                    if (hasCurrent) return prev
                    return { ...prev, carModel: models[0].name }
                })
                if (event.type === 'COMPLETE') {
                    setLoadingModels(false)
                    if (!gotAnyModels && streamClosed) runLiveFetchIfNeeded()
                }
            } else if (event.type === 'ERROR') {
                runLiveFetchIfNeeded()
            } else if (event.type === 'STREAM_CLOSED') {
                streamClosed = true
                if (!gotAnyModels) runLiveFetchIfNeeded()
            }
        })
        return () => {
            cleanup()
            setLoadingModels(false)
        }
    }, [form.country])

    const handleCountrySelect = useCallback((c: Country) => {
        setSelectedCountry(c)
        setForm(f => ({ ...f, country: c.code, currency: c.currency, city: c.cities[0] || '' }))
    }, [])

    const updateStep = useCallback((id: string, status: LoadingStep['status'], message?: string) => {
        setLoadingSteps(prev => prev.map(s => s.id === id ? { ...s, status, message } : s))
    }, [])

    const handleSubmit = useCallback(() => {
        if (!form.country || !form.carModel || !form.city) return
        setIsStreaming(true)
        setResult(null)
        setError(null)
        setLoadingSteps(INITIAL_STEPS)

        const cleanup = streamVerdict(
            {
                country: form.country, city: form.city, car_model: form.carModel,
                daily_km: form.dailyKm, occasional_km: form.occasionalKm,
                has_home_charging: form.hasHomeCharging, currency: form.currency, user_id: userId,
            },
            event => {
                switch (event.type) {
                    case 'SCRAPING_CHARGERS': updateStep('chargers', 'active', event.message); break
                    case 'CHARGERS_DONE':     updateStep('chargers', 'done',   event.message); break
                    case 'SCRAPING_OWNERS':   updateStep('owners',   'active', event.message); break
                    case 'OWNERS_DONE':       updateStep('owners',   'done',   event.message); break
                    case 'SCRAPING_SPECS':    updateStep('specs',    'active', event.message); break
                    case 'SPECS_DONE':        updateStep('specs',    'done',   event.message); break
                    case 'SCORING':           updateStep('scoring',  'active', event.message); break
                    case 'LLM':
                        updateStep('scoring', 'done')
                        updateStep('llm', 'active', event.message)
                        break
                    case 'COMPLETE':
                        updateStep('llm', 'done')
                        setResult(event.data as VerdictResult)
                        setIsStreaming(false)
                        break
                    case 'ERROR':
                        setError(event.message || 'Something went wrong')
                        setIsStreaming(false)
                        break
                }
            }
        )
        return () => cleanup()
    }, [form, userId, updateStep])

    const handleReset = useCallback(() => {
        setResult(null); setError(null)
        setIsStreaming(false); setLoadingSteps(INITIAL_STEPS)
    }, [])

    const showForm = !result && !isStreaming

    return (
        <div className="relative min-h-screen bg-[#07090f]">
            <Header />

            <main className="relative z-10 max-w-5xl mx-auto px-6 py-10">

                {/* ── FORM ── */}
                {showForm && (
                    <div className="animate-fade-up" style={{ animationDelay: '0ms' }}>
                        {/* Hero */}
                        <div className="text-center mb-10 pt-2">
                            <div className="inline-flex items-center gap-2 px-3 py-1.5 border border-[#1e2d42] bg-[#0d1220] font-mono text-[11px] text-slate-500 mb-7">
                                <div className="w-1.5 h-1.5 rounded-full bg-[#22d3ee] animate-pulse" />
                                Live data · {countries.length || 16} countries · TinyFish powered
                            </div>
                            <h1
                                className="text-5xl sm:text-6xl text-white tracking-tight leading-[1.05] mb-4"
                                style={{ fontFamily: "'Syne', sans-serif", fontWeight: 800 }}
                            >
                                The world&apos;s most{' '}
                                <span style={{ color: '#22d3ee' }}>honest</span>
                                <br />EV advisor
                            </h1>
                            <p className="text-slate-500 text-base max-w-md mx-auto leading-relaxed">
                                Real data from real owners, live-scraped charging networks,
                                and AI synthesis — for any EV, anywhere on Earth.
                            </p>
                        </div>

                        {/* Form card */}
                        <div className="max-w-sm mx-auto space-y-3">
                            <div className="bg-[#0d1220] border border-[#1e2d42] p-6 space-y-5">
                                <div className="font-mono text-[10px] tracking-[0.22em] uppercase text-[#22d3ee] pb-3 border-b border-[#1e2d42]">
                                    Configure Analysis
                                </div>

                                {/* Country */}
                                <div>
                                    <div className="font-mono text-[10px] tracking-[0.18em] uppercase text-slate-600 mb-2">Country</div>
                                    {loadingCountries ? (
                                        <div className="h-12 animate-shimmer" />
                                    ) : (
                                        <CountrySelector countries={countries} selected={selectedCountry} onSelect={handleCountrySelect} />
                                    )}
                                </div>

                                {/* City */}
                                <div>
                                    <div className="font-mono text-[10px] tracking-[0.18em] uppercase text-slate-600 mb-2">City</div>
                                    {selectedCountry?.cities.length ? (
                                        <select
                                            id="city-select"
                                            value={form.city}
                                            onChange={e => setForm(f => ({ ...f, city: e.target.value }))}
                                            className="w-full px-4 py-3 bg-[#0d1220] border border-[#1e2d42] text-sm text-white outline-none hover:border-[#22d3ee]/40 focus:border-[#22d3ee]/60 transition-colors appearance-none cursor-pointer"
                                            style={{ colorScheme: 'dark' }}
                                        >
                                            {selectedCountry.cities.map(city => (
                                                <option key={city} value={city}>{city}</option>
                                            ))}
                                            <option value="__custom__">Other (type below)</option>
                                        </select>
                                    ) : null}
                                    {(form.city === '__custom__' || !selectedCountry?.cities.includes(form.city)) && (
                                        <input
                                            type="text"
                                            placeholder="Enter city name..."
                                            value={form.city === '__custom__' ? '' : form.city}
                                            onChange={e => setForm(f => ({ ...f, city: e.target.value }))}
                                            className="mt-2 w-full px-4 py-3 bg-[#0d1220] border border-[#1e2d42] text-sm text-white outline-none placeholder-slate-700 focus:border-[#22d3ee]/60 transition-colors font-mono"
                                        />
                                    )}
                                </div>

                                {/* EV Model */}
                                <div>
                                    <div className="font-mono text-[10px] tracking-[0.18em] uppercase text-slate-600 mb-2">
                                        EV Model {loadingModels && <Loader2 size={10} className="inline animate-spin ml-1" />}
                                    </div>
                                    <select
                                        id="car-select"
                                        value={form.carModel}
                                        onChange={e => setForm(f => ({ ...f, carModel: e.target.value }))}
                                        disabled={loadingModels}
                                        className="w-full px-4 py-3 bg-[#0d1220] border border-[#1e2d42] text-sm text-white outline-none hover:border-[#22d3ee]/40 focus:border-[#22d3ee]/60 transition-colors appearance-none cursor-pointer disabled:opacity-50"
                                        style={{ colorScheme: 'dark' }}
                                    >
                                        {loadingModels ? (
                                            <option>Loading EVs for {selectedCountry?.name}...</option>
                                        ) : evModels.length === 0 ? (
                                            <option>No models found — check backend</option>
                                        ) : (
                                            evModels.map(m => (
                                                <option key={m.name} value={m.name}>
                                                    {m.name}{m.real_range_city_km > 0 ? ` · ${m.real_range_city_km}km` : ''}
                                                </option>
                                            ))
                                        )}
                                    </select>
                                    {evModels.some(m => m.source === 'live') && (
                                        <div className="mt-1.5 flex items-center gap-1.5 font-mono text-[11px] text-[#10b981]">
                                            <div className="w-1.5 h-1.5 rounded-full bg-[#10b981] animate-pulse" />
                                            {evModels.filter(m => m.source === 'live').length} models fetched live
                                        </div>
                                    )}
                                </div>

                                {/* Sliders */}
                                <div className="space-y-5 border-t border-[#1e2d42] pt-5">
                                    <RangeSlider
                                        id="daily" label="Daily commute" value={form.dailyKm}
                                        min={5} max={200} step={5} unit="km"
                                        onChange={v => setForm(f => ({ ...f, dailyKm: v }))}
                                    />
                                    <RangeSlider
                                        id="occasional" label="Longest trip" value={form.occasionalKm}
                                        min={50} max={800} step={10} unit="km"
                                        onChange={v => setForm(f => ({ ...f, occasionalKm: v }))}
                                    />
                                </div>

                                {/* Home charging toggle */}
                                <button
                                    id="home-charging-toggle"
                                    type="button"
                                    onClick={() => setForm(f => ({ ...f, hasHomeCharging: !f.hasHomeCharging }))}
                                    className={`w-full flex items-center justify-between p-4 border transition-all ${form.hasHomeCharging ? 'border-[#22d3ee]/30 bg-[#22d3ee]/5' : 'border-[#1e2d42] hover:border-[#22d3ee]/20'}`}
                                >
                                    <div className="flex items-center gap-3">
                                        <Home size={14} className={form.hasHomeCharging ? 'text-[#22d3ee]' : 'text-slate-500'} />
                                        <div className="text-left">
                                            <div className="text-sm text-white">Home Charging</div>
                                            <div className="text-xs text-slate-500 mt-0.5">Dedicated EV charger installed</div>
                                        </div>
                                    </div>
                                    <div
                                        className="rounded-full relative transition-colors flex-shrink-0"
                                        style={{ width: '40px', height: '22px', background: form.hasHomeCharging ? '#22d3ee' : '#1e2d42' }}
                                    >
                                        <div
                                            className="absolute top-[3px] w-4 h-4 rounded-full bg-white shadow-sm transition-transform"
                                            style={{ transform: form.hasHomeCharging ? 'translateX(20px)' : 'translateX(3px)' }}
                                        />
                                    </div>
                                </button>
                            </div>

                            {/* Submit button */}
                            <button
                                id="get-verdict-btn"
                                onClick={handleSubmit}
                                disabled={!form.country || !form.carModel || !form.city}
                                className="w-full py-4 px-6 text-black font-bold text-sm tracking-widest uppercase disabled:opacity-40 disabled:cursor-not-allowed transition-opacity flex items-center justify-center gap-2"
                                style={{
                                    background: 'linear-gradient(135deg, #22d3ee 0%, #06b6d4 50%, #0891b2 100%)',
                                    fontFamily: "'Syne', sans-serif",
                                    boxShadow: '0 0 30px rgba(34,211,238,0.25)',
                                }}
                            >
                                <Zap size={15} fill="currentColor" />
                                Get Honest Verdict
                                <ArrowRight size={15} />
                            </button>

                            {/* Stat strip */}
                            <div className="grid grid-cols-3 gap-2">
                                {[
                                    { v: String(countries.length || 16), l: 'Countries' },
                                    { v: '45+', l: 'EV Models' },
                                    { v: 'Live', l: 'Data' },
                                ].map(s => (
                                    <div key={s.l} className="bg-[#0d1220] border border-[#1e2d42] py-3 text-center">
                                        <div className="text-base font-bold text-[#22d3ee]" style={{ fontFamily: "'Space Mono', monospace" }}>
                                            {s.v}
                                        </div>
                                        <div className="font-mono text-[10px] text-slate-600 mt-0.5">{s.l}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {/* ── Error ── */}
                {error && (
                    <div className="max-w-lg mx-auto bg-[#f43f5e]/8 border border-[#f43f5e]/30 p-4 flex items-start gap-3 animate-fade-up mb-4">
                        <AlertCircle size={15} className="text-[#f43f5e] flex-shrink-0 mt-0.5" />
                        <div>
                            <div className="text-sm font-semibold text-[#f43f5e]">Connection error</div>
                            <p className="text-sm text-[#f43f5e]/70 mt-1">{error}</p>
                            <p className="font-mono text-[11px] text-slate-600 mt-2">
                                Backend: <span className="text-slate-400">http://localhost:8080</span>
                            </p>
                        </div>
                    </div>
                )}

                {/* ── Loading terminal ── */}
                {isStreaming && <LoadingPanel steps={loadingSteps} />}

                {/* ── Results dashboard ── */}
                {result && !isStreaming && <ResultDashboard result={result} onReset={handleReset} />}
            </main>

            {/* Footer */}
            <footer className="no-print border-t border-[#1e2d42] py-8 mt-16 relative z-10">
                <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
                    <div className="font-mono text-[11px] text-slate-600 text-center sm:text-left">
                        <span className="text-[#22d3ee]">VoltSage</span> · Global EV Advisor · Real-time data via TinyFish Web Agent
                        <br />Range figures are real-world owner-reported, not WLTP/EPA claims.
                    </div>
                    <div className="flex items-center gap-2 font-mono text-[11px] text-slate-600">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#22d3ee] animate-pulse" />
                        Powered by TinyFish
                    </div>
                </div>
            </footer>
        </div>
    )
}

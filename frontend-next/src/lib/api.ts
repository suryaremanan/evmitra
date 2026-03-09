// VoltSage — API client

const API_URL =
    process.env.NEXT_PUBLIC_API_URL ||
    (process.env.NODE_ENV === 'development' ? 'http://localhost:8080' : '/api')

export async function fetchCountries() {
    const res = await fetch(`${API_URL}/countries`)
    if (!res.ok) throw new Error('Failed to fetch countries')
    return res.json()
}

export async function fetchEVDatabase(country: string) {
    const res = await fetch(`${API_URL}/ev-database?country=${country}&live=true`, { cache: 'no-store' })
    if (!res.ok) throw new Error('Failed to fetch EV database')
    return res.json()
}

export function streamEVDatabase(
    country: string,
    onEvent: (event: { type: string; message?: string; data?: unknown }) => void
): () => void {
    const controller = new AbortController()

    fetch(`${API_URL}/ev-database/stream?country=${encodeURIComponent(country)}&live=true`, {
        method: 'GET',
        signal: controller.signal,
        cache: 'no-store',
    })
        .then(async (res) => {
            if (!res.ok) {
                onEvent({ type: 'ERROR', message: `API error: ${res.status}` })
                return
            }
            const reader = res.body?.getReader()
            if (!reader) return
            const decoder = new TextDecoder()
            let buffer = ''
            while (true) {
                const { done, value } = await reader.read()
                if (done) {
                    onEvent({ type: 'STREAM_CLOSED' })
                    break
                }
                buffer += decoder.decode(value, { stream: true })
                const lines = buffer.split('\n')
                buffer = lines.pop() ?? ''
                for (const line of lines) {
                    const trimmed = line.trim()
                    if (!trimmed.startsWith('data: ')) continue
                    try {
                        const payload = JSON.parse(trimmed.slice(6))
                        onEvent(payload)
                    } catch { }
                }
            }
        })
        .catch((err) => {
            if (err.name === 'AbortError') {
                onEvent({ type: 'STREAM_CLOSED' })
                return
            }
            onEvent({ type: 'ERROR', message: err.message })
        })

    return () => controller.abort()
}

export function streamVerdict(
    params: {
        country: string
        city: string
        car_model: string
        daily_km: number
        occasional_km: number
        has_home_charging: boolean
        currency: string
        user_id: string
    },
    onEvent: (event: { type: string; message?: string; data?: unknown }) => void
): () => void {
    const controller = new AbortController()

    fetch(`${API_URL}/verdict/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
        signal: controller.signal,
    })
        .then(async (res) => {
            if (!res.ok) {
                onEvent({ type: 'ERROR', message: `API error: ${res.status}` })
                return
            }
            const reader = res.body?.getReader()
            if (!reader) return
            const decoder = new TextDecoder()
            let buffer = ''
            while (true) {
                const { done, value } = await reader.read()
                if (done) break
                buffer += decoder.decode(value, { stream: true })
                const lines = buffer.split('\n')
                buffer = lines.pop() ?? ''
                for (const line of lines) {
                    const trimmed = line.trim()
                    if (!trimmed.startsWith('data: ')) continue
                    try {
                        const payload = JSON.parse(trimmed.slice(6))
                        onEvent(payload)
                    } catch { }
                }
            }
        })
        .catch((err) => {
            if (err.name === 'AbortError') {
                return
            }
            onEvent({ type: 'ERROR', message: err.message })
        })

    return () => controller.abort()
}

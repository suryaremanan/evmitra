'use client'

import { useCallback, useRef, useState } from 'react'
import { streamUsedEvInvestigation } from '@/lib/api'
import type { UsedEvReport, UsedEvSseEvent } from '@/lib/used-ev-types'

export interface UsedEvStreamState {
    status: 'idle' | 'streaming' | 'complete' | 'error'
    stage: number
    messages: string[]
    report: UsedEvReport | null
    error: string | null
    elapsedSeconds: number | null
}

export function useUsedEvStream() {
    const [state, setState] = useState<UsedEvStreamState>({
        status: 'idle',
        stage: 0,
        messages: [],
        report: null,
        error: null,
        elapsedSeconds: null,
    })

    const abortRef = useRef<(() => void) | null>(null)

    const start = useCallback((params: {
        listing_url: string
        country: string
        city?: string
        vin_hint?: string
        phone_hint?: string
    }) => {
        // Cancel any in-flight request
        abortRef.current?.()

        setState({
            status: 'streaming',
            stage: 0,
            messages: [],
            report: null,
            error: null,
            elapsedSeconds: null,
        })

        const abort = streamUsedEvInvestigation(params, (raw) => {
            const event = raw as UsedEvSseEvent
            setState((prev) => {
                switch (event.type) {
                    case 'STAGE':
                        return {
                            ...prev,
                            stage: event.stage ?? prev.stage,
                            messages: event.message
                                ? [...prev.messages, event.message]
                                : prev.messages,
                        }
                    case 'PROGRESS':
                    case 'AGENT_COMPLETE':
                    case 'WARNING':
                        return {
                            ...prev,
                            messages: event.message
                                ? [...prev.messages, event.message]
                                : prev.messages,
                        }
                    case 'COMPLETE':
                        return {
                            ...prev,
                            status: 'complete',
                            report: event.report ?? null,
                            elapsedSeconds: event.elapsed_seconds ?? null,
                            messages: event.message
                                ? [...prev.messages, event.message]
                                : prev.messages,
                        }
                    case 'ERROR':
                        return {
                            ...prev,
                            status: 'error',
                            error: event.message ?? 'Unknown error',
                        }
                    default:
                        return prev
                }
            })
        })

        abortRef.current = abort
    }, [])

    const reset = useCallback(() => {
        abortRef.current?.()
        setState({
            status: 'idle',
            stage: 0,
            messages: [],
            report: null,
            error: null,
            elapsedSeconds: null,
        })
    }, [])

    return { state, start, reset }
}

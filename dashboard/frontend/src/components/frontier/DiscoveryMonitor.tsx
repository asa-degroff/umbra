import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  X, Brain, Sparkles, Search, BookOpen, CheckCircle,
  AlertCircle, Play, Flag, Compass, Pin, PinOff, Trash2,
  Cpu, Clock, Wifi, WifiOff,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { API_BASE, WS_URL } from '@/lib/config'
import { useWebSocket } from '@/hooks/useWebSocket'
import type { Event } from '@/types'

// --- Types ---

interface DiscoveryMonitorProps {
  isOpen: boolean
  onClose: () => void
  onActivityChange?: (active: boolean) => void
}

interface DiscoveryEvent {
  type: string
  timestamp: string
  [key: string]: unknown
}

interface ModelInfo {
  name: string
  family: string
  parameter_size: string
  quantization: string
  size_vram_gb: number
  size_total_gb: number
  context_length: number
  expires_at: string
  seconds_remaining: number | null
  status: 'active' | 'idle'
}

interface GpuInfo {
  gpu: string
  total_gb: number
  used_gb: number
  pct: number
}

interface ModelsResponse {
  models: ModelInfo[]
  error: string | null
  gpu?: GpuInfo[]
}

// --- Event rendering config ---

interface EventConfig {
  icon: React.ElementType
  color: string // tailwind text color
  label: (evt: DiscoveryEvent) => string
  detail?: (evt: DiscoveryEvent) => string | null
}

const EVENT_CONFIG: Record<string, EventConfig> = {
  'discovery:started': {
    icon: Play,
    color: 'text-blue-400',
    label: () => 'Discovery started',
  },
  'discovery:seed_exploring': {
    icon: Compass,
    color: 'text-blue-400',
    label: (e) => `Exploring seed: ${e.seed_label || e.seed_id}`,
    detail: (e) => e.seed_type ? `Type: ${e.seed_type}` : null,
  },
  'discovery:zone_exploring': {
    icon: Compass,
    color: 'text-blue-400',
    label: (e) => `Exploring zone${e.seed_label ? `: ${e.seed_label}` : ''}`,
    detail: (e) => e.zone_id ? `Zone ${e.zone_id}` : null,
  },
  'discovery:llm_generating': {
    icon: Brain,
    color: 'text-amber-400',
    label: () => 'Generating queries...',
  },
  'discovery:llm_result': {
    icon: Sparkles,
    color: 'text-green-400',
    label: (e) => {
      const queries = e.queries as string[] | undefined
      return queries ? `${queries.length} queries generated` : 'Queries generated'
    },
    detail: (e) => {
      const queries = e.queries as string[] | undefined
      return queries?.join(', ') ?? null
    },
  },
  'discovery:provider_searching': {
    icon: Search,
    color: 'text-amber-400',
    label: (e) => `${e.provider}: searching`,
    detail: (e) => e.query as string ?? null,
  },
  'discovery:provider_result': {
    icon: CheckCircle,
    color: 'text-green-400',
    label: (e) => `${e.count} results from ${e.provider}`,
    detail: (e) => {
      const titles = e.titles as string[] | undefined
      return titles?.slice(0, 3).join(', ') ?? null
    },
  },
  'discovery:source_scored': {
    icon: BookOpen,
    color: 'text-cyan-400',
    label: (e) => `${e.title}`,
    detail: (e) => {
      const rel = e.relevance as number
      const status = e.status as string
      return `${(rel * 100).toFixed(0)}% relevance — ${status}`
    },
  },
  'discovery:round_complete': {
    icon: Flag,
    color: 'text-blue-400',
    label: (e) => `Round ${e.round}/${e.total_rounds} complete`,
    detail: (e) => `${e.sources_so_far} sources, ${e.zones_explored} zones`,
  },
  'discovery:complete': {
    icon: CheckCircle,
    color: 'text-green-400',
    label: (e) => `Discovery complete: ${e.total} sources`,
    detail: (e) => `${e.frontier_count} frontier, ${e.pending_count} pending — ${e.rounds_completed} rounds, ${e.zones_explored} zones`,
  },
  'discovery:error': {
    icon: AlertCircle,
    color: 'text-red-400',
    label: (e) => `Error: ${e.message}`,
  },
}

function getSourceScoreColor(status: string): string {
  switch (status) {
    case 'frontier': return 'text-green-400'
    case 'pending': return 'text-amber-400'
    case 'rejected': return 'text-red-400'
    default: return 'text-cyan-400'
  }
}

// --- Progress state derived from events ---

interface ProgressState {
  active: boolean
  currentRound: number
  totalRounds: number
  currentLabel: string
  sourcesFound: number
  frontierCount: number
  pendingCount: number
  zonesExplored: number
}

const IDLE_PROGRESS: ProgressState = {
  active: false,
  currentRound: 0,
  totalRounds: 0,
  currentLabel: 'Idle',
  sourcesFound: 0,
  frontierCount: 0,
  pendingCount: 0,
  zonesExplored: 0,
}

function deriveProgress(events: DiscoveryEvent[]): ProgressState {
  const state = { ...IDLE_PROGRESS }

  // Walk events in order
  for (const evt of events) {
    switch (evt.type) {
      case 'discovery:started':
        state.active = true
        state.currentLabel = 'Starting...'
        state.sourcesFound = 0
        state.frontierCount = 0
        state.pendingCount = 0
        state.zonesExplored = 0
        state.currentRound = 0
        state.totalRounds = 0
        break
      case 'discovery:seed_exploring':
        state.currentLabel = `Exploring: ${evt.seed_label || evt.seed_id}`
        break
      case 'discovery:zone_exploring':
        state.currentLabel = evt.seed_label ? `Zone: ${evt.seed_label}` : `Zone ${evt.zone_id}`
        break
      case 'discovery:llm_generating':
        state.currentLabel = 'Generating queries...'
        break
      case 'discovery:llm_result':
        state.currentLabel = 'Searching providers...'
        break
      case 'discovery:provider_searching':
        state.currentLabel = `Searching ${evt.provider}...`
        break
      case 'discovery:source_scored':
        state.sourcesFound++
        if (evt.status === 'frontier') state.frontierCount++
        else if (evt.status === 'pending') state.pendingCount++
        break
      case 'discovery:round_complete':
        state.currentRound = evt.round as number
        state.totalRounds = evt.total_rounds as number
        state.sourcesFound = evt.sources_so_far as number
        state.zonesExplored = evt.zones_explored as number
        state.currentLabel = `Round ${evt.round}/${evt.total_rounds} complete`
        break
      case 'discovery:complete':
        state.active = false
        state.currentLabel = 'Complete'
        state.frontierCount = evt.frontier_count as number
        state.pendingCount = evt.pending_count as number
        state.sourcesFound = evt.total as number
        state.zonesExplored = evt.zones_explored as number
        break
      case 'discovery:error':
        state.active = false
        state.currentLabel = 'Error'
        break
    }
  }

  return state
}

// --- Format helpers ---

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

function formatCountdown(seconds: number | null): string {
  if (seconds === null || seconds <= 0) return 'expired'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

const MAX_EVENTS = 200

// --- Component ---

export default function DiscoveryMonitor({ isOpen, onClose, onActivityChange }: DiscoveryMonitorProps) {
  const [events, setEvents] = useState<DiscoveryEvent[]>([])
  const [pinToBottom, setPinToBottom] = useState(true)
  const logEndRef = useRef<HTMLDivElement>(null)
  const logContainerRef = useRef<HTMLDivElement>(null)
  const onActivityChangeRef = useRef(onActivityChange)
  onActivityChangeRef.current = onActivityChange

  // --- WebSocket for discovery events ---

  const handleEvent = useCallback((event: Event) => {
    // Cast to any since discovery events don't match the typed Event union
    const raw = event as unknown as DiscoveryEvent
    if (!raw.type?.startsWith('discovery:')) return

    setEvents(prev => {
      const next = [...prev, raw]
      return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next
    })

    // Notify parent about activity changes
    if (raw.type === 'discovery:started') {
      onActivityChangeRef.current?.(true)
    } else if (raw.type === 'discovery:complete' || raw.type === 'discovery:error') {
      onActivityChangeRef.current?.(false)
    }
  }, [])

  const handleHistory = useCallback((historyEvents: Event[]) => {
    const discoveryEvents = (historyEvents as unknown as DiscoveryEvent[])
      .filter(e => e.type?.startsWith('discovery:'))
    if (discoveryEvents.length > 0) {
      setEvents(prev => {
        const merged = [...prev, ...discoveryEvents]
        return merged.length > MAX_EVENTS ? merged.slice(-MAX_EVENTS) : merged
      })

      // Check if discovery is currently active from history
      const last = discoveryEvents[discoveryEvents.length - 1]
      if (last.type === 'discovery:started' ||
          last.type === 'discovery:seed_exploring' ||
          last.type === 'discovery:zone_exploring' ||
          last.type === 'discovery:llm_generating' ||
          last.type === 'discovery:llm_result' ||
          last.type === 'discovery:provider_searching' ||
          last.type === 'discovery:provider_result' ||
          last.type === 'discovery:source_scored' ||
          last.type === 'discovery:round_complete') {
        onActivityChangeRef.current?.(true)
      }
    }
  }, [])

  const { isConnected } = useWebSocket({
    url: WS_URL,
    onEvent: handleEvent,
    onHistory: handleHistory,
  })

  // --- Model status polling ---

  const { data: modelsData } = useQuery<ModelsResponse>({
    queryKey: ['frontierModels'],
    queryFn: () => fetch(`${API_BASE}/semantic/frontier/models`).then(r => r.json()),
    refetchInterval: 10000,
  })

  // --- Auto-scroll ---

  useEffect(() => {
    if (pinToBottom && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [events, pinToBottom])

  // Detect user scroll to auto-unpin
  const handleScroll = useCallback(() => {
    const el = logContainerRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    if (pinToBottom && !atBottom) {
      setPinToBottom(false)
    }
  }, [pinToBottom])

  // --- Derived progress ---

  const progress = deriveProgress(events)

  // --- Clear log ---

  const clearLog = () => setEvents([])

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-40"
          onClick={onClose}
        />
      )}

      {/* Drawer */}
      <div
        className={cn(
          'fixed top-0 right-0 h-full w-[480px] max-w-[90vw] bg-background border-l border-border shadow-xl z-50',
          'flex flex-col transition-transform duration-300 ease-in-out',
          isOpen ? 'translate-x-0' : 'translate-x-full',
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-primary" />
            <span className="font-semibold text-sm">Discovery Monitor</span>
            {isConnected ? (
              <Wifi className="w-3 h-3 text-green-400" />
            ) : (
              <WifiOff className="w-3 h-3 text-red-400" />
            )}
          </div>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Model Status Panel */}
        <div className="px-4 py-3 border-b border-border flex-shrink-0 space-y-2">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Models</div>
          {modelsData?.error ? (
            <div className="text-xs text-red-400 flex items-center gap-1">
              <AlertCircle className="w-3 h-3" />
              {modelsData.error}
            </div>
          ) : !modelsData?.models?.length ? (
            <div className="text-xs text-muted-foreground">No models loaded</div>
          ) : (
            <div className="space-y-2">
              {modelsData.models.map((model) => (
                <div key={model.name} className="p-2 bg-secondary rounded-lg">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium truncate flex-1">{model.name}</span>
                    <Badge
                      variant="outline"
                      className={cn(
                        'text-[10px] ml-2',
                        model.status === 'active' ? 'border-green-500 text-green-400' : 'border-amber-500 text-amber-400',
                      )}
                    >
                      {model.status}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                    {model.parameter_size && <span>{model.parameter_size}</span>}
                    {model.quantization && <span>{model.quantization}</span>}
                    <span>{model.size_vram_gb}GB VRAM</span>
                    {model.seconds_remaining !== null && (
                      <span className="flex items-center gap-0.5">
                        <Clock className="w-2.5 h-2.5" />
                        {formatCountdown(model.seconds_remaining)}
                      </span>
                    )}
                  </div>
                  {/* VRAM bar */}
                  {model.size_total_gb > 0 && (
                    <div className="mt-1 h-1 bg-muted rounded-full overflow-hidden">
                      <div
                        className={cn(
                          'h-full rounded-full transition-all',
                          model.status === 'active' ? 'bg-green-500' : 'bg-amber-500',
                        )}
                        style={{ width: `${Math.min(100, (model.size_vram_gb / model.size_total_gb) * 100)}%` }}
                      />
                    </div>
                  )}
                </div>
              ))}

              {/* GPU summary */}
              {modelsData.gpu && modelsData.gpu.length > 0 && (
                <div className="text-[10px] text-muted-foreground flex items-center gap-2">
                  {modelsData.gpu.map((g, i) => (
                    <span key={i}>
                      GPU{i}: {g.used_gb}/{g.total_gb}GB ({g.pct}%)
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Live Event Log */}
        <div className="flex-1 flex flex-col min-h-0">
          {/* Log toolbar */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-border flex-shrink-0">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Event Log
              <span className="ml-1 text-muted-foreground/60">({events.length})</span>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => setPinToBottom(!pinToBottom)}
                title={pinToBottom ? 'Unpin from bottom' : 'Pin to bottom'}
              >
                {pinToBottom ? (
                  <Pin className="w-3 h-3 text-primary" />
                ) : (
                  <PinOff className="w-3 h-3 text-muted-foreground" />
                )}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={clearLog}
                title="Clear log"
              >
                <Trash2 className="w-3 h-3 text-muted-foreground" />
              </Button>
            </div>
          </div>

          {/* Log entries */}
          <div
            ref={logContainerRef}
            className="flex-1 overflow-y-auto px-3 py-2 space-y-0.5"
            onScroll={handleScroll}
          >
            {events.length === 0 ? (
              <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
                No discovery events yet. Run a discovery to see live progress.
              </div>
            ) : (
              events.map((evt, i) => {
                const config = EVENT_CONFIG[evt.type]
                if (!config) return null

                const Icon = config.icon
                const colorClass = evt.type === 'discovery:source_scored'
                  ? getSourceScoreColor(evt.status as string)
                  : config.color
                const detail = config.detail?.(evt)

                return (
                  <div key={i} className="flex items-start gap-2 py-1 group">
                    <span className="text-[10px] text-muted-foreground/50 mt-0.5 whitespace-nowrap font-mono">
                      {formatTime(evt.timestamp)}
                    </span>
                    <Icon className={cn('w-3 h-3 mt-0.5 flex-shrink-0', colorClass)} />
                    <div className="min-w-0 flex-1">
                      <span className={cn('text-xs', colorClass)}>
                        {config.label(evt)}
                      </span>
                      {detail && (
                        <div className="text-[10px] text-muted-foreground/60 truncate font-mono">
                          {detail}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })
            )}
            <div ref={logEndRef} />
          </div>
        </div>

        {/* Progress Summary (sticky bottom) */}
        <div className="px-4 py-3 border-t border-border bg-secondary/50 flex-shrink-0">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              {progress.active ? (
                <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              ) : (
                <div className="w-2 h-2 rounded-full bg-muted-foreground/30" />
              )}
              <span className="text-xs font-medium">
                {progress.active && progress.totalRounds > 0
                  ? `Round ${progress.currentRound}/${progress.totalRounds}`
                  : progress.active
                    ? 'Running'
                    : 'Idle'
                }
              </span>
            </div>
            <span className="text-[10px] text-muted-foreground truncate ml-2">
              {progress.currentLabel}
            </span>
          </div>
          <div className="grid grid-cols-4 gap-2 text-center">
            <div>
              <div className="text-sm font-bold">{progress.sourcesFound}</div>
              <div className="text-[10px] text-muted-foreground">Found</div>
            </div>
            <div>
              <div className="text-sm font-bold text-green-400">{progress.frontierCount}</div>
              <div className="text-[10px] text-muted-foreground">Frontier</div>
            </div>
            <div>
              <div className="text-sm font-bold text-amber-400">{progress.pendingCount}</div>
              <div className="text-[10px] text-muted-foreground">Pending</div>
            </div>
            <div>
              <div className="text-sm font-bold">{progress.zonesExplored}</div>
              <div className="text-[10px] text-muted-foreground">Zones</div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

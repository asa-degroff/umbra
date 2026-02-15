import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useMemo } from 'react'
import {
  Compass, Map, Globe, Zap, BookOpen, Sprout, Sparkles,
  ChevronLeft, ChevronRight, ExternalLink, X, Check,
  Loader2, Play, AlertCircle, ThumbsUp, ThumbsDown, Focus,
} from 'lucide-react'
import {
  ScatterChart, Scatter, XAxis, YAxis,
  Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { API_BASE } from '@/lib/config'

// --- Types ---

interface NearbyPost {
  text: string
  uri: string
}

interface FrontierZone {
  id: string
  grid_cell: [number, number]
  centroid_2d: [number, number]
  frontier_score: number
  density_score: number
  adjacency_score: number
  relevance_score: number
  seed_id?: string
  seed_label?: string
  nearby_posts: NearbyPost[]
}

interface ZonesResponse {
  zones: FrontierZone[]
  count: number
  seeded?: boolean
  days: number
  source: string
  detected_at?: string
  error?: string
}

interface InterestSeed {
  seed_id: string
  seed_type: 'cluster' | 'outlier'
  label: string
  post_count: number
  weight: number
  recency_weight: number
  rarity_weight: number
  avg_distance_to_global_centroid: number
  representative_texts: string[]
}

interface SeedsResponse {
  seeds: InterestSeed[]
  count: number
  cluster_count: number
  outlier_count: number
  days: number
  detected_at?: string
  error?: string
}

interface DiscoveredSourceItem {
  id: number
  title: string
  url: string
  excerpt: string
  source_type: string
  relevance_score: number
  status: string
  frontier_zone_id?: string
  query_used?: string
  discovered_at: string
  chunk_index: number
  total_chunks: number
  user_rating?: number   // -1 | 0 | 1
  rated_at?: string | null
}

interface SourcesResponse {
  sources: DiscoveredSourceItem[]
  count: number
  error?: string
}

interface FrontierStats {
  available: boolean
  zones_cached: boolean
  discovery_cached: boolean
  cache_ttl: number
  source_db?: {
    frontier: number
    pending: number
    used: number
    rejected: number
    total: number
  }
  source_db_error?: string
  error?: string
}

interface DiscoverySource {
  title: string
  url: string
  excerpt: string
  source_type: string
  relevance_score: number
  query_used?: string
  status: string
}

interface DiscoveryResponse {
  frontier_sources: DiscoverySource[]
  pending_sources: DiscoverySource[]
  stats: {
    zones_explored: number
    rounds_completed: number
    total_sources_found: number
    capped: boolean
  }
  errors: string[]
  discovered_at?: string
  error?: string
  focused?: boolean
  focused_seeds?: string[]
}

// --- Helpers ---

function StatCard({
  title, value, subtitle, icon: Icon, iconColor = 'text-primary'
}: {
  title: string
  value: string | number
  subtitle?: string
  icon: React.ElementType
  iconColor?: string
}) {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-center gap-4">
          <div className={cn("p-3 rounded-lg bg-secondary", iconColor)}>
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold">{value}</div>
            <div className="text-sm text-muted-foreground">{title}</div>
            {subtitle && (
              <div className="text-xs text-muted-foreground">{subtitle}</div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function scoreColor(score: number): string {
  if (score >= 0.7) return '#22c55e'   // green-500
  if (score >= 0.5) return '#3b82f6'   // blue-500
  if (score >= 0.3) return '#f59e0b'   // amber-500
  return '#6b7280'                      // gray-500
}

// Distinct colors for seed-tagged zones
const SEED_COLORS = [
  '#22c55e', // green
  '#3b82f6', // blue
  '#f59e0b', // amber
  '#a855f7', // purple
  '#ec4899', // pink
  '#06b6d4', // cyan
  '#f97316', // orange
  '#84cc16', // lime
  '#e11d48', // rose
  '#6366f1', // indigo
]

function seedColor(seedId: string | undefined, seeds: InterestSeed[]): string {
  if (!seedId) return '#6b7280'
  const idx = seeds.findIndex(s => s.seed_id === seedId)
  return idx >= 0 ? SEED_COLORS[idx % SEED_COLORS.length] : '#6b7280'
}

function statusBadgeVariant(status: string): 'default' | 'secondary' | 'outline' | 'destructive' {
  switch (status) {
    case 'frontier': return 'default'
    case 'pending': return 'secondary'
    case 'used': return 'outline'
    case 'rejected': return 'destructive'
    default: return 'secondary'
  }
}

// --- Zone Tooltip ---

function ZoneTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const zone = payload[0].payload as FrontierZone
  return (
    <div className="bg-popover border rounded-lg shadow-lg p-3 max-w-xs">
      <div className="flex items-center gap-2 mb-2">
        <Badge style={{ backgroundColor: scoreColor(zone.frontier_score) }} className="text-white">
          Score: {(zone.frontier_score * 100).toFixed(0)}%
        </Badge>
        <span className="text-xs text-muted-foreground">
          Zone {zone.id}
        </span>
      </div>
      {zone.seed_label && (
        <div className="text-xs font-medium text-primary mb-2">
          Seed: {zone.seed_label}
        </div>
      )}
      <div className="text-xs space-y-1 mb-2">
        <div>Density: {(zone.density_score * 100).toFixed(0)}%</div>
        <div>Adjacency: {(zone.adjacency_score * 100).toFixed(0)}%</div>
        <div>Relevance: {(zone.relevance_score * 100).toFixed(0)}%</div>
      </div>
      {zone.nearby_posts?.[0] && (
        <p className="text-sm text-foreground line-clamp-2">
          {zone.nearby_posts[0].text}
        </p>
      )}
    </div>
  )
}

// --- Rating Button ---

function RatingButton({
  current,
  target,
  icon: Icon,
  activeColor,
  onClick,
}: {
  current: number
  target: 1 | -1
  icon: React.ElementType
  activeColor: string
  onClick: () => void
}) {
  const isActive = current === target
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick() }}
      className={cn(
        'p-1 rounded transition-colors',
        isActive ? activeColor : 'text-muted-foreground/40 hover:text-muted-foreground',
      )}
      title={target === 1 ? 'Uprank' : 'Downrank'}
    >
      <Icon className="w-4 h-4" />
    </button>
  )
}

// --- Constants ---

const PAGE_SIZE = 20

const DAYS_OPTIONS = [
  { value: '7', label: '7 days' },
  { value: '14', label: '14 days' },
  { value: '30', label: '30 days' },
  { value: '60', label: '60 days' },
  { value: '90', label: '90 days' },
]

const SOURCE_OPTIONS = [
  { value: 'all', label: 'All Sources' },
  { value: 'umbra', label: 'Umbra Only' },
  { value: 'network', label: 'Network Only' },
]

const STATUS_OPTIONS = [
  { value: 'all', label: 'All Statuses' },
  { value: 'frontier', label: 'Frontier' },
  { value: 'pending', label: 'Pending' },
  { value: 'used', label: 'Used' },
  { value: 'rejected', label: 'Rejected' },
]

type TabId = 'seeds' | 'zones' | 'sources' | 'discover'

// --- Component ---

export default function FrontierView() {
  const queryClient = useQueryClient()
  const [days, setDays] = useState(30)
  const [source, setSource] = useState('all')
  const [activeTab, setActiveTab] = useState<TabId>('zones')
  const [selectedZone, setSelectedZone] = useState<FrontierZone | null>(null)
  const [selectedSource, setSelectedSource] = useState<DiscoveredSourceItem | null>(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage] = useState(0)
  const [selectedSeedIds, setSelectedSeedIds] = useState<Set<string>>(new Set())

  // Discover params
  const [discoverRounds, setDiscoverRounds] = useState('2')
  const [discoverMaxSources, setDiscoverMaxSources] = useState('25')
  const [discoverZones, setDiscoverZones] = useState('3')

  // --- Data fetching ---

  const { data: seedsData, isLoading: seedsLoading } = useQuery<SeedsResponse>({
    queryKey: ['interestSeeds', days],
    queryFn: () => fetch(
      `${API_BASE}/semantic/frontier/seeds?days=${days}`
    ).then(r => r.json()),
    refetchInterval: 120000,
  })

  const { data: zonesData, isLoading: zonesLoading } = useQuery<ZonesResponse>({
    queryKey: ['frontierZones', days, source],
    queryFn: () => fetch(
      `${API_BASE}/semantic/frontier/zones?days=${days}&top_n=10&source=${source}&use_seeds=true`
    ).then(r => r.json()),
    refetchInterval: 120000,
  })

  const { data: sourcesData, isLoading: sourcesLoading } = useQuery<SourcesResponse>({
    queryKey: ['frontierSources', statusFilter],
    queryFn: () => fetch(
      `${API_BASE}/semantic/frontier/sources?limit=500${statusFilter !== 'all' ? `&status=${statusFilter}` : ''}`
    ).then(r => r.json()),
    refetchInterval: 60000,
  })

  const { data: statsData } = useQuery<FrontierStats>({
    queryKey: ['frontierStats'],
    queryFn: () => fetch(`${API_BASE}/semantic/frontier/stats`).then(r => r.json()),
    refetchInterval: 60000,
  })

  const discoverMutation = useMutation<DiscoveryResponse>({
    mutationFn: () => fetch(
      `${API_BASE}/semantic/frontier/discover?max_rounds=${discoverRounds}&max_sources=${discoverMaxSources}&initial_zones=${discoverZones}&days=${days}&source=${source}&refresh=true`
    ).then(r => r.json()),
  })

  const rateMutation = useMutation({
    mutationFn: ({ sourceId, rating }: { sourceId: number; rating: number }) =>
      fetch(
        `${API_BASE}/semantic/frontier/sources/${sourceId}/feedback?rating=${rating}`,
        { method: 'POST' },
      ).then(r => r.json()),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['frontierSources'] })
      // Update selected source in-place so modal reflects new state
      setSelectedSource(prev =>
        prev && prev.id === variables.sourceId
          ? { ...prev, user_rating: variables.rating, status: variables.rating === -1 ? 'rejected' : prev.status }
          : prev
      )
    },
  })

  const focusedDiscoveryMutation = useMutation<DiscoveryResponse>({
    mutationFn: () => fetch(
      `${API_BASE}/semantic/frontier/discover/focused`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          seed_ids: Array.from(selectedSeedIds),
          max_rounds: Number(discoverRounds),
          max_sources: Number(discoverMaxSources),
          initial_zones: Number(discoverZones),
          days,
          source,
        }),
      },
    ).then(r => r.json()),
    onSuccess: (data) => {
      if (!data.error) {
        queryClient.invalidateQueries({ queryKey: ['frontierSources'] })
        setActiveTab('discover')
        setSelectedSeedIds(new Set())
      }
    },
  })

  // --- Seed selection helpers ---

  const toggleSeed = (seedId: string) => {
    setSelectedSeedIds(prev => {
      const next = new Set(prev)
      if (next.has(seedId)) next.delete(seedId)
      else next.add(seedId)
      return next
    })
  }

  // --- Derived data ---

  const paginatedSources = useMemo(() => {
    const sources = sourcesData?.sources ?? []
    return sources.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  }, [sourcesData, page])

  const totalSources = sourcesData?.sources?.length ?? 0
  const totalPages = Math.max(1, Math.ceil(totalSources / PAGE_SIZE))

  // --- Handlers ---

  const handleDaysChange = (v: string) => { setDays(Number(v)); setPage(0) }
  const handleSourceChange = (v: string) => { setSource(v); setPage(0) }
  const handleStatusChange = (v: string) => { setStatusFilter(v); setPage(0) }

  // --- Tabs ---

  const tabs: { id: TabId; label: string }[] = [
    { id: 'seeds', label: 'Seeds' },
    { id: 'zones', label: 'Zones' },
    { id: 'sources', label: 'Sources' },
    { id: 'discover', label: 'Discover' },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Compass className="w-6 h-6 text-primary" />
          Frontier Detection
        </h1>
        <p className="text-muted-foreground">
          Explore unexplored regions in embedding space and discover new sources
        </p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          title="Interest Seeds"
          value={seedsData?.count ?? 0}
          subtitle={seedsData ? `${seedsData.cluster_count} clusters, ${seedsData.outlier_count} outliers` : undefined}
          icon={Sprout}
          iconColor="text-purple-400"
        />
        <StatCard
          title="Frontier Zones"
          value={zonesData?.count ?? 0}
          subtitle={zonesData?.seeded ? 'Seed-guided' : 'Legacy mode'}
          icon={Map}
          iconColor="text-cyan-400"
        />
        <StatCard
          title="Frontier Sources"
          value={statsData?.source_db?.frontier ?? 0}
          icon={Zap}
          iconColor="text-green-400"
        />
        <StatCard
          title="Pending Sources"
          value={statsData?.source_db?.pending ?? 0}
          icon={BookOpen}
          iconColor="text-amber-400"
        />
        <StatCard
          title="Service Status"
          value={statsData?.available ? 'Online' : 'Offline'}
          subtitle={statsData?.source_db ? `${statsData.source_db.total} total sources` : undefined}
          icon={Globe}
          iconColor={statsData?.available ? 'text-green-400' : 'text-red-400'}
        />
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="w-36">
              <Select value={String(days)} onValueChange={handleDaysChange}>
                <SelectTrigger>
                  <SelectValue placeholder="Lookback" />
                </SelectTrigger>
                <SelectContent>
                  {DAYS_OPTIONS.map(o => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="w-40">
              <Select value={source} onValueChange={handleSourceChange}>
                <SelectTrigger>
                  <SelectValue placeholder="Source" />
                </SelectTrigger>
                <SelectContent>
                  {SOURCE_OPTIONS.map(o => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {activeTab === 'sources' && (
              <div className="w-40">
                <Select value={statusFilter} onValueChange={handleStatusChange}>
                  <SelectTrigger>
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUS_OPTIONS.map(o => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Tab Switcher */}
      <div className="flex gap-1">
        {tabs.map(tab => (
          <Button
            key={tab.id}
            variant={activeTab === tab.id ? 'secondary' : 'ghost'}
            className={cn(activeTab === tab.id && 'bg-secondary')}
            onClick={() => { setActiveTab(tab.id); setPage(0) }}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      {/* ==================== SEEDS TAB ==================== */}
      {activeTab === 'seeds' && (
        <div className="space-y-4">
          {seedsLoading ? (
            <Card>
              <CardContent className="p-6 flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
                <span className="ml-2 text-muted-foreground">Detecting interest seeds...</span>
              </CardContent>
            </Card>
          ) : seedsData?.error ? (
            <Card>
              <CardContent className="p-6 flex items-center text-destructive">
                <AlertCircle className="w-5 h-5 mr-2" />
                {seedsData.error}
              </CardContent>
            </Card>
          ) : !seedsData?.seeds?.length ? (
            <Card>
              <CardContent className="p-6 text-center text-muted-foreground">
                No interest seeds detected.
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Seed Selection Action Bar */}
              {selectedSeedIds.size > 0 && (
                <div className="flex items-center gap-3 p-3 bg-primary/10 border border-primary/20 rounded-lg">
                  <Badge variant="secondary" className="text-sm">
                    {selectedSeedIds.size} seed{selectedSeedIds.size > 1 ? 's' : ''} selected
                  </Badge>
                  <div className="flex-1" />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedSeedIds(new Set())}
                  >
                    Clear Selection
                  </Button>
                  <Button
                    size="sm"
                    className="gap-2"
                    onClick={() => focusedDiscoveryMutation.mutate()}
                    disabled={focusedDiscoveryMutation.isPending}
                  >
                    {focusedDiscoveryMutation.isPending ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Discovering...
                      </>
                    ) : (
                      <>
                        <Focus className="w-4 h-4" />
                        Run Focused Discovery
                      </>
                    )}
                  </Button>
                </div>
              )}

              {/* Cluster Seeds */}
              {seedsData.seeds.filter(s => s.seed_type === 'cluster').length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Sprout className="w-5 h-5 text-green-400" />
                      Topic Clusters
                    </CardTitle>
                    <CardDescription>
                      Main content areas — click to select seeds for focused discovery
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {seedsData.seeds.filter(s => s.seed_type === 'cluster').map((seed, i) => {
                        const isSelected = selectedSeedIds.has(seed.seed_id)
                        return (
                          <div
                            key={seed.seed_id}
                            className={cn(
                              "p-4 bg-secondary rounded-lg border-l-4 cursor-pointer transition-all",
                              isSelected
                                ? "ring-2 ring-primary ring-offset-2 ring-offset-background"
                                : "hover:ring-1 hover:ring-muted-foreground/30"
                            )}
                            style={{ borderLeftColor: SEED_COLORS[i % SEED_COLORS.length] }}
                            onClick={() => toggleSeed(seed.seed_id)}
                          >
                            <div className="flex items-center justify-between mb-2">
                              <span className="font-medium text-sm">{seed.label}</span>
                              <div className="flex items-center gap-1">
                                {isSelected && (
                                  <div className="w-5 h-5 rounded-full bg-primary flex items-center justify-center">
                                    <Check className="w-3 h-3 text-primary-foreground" />
                                  </div>
                                )}
                                <Badge variant="outline" className="text-xs">
                                  {seed.post_count} posts
                                </Badge>
                              </div>
                            </div>
                            <div className="flex gap-2 mb-3">
                              <Badge variant="secondary" className="text-xs">
                                Weight: {(seed.weight * 100).toFixed(0)}%
                              </Badge>
                              <Badge variant="secondary" className="text-xs">
                                Recency: {(seed.recency_weight * 100).toFixed(0)}%
                              </Badge>
                            </div>
                            {seed.representative_texts?.[0] && (
                              <p className="text-xs text-muted-foreground line-clamp-3">
                                {seed.representative_texts[0]}
                              </p>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Outlier Seeds */}
              {seedsData.seeds.filter(s => s.seed_type === 'outlier').length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Sparkles className="w-5 h-5 text-amber-400" />
                      Creative Outliers
                    </CardTitle>
                    <CardDescription>
                      Intentional diversifications — click to select seeds for focused discovery
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {seedsData.seeds.filter(s => s.seed_type === 'outlier').map((seed) => {
                        const colorIdx = seedsData.seeds.findIndex(s => s.seed_id === seed.seed_id)
                        const isSelected = selectedSeedIds.has(seed.seed_id)
                        return (
                          <div
                            key={seed.seed_id}
                            className={cn(
                              "p-4 bg-secondary rounded-lg border-l-4 cursor-pointer transition-all",
                              isSelected
                                ? "ring-2 ring-primary ring-offset-2 ring-offset-background"
                                : "hover:ring-1 hover:ring-muted-foreground/30"
                            )}
                            style={{ borderLeftColor: SEED_COLORS[colorIdx % SEED_COLORS.length] }}
                            onClick={() => toggleSeed(seed.seed_id)}
                          >
                            <div className="flex items-center justify-between mb-2">
                              <span className="font-medium text-sm">{seed.label}</span>
                              <div className="flex items-center gap-1">
                                {isSelected && (
                                  <div className="w-5 h-5 rounded-full bg-primary flex items-center justify-center">
                                    <Check className="w-3 h-3 text-primary-foreground" />
                                  </div>
                                )}
                                <Badge variant="secondary" className="text-xs">
                                  Dist: {(seed.avg_distance_to_global_centroid * 100).toFixed(0)}%
                                </Badge>
                              </div>
                            </div>
                            <div className="flex gap-2 mb-3">
                              <Badge variant="secondary" className="text-xs">
                                Weight: {(seed.weight * 100).toFixed(0)}%
                              </Badge>
                              <Badge variant="secondary" className="text-xs">
                                Recency: {(seed.recency_weight * 100).toFixed(0)}%
                              </Badge>
                            </div>
                            {seed.representative_texts?.[0] && (
                              <p className="text-xs text-muted-foreground line-clamp-3">
                                {seed.representative_texts[0]}
                              </p>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      )}

      {/* ==================== ZONES TAB ==================== */}
      {activeTab === 'zones' && (
        <Card>
          <CardHeader>
            <CardTitle>Frontier Zones</CardTitle>
            <CardDescription>
              {zonesData?.count ?? 0} zones detected — click a zone to see nearby posts
            </CardDescription>
          </CardHeader>
          <CardContent>
            {zonesLoading ? (
              <div className="h-[400px] flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
                <span className="ml-2 text-muted-foreground">Detecting frontier zones...</span>
              </div>
            ) : zonesData?.error ? (
              <div className="h-[400px] flex items-center justify-center text-destructive">
                <AlertCircle className="w-5 h-5 mr-2" />
                {zonesData.error}
              </div>
            ) : !zonesData?.zones?.length ? (
              <div className="h-[400px] flex items-center justify-center text-muted-foreground">
                No frontier zones detected. Try adjusting the lookback period or source filter.
              </div>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={400}>
                  <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                    <XAxis
                      type="number"
                      dataKey="x"
                      name="X"
                      tick={false}
                      axisLine={{ stroke: 'hsl(var(--border))' }}
                    />
                    <YAxis
                      type="number"
                      dataKey="y"
                      name="Y"
                      tick={false}
                      axisLine={{ stroke: 'hsl(var(--border))' }}
                    />
                    <Tooltip content={<ZoneTooltip />} isAnimationActive={false} />
                    <Scatter
                      data={zonesData.zones.map(z => ({
                        ...z,
                        x: z.centroid_2d[0],
                        y: z.centroid_2d[1],
                      }))}
                      onClick={(point: any) => setSelectedZone(point as FrontierZone)}
                    >
                      {zonesData.zones.map((zone, i) => {
                        const seeds = seedsData?.seeds ?? []
                        const color = zone.seed_id
                          ? seedColor(zone.seed_id, seeds)
                          : scoreColor(zone.frontier_score)
                        return (
                          <Cell
                            key={i}
                            fill={color}
                            fillOpacity={0.8}
                            stroke={color}
                            strokeWidth={selectedZone?.id === zone.id ? 3 : 1}
                            r={Math.max(6, zone.frontier_score * 20)}
                          />
                        )
                      })}
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>

                {/* Legend — show seed labels if seeded, score ranges otherwise */}
                <div className="flex flex-wrap gap-4 mt-4 justify-center">
                  {zonesData.seeded && seedsData?.seeds?.length ? (
                    // Seed-based legend: show only seeds that have zones
                    (() => {
                      const usedSeedIds = new Set(zonesData.zones.map(z => z.seed_id).filter(Boolean))
                      return seedsData.seeds
                        .filter(s => usedSeedIds.has(s.seed_id))
                        .map(s => (
                          <div key={s.seed_id} className="flex items-center gap-2">
                            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: seedColor(s.seed_id, seedsData.seeds) }} />
                            <span className="text-sm text-muted-foreground">{s.label}</span>
                          </div>
                        ))
                    })()
                  ) : (
                    [
                      { label: 'High (70%+)', color: '#22c55e' },
                      { label: 'Medium (50%+)', color: '#3b82f6' },
                      { label: 'Low (30%+)', color: '#f59e0b' },
                      { label: 'Minimal (<30%)', color: '#6b7280' },
                    ].map(item => (
                      <div key={item.label} className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }} />
                        <span className="text-sm text-muted-foreground">{item.label}</span>
                      </div>
                    ))
                  )}
                </div>

                {/* Selected Zone Detail */}
                {selectedZone && (
                  <div className="mt-4 p-4 bg-secondary rounded-lg">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <Badge style={{ backgroundColor: scoreColor(selectedZone.frontier_score) }} className="text-white">
                          Score: {(selectedZone.frontier_score * 100).toFixed(0)}%
                        </Badge>
                        <span className="text-sm text-muted-foreground">Zone {selectedZone.id}</span>
                        {selectedZone.seed_label && (
                          <Badge
                            variant="outline"
                            className="text-xs"
                            style={{ borderColor: seedColor(selectedZone.seed_id, seedsData?.seeds ?? []) }}
                          >
                            {selectedZone.seed_label}
                          </Badge>
                        )}
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => setSelectedZone(null)}>
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                    <div className="grid grid-cols-3 gap-4 mb-3 text-sm">
                      <div>
                        <span className="text-muted-foreground">Density: </span>
                        <span className="font-medium">{(selectedZone.density_score * 100).toFixed(0)}%</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Adjacency: </span>
                        <span className="font-medium">{(selectedZone.adjacency_score * 100).toFixed(0)}%</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Relevance: </span>
                        <span className="font-medium">{(selectedZone.relevance_score * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                    {selectedZone.nearby_posts?.length > 0 && (
                      <div>
                        <div className="text-sm font-medium mb-2">Nearby Posts:</div>
                        <div className="space-y-2">
                          {selectedZone.nearby_posts.map((post, i) => (
                            <div key={i} className="text-sm text-muted-foreground p-2 bg-background rounded">
                              {post.text}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* ==================== SOURCES TAB ==================== */}
      {activeTab === 'sources' && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Discovered Sources</CardTitle>
            <CardDescription>
              {totalSources} sources{statusFilter !== 'all' ? ` with status "${statusFilter}"` : ''}
              {' — click a row for details'}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-hidden">
              <table className="w-full">
                <thead className="bg-secondary">
                  <tr>
                    <th className="text-left p-3 text-sm font-medium text-muted-foreground">Title</th>
                    <th className="text-left p-3 text-sm font-medium text-muted-foreground w-24">Type</th>
                    <th className="text-left p-3 text-sm font-medium text-muted-foreground w-24">Relevance</th>
                    <th className="text-left p-3 text-sm font-medium text-muted-foreground w-24">Status</th>
                    <th className="text-left p-3 text-sm font-medium text-muted-foreground w-28">Date</th>
                    <th className="text-left p-3 text-sm font-medium text-muted-foreground w-12">Link</th>
                    <th className="text-left p-3 text-sm font-medium text-muted-foreground w-16">Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {sourcesLoading ? (
                    <tr>
                      <td colSpan={7} className="p-4 text-center text-muted-foreground">
                        Loading...
                      </td>
                    </tr>
                  ) : paginatedSources.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="p-4 text-center text-muted-foreground">
                        No sources found. Run a discovery to populate this list.
                      </td>
                    </tr>
                  ) : (
                    paginatedSources.map((src, i) => {
                      const rating = src.user_rating ?? 0
                      return (
                        <tr
                          key={src.id || i}
                          className={cn(
                            'border-t border-border hover:bg-secondary/50 cursor-pointer',
                            rating === -1 && 'opacity-50',
                            rating === 1 && 'border-l-2 border-l-green-500',
                          )}
                          onClick={() => setSelectedSource(src)}
                        >
                          <td className="p-3 max-w-md">
                            <div className={cn('truncate text-sm font-medium', rating === -1 && 'line-through')}>
                              {src.title}
                              {src.total_chunks > 1 && (
                                <span className="text-xs text-muted-foreground ml-1">
                                  (part {src.chunk_index + 1}/{src.total_chunks})
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="p-3">
                            <Badge variant="outline" className="text-xs capitalize">
                              {src.source_type}
                            </Badge>
                          </td>
                          <td className="p-3">
                            <Badge variant="outline" className="text-xs">
                              {(src.relevance_score * 100).toFixed(0)}%
                            </Badge>
                          </td>
                          <td className="p-3">
                            <Badge variant={statusBadgeVariant(src.status)} className="text-xs capitalize">
                              {src.status}
                            </Badge>
                          </td>
                          <td className="p-3 text-sm text-muted-foreground">
                            {new Date(src.discovered_at).toLocaleDateString()}
                          </td>
                          <td className="p-3">
                            <a
                              href={src.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-muted-foreground hover:text-cyan-400 transition-colors"
                              title="Open source"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <ExternalLink className="w-4 h-4" />
                            </a>
                          </td>
                          <td className="p-3">
                            <div className="flex gap-1">
                              <RatingButton
                                current={rating}
                                target={1}
                                icon={ThumbsUp}
                                activeColor="text-green-400"
                                onClick={() => rateMutation.mutate({ sourceId: src.id, rating: rating === 1 ? 0 : 1 })}
                              />
                              <RatingButton
                                current={rating}
                                target={-1}
                                icon={ThumbsDown}
                                activeColor="text-red-400"
                                onClick={() => rateMutation.mutate({ sourceId: src.id, rating: rating === -1 ? 0 : -1 })}
                              />
                            </div>
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>

              {/* Pagination */}
              <div className="flex items-center justify-between p-3 bg-secondary border-t border-border">
                <span className="text-sm text-muted-foreground">
                  Showing {totalSources ? page * PAGE_SIZE + 1 : 0}-{Math.min((page + 1) * PAGE_SIZE, totalSources)} of {totalSources}
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => setPage(p => Math.max(0, p - 1))}
                    disabled={page === 0}
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => setPage(p => p + 1)}
                    disabled={page + 1 >= totalPages}
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ==================== DISCOVER TAB ==================== */}
      {activeTab === 'discover' && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Run Source Discovery</CardTitle>
              <CardDescription>
                Search for external content in frontier zones. This may take 30-60 seconds.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap items-end gap-4">
                <div>
                  <label className="text-sm text-muted-foreground mb-1 block">Max Rounds</label>
                  <Input
                    type="number"
                    min={1}
                    max={5}
                    value={discoverRounds}
                    onChange={e => setDiscoverRounds(e.target.value)}
                    className="w-24"
                  />
                </div>
                <div>
                  <label className="text-sm text-muted-foreground mb-1 block">Max Sources</label>
                  <Input
                    type="number"
                    min={5}
                    max={100}
                    value={discoverMaxSources}
                    onChange={e => setDiscoverMaxSources(e.target.value)}
                    className="w-24"
                  />
                </div>
                <div>
                  <label className="text-sm text-muted-foreground mb-1 block">Initial Zones</label>
                  <Input
                    type="number"
                    min={1}
                    max={10}
                    value={discoverZones}
                    onChange={e => setDiscoverZones(e.target.value)}
                    className="w-24"
                  />
                </div>
                <Button
                  onClick={() => discoverMutation.mutate()}
                  disabled={discoverMutation.isPending}
                  className="gap-2"
                >
                  {discoverMutation.isPending ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Discovering...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4" />
                      Run Discovery
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Focused Discovery Results */}
          {focusedDiscoveryMutation.data && !focusedDiscoveryMutation.data.error && focusedDiscoveryMutation.data.focused && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Focus className="w-5 h-5 text-primary" />
                  Focused Discovery Results
                </CardTitle>
                <CardDescription>
                  <div className="flex flex-wrap items-center gap-2">
                    <span>
                      {focusedDiscoveryMutation.data.discovered_at
                        ? `Completed at ${new Date(focusedDiscoveryMutation.data.discovered_at).toLocaleTimeString()}`
                        : 'Completed'
                      }
                      {' — focused on:'}
                    </span>
                    {focusedDiscoveryMutation.data.focused_seeds?.map(label => (
                      <Badge key={label} variant="outline" className="text-xs">
                        {label}
                      </Badge>
                    ))}
                  </div>
                </CardDescription>
              </CardHeader>
              <CardContent>
                {/* Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                  <div className="p-3 bg-secondary rounded-lg text-center">
                    <div className="text-xl font-bold text-green-400">
                      {focusedDiscoveryMutation.data.frontier_sources.length}
                    </div>
                    <div className="text-xs text-muted-foreground">Frontier Sources</div>
                  </div>
                  <div className="p-3 bg-secondary rounded-lg text-center">
                    <div className="text-xl font-bold text-amber-400">
                      {focusedDiscoveryMutation.data.pending_sources.length}
                    </div>
                    <div className="text-xs text-muted-foreground">Pending Sources</div>
                  </div>
                  <div className="p-3 bg-secondary rounded-lg text-center">
                    <div className="text-xl font-bold">
                      {focusedDiscoveryMutation.data.stats.zones_explored}
                    </div>
                    <div className="text-xs text-muted-foreground">Zones Explored</div>
                  </div>
                  <div className="p-3 bg-secondary rounded-lg text-center">
                    <div className="text-xl font-bold">
                      {focusedDiscoveryMutation.data.stats.rounds_completed}
                    </div>
                    <div className="text-xs text-muted-foreground">Rounds Completed</div>
                  </div>
                </div>

                {focusedDiscoveryMutation.data.errors.length > 0 && (
                  <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm mb-4">
                    <div className="font-medium mb-1">Errors:</div>
                    {focusedDiscoveryMutation.data.errors.map((err, i) => (
                      <div key={i}>{err}</div>
                    ))}
                  </div>
                )}

                {/* Frontier Sources List */}
                {focusedDiscoveryMutation.data.frontier_sources.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium mb-2">Frontier Sources:</h3>
                    <div className="space-y-2">
                      {focusedDiscoveryMutation.data.frontier_sources.map((src, i) => (
                        <div key={i} className="p-3 bg-secondary rounded-lg">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-medium text-sm">{src.title}</span>
                            <Badge variant="outline" className="text-xs">
                              {(src.relevance_score * 100).toFixed(0)}%
                            </Badge>
                            <a
                              href={src.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-muted-foreground hover:text-cyan-400"
                            >
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          </div>
                          <p className="text-xs text-muted-foreground line-clamp-2">{src.excerpt}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Focused Discovery Error */}
          {focusedDiscoveryMutation.data?.error && (
            <Card>
              <CardContent className="p-6">
                <div className="flex items-center gap-2 text-destructive">
                  <AlertCircle className="w-5 h-5" />
                  <span>Focused discovery error: {focusedDiscoveryMutation.data.error}</span>
                </div>
              </CardContent>
            </Card>
          )}

          {focusedDiscoveryMutation.error && (
            <Card>
              <CardContent className="p-6">
                <div className="flex items-center gap-2 text-destructive">
                  <AlertCircle className="w-5 h-5" />
                  <span>Focused discovery request failed: {String(focusedDiscoveryMutation.error)}</span>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Discovery Results */}
          {discoverMutation.data && !discoverMutation.data.error && (
            <Card>
              <CardHeader>
                <CardTitle>Discovery Results</CardTitle>
                <CardDescription>
                  {discoverMutation.data.discovered_at
                    ? `Completed at ${new Date(discoverMutation.data.discovered_at).toLocaleTimeString()}`
                    : 'Completed'
                  }
                </CardDescription>
              </CardHeader>
              <CardContent>
                {/* Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                  <div className="p-3 bg-secondary rounded-lg text-center">
                    <div className="text-xl font-bold text-green-400">
                      {discoverMutation.data.frontier_sources.length}
                    </div>
                    <div className="text-xs text-muted-foreground">Frontier Sources</div>
                  </div>
                  <div className="p-3 bg-secondary rounded-lg text-center">
                    <div className="text-xl font-bold text-amber-400">
                      {discoverMutation.data.pending_sources.length}
                    </div>
                    <div className="text-xs text-muted-foreground">Pending Sources</div>
                  </div>
                  <div className="p-3 bg-secondary rounded-lg text-center">
                    <div className="text-xl font-bold">
                      {discoverMutation.data.stats.zones_explored}
                    </div>
                    <div className="text-xs text-muted-foreground">Zones Explored</div>
                  </div>
                  <div className="p-3 bg-secondary rounded-lg text-center">
                    <div className="text-xl font-bold">
                      {discoverMutation.data.stats.rounds_completed}
                    </div>
                    <div className="text-xs text-muted-foreground">Rounds Completed</div>
                  </div>
                </div>

                {discoverMutation.data.stats.capped && (
                  <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg text-amber-400 text-sm mb-4">
                    Discovery was capped at the maximum source limit.
                  </div>
                )}

                {discoverMutation.data.errors.length > 0 && (
                  <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm mb-4">
                    <div className="font-medium mb-1">Errors:</div>
                    {discoverMutation.data.errors.map((err, i) => (
                      <div key={i}>{err}</div>
                    ))}
                  </div>
                )}

                {/* Frontier Sources List */}
                {discoverMutation.data.frontier_sources.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium mb-2">Frontier Sources:</h3>
                    <div className="space-y-2">
                      {discoverMutation.data.frontier_sources.map((src, i) => (
                        <div key={i} className="p-3 bg-secondary rounded-lg">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-medium text-sm">{src.title}</span>
                            <Badge variant="outline" className="text-xs">
                              {(src.relevance_score * 100).toFixed(0)}%
                            </Badge>
                            <a
                              href={src.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-muted-foreground hover:text-cyan-400"
                            >
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          </div>
                          <p className="text-xs text-muted-foreground line-clamp-2">{src.excerpt}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Discovery Error */}
          {discoverMutation.data?.error && (
            <Card>
              <CardContent className="p-6">
                <div className="flex items-center gap-2 text-destructive">
                  <AlertCircle className="w-5 h-5" />
                  <span>{discoverMutation.data.error}</span>
                </div>
              </CardContent>
            </Card>
          )}

          {discoverMutation.error && (
            <Card>
              <CardContent className="p-6">
                <div className="flex items-center gap-2 text-destructive">
                  <AlertCircle className="w-5 h-5" />
                  <span>Discovery request failed: {String(discoverMutation.error)}</span>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ==================== SOURCE DETAIL MODAL ==================== */}
      {selectedSource && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="max-w-2xl w-full max-h-[80vh] overflow-hidden flex flex-col">
            <CardHeader className="flex-shrink-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{selectedSource.title}</span>
                  <Badge variant={statusBadgeVariant(selectedSource.status)} className="capitalize">
                    {selectedSource.status}
                  </Badge>
                  <Badge variant="outline" className="text-xs">
                    {(selectedSource.relevance_score * 100).toFixed(0)}%
                  </Badge>
                  <a
                    href={selectedSource.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-muted-foreground hover:text-cyan-400 transition-colors"
                    title="Open source"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </a>
                </div>
                <Button variant="ghost" size="icon" onClick={() => setSelectedSource(null)}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
              <CardDescription>
                <span className="capitalize">{selectedSource.source_type}</span>
                {' — '}
                {new Date(selectedSource.discovered_at).toLocaleString()}
                {selectedSource.total_chunks > 1 && ` — Part ${selectedSource.chunk_index + 1} of ${selectedSource.total_chunks}`}
                {selectedSource.query_used && (
                  <span className="block mt-1">Query: "{selectedSource.query_used}"</span>
                )}
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-auto flex-1">
              <p className="whitespace-pre-wrap text-sm">{selectedSource.excerpt}</p>

              {/* Feedback section */}
              <div className="mt-6 pt-4 border-t border-border">
                <div className="text-sm font-medium mb-3">Rate this source</div>
                <div className="flex items-center gap-3">
                  <Button
                    variant={(selectedSource.user_rating ?? 0) === 1 ? 'default' : 'outline'}
                    size="sm"
                    className={cn('gap-2', (selectedSource.user_rating ?? 0) === 1 && 'bg-green-600 hover:bg-green-700')}
                    onClick={() => rateMutation.mutate({
                      sourceId: selectedSource.id,
                      rating: (selectedSource.user_rating ?? 0) === 1 ? 0 : 1,
                    })}
                  >
                    <ThumbsUp className="w-4 h-4" />
                    Uprank
                  </Button>
                  <Button
                    variant={(selectedSource.user_rating ?? 0) === -1 ? 'default' : 'outline'}
                    size="sm"
                    className={cn('gap-2', (selectedSource.user_rating ?? 0) === -1 && 'bg-red-600 hover:bg-red-700')}
                    onClick={() => rateMutation.mutate({
                      sourceId: selectedSource.id,
                      rating: (selectedSource.user_rating ?? 0) === -1 ? 0 : -1,
                    })}
                  >
                    <ThumbsDown className="w-4 h-4" />
                    Downrank
                  </Button>
                  {(selectedSource.user_rating ?? 0) !== 0 && (
                    <span className="text-xs text-muted-foreground">
                      Rated {selectedSource.rated_at ? new Date(selectedSource.rated_at).toLocaleString() : ''}
                    </span>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

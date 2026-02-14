import { useQuery } from '@tanstack/react-query'
import { useState, useMemo } from 'react'
import {
  Radio, Users, TrendingUp, Activity,
  ChevronLeft, ChevronRight, Search, X, ExternalLink
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { API_BASE } from '@/lib/config'

// --- Types ---

interface RelevantPost {
  uri: string
  text: string
  relevance_score: number
  source_handle: string
  created_at?: string
}

interface RelevantAccount {
  handle: string
  post_count: number
  avg_relevance: number
  top_post?: string
}

interface TrendingTopic {
  post_count: number
  avg_relevance: number
  contributors: string[]
  sample_text?: string
}

interface RelevanceStats {
  last_refresh?: string
  refresh_interval?: number
  error?: string
}

// --- Helpers ---

function getBlueskyUrl(uri: string, handle: string): string | null {
  const match = uri.match(/at:\/\/[^/]+\/app\.bsky\.feed\.post\/([^/]+)/)
  if (match && handle) {
    return `https://bsky.app/profile/${handle}/post/${match[1]}`
  }
  return null
}

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  iconColor = 'text-primary'
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

// --- Constants ---

const PAGE_SIZE = 20

const TIME_RANGES = [
  { value: '7', label: '7 days' },
  { value: '14', label: '14 days' },
  { value: '30', label: '30 days' },
]

const RELEVANCE_THRESHOLDS = [
  { value: '0.3', label: '30%+' },
  { value: '0.4', label: '40%+' },
  { value: '0.5', label: '50%+' },
  { value: '0.6', label: '60%+' },
  { value: '0.7', label: '70%+' },
]

type TabId = 'posts' | 'accounts' | 'topics'

// --- Component ---

export default function NetworkView() {
  const [days, setDays] = useState(14)
  const [minRelevance, setMinRelevance] = useState(0.5)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [activeTab, setActiveTab] = useState<TabId>('posts')
  const [page, setPage] = useState(0)
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null)
  const [selectedPost, setSelectedPost] = useState<RelevantPost | null>(null)

  // --- Data fetching ---

  const { data: postsData, isLoading: postsLoading } = useQuery<{ posts: RelevantPost[]; count: number }>({
    queryKey: ['networkPosts', days, minRelevance],
    queryFn: () => fetch(
      `${API_BASE}/semantic/relevance/top?days=${days}&min_relevance=${minRelevance}&limit=100`
    ).then(r => r.json()),
    refetchInterval: 120000,
  })

  const { data: accountsData, isLoading: accountsLoading } = useQuery<{ accounts: RelevantAccount[]; count: number }>({
    queryKey: ['networkAccounts', days, minRelevance],
    queryFn: () => fetch(
      `${API_BASE}/semantic/relevance/accounts?days=${days}&min_relevance=${minRelevance}&limit=50`
    ).then(r => r.json()),
    refetchInterval: 120000,
  })

  const { data: topicsData, isLoading: topicsLoading } = useQuery<{ topics: TrendingTopic[]; count: number }>({
    queryKey: ['networkTopics', days, minRelevance],
    queryFn: () => fetch(
      `${API_BASE}/semantic/relevance/trending?days=${days}&min_relevance=${minRelevance}`
    ).then(r => r.json()),
    refetchInterval: 120000,
  })

  const { data: statsData } = useQuery<RelevanceStats>({
    queryKey: ['networkStats'],
    queryFn: () => fetch(`${API_BASE}/semantic/relevance/stats`).then(r => r.json()),
    refetchInterval: 120000,
  })

  // --- Client-side filtering & pagination ---

  const filteredPosts = useMemo(() => {
    let posts = postsData?.posts ?? []
    if (selectedAccount) {
      posts = posts.filter(p => p.source_handle === selectedAccount)
    }
    if (search) {
      const q = search.toLowerCase()
      posts = posts.filter(p =>
        p.text.toLowerCase().includes(q) ||
        p.source_handle.toLowerCase().includes(q)
      )
    }
    return posts
  }, [postsData, selectedAccount, search])

  const totalFilteredPosts = filteredPosts.length
  const totalPages = Math.max(1, Math.ceil(totalFilteredPosts / PAGE_SIZE))
  const paginatedPosts = filteredPosts.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  // Avg relevance across all returned posts
  const avgRelevance = useMemo(() => {
    const posts = postsData?.posts
    if (!posts || posts.length === 0) return 0
    return posts.reduce((sum, p) => sum + p.relevance_score, 0) / posts.length
  }, [postsData])

  // --- Handlers ---

  const handleSearch = () => {
    setSearch(searchInput)
    setPage(0)
  }

  const clearSearch = () => {
    setSearchInput('')
    setSearch('')
    setPage(0)
  }

  const handleAccountClick = (handle: string) => {
    setSelectedAccount(handle)
    setActiveTab('posts')
    setPage(0)
    setSearch('')
    setSearchInput('')
  }

  const clearAccountFilter = () => {
    setSelectedAccount(null)
    setPage(0)
  }

  const handleDaysChange = (v: string) => {
    setDays(Number(v))
    setPage(0)
  }

  const handleRelevanceChange = (v: string) => {
    setMinRelevance(Number(v))
    setPage(0)
  }

  // --- Tab definitions ---

  const tabs: { id: TabId; label: string }[] = [
    { id: 'posts', label: 'Posts' },
    { id: 'accounts', label: 'Accounts' },
    { id: 'topics', label: 'Topics' },
  ]

  // --- Last refresh subtitle ---
  const lastRefresh = statsData?.last_refresh
    ? `Last refresh: ${new Date(statsData.last_refresh).toLocaleString()}`
    : undefined

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Network Analysis</h1>
        <p className="text-muted-foreground">
          Relevant content from your network
        </p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Relevant Posts"
          value={postsData?.count ?? 0}
          subtitle={lastRefresh}
          icon={Radio}
          iconColor="text-cyan-400"
        />
        <StatCard
          title="Active Accounts"
          value={accountsData?.count ?? 0}
          icon={Users}
          iconColor="text-violet-400"
        />
        <StatCard
          title="Trending Topics"
          value={topicsData?.count ?? 0}
          icon={TrendingUp}
          iconColor="text-amber-400"
        />
        <StatCard
          title="Avg Relevance"
          value={avgRelevance ? `${(avgRelevance * 100).toFixed(1)}%` : '—'}
          icon={Activity}
          iconColor="text-green-400"
        />
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="w-36">
              <Select value={String(days)} onValueChange={handleDaysChange}>
                <SelectTrigger>
                  <SelectValue placeholder="Time Range" />
                </SelectTrigger>
                <SelectContent>
                  {TIME_RANGES.map(t => (
                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="w-36">
              <Select value={String(minRelevance)} onValueChange={handleRelevanceChange}>
                <SelectTrigger>
                  <SelectValue placeholder="Min Relevance" />
                </SelectTrigger>
                <SelectContent>
                  {RELEVANCE_THRESHOLDS.map(t => (
                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex gap-2 flex-1 min-w-[200px]">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search posts..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  className="pl-9"
                />
                {searchInput && (
                  <button
                    onClick={clearSearch}
                    className="absolute right-3 top-1/2 -translate-y-1/2"
                  >
                    <X className="w-4 h-4 text-muted-foreground hover:text-foreground" />
                  </button>
                )}
              </div>
              <Button onClick={handleSearch}>Search</Button>
            </div>

            {selectedAccount && (
              <Badge
                variant="secondary"
                className="gap-1 cursor-pointer hover:bg-destructive/20"
                onClick={clearAccountFilter}
              >
                @{selectedAccount}
                <X className="w-3 h-3" />
              </Badge>
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
            onClick={() => {
              setActiveTab(tab.id)
              setPage(0)
            }}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'posts' && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Relevant Posts</CardTitle>
            <CardDescription>
              {totalFilteredPosts} posts
              {search && ` matching "${search}"`}
              {selectedAccount && ` from @${selectedAccount}`}
              {' — click a row to view full content'}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-hidden">
              <table className="w-full">
                <thead className="bg-secondary">
                  <tr>
                    <th className="text-left p-3 text-sm font-medium text-muted-foreground w-36">Handle</th>
                    <th className="text-left p-3 text-sm font-medium text-muted-foreground">Text</th>
                    <th className="text-left p-3 text-sm font-medium text-muted-foreground w-24">Relevance</th>
                    <th className="text-left p-3 text-sm font-medium text-muted-foreground w-28">Date</th>
                    <th className="text-left p-3 text-sm font-medium text-muted-foreground w-12">Link</th>
                  </tr>
                </thead>
                <tbody>
                  {postsLoading ? (
                    <tr>
                      <td colSpan={5} className="p-4 text-center text-muted-foreground">
                        Loading...
                      </td>
                    </tr>
                  ) : paginatedPosts.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-4 text-center text-muted-foreground">
                        No posts found
                      </td>
                    </tr>
                  ) : (
                    paginatedPosts.map((post, i) => {
                      const blueskyUrl = getBlueskyUrl(post.uri, post.source_handle)
                      return (
                        <tr
                          key={post.uri || i}
                          className="border-t border-border hover:bg-secondary/50 cursor-pointer"
                          onClick={() => setSelectedPost(post)}
                        >
                          <td className="p-3">
                            <span className="text-sm font-medium text-cyan-400">
                              @{post.source_handle}
                            </span>
                          </td>
                          <td className="p-3 max-w-md">
                            <div className="truncate text-sm">
                              {post.text?.slice(0, 120)}{post.text?.length > 120 ? '...' : ''}
                            </div>
                          </td>
                          <td className="p-3">
                            <Badge variant="outline" className="text-xs">
                              {(post.relevance_score * 100).toFixed(0)}%
                            </Badge>
                          </td>
                          <td className="p-3 text-sm text-muted-foreground">
                            {post.created_at
                              ? new Date(post.created_at).toLocaleDateString()
                              : '—'
                            }
                          </td>
                          <td className="p-3">
                            {blueskyUrl && (
                              <a
                                href={blueskyUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-muted-foreground hover:text-cyan-400 transition-colors"
                                title="View on Bluesky"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <ExternalLink className="w-4 h-4" />
                              </a>
                            )}
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
                  Showing {totalFilteredPosts ? page * PAGE_SIZE + 1 : 0}-{Math.min((page + 1) * PAGE_SIZE, totalFilteredPosts)} of {totalFilteredPosts}
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

      {activeTab === 'accounts' && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Top Accounts</CardTitle>
            <CardDescription>
              Accounts sharing the most relevant content — click to filter posts
            </CardDescription>
          </CardHeader>
          <CardContent>
            {accountsLoading ? (
              <div className="p-4 text-center text-muted-foreground">Loading...</div>
            ) : !accountsData?.accounts?.length ? (
              <div className="p-4 text-center text-muted-foreground">No accounts found</div>
            ) : (
              <div className="space-y-3">
                {accountsData.accounts.map((account, i) => (
                  <div
                    key={account.handle}
                    className="flex items-center gap-4 p-4 bg-secondary rounded-lg cursor-pointer hover:bg-secondary/70 transition-colors"
                    onClick={() => handleAccountClick(account.handle)}
                  >
                    <div className="text-2xl font-bold text-muted-foreground w-8 text-right">
                      {i + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-violet-400">@{account.handle}</div>
                      {account.top_post && (
                        <p className="text-xs text-muted-foreground truncate mt-0.5">
                          {account.top_post}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant="secondary" className="text-xs">
                        {account.post_count} posts
                      </Badge>
                      <Badge variant="outline" className="text-xs">
                        {(account.avg_relevance * 100).toFixed(0)}%
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === 'topics' && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Trending Topics</CardTitle>
            <CardDescription>
              Emerging themes in your network
            </CardDescription>
          </CardHeader>
          <CardContent>
            {topicsLoading ? (
              <div className="p-4 text-center text-muted-foreground">Loading...</div>
            ) : !topicsData?.topics?.length ? (
              <div className="p-4 text-center text-muted-foreground">No topics found</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {topicsData.topics.map((topic, i) => (
                  <div key={i} className="p-4 bg-secondary rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <Badge variant="default" className="bg-amber-500/20 text-amber-400">
                        {topic.post_count} posts
                      </Badge>
                      <Badge variant="outline" className="text-xs">
                        {(topic.avg_relevance * 100).toFixed(0)}% relevant
                      </Badge>
                    </div>
                    {topic.sample_text && (
                      <p className="text-sm text-muted-foreground whitespace-pre-wrap mb-2">
                        {topic.sample_text}
                      </p>
                    )}
                    <div className="text-xs text-muted-foreground">
                      {topic.contributors.slice(0, 5).map(c => `@${c}`).join(', ')}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Post Detail Modal */}
      {selectedPost && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="max-w-2xl w-full max-h-[80vh] overflow-hidden flex flex-col">
            <CardHeader className="flex-shrink-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-cyan-400">@{selectedPost.source_handle}</span>
                  <Badge variant="outline">
                    {(selectedPost.relevance_score * 100).toFixed(0)}% relevant
                  </Badge>
                  {(() => {
                    const url = getBlueskyUrl(selectedPost.uri, selectedPost.source_handle)
                    return url ? (
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-muted-foreground hover:text-cyan-400 transition-colors"
                        title="View on Bluesky"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    ) : null
                  })()}
                </div>
                <Button variant="ghost" size="icon" onClick={() => setSelectedPost(null)}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
              <CardDescription>
                {selectedPost.created_at
                  ? new Date(selectedPost.created_at).toLocaleString()
                  : 'No date'
                }
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-auto flex-1">
              <p className="whitespace-pre-wrap">{selectedPost.text}</p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

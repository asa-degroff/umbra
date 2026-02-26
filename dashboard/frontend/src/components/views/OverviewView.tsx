import { useQuery } from '@tanstack/react-query'
import { Activity, Database, Cpu, Clock, Radio, Users, TrendingUp, ExternalLink } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { API_BASE } from '@/lib/config'

// Convert AT URI to Bluesky web URL
function getBlueskyUrl(uri: string, handle: string): string | null {
  // URI format: at://did:plc:xxx/app.bsky.feed.post/rkey
  const match = uri.match(/at:\/\/[^/]+\/app\.bsky\.feed\.post\/([^/]+)/)
  if (match && handle) {
    return `https://bsky.app/profile/${handle}/post/${match[1]}`
  }
  return null
}

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

interface SystemStatus {
  dashboard: {
    websocket_clients: number
    event_history_size: number
  }
  event_listener: {
    running: boolean
    connected_sources: number
  }
}

interface DatabaseStats {
  sqlite: {
    available: boolean
    tables?: Record<string, number>
  }
  chromadb: {
    available: boolean
    total_records?: number
  }
}

interface OllamaStatus {
  status: 'running' | 'offline' | 'error'
  models?: Array<{ name: string; size: number }>
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

export default function OverviewView() {
  const { data: systemStatus } = useQuery<SystemStatus>({
    queryKey: ['systemStatus'],
    queryFn: () => fetch(`${API_BASE}/system/status`).then(r => r.json()),
    refetchInterval: 5000,
  })

  const { data: dbStats } = useQuery<DatabaseStats>({
    queryKey: ['databaseStats'],
    queryFn: () => fetch(`${API_BASE}/system/databases`).then(r => r.json()),
    refetchInterval: 10000,
  })

  const { data: ollamaStatus } = useQuery<OllamaStatus>({
    queryKey: ['ollamaStatus'],
    queryFn: () => fetch(`${API_BASE}/system/ollama`).then(r => r.json()),
    refetchInterval: 10000,
  })

  const { data: semanticMetrics } = useQuery({
    queryKey: ['semanticMetrics'],
    queryFn: () => fetch(`${API_BASE}/semantic/metrics`).then(r => r.json()),
    refetchInterval: 30000,
  })

  // Network relevance queries
  const { data: relevantPosts } = useQuery<{ posts: RelevantPost[] }>({
    queryKey: ['relevantPosts'],
    queryFn: () => fetch(`${API_BASE}/semantic/relevance/top?limit=5`).then(r => r.json()),
    refetchInterval: 60000,
  })

  const { data: relevantAccounts } = useQuery<{ accounts: RelevantAccount[] }>({
    queryKey: ['relevantAccounts'],
    queryFn: () => fetch(`${API_BASE}/semantic/relevance/accounts?limit=5`).then(r => r.json()),
    refetchInterval: 60000,
  })

  const { data: trendingTopics } = useQuery<{ topics: TrendingTopic[] }>({
    queryKey: ['trendingTopics'],
    queryFn: () => fetch(`${API_BASE}/semantic/relevance/trending`).then(r => r.json()),
    refetchInterval: 60000,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Overview</h1>
        <p className="text-muted-foreground">
          System status and key metrics at a glance
        </p>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="WebSocket Clients"
          value={systemStatus?.dashboard?.websocket_clients ?? 0}
          subtitle={systemStatus?.event_listener?.running ? 'Listener running' : 'Listener stopped'}
          icon={Activity}
          iconColor="text-blue-400"
        />
        
        <StatCard
          title="Semantic Records"
          value={dbStats?.chromadb?.total_records ?? 0}
          subtitle={dbStats?.chromadb?.available ? 'ChromaDB connected' : 'ChromaDB offline'}
          icon={Database}
          iconColor="text-green-400"
        />

        <StatCard
          title="Ollama Models"
          value={ollamaStatus?.models?.length ?? 0}
          subtitle={ollamaStatus?.status === 'running' ? 'Ollama running' : 'Ollama offline'}
          icon={Cpu}
          iconColor="text-yellow-400"
        />

        <StatCard
          title="Diversity Score"
          value={semanticMetrics?.weighted_avg_diversity?.toFixed(3) ?? '—'}
          subtitle={`${semanticMetrics?.records_with_embeddings ?? 0} records analyzed`}
          icon={Clock}
          iconColor="text-purple-400"
        />
      </div>

      {/* Semantic Guidance */}
      {semanticMetrics && !semanticMetrics.error && (
        <Card>
          <CardHeader>
            <CardTitle>Semantic Analysis</CardTitle>
            <CardDescription>Content diversity metrics from the last 7 days</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <div className="text-sm text-muted-foreground">Diversity Score</div>
                <div className="text-2xl font-bold">
                  {(semanticMetrics.weighted_avg_diversity * 100).toFixed(1)}%
                </div>
              </div>
              <div>
                <div className="text-sm text-muted-foreground">Cluster Dominance</div>
                <div className="text-2xl font-bold">
                  {(semanticMetrics.cluster_dominance * 100).toFixed(1)}%
                </div>
              </div>
              <div>
                <div className="text-sm text-muted-foreground">Platforms</div>
                <div className="flex flex-wrap gap-2 mt-1">
                  {semanticMetrics.platforms && Object.entries(semanticMetrics.platforms).map(([k, v]) => (
                    <Badge key={k} variant="secondary">
                      {k}: {v as number}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Ollama Models */}
      {ollamaStatus?.models && ollamaStatus.models.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Ollama Models</CardTitle>
            <CardDescription>Available local models for inference</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {ollamaStatus.models.map(model => (
                <div key={model.name} className="flex justify-between items-center p-3 bg-secondary rounded-lg">
                  <span className="font-mono text-sm">{model.name}</span>
                  <Badge variant="outline">
                    {(model.size / 1e9).toFixed(1)} GB
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Network Relevance Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Network Pulse - Top Relevant Posts */}
        {relevantPosts?.posts && relevantPosts.posts.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Radio className="w-5 h-5 text-cyan-400" />
                Network Pulse
              </CardTitle>
              <CardDescription>Most relevant posts from your network</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {relevantPosts.posts.slice(0, 5).map((post, _i) => {
                  const blueskyUrl = getBlueskyUrl(post.uri, post.source_handle)
                  return (
                    <div key={post.uri} className="p-3 bg-secondary rounded-lg">
                      <div className="flex justify-between items-start mb-1">
                        <span className="text-sm font-medium text-cyan-400">@{post.source_handle}</span>
                        <div className="flex items-center gap-2">
                          {blueskyUrl && (
                            <a
                              href={blueskyUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-muted-foreground hover:text-cyan-400 transition-colors"
                              title="View on Bluesky"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          )}
                          <Badge variant="outline" className="text-xs">
                            {(post.relevance_score * 100).toFixed(0)}%
                          </Badge>
                        </div>
                      </div>
                      <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                        {post.text}
                      </p>
                    </div>
                  )
                })}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Top Voices - Relevant Accounts */}
        {relevantAccounts?.accounts && relevantAccounts.accounts.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="w-5 h-5 text-violet-400" />
                Top Voices
              </CardTitle>
              <CardDescription>Accounts sharing the most relevant content</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {relevantAccounts.accounts.slice(0, 5).map((account, _i) => (
                  <div key={account.handle} className="flex items-center justify-between p-3 bg-secondary rounded-lg">
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-violet-400">@{account.handle}</div>
                      {account.top_post && (
                        <p className="text-xs text-muted-foreground truncate mt-0.5">
                          {account.top_post}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 ml-3 shrink-0">
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
            </CardContent>
          </Card>
        )}
      </div>

      {/* Trending Topics */}
      {trendingTopics?.topics && trendingTopics.topics.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-amber-400" />
              Trending Topics
            </CardTitle>
            <CardDescription>Emerging themes in your network</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {trendingTopics.topics.slice(0, 6).map((topic, i) => (
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
                    {topic.contributors.slice(0, 3).map(c => `@${c}`).join(', ')}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

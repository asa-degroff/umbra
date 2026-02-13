import { useQuery } from '@tanstack/react-query'
import { Activity, Database, Cpu, Clock } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { API_BASE } from '@/lib/config'

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
    </div>
  )
}

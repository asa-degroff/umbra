import { useQuery } from '@tanstack/react-query'
import { Brain, TrendingUp, MessageSquare } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const API_BASE = `http://${window.location.hostname}:8081/api`

export default function SemanticView() {
  const { data: guidance, isLoading } = useQuery({
    queryKey: ['semanticGuidance'],
    queryFn: () => fetch(`${API_BASE}/semantic/guidance`).then(r => r.json()),
    refetchInterval: 60000,
  })

  const { data: metrics } = useQuery({
    queryKey: ['semanticMetrics'],
    queryFn: () => fetch(`${API_BASE}/semantic/metrics`).then(r => r.json()),
    refetchInterval: 30000,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Semantic Analysis</h1>
        <p className="text-muted-foreground">
          Content diversity metrics and guidance
        </p>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-3 mb-2">
              <Brain className="w-5 h-5 text-purple-400" />
              <span className="text-sm text-muted-foreground">Diversity Score</span>
            </div>
            <div className="text-3xl font-bold">
              {metrics?.weighted_avg_diversity 
                ? `${(metrics.weighted_avg_diversity * 100).toFixed(1)}%`
                : '—'
              }
            </div>
            <div className="text-sm text-muted-foreground mt-1">
              Higher is more diverse
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-3 mb-2">
              <TrendingUp className="w-5 h-5 text-blue-400" />
              <span className="text-sm text-muted-foreground">Cluster Dominance</span>
            </div>
            <div className="text-3xl font-bold">
              {metrics?.cluster_dominance 
                ? `${(metrics.cluster_dominance * 100).toFixed(1)}%`
                : '—'
              }
            </div>
            <div className="text-sm text-muted-foreground mt-1">
              Lower is better balanced
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-3 mb-2">
              <MessageSquare className="w-5 h-5 text-green-400" />
              <span className="text-sm text-muted-foreground">Records Analyzed</span>
            </div>
            <div className="text-3xl font-bold">
              {metrics?.records_with_embeddings ?? '—'}
            </div>
            <div className="text-sm text-muted-foreground mt-1">
              Last 7 days
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Guidance Panel */}
      <Card>
        <CardHeader>
          <CardTitle>Diversity Guidance</CardTitle>
          <CardDescription>AI-generated recommendations for content variety</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="text-muted-foreground">Loading guidance...</div>
          ) : guidance?.error ? (
            <div className="text-destructive">{guidance.error}</div>
          ) : (
            <>
              <div className="bg-secondary rounded-lg p-4 mb-4">
                <p className="text-foreground whitespace-pre-wrap">{guidance?.guidance}</p>
              </div>
              
              {guidance?.summary && (
                <div className="text-sm text-muted-foreground">
                  <strong>Summary:</strong> {guidance.summary}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Platform Breakdown */}
      {metrics?.platforms && (
        <Card>
          <CardHeader>
            <CardTitle>Platform Distribution</CardTitle>
            <CardDescription>Content breakdown by source</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(metrics.platforms).map(([platform, count]) => {
                const percentage = ((count as number) / metrics.records_with_embeddings) * 100
                return (
                  <div key={platform} className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span className="capitalize">{platform}</span>
                      <span className="text-muted-foreground">
                        {count as number} ({percentage.toFixed(1)}%)
                      </span>
                    </div>
                    <div className="h-2 bg-secondary rounded-full overflow-hidden">
                      <div 
                        className={cn(
                          "h-full rounded-full",
                          platform === 'bluesky' ? 'bg-blue-500' :
                          platform === 'comind' ? 'bg-purple-500' :
                          platform === 'greengale' ? 'bg-green-500' :
                          'bg-primary'
                        )}
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

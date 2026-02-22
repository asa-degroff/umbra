import { useQuery } from '@tanstack/react-query'
import { Brain, TrendingUp, MessageSquare, Layers, Activity, BarChart3 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import ClusterVisualization from '@/components/semantic/ClusterVisualization'
import { API_BASE } from '@/lib/config'

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

      {/* Cluster Visualization */}
      <ClusterVisualization />

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

      {/* LLM Context: Topic Clusters & Metrics */}
      {guidance?.clusters && guidance.clusters.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Layers className="w-5 h-5 text-amber-400" />
              LLM Context
            </CardTitle>
            <CardDescription>
              Metrics and topic clusters passed to the LLM for guidance generation
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Detailed Metrics Grid */}
            <div>
              <h4 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-1.5">
                <BarChart3 className="w-3.5 h-3.5" />
                Metrics
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-secondary rounded-lg p-3">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Diversity</div>
                  <div className="text-lg font-bold">
                    {guidance.metrics?.diversity != null
                      ? `${(guidance.metrics.diversity * 100).toFixed(1)}%`
                      : '—'}
                  </div>
                  <div className="text-[10px] text-muted-foreground">weighted by recency</div>
                </div>
                <div className="bg-secondary rounded-lg p-3">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Avg Diversity</div>
                  <div className="text-lg font-bold">
                    {guidance.metrics?.avg_diversity != null
                      ? `${(guidance.metrics.avg_diversity * 100).toFixed(1)}%`
                      : '—'}
                  </div>
                  <div className="text-[10px] text-muted-foreground">unweighted</div>
                </div>
                <div className="bg-secondary rounded-lg p-3">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Pairwise Similarity</div>
                  <div className="text-lg font-bold">
                    {guidance.metrics?.avg_pairwise_similarity != null
                      ? `${(guidance.metrics.avg_pairwise_similarity * 100).toFixed(1)}%`
                      : '—'}
                  </div>
                  <div className="text-[10px] text-muted-foreground">lower = more diverse</div>
                </div>
                <div className="bg-secondary rounded-lg p-3">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Cluster Dominance</div>
                  <div className="text-lg font-bold">
                    {guidance.metrics?.cluster_dominance != null
                      ? `${(guidance.metrics.cluster_dominance * 100).toFixed(1)}%`
                      : '—'}
                  </div>
                  <div className="text-[10px] text-muted-foreground">largest cluster share</div>
                </div>
              </div>
            </div>

            {/* Topic Clusters */}
            <div>
              <h4 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5" />
                Topic Clusters
                <span className="text-[10px] text-muted-foreground/60">
                  (by recency-weighted importance)
                </span>
              </h4>
              <div className="space-y-3">
                {guidance.clusters.map((cluster: {
                  index: number
                  pct: number
                  size: number
                  weight_sum: number
                  sample_texts: string[]
                }) => (
                  <div
                    key={cluster.index}
                    className="bg-secondary rounded-lg p-3"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className={cn(
                          'text-xs font-bold px-1.5 py-0.5 rounded',
                          cluster.index === 1 ? 'bg-amber-500/20 text-amber-400' :
                          cluster.index === 2 ? 'bg-blue-500/20 text-blue-400' :
                          cluster.index === 3 ? 'bg-green-500/20 text-green-400' :
                          cluster.index === 4 ? 'bg-purple-500/20 text-purple-400' :
                          'bg-muted text-muted-foreground'
                        )}>
                          #{cluster.index}
                        </span>
                        <span className="text-sm font-medium">
                          {cluster.pct}% of content
                        </span>
                      </div>
                      <span className="text-[10px] text-muted-foreground">
                        {cluster.size} records · weight {cluster.weight_sum}
                      </span>
                    </div>
                    {/* Dominance bar */}
                    <div className="h-1 bg-muted rounded-full overflow-hidden mb-2">
                      <div
                        className={cn(
                          'h-full rounded-full',
                          cluster.index === 1 ? 'bg-amber-500' :
                          cluster.index === 2 ? 'bg-blue-500' :
                          cluster.index === 3 ? 'bg-green-500' :
                          cluster.index === 4 ? 'bg-purple-500' :
                          'bg-muted-foreground'
                        )}
                        style={{ width: `${Math.min(100, cluster.pct)}%` }}
                      />
                    </div>
                    {/* Sample texts */}
                    <div className="space-y-1">
                      {cluster.sample_texts.map((text: string, ti: number) => (
                        <div
                          key={ti}
                          className="text-xs text-muted-foreground pl-2 border-l-2 border-border truncate"
                          title={text}
                        >
                          {text}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

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

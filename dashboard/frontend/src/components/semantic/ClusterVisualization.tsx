import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { 
  ScatterChart, 
  Scatter, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Loader2 } from 'lucide-react'
import { API_BASE } from '@/lib/config'

interface Point {
  x: number
  y: number
  uri: string
  platform: string
  cluster_id: number
  text_preview: string
  text: string
  created_at: string
}

interface ClusterInfo {
  id: number
  label: string
  count: number
  color: string
}

interface ClusterData {
  points: Point[]
  method: string
  total: number
  clusters?: ClusterInfo[]
  error?: string
}

// Platform colors
const PLATFORM_COLORS: Record<string, string> = {
  bluesky: '#3b82f6',
  comind: '#a855f7',
  greengale: '#22c55e',
  whitewind: '#f59e0b',
  unknown: '#6b7280',
}

type ColorMode = 'topic' | 'platform'

function CustomTooltip({ active, payload, clusters }: any) {
  if (!active || !payload || !payload.length) return null
  
  const data = payload[0].payload as Point
  const cluster = clusters?.find((c: ClusterInfo) => c.id === data.cluster_id)
  
  return (
    <div className="bg-popover border rounded-lg shadow-lg p-3 max-w-xs">
      <div className="flex items-center gap-2 mb-2">
        <Badge 
          style={{ backgroundColor: PLATFORM_COLORS[data.platform] || PLATFORM_COLORS.unknown }}
          className="text-white text-xs"
        >
          {data.platform}
        </Badge>
        {cluster && cluster.id !== -1 && (
          <Badge 
            style={{ backgroundColor: cluster.color }}
            className="text-white text-xs"
          >
            {cluster.label}
          </Badge>
        )}
        <span className="text-xs text-muted-foreground">
          {data.created_at ? new Date(data.created_at).toLocaleDateString() : ''}
        </span>
      </div>
      <p className="text-sm text-foreground line-clamp-3">
        {data.text_preview}
      </p>
    </div>
  )
}

export default function ClusterVisualization() {
  const [method, setMethod] = useState<'umap' | 'pca'>('umap')
  const [colorBy, setColorBy] = useState<ColorMode>('topic')
  const [selectedPoint, setSelectedPoint] = useState<Point | null>(null)
  
  const { data, isLoading, error } = useQuery<ClusterData>({
    queryKey: ['embeddings2d', method],
    queryFn: () => fetch(`${API_BASE}/semantic/embeddings/2d?limit=1000&method=${method}`).then(r => r.json()),
    staleTime: 5 * 60 * 1000,
  })

  const hasClusters = (data?.clusters?.length ?? 0) > 0

  // Build color lookup for topic mode
  const clusterColorMap = useMemo(() => {
    const map: Record<number, string> = {}
    if (data?.clusters) {
      for (const c of data.clusters) {
        map[c.id] = c.color
      }
    }
    return map
  }, [data?.clusters])

  // Get point color based on mode
  const getPointColor = (point: Point): string => {
    if (colorBy === 'topic' && hasClusters) {
      return clusterColorMap[point.cluster_id] || '#6b7280'
    }
    return PLATFORM_COLORS[point.platform] || PLATFORM_COLORS.unknown
  }

  // Group points by platform for platform legend
  const platformCounts = data?.points?.reduce((acc, p) => {
    acc[p.platform] = (acc[p.platform] || 0) + 1
    return acc
  }, {} as Record<string, number>) || {}
  
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Cluster Visualization</CardTitle>
            <CardDescription>
              2D projection of content embeddings ({data?.total || 0} records
              {hasClusters && `, ${data!.clusters!.filter(c => c.id !== -1).length} topics`})
            </CardDescription>
          </div>
          <div className="flex gap-2">
            {hasClusters && (
              <>
                <Button
                  variant={colorBy === 'topic' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setColorBy('topic')}
                >
                  Topics
                </Button>
                <Button
                  variant={colorBy === 'platform' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setColorBy('platform')}
                >
                  Platform
                </Button>
                <div className="w-px bg-border mx-1" />
              </>
            )}
            <Button
              variant={method === 'umap' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setMethod('umap')}
            >
              UMAP
            </Button>
            <Button
              variant={method === 'pca' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setMethod('pca')}
            >
              PCA
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-[400px] flex items-center justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">
              Computing {method.toUpperCase()} projection...
            </span>
          </div>
        ) : error || data?.error ? (
          <div className="h-[400px] flex items-center justify-center text-destructive">
            Error: {data?.error || 'Failed to load data'}
          </div>
        ) : !data?.points?.length ? (
          <div className="h-[400px] flex items-center justify-center text-muted-foreground">
            No embedding data available
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
                <Tooltip 
                  content={<CustomTooltip clusters={data.clusters} />} 
                  isAnimationActive={false} 
                />
                <Scatter 
                  data={data.points} 
                  onClick={(point) => setSelectedPoint(point as unknown as Point)}
                >
                  {data.points.map((point, index) => {
                    const color = getPointColor(point)
                    return (
                      <Cell 
                        key={index}
                        fill={color}
                        fillOpacity={point.cluster_id === -1 && colorBy === 'topic' ? 0.3 : 0.7}
                        stroke={color}
                        strokeWidth={1}
                      />
                    )
                  })}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
            
            {/* Legend */}
            <div className="flex flex-wrap gap-4 mt-4 justify-center">
              {colorBy === 'topic' && hasClusters ? (
                // Topic legend — show cluster labels
                data.clusters!
                  .filter(c => c.count > 0)
                  .sort((a, b) => b.count - a.count)
                  .map(cluster => (
                    <div key={cluster.id} className="flex items-center gap-2">
                      <div 
                        className="w-3 h-3 rounded-full"
                        style={{ 
                          backgroundColor: cluster.color,
                          opacity: cluster.id === -1 ? 0.4 : 1,
                        }}
                      />
                      <span className="text-sm text-muted-foreground">
                        {cluster.label} ({cluster.count})
                      </span>
                    </div>
                  ))
              ) : (
                // Platform legend
                Object.entries(platformCounts).map(([platform, count]) => (
                  <div key={platform} className="flex items-center gap-2">
                    <div 
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: PLATFORM_COLORS[platform] || PLATFORM_COLORS.unknown }}
                    />
                    <span className="text-sm text-muted-foreground capitalize">
                      {platform} ({count})
                    </span>
                  </div>
                ))
              )}
            </div>
            
            {/* Selected Point Detail */}
            {selectedPoint && (
              <div className="mt-4 p-4 bg-secondary rounded-lg max-h-64 overflow-auto">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Badge 
                      style={{ backgroundColor: PLATFORM_COLORS[selectedPoint.platform] }}
                      className="text-white"
                    >
                      {selectedPoint.platform}
                    </Badge>
                    {hasClusters && selectedPoint.cluster_id !== -1 && (
                      <Badge 
                        style={{ backgroundColor: clusterColorMap[selectedPoint.cluster_id] || '#6b7280' }}
                        className="text-white"
                      >
                        {data.clusters?.find(c => c.id === selectedPoint.cluster_id)?.label || 'Unknown'}
                      </Badge>
                    )}
                  </div>
                  <Button 
                    variant="ghost" 
                    size="sm"
                    onClick={() => setSelectedPoint(null)}
                  >
                    Close
                  </Button>
                </div>
                <p className="text-sm whitespace-pre-wrap">{selectedPoint.text}</p>
                <p className="text-xs text-muted-foreground mt-2">
                  {selectedPoint.created_at && new Date(selectedPoint.created_at).toLocaleString()}
                </p>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

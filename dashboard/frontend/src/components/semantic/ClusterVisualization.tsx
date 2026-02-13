import { useState } from 'react'
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

const API_BASE = `http://${window.location.hostname}:8081/api`

interface Point {
  x: number
  y: number
  uri: string
  platform: string
  text_preview: string
  created_at: string
}

interface ClusterData {
  points: Point[]
  method: string
  total: number
  error?: string
}

// Platform colors
const PLATFORM_COLORS: Record<string, string> = {
  bluesky: '#3b82f6',    // blue-500
  comind: '#a855f7',     // purple-500
  greengale: '#22c55e',  // green-500
  whitewind: '#f59e0b',  // amber-500
  unknown: '#6b7280',    // gray-500
}

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload || !payload.length) return null
  
  const data = payload[0].payload as Point
  
  return (
    <div className="bg-popover border rounded-lg shadow-lg p-3 max-w-xs">
      <div className="flex items-center gap-2 mb-2">
        <Badge 
          style={{ backgroundColor: PLATFORM_COLORS[data.platform] || PLATFORM_COLORS.unknown }}
          className="text-white"
        >
          {data.platform}
        </Badge>
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
  const [selectedPoint, setSelectedPoint] = useState<Point | null>(null)
  
  const { data, isLoading, error } = useQuery<ClusterData>({
    queryKey: ['embeddings2d', method],
    queryFn: () => fetch(`${API_BASE}/semantic/embeddings/2d?limit=1000&method=${method}`).then(r => r.json()),
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  })
  
  // Group points by platform for legend
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
              2D projection of content embeddings ({data?.total || 0} records)
            </CardDescription>
          </div>
          <div className="flex gap-2">
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
                <Tooltip content={<CustomTooltip />} />
                <Scatter 
                  data={data.points} 
                  onClick={(point) => setSelectedPoint(point as unknown as Point)}
                >
                  {data.points.map((point, index) => (
                    <Cell 
                      key={index}
                      fill={PLATFORM_COLORS[point.platform] || PLATFORM_COLORS.unknown}
                      fillOpacity={0.7}
                      stroke={PLATFORM_COLORS[point.platform] || PLATFORM_COLORS.unknown}
                      strokeWidth={1}
                    />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
            
            {/* Legend */}
            <div className="flex flex-wrap gap-4 mt-4 justify-center">
              {Object.entries(platformCounts).map(([platform, count]) => (
                <div key={platform} className="flex items-center gap-2">
                  <div 
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: PLATFORM_COLORS[platform] || PLATFORM_COLORS.unknown }}
                  />
                  <span className="text-sm text-muted-foreground capitalize">
                    {platform} ({count})
                  </span>
                </div>
              ))}
            </div>
            
            {/* Selected Point Detail */}
            {selectedPoint && (
              <div className="mt-4 p-4 bg-secondary rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <Badge 
                    style={{ backgroundColor: PLATFORM_COLORS[selectedPoint.platform] }}
                    className="text-white"
                  >
                    {selectedPoint.platform}
                  </Badge>
                  <Button 
                    variant="ghost" 
                    size="sm"
                    onClick={() => setSelectedPoint(null)}
                  >
                    Close
                  </Button>
                </div>
                <p className="text-sm">{selectedPoint.text_preview}</p>
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

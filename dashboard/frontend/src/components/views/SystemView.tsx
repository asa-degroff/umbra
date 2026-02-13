import { useQuery } from '@tanstack/react-query'
import { Cpu, Database, HardDrive, CheckCircle, XCircle } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { API_BASE } from '@/lib/config'

export default function SystemView() {
  const { data: ollama } = useQuery({
    queryKey: ['ollamaStatus'],
    queryFn: () => fetch(`${API_BASE}/system/ollama`).then(r => r.json()),
    refetchInterval: 10000,
  })

  const { data: databases } = useQuery({
    queryKey: ['databaseStats'],
    queryFn: () => fetch(`${API_BASE}/system/databases`).then(r => r.json()),
    refetchInterval: 30000,
  })

  const { data: memory } = useQuery({
    queryKey: ['memoryBlocks'],
    queryFn: () => fetch(`${API_BASE}/system/memory`).then(r => r.json()),
    refetchInterval: 30000,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">System Status</h1>
        <p className="text-muted-foreground">
          Infrastructure and service health
        </p>
      </div>

      {/* Ollama Status */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Cpu className="w-5 h-5 text-yellow-400" />
              <CardTitle>Ollama</CardTitle>
            </div>
            {ollama?.status === 'running' ? (
              <Badge variant="success" className="gap-1">
                <CheckCircle className="w-3 h-3" />
                Running
              </Badge>
            ) : (
              <Badge variant="destructive" className="gap-1">
                <XCircle className="w-3 h-3" />
                {ollama?.status || 'Unknown'}
              </Badge>
            )}
          </div>
          <CardDescription>Local inference server</CardDescription>
        </CardHeader>
        <CardContent>
          {ollama?.models && ollama.models.length > 0 ? (
            <div className="space-y-2">
              {ollama.models.map((model: any) => (
                <div key={model.name} className="flex justify-between items-center p-3 bg-secondary rounded-lg">
                  <span className="font-mono text-sm">{model.name}</span>
                  <Badge variant="outline">
                    {(model.size / 1e9).toFixed(1)} GB
                  </Badge>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-muted-foreground text-sm">No models loaded</div>
          )}
          {ollama?.error && (
            <div className="text-destructive text-sm mt-2">{ollama.error}</div>
          )}
        </CardContent>
      </Card>

      {/* Databases */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* SQLite */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Database className="w-5 h-5 text-blue-400" />
                <CardTitle className="text-base">SQLite</CardTitle>
              </div>
              {databases?.sqlite?.available ? (
                <Badge variant="success" className="gap-1">
                  <CheckCircle className="w-3 h-3" />
                  Connected
                </Badge>
              ) : (
                <Badge variant="destructive" className="gap-1">
                  <XCircle className="w-3 h-3" />
                  Offline
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {databases?.sqlite?.tables ? (
              <div className="space-y-1 text-sm">
                {Object.entries(databases.sqlite.tables).map(([table, count]) => (
                  <div key={table} className="flex justify-between">
                    <span className="text-muted-foreground">{table}</span>
                    <span>{count as number} rows</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-muted-foreground text-sm">No data available</div>
            )}
          </CardContent>
        </Card>

        {/* ChromaDB */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <HardDrive className="w-5 h-5 text-green-400" />
                <CardTitle className="text-base">ChromaDB</CardTitle>
              </div>
              {databases?.chromadb?.available ? (
                <Badge variant="success" className="gap-1">
                  <CheckCircle className="w-3 h-3" />
                  Connected
                </Badge>
              ) : (
                <Badge variant="destructive" className="gap-1">
                  <XCircle className="w-3 h-3" />
                  Offline
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {databases?.chromadb?.total_records !== undefined ? (
              <div className="text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Total records</span>
                  <span>{databases.chromadb.total_records}</span>
                </div>
              </div>
            ) : (
              <div className="text-muted-foreground text-sm">No data available</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Memory Blocks */}
      {memory?.blocks && (
        <Card>
          <CardHeader>
            <CardTitle>Memory Blocks</CardTitle>
            <CardDescription>Letta agent memory state</CardDescription>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[400px]">
              <div className="space-y-4">
                {memory.blocks.map((block: any, index: number) => (
                  <div key={block.label}>
                    {index > 0 && <Separator className="my-4" />}
                    <div className="space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="font-medium">{block.label}</span>
                        <Badge variant="outline" className="text-xs">
                          {block.full_length} chars
                        </Badge>
                      </div>
                      <div className="text-sm text-muted-foreground bg-secondary p-3 rounded-lg font-mono text-xs whitespace-pre-wrap max-h-32 overflow-auto">
                        {block.value}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

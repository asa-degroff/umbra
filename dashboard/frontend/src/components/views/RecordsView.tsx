import { useQuery } from '@tanstack/react-query'
import { useState, useMemo } from 'react'
import { Database, ChevronLeft, ChevronRight, Search, X } from 'lucide-react'
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
import { API_BASE } from '@/lib/config'

const SOURCES = [
  { value: 'all', label: 'All Sources' },
  { value: 'umbra', label: 'Umbra Only' },
  { value: 'network', label: 'Network Only' },
]

const PLATFORMS = [
  { value: 'all', label: 'All Platforms' },
  { value: 'bluesky', label: 'Bluesky' },
  { value: 'comind', label: 'Comind' },
  { value: 'greengale', label: 'Greengale' },
  { value: 'whitewind', label: 'WhiteWind' },
]

const COLLECTIONS = [
  { value: 'all', label: 'All Collections' },
  { value: 'app.bsky.feed.post', label: 'Bluesky Posts' },
  { value: 'network.comind.memory', label: 'Comind Memory' },
  { value: 'network.comind.thought', label: 'Comind Thought' },
  { value: 'network.comind.reflection', label: 'Comind Reflection' },
  { value: 'network.comind.concept', label: 'Comind Concept' },
  { value: 'app.greengale.document', label: 'Greengale Documents' },
  { value: 'com.whtwnd.blog.entry', label: 'WhiteWind Blog' },
]

interface RecordData {
  uri: string
  text: string
  metadata: {
    platform?: string
    collection?: string
    created_at?: string
    word_count?: number
    is_network?: number
    source_handle?: string
    source_did?: string
  }
}

export default function RecordsView() {
  const [page, setPage] = useState(0)
  const [source, setSource] = useState('all')
  const [platform, setPlatform] = useState('all')
  const [collection, setCollection] = useState('all')
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [selectedRecord, setSelectedRecord] = useState<RecordData | null>(null)
  const limit = 20

  // Build query params
  const queryParams = useMemo(() => {
    const params = new URLSearchParams()
    params.set('limit', String(limit))
    params.set('offset', String(page * limit))
    if (source !== 'all') params.set('source', source)
    if (platform !== 'all') params.set('platform', platform)
    if (collection !== 'all') params.set('collection', collection)
    if (search) params.set('search', search)
    return params.toString()
  }, [page, source, platform, collection, search])

  const { data, isLoading } = useQuery({
    queryKey: ['records', queryParams],
    queryFn: () => fetch(`${API_BASE}/semantic/records?${queryParams}`).then(r => r.json()),
  })

  const handleSearch = () => {
    setSearch(searchInput)
    setPage(0)
  }

  const clearSearch = () => {
    setSearchInput('')
    setSearch('')
    setPage(0)
  }

  const handleFilterChange = (type: 'source' | 'platform' | 'collection', value: string) => {
    if (type === 'source') setSource(value)
    if (type === 'platform') setPlatform(value)
    if (type === 'collection') setCollection(value)
    setPage(0)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Records Browser</h1>
        <p className="text-muted-foreground">
          Search and explore semantic analysis records
        </p>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="space-y-4">
            {/* Search Bar */}
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search records..."
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

            {/* Filters */}
            <div className="flex flex-wrap gap-4">
              <div className="w-40">
                <Select value={source} onValueChange={(v) => handleFilterChange('source', v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Source" />
                  </SelectTrigger>
                  <SelectContent>
                    {SOURCES.map(s => (
                      <SelectItem key={s.value} value={s.value}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="w-48">
                <Select value={platform} onValueChange={(v) => handleFilterChange('platform', v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Platform" />
                  </SelectTrigger>
                  <SelectContent>
                    {PLATFORMS.map(p => (
                      <SelectItem key={p.value} value={p.value}>
                        {p.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              <div className="w-56">
                <Select value={collection} onValueChange={(v) => handleFilterChange('collection', v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Collection" />
                  </SelectTrigger>
                  <SelectContent>
                    {COLLECTIONS.map(c => (
                      <SelectItem key={c.value} value={c.value}>
                        {c.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {(source !== 'all' || platform !== 'all' || collection !== 'all' || search) && (
                <Button 
                  variant="ghost" 
                  size="sm"
                  onClick={() => {
                    setSource('all')
                    setPlatform('all')
                    setCollection('all')
                    setSearch('')
                    setSearchInput('')
                    setPage(0)
                  }}
                >
                  Clear Filters
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stats */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Database className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            {data?.total ?? 0} records {search && `matching "${search}"`}
          </span>
        </div>
      </div>

      {/* Records Table */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Records</CardTitle>
          <CardDescription>Click a row to view full content</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-hidden">
            <table className="w-full">
              <thead className="bg-secondary">
                <tr>
                  <th className="text-left p-3 text-sm font-medium text-muted-foreground w-32">Author</th>
                  <th className="text-left p-3 text-sm font-medium text-muted-foreground">Text</th>
                  <th className="text-left p-3 text-sm font-medium text-muted-foreground w-24">Words</th>
                  <th className="text-left p-3 text-sm font-medium text-muted-foreground w-28">Date</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={4} className="p-4 text-center text-muted-foreground">
                      Loading...
                    </td>
                  </tr>
                ) : data?.records?.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="p-4 text-center text-muted-foreground">
                      No records found
                    </td>
                  </tr>
                ) : (
                  data?.records?.map((record: RecordData, i: number) => (
                    <tr 
                      key={record.uri || i} 
                      className="border-t border-border hover:bg-secondary/50 cursor-pointer"
                      onClick={() => setSelectedRecord(record)}
                    >
                      <td className="p-3">
                        <div className="flex flex-col gap-1">
                          <span className="text-sm font-medium truncate max-w-[120px]">
                            {record.metadata?.is_network 
                              ? `@${record.metadata?.source_handle || 'unknown'}`
                              : 'Umbra'
                            }
                          </span>
                          <Badge variant="secondary" className="w-fit text-xs">
                            {record.metadata?.platform || 'unknown'}
                          </Badge>
                        </div>
                      </td>
                      <td className="p-3 max-w-md">
                        <div className="truncate text-sm">
                          {record.text?.slice(0, 120)}...
                        </div>
                      </td>
                      <td className="p-3 text-sm text-muted-foreground">
                        {record.metadata?.word_count || '—'}
                      </td>
                      <td className="p-3 text-sm text-muted-foreground">
                        {record.metadata?.created_at 
                          ? new Date(record.metadata.created_at).toLocaleDateString()
                          : '—'
                        }
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>

            {/* Pagination */}
            <div className="flex items-center justify-between p-3 bg-secondary border-t border-border">
              <span className="text-sm text-muted-foreground">
                Showing {data?.total ? page * limit + 1 : 0}-{Math.min((page + 1) * limit, data?.total ?? 0)} of {data?.total ?? 0}
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
                  disabled={(page + 1) * limit >= (data?.total ?? 0)}
                >
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Record Detail Modal */}
      {selectedRecord && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="max-w-2xl w-full max-h-[80vh] overflow-hidden flex flex-col">
            <CardHeader className="flex-shrink-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-medium">
                    {selectedRecord.metadata?.is_network 
                      ? `@${selectedRecord.metadata?.source_handle}`
                      : 'Umbra'
                    }
                  </span>
                  <Badge variant="secondary">
                    {selectedRecord.metadata?.platform}
                  </Badge>
                </div>
                <Button variant="ghost" size="icon" onClick={() => setSelectedRecord(null)}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
              <CardDescription>
                {selectedRecord.metadata?.collection}
                {selectedRecord.metadata?.created_at && 
                  ` • ${new Date(selectedRecord.metadata.created_at).toLocaleString()}`
                }
                {selectedRecord.metadata?.word_count && 
                  ` • ${selectedRecord.metadata.word_count} words`
                }
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-auto flex-1">
              <p className="whitespace-pre-wrap">{selectedRecord.text}</p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

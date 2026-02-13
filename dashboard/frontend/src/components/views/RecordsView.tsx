import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Database, ChevronLeft, ChevronRight } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

const API_BASE = `http://${window.location.hostname}:8081/api`

export default function RecordsView() {
  const [page, setPage] = useState(0)
  const limit = 20

  const { data, isLoading } = useQuery({
    queryKey: ['records', page],
    queryFn: () => fetch(`${API_BASE}/semantic/records?limit=${limit}&offset=${page * limit}`).then(r => r.json()),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Records Browser</h1>
        <p className="text-muted-foreground">
          Browse semantic analysis records
        </p>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Database className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            {data?.total ?? 0} total records
          </span>
        </div>
      </div>

      {/* Records Table */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Records</CardTitle>
          <CardDescription>Content indexed for semantic analysis</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-hidden">
            <table className="w-full">
              <thead className="bg-secondary">
                <tr>
                  <th className="text-left p-3 text-sm font-medium text-muted-foreground">Platform</th>
                  <th className="text-left p-3 text-sm font-medium text-muted-foreground">Text</th>
                  <th className="text-left p-3 text-sm font-medium text-muted-foreground">Created</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={3} className="p-4 text-center text-muted-foreground">
                      Loading...
                    </td>
                  </tr>
                ) : data?.records?.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="p-4 text-center text-muted-foreground">
                      No records found
                    </td>
                  </tr>
                ) : (
                  data?.records?.map((record: any, i: number) => (
                    <tr key={record.uri || i} className="border-t border-border">
                      <td className="p-3">
                        <Badge variant="secondary">
                          {record.metadata?.platform || 'unknown'}
                        </Badge>
                      </td>
                      <td className="p-3 max-w-md">
                        <div className="truncate text-sm">
                          {record.text?.slice(0, 150)}...
                        </div>
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
                Showing {page * limit + 1}-{Math.min((page + 1) * limit, data?.total ?? 0)} of {data?.total ?? 0}
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
    </div>
  )
}

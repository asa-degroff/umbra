import { useQuery } from '@tanstack/react-query'
import { Clock, CheckCircle, XCircle } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { API_BASE } from '@/lib/config'

export default function TasksView() {
  const { data, isLoading } = useQuery({
    queryKey: ['scheduledTasks'],
    queryFn: () => fetch(`${API_BASE}/system/tasks`).then(r => r.json()),
    refetchInterval: 10000,
  })

  const formatTime = (timestamp: string | null) => {
    if (!timestamp) return '—'
    return new Date(timestamp).toLocaleString()
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Scheduled Tasks</h1>
        <p className="text-muted-foreground">
          View and manage scheduled tasks
        </p>
      </div>

      {data?.error ? (
        <Card>
          <CardContent className="p-6">
            <div className="text-muted-foreground">{data.error}</div>
          </CardContent>
        </Card>
      ) : isLoading ? (
        <div className="text-muted-foreground">Loading tasks...</div>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Tasks</CardTitle>
            <CardDescription>Recurring and one-time scheduled operations</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <table className="w-full">
              <thead className="bg-secondary">
                <tr>
                  <th className="text-left p-3 text-sm font-medium text-muted-foreground">Task</th>
                  <th className="text-left p-3 text-sm font-medium text-muted-foreground">Status</th>
                  <th className="text-left p-3 text-sm font-medium text-muted-foreground">Next Run</th>
                  <th className="text-left p-3 text-sm font-medium text-muted-foreground">Last Run</th>
                </tr>
              </thead>
              <tbody>
                {data?.tasks?.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="p-4 text-center text-muted-foreground">
                      No scheduled tasks found
                    </td>
                  </tr>
                ) : (
                  data?.tasks?.map((task: any, i: number) => (
                    <tr key={task.task_name || i} className="border-t border-border">
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <Clock className="w-4 h-4 text-muted-foreground" />
                          <span className="font-medium">{task.task_name}</span>
                        </div>
                      </td>
                      <td className="p-3">
                        {task.enabled ? (
                          <Badge variant="success" className="gap-1">
                            <CheckCircle className="w-3 h-3" />
                            Enabled
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="gap-1">
                            <XCircle className="w-3 h-3" />
                            Disabled
                          </Badge>
                        )}
                      </td>
                      <td className="p-3 text-sm text-muted-foreground">
                        {formatTime(task.next_run)}
                      </td>
                      <td className="p-3 text-sm text-muted-foreground">
                        {formatTime(task.last_run)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

import { useState, useEffect, useCallback } from 'react'
import { Clock, CheckCircle, XCircle, RefreshCw } from 'lucide-react'
import { getTasks } from '../lib/api'

interface Task {
  task_name: string
  next_run: string | null
  last_run: string | null
  enabled: number
  interval_seconds: number | null
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '-'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function formatRelative(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  const now = new Date()
  const diff = d.getTime() - now.getTime()
  const absDiff = Math.abs(diff)
  const mins = Math.floor(absDiff / 60000)
  const hours = Math.floor(mins / 60)

  if (diff > 0) {
    return hours > 0 ? `in ${hours}h ${mins % 60}m` : `in ${mins}m`
  } else {
    return hours > 0 ? `${hours}h ${mins % 60}m ago` : `${mins}m ago`
  }
}

export default function TaskDashboard() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await getTasks()
      if (Array.isArray(data)) setTasks(data)
    } catch (e) {
      console.error('Failed to load tasks:', e)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [load])

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <h2 className="text-xl font-bold">Scheduled Tasks</h2>
        <button onClick={load} className="ml-auto text-gray-500 hover:text-gray-300">
          <RefreshCw size={16} />
        </button>
      </div>

      {loading ? (
        <p className="text-gray-600 text-sm">Loading...</p>
      ) : tasks.length === 0 ? (
        <p className="text-gray-600 text-sm">No scheduled tasks found</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {tasks.map((task) => (
            <div key={task.task_name} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="font-mono text-sm text-cyan-400">{task.task_name}</span>
                {task.enabled ? (
                  <span className="flex items-center gap-1 text-xs text-green-400">
                    <CheckCircle size={12} /> enabled
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-xs text-red-400">
                    <XCircle size={12} /> disabled
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
                <div>
                  <span className="text-gray-600">Next run</span>
                  <p className="mt-0.5">{formatRelative(task.next_run)}</p>
                </div>
                <div>
                  <span className="text-gray-600">Last run</span>
                  <p className="mt-0.5">{formatRelative(task.last_run)}</p>
                </div>
                <div>
                  <span className="text-gray-600">Interval</span>
                  <p className="mt-0.5">{formatDuration(task.interval_seconds)}</p>
                </div>
                <div>
                  <span className="text-gray-600">Next at</span>
                  <p className="mt-0.5">
                    {task.next_run ? new Date(task.next_run).toLocaleTimeString() : '-'}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

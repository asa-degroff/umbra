import { Activity } from 'lucide-react'
import type { WSEvent } from '../hooks/useWebSocket'

const TYPE_COLORS: Record<string, string> = {
  notification: 'text-blue-400',
  response: 'text-green-400',
  tool_call: 'text-yellow-400',
  tool_result: 'text-orange-400',
  reasoning: 'text-purple-400',
  error: 'text-red-400',
  status: 'text-gray-400',
  scheduled_task: 'text-cyan-400',
}

function EventCard({ event }: { event: WSEvent }) {
  const color = TYPE_COLORS[event.type] || 'text-gray-500'
  const content = event.content || event.message || event.tool_name || event.task_name || ''
  const truncated = typeof content === 'string' && content.length > 120
    ? content.slice(0, 120) + '...'
    : String(content)

  return (
    <div className="px-3 py-2 border-b border-gray-800/50 text-xs">
      <div className="flex items-center justify-between mb-0.5">
        <span className={`font-medium ${color}`}>{event.type}</span>
        <span className="text-gray-600">
          {event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : ''}
        </span>
      </div>
      <p className="text-gray-400 break-words">{truncated}</p>
    </div>
  )
}

export default function ActivityStream({ events }: { events: WSEvent[] }) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 p-3 border-b border-gray-800">
        <Activity size={16} className="text-gray-500" />
        <span className="text-sm font-medium">Activity</span>
        <span className="text-xs text-gray-600 ml-auto">{events.length}</span>
      </div>
      <div className="flex-1 overflow-auto">
        {events.length === 0 ? (
          <p className="text-gray-600 text-xs p-4 text-center">No events yet</p>
        ) : (
          [...events].reverse().map((e, i) => <EventCard key={i} event={e} />)
        )}
      </div>
    </div>
  )
}

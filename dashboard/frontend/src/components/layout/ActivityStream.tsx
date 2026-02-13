import { Bell, MessageSquare, Wrench, Brain, AlertCircle, Clock, CheckCircle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import type { Event } from '@/types'

interface ActivityStreamProps {
  events: Event[]
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('en-US', { 
    hour: 'numeric', 
    minute: '2-digit',
    hour12: true 
  })
}

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength) + '...'
}

function EventCard({ event }: { event: Event }) {
  const getIcon = () => {
    switch (event.type) {
      case 'notification':
        return <Bell className="w-4 h-4 text-blue-400" />
      case 'response':
        return <MessageSquare className="w-4 h-4 text-green-400" />
      case 'tool_call':
        return <Wrench className="w-4 h-4 text-yellow-400" />
      case 'tool_result':
        return event.status === 'success' 
          ? <CheckCircle className="w-4 h-4 text-green-400" />
          : <AlertCircle className="w-4 h-4 text-red-400" />
      case 'reasoning':
        return <Brain className="w-4 h-4 text-purple-400" />
      case 'scheduled_task':
        return <Clock className="w-4 h-4 text-cyan-400" />
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-400" />
      default:
        return <Bell className="w-4 h-4 text-muted-foreground" />
    }
  }

  const getContent = () => {
    switch (event.type) {
      case 'notification':
        return (
          <>
            <div className="font-medium text-blue-400">@{event.author_handle}</div>
            <div className="text-sm text-muted-foreground">
              {truncate(event.text, 100)}
            </div>
          </>
        )
      case 'response':
        return (
          <>
            <div className="font-medium text-green-400">Response</div>
            <div className="text-sm text-muted-foreground">
              {truncate(event.content, 100)}
            </div>
          </>
        )
      case 'tool_call':
        return (
          <>
            <div className="font-medium text-yellow-400">{event.name}()</div>
            <div className="text-xs text-muted-foreground font-mono">
              {truncate(JSON.stringify(event.arguments), 80)}
            </div>
          </>
        )
      case 'tool_result':
        return (
          <>
            <div className={cn(
              "font-medium",
              event.status === 'success' ? 'text-green-400' : 'text-red-400'
            )}>
              {event.name} → {event.status}
            </div>
            {event.result && (
              <div className="text-xs text-muted-foreground">
                {truncate(event.result, 60)}
              </div>
            )}
          </>
        )
      case 'reasoning':
        return (
          <>
            <div className="font-medium text-purple-400">Reasoning</div>
            <div className="text-sm text-muted-foreground italic">
              {truncate(event.content, 100)}
            </div>
          </>
        )
      case 'scheduled_task':
        return (
          <>
            <div className="font-medium text-cyan-400">{event.task_name}</div>
            <Badge variant="secondary" className="text-xs">
              {event.status}
            </Badge>
          </>
        )
      case 'error':
        return (
          <>
            <div className="font-medium text-red-400">Error</div>
            <div className="text-sm text-red-300">
              {truncate(event.message, 100)}
            </div>
          </>
        )
      default:
        return <div className="text-muted-foreground">Unknown event</div>
    }
  }

  return (
    <Card className="bg-secondary/50">
      <CardContent className="p-3">
        <div className="flex items-start gap-2">
          <div className="mt-0.5">{getIcon()}</div>
          <div className="flex-1 min-w-0">
            {getContent()}
          </div>
          <div className="text-xs text-muted-foreground whitespace-nowrap">
            {formatTime(event.timestamp)}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function ActivityStream({ events }: ActivityStreamProps) {
  return (
    <div className="w-80 bg-card border-l flex flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Activity Stream</CardTitle>
        <p className="text-sm text-muted-foreground">
          {events.length} events
        </p>
      </CardHeader>

      <Separator />

      <ScrollArea className="flex-1">
        <div className="p-3 space-y-2">
          {events.length === 0 ? (
            <div className="text-center text-muted-foreground py-8">
              <Bell className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <div>No activity yet</div>
              <div className="text-sm">Events will appear here in real-time</div>
            </div>
          ) : (
            events.map((event, index) => (
              <EventCard key={`${event.timestamp}-${index}`} event={event} />
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

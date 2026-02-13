export type EventType = 
  | 'notification'
  | 'response'
  | 'tool_call'
  | 'tool_result'
  | 'reasoning'
  | 'status'
  | 'scheduled_task'
  | 'error'
  | 'history'

export interface BaseEvent {
  type: EventType
  timestamp: string
}

export interface NotificationEvent extends BaseEvent {
  type: 'notification'
  uri: string
  author_handle: string
  author_did: string
  text: string
  reason: string
}

export interface ResponseEvent extends BaseEvent {
  type: 'response'
  content: string
  thread_uri?: string
  post_uri?: string
}

export interface ToolCallEvent extends BaseEvent {
  type: 'tool_call'
  name: string
  arguments: Record<string, unknown>
}

export interface ToolResultEvent extends BaseEvent {
  type: 'tool_result'
  name: string
  status: 'success' | 'error'
  result?: string
  error?: string
}

export interface ReasoningEvent extends BaseEvent {
  type: 'reasoning'
  content: string
}

export interface StatusEvent extends BaseEvent {
  type: 'status'
  state: string
  queue_size: number
  current_task?: string
}

export interface ScheduledTaskEvent extends BaseEvent {
  type: 'scheduled_task'
  task_name: string
  status: 'started' | 'completed' | 'failed'
  error?: string
}

export interface ErrorEvent extends BaseEvent {
  type: 'error'
  message: string
}

export interface HistoryEvent {
  type: 'history'
  events: Event[]
}

export type Event = 
  | NotificationEvent 
  | ResponseEvent 
  | ToolCallEvent 
  | ToolResultEvent 
  | ReasoningEvent 
  | StatusEvent 
  | ScheduledTaskEvent 
  | ErrorEvent

export interface SemanticMetrics {
  total_records: number
  records_with_embeddings: number
  avg_diversity: number
  weighted_avg_diversity: number
  cluster_dominance: number
  platforms: Record<string, number>
}

export interface SemanticRecord {
  uri: string
  text: string
  metadata: {
    platform?: string
    collection?: string
    created_at?: string
  }
}

export interface OllamaStatus {
  status: 'running' | 'offline' | 'error'
  url: string
  models?: Array<{
    name: string
    size: number
    modified_at: string
  }>
  error?: string
}

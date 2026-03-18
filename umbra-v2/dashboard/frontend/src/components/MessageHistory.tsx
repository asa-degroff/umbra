import { useState, useEffect, useCallback } from 'react'
import { User, Bot, Wrench, ChevronDown, ChevronRight, AlertCircle } from 'lucide-react'
import { getMessages } from '../lib/api'

interface Message {
  id: string | null
  type: string
  content?: string
  tool_name?: string
  arguments?: string
  status?: string
  created_at?: string
  reasoning?: string
}

function MessageBubble({ msg }: { msg: Message }) {
  const [expanded, setExpanded] = useState(false)

  if (msg.type === 'user') {
    return (
      <div className="flex gap-3 py-3">
        <div className="w-7 h-7 rounded-full bg-blue-600/20 flex items-center justify-center flex-shrink-0">
          <User size={14} className="text-blue-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-200 whitespace-pre-wrap break-words">{msg.content}</p>
          {msg.created_at && (
            <span className="text-xs text-gray-600 mt-1 block">{new Date(msg.created_at).toLocaleString()}</span>
          )}
        </div>
      </div>
    )
  }

  if (msg.type === 'assistant') {
    return (
      <div className="flex gap-3 py-3">
        <div className="w-7 h-7 rounded-full bg-cyan-600/20 flex items-center justify-center flex-shrink-0">
          <Bot size={14} className="text-cyan-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-200 whitespace-pre-wrap break-words">{msg.content}</p>
          {msg.created_at && (
            <span className="text-xs text-gray-600 mt-1 block">{new Date(msg.created_at).toLocaleString()}</span>
          )}
        </div>
      </div>
    )
  }

  if (msg.type === 'tool_call' || msg.type === 'tool_return') {
    const isCall = msg.type === 'tool_call'
    return (
      <div className="ml-10 my-1">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300"
        >
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          <Wrench size={12} className="text-yellow-500" />
          <span>{isCall ? msg.tool_name : 'result'}</span>
          {msg.status === 'error' && <AlertCircle size={12} className="text-red-500" />}
        </button>
        {expanded && (
          <pre className="mt-1 p-2 bg-gray-950 border border-gray-800 rounded text-xs text-gray-400 overflow-x-auto max-h-48 overflow-y-auto">
            {isCall ? msg.arguments : msg.content}
          </pre>
        )}
      </div>
    )
  }

  if (msg.type === 'reasoning') {
    return (
      <div className="ml-10 my-1">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 text-xs text-purple-500/60 hover:text-purple-400"
        >
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          thinking...
        </button>
        {expanded && (
          <p className="mt-1 text-xs text-purple-400/50 italic whitespace-pre-wrap">{msg.content}</p>
        )}
      </div>
    )
  }

  // System / unknown
  return (
    <div className="ml-10 my-1 text-xs text-gray-600 italic">
      [{msg.type}] {msg.content?.slice(0, 200)}
    </div>
  )
}

export default function MessageHistory() {
  const [messages, setMessages] = useState<Message[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (reset = false) => {
    setLoading(true)
    try {
      const data = await getMessages({
        cursor: reset ? undefined : cursor || undefined,
        limit: 50,
      })
      const msgs = data.messages || []
      if (reset) {
        setMessages(msgs)
      } else {
        setMessages((prev) => [...prev, ...msgs])
      }
      setCursor(data.next_cursor)
    } catch (e) {
      console.error('Failed to load messages:', e)
    }
    setLoading(false)
  }, [cursor])

  useEffect(() => { load(true) }, [])

  return (
    <div>
      <h2 className="text-xl font-bold mb-6">Messages</h2>

      <div className="bg-gray-900 rounded-lg border border-gray-800 divide-y divide-gray-800/50">
        {messages.length === 0 && !loading ? (
          <p className="text-center text-gray-600 text-sm py-8">No messages</p>
        ) : (
          messages.map((msg, i) => (
            <div key={msg.id || i} className="px-4">
              <MessageBubble msg={msg} />
            </div>
          ))
        )}
      </div>

      {cursor && (
        <button
          onClick={() => load(false)}
          disabled={loading}
          className="mt-4 w-full py-2 bg-gray-800 hover:bg-gray-700 rounded text-sm disabled:opacity-50"
        >
          {loading ? 'Loading...' : 'Load older messages'}
        </button>
      )}
    </div>
  )
}

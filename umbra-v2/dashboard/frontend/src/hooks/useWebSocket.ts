import { useEffect, useRef, useState, useCallback } from 'react'

export interface WSEvent {
  type: string
  [key: string]: any
}

export function useWebSocket(url: string) {
  const [events, setEvents] = useState<WSEvent[]>([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<number>()

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
      }

      ws.onmessage = (e) => {
        if (e.data === 'pong') return
        try {
          const event = JSON.parse(e.data) as WSEvent
          setEvents((prev) => [...prev.slice(-99), event])
        } catch {}
      }

      ws.onclose = () => {
        setConnected(false)
        reconnectTimer.current = window.setTimeout(connect, 3000)
      }

      ws.onerror = () => ws.close()
    } catch {}
  }, [url])

  useEffect(() => {
    connect()
    // Ping keepalive
    const ping = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send('ping')
      }
    }, 30000)
    return () => {
      clearInterval(ping)
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { events, connected }
}

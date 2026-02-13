import { useEffect, useRef, useState } from 'react'
import type { Event } from '../types'

interface UseWebSocketOptions {
  url: string
  onEvent?: (event: Event) => void
  onHistory?: (events: Event[]) => void
  onConnect?: () => void
  onDisconnect?: () => void
  reconnectInterval?: number
}

export function useWebSocket({
  url,
  onEvent,
  onHistory,
  onConnect,
  onDisconnect,
  reconnectInterval = 5000,
}: UseWebSocketOptions) {
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const reconnectAttemptRef = useRef(0)
  const mountedRef = useRef(true)
  const connectingRef = useRef(false)
  
  // Store callbacks in refs to avoid dependency changes
  const callbacksRef = useRef({ onEvent, onHistory, onConnect, onDisconnect })
  callbacksRef.current = { onEvent, onHistory, onConnect, onDisconnect }

  useEffect(() => {
    mountedRef.current = true
    
    const connect = () => {
      // Prevent multiple simultaneous connection attempts
      if (connectingRef.current) return
      if (wsRef.current?.readyState === WebSocket.OPEN) return
      if (wsRef.current?.readyState === WebSocket.CONNECTING) return
      
      connectingRef.current = true

      try {
        console.log('WebSocket connecting to', url)
        const ws = new WebSocket(url)

        ws.onopen = () => {
          if (!mountedRef.current) {
            ws.close()
            return
          }
          console.log('WebSocket connected')
          connectingRef.current = false
          reconnectAttemptRef.current = 0
          setIsConnected(true)
          callbacksRef.current.onConnect?.()
        }

        ws.onmessage = (event) => {
          if (!mountedRef.current) return

          // Handle pong before JSON.parse (it's a plain string)
          if (event.data === 'pong') return

          try {
            const data = JSON.parse(event.data)

            // Handle history message (sent on connect)
            if (data.type === 'history' && data.events) {
              callbacksRef.current.onHistory?.(data.events)
              return
            }

            // Handle regular events
            callbacksRef.current.onEvent?.(data as Event)
          } catch (e) {
            console.error('Failed to parse WebSocket message:', e)
          }
        }

        ws.onclose = () => {
          console.log('WebSocket disconnected')
          connectingRef.current = false

          if (!mountedRef.current) return

          setIsConnected(false)
          callbacksRef.current.onDisconnect?.()

          // Reconnect with exponential backoff (only if still mounted)
          if (mountedRef.current) {
            const delay = Math.min(reconnectInterval * Math.pow(2, reconnectAttemptRef.current), 60000)
            reconnectAttemptRef.current++
            reconnectTimeoutRef.current = window.setTimeout(() => {
              if (mountedRef.current) {
                connect()
              }
            }, delay)
          }
        }

        ws.onerror = (error) => {
          console.error('WebSocket error:', error)
          connectingRef.current = false
        }

        wsRef.current = ws
      } catch (e) {
        console.error('Failed to connect WebSocket:', e)
        connectingRef.current = false
        
        // Retry connection with exponential backoff
        if (mountedRef.current) {
          const delay = Math.min(reconnectInterval * Math.pow(2, reconnectAttemptRef.current), 60000)
          reconnectAttemptRef.current++
          reconnectTimeoutRef.current = window.setTimeout(() => {
            if (mountedRef.current) {
              connect()
            }
          }, delay)
        }
      }
    }

    // Initial connection
    connect()

    // Ping every 30 seconds to keep connection alive
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send('ping')
      }
    }, 30000)

    // Cleanup
    return () => {
      mountedRef.current = false
      clearInterval(pingInterval)
      
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [url, reconnectInterval]) // Only reconnect if URL changes

  return {
    isConnected,
  }
}

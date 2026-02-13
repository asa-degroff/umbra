import { useState, useEffect, useCallback } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Sidebar from './components/layout/Sidebar'
import MainPanel from './components/layout/MainPanel'
import ActivityStream from './components/layout/ActivityStream'
import { useWebSocket } from './hooks/useWebSocket'
import type { Event } from './types'
import { WS_URL } from './lib/config'
import './App.css'

const queryClient = new QueryClient()

function Dashboard() {
  const [activeView, setActiveView] = useState('overview')
  const [events, setEvents] = useState<Event[]>([])
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')

  const handleEvent = useCallback((event: Event) => {
    setEvents(prev => [event, ...prev].slice(0, 100)) // Keep last 100 events
  }, [])

  const handleHistory = useCallback((historyEvents: Event[]) => {
    setEvents(historyEvents.reverse())
  }, [])

  const { isConnected } = useWebSocket({
    url: WS_URL,
    onEvent: handleEvent,
    onHistory: handleHistory,
    onConnect: () => setConnectionStatus('connected'),
    onDisconnect: () => setConnectionStatus('disconnected'),
  })

  useEffect(() => {
    setConnectionStatus(isConnected ? 'connected' : 'disconnected')
  }, [isConnected])

  return (
    <div className="h-screen flex bg-background">
      {/* Left Sidebar - Navigation */}
      <Sidebar 
        activeView={activeView} 
        onViewChange={setActiveView}
        connectionStatus={connectionStatus}
      />

      {/* Main Content Area */}
      <MainPanel activeView={activeView} />

      {/* Right Sidebar - Activity Stream */}
      <ActivityStream events={events} />
    </div>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Dashboard />
    </QueryClientProvider>
  )
}

export default App

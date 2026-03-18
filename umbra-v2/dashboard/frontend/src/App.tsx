import { useState } from 'react'
import { Brain, MessageSquare, Wrench, Clock, Activity, Server } from 'lucide-react'
import { useWebSocket } from './hooks/useWebSocket'
import MemoryViewer from './components/MemoryViewer'
import MessageHistory from './components/MessageHistory'
import ToolConfig from './components/ToolConfig'
import TaskDashboard from './components/TaskDashboard'
import ActivityStream from './components/ActivityStream'
import SystemStatus from './components/SystemStatus'

type View = 'memory' | 'messages' | 'tools' | 'tasks' | 'system'

const NAV: { id: View; label: string; icon: React.ReactNode }[] = [
  { id: 'memory', label: 'Memory', icon: <Brain size={18} /> },
  { id: 'messages', label: 'Messages', icon: <MessageSquare size={18} /> },
  { id: 'tools', label: 'Tools', icon: <Wrench size={18} /> },
  { id: 'tasks', label: 'Tasks', icon: <Clock size={18} /> },
  { id: 'system', label: 'System', icon: <Server size={18} /> },
]

const wsUrl = `ws://${window.location.hostname}:${window.location.port || '8081'}/ws`

export default function App() {
  const [view, setView] = useState<View>('memory')
  const { events, connected } = useWebSocket(wsUrl)

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      {/* Sidebar */}
      <nav className="w-48 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800">
          <h1 className="text-lg font-bold tracking-tight">umbra</h1>
          <div className="flex items-center gap-1.5 mt-1">
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-xs text-gray-500">{connected ? 'connected' : 'disconnected'}</span>
          </div>
        </div>
        <div className="flex-1 py-2">
          {NAV.map(({ id, label, icon }) => (
            <button
              key={id}
              onClick={() => setView(id)}
              className={`w-full flex items-center gap-2.5 px-4 py-2 text-sm transition-colors ${
                view === id
                  ? 'bg-gray-800 text-white'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }`}
            >
              {icon}
              {label}
            </button>
          ))}
        </div>
        <div className="p-3 border-t border-gray-800 text-xs text-gray-600">v0.2.0</div>
      </nav>

      {/* Main panel */}
      <main className="flex-1 overflow-auto p-6">
        {view === 'memory' && <MemoryViewer />}
        {view === 'messages' && <MessageHistory />}
        {view === 'tools' && <ToolConfig />}
        {view === 'tasks' && <TaskDashboard />}
        {view === 'system' && <SystemStatus />}
      </main>

      {/* Activity stream */}
      <aside className="w-80 bg-gray-900 border-l border-gray-800 overflow-auto">
        <ActivityStream events={events} />
      </aside>
    </div>
  )
}

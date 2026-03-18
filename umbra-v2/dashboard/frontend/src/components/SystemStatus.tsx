import { useState, useEffect, useCallback } from 'react'
import { Server, Database, Bot, Cpu, RefreshCw } from 'lucide-react'
import { getHealth, getAgentInfo } from '../lib/api'

function StatusBadge({ status }: { status: string }) {
  const color = status === 'ok' ? 'bg-green-500' : status === 'down' ? 'bg-red-500' : 'bg-yellow-500'
  return (
    <span className="flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full ${color}`} />
      <span className="text-xs text-gray-400">{status}</span>
    </span>
  )
}

export default function SystemStatus() {
  const [health, setHealth] = useState<any>(null)
  const [agent, setAgent] = useState<any>(null)

  const load = useCallback(async () => {
    try {
      const [h, a] = await Promise.all([getHealth(), getAgentInfo()])
      setHealth(h)
      setAgent(a)
    } catch (e) {
      console.error('Failed to load system status:', e)
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 15000)
    return () => clearInterval(interval)
  }, [load])

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <h2 className="text-xl font-bold">System</h2>
        <button onClick={load} className="ml-auto text-gray-500 hover:text-gray-300">
          <RefreshCw size={16} />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Services */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h3 className="flex items-center gap-2 text-sm font-medium text-gray-300 mb-4">
            <Server size={16} /> Services
          </h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Letta Server</span>
              {health ? <StatusBadge status={health.letta?.status || 'unknown'} /> : <span className="text-xs text-gray-600">...</span>}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Ollama</span>
              {health ? <StatusBadge status={health.ollama?.status || 'unknown'} /> : <span className="text-xs text-gray-600">...</span>}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Claude Proxy</span>
              {health ? <StatusBadge status={health.proxy?.status || 'unknown'} /> : <span className="text-xs text-gray-600">...</span>}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Database</span>
              {health ? <StatusBadge status={health.database?.status || 'unknown'} /> : <span className="text-xs text-gray-600">...</span>}
            </div>
          </div>
          {health?.ollama?.models && (
            <div className="mt-4 pt-3 border-t border-gray-800">
              <span className="text-xs text-gray-500">Ollama models:</span>
              <div className="flex flex-wrap gap-1 mt-1">
                {health.ollama.models.map((m: string) => (
                  <span key={m} className="px-2 py-0.5 bg-gray-800 rounded text-xs text-gray-400">{m}</span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Agent */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h3 className="flex items-center gap-2 text-sm font-medium text-gray-300 mb-4">
            <Bot size={16} /> Agent
          </h3>
          {agent && !agent.error ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Name</span>
                <span className="text-gray-300 font-mono">{agent.name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">ID</span>
                <span className="text-gray-400 font-mono text-xs truncate max-w-48">{agent.id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Model</span>
                <span className="text-gray-300 font-mono text-xs">{agent.model || '-'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Embedding</span>
                <span className="text-gray-300 font-mono text-xs">{agent.embedding_model || '-'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Created</span>
                <span className="text-gray-400 text-xs">
                  {agent.created_at ? new Date(agent.created_at).toLocaleDateString() : '-'}
                </span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-600">{agent?.error || 'Loading...'}</p>
          )}
        </div>

        {/* Database tables */}
        {health?.database?.tables && (
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 md:col-span-2">
            <h3 className="flex items-center gap-2 text-sm font-medium text-gray-300 mb-4">
              <Database size={16} /> Database Tables
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(health.database.tables as Record<string, number>).map(([table, count]) => (
                <div key={table} className="bg-gray-950 rounded p-2">
                  <span className="text-xs font-mono text-gray-500">{table}</span>
                  <p className="text-lg font-bold text-gray-300">{count}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

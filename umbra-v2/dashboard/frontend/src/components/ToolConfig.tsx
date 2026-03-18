import { useState, useEffect, useCallback } from 'react'
import { Link2, Unlink, RefreshCw, Eye, EyeOff } from 'lucide-react'
import { getAttachedTools, getAvailableTools, attachTool, detachTool, getEnvVars, updateEnvVars } from '../lib/api'

interface Tool {
  id: string
  name: string
  description: string
  tags: string[]
}

export default function ToolConfig() {
  const [attached, setAttached] = useState<Tool[]>([])
  const [available, setAvailable] = useState<Tool[]>([])
  const [envVars, setEnvVars] = useState<Record<string, string>>({})
  const [editEnv, setEditEnv] = useState<Record<string, string>>({})
  const [showSecrets, setShowSecrets] = useState(false)
  const [tab, setTab] = useState<'tools' | 'env'>('tools')

  const loadTools = useCallback(async () => {
    try {
      const [att, avail] = await Promise.all([getAttachedTools(), getAvailableTools()])
      if (Array.isArray(att)) setAttached(att)
      if (Array.isArray(avail)) setAvailable(avail)
    } catch (e) {
      console.error('Failed to load tools:', e)
    }
  }, [])

  const loadEnv = useCallback(async () => {
    try {
      const data = await getEnvVars()
      if (data && typeof data === 'object' && !('error' in data)) {
        setEnvVars(data)
        setEditEnv(data)
      }
    } catch (e) {
      console.error('Failed to load env:', e)
    }
  }, [])

  const handleAttach = async (id: string) => {
    await attachTool(id)
    await loadTools()
  }

  const handleDetach = async (id: string) => {
    await detachTool(id)
    await loadTools()
  }

  const handleSaveEnv = async () => {
    await updateEnvVars(editEnv)
    await loadEnv()
  }

  useEffect(() => { loadTools(); loadEnv() }, [loadTools, loadEnv])

  const attachedIds = new Set(attached.map((t) => t.id))
  const unattached = available.filter((t) => !attachedIds.has(t.id))

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <h2 className="text-xl font-bold">Tools</h2>
        <div className="flex gap-1 bg-gray-800 rounded-lg p-0.5">
          <button
            onClick={() => setTab('tools')}
            className={`px-3 py-1 text-sm rounded-md transition ${tab === 'tools' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}
          >Tools</button>
          <button
            onClick={() => setTab('env')}
            className={`px-3 py-1 text-sm rounded-md transition ${tab === 'env' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}
          >Env Vars</button>
        </div>
        <button onClick={() => { loadTools(); loadEnv() }} className="ml-auto text-gray-500 hover:text-gray-300">
          <RefreshCw size={16} />
        </button>
      </div>

      {tab === 'tools' && (
        <div className="space-y-6">
          <div>
            <h3 className="text-sm font-medium text-gray-400 mb-3">Attached ({attached.length})</h3>
            <div className="space-y-2">
              {attached.map((t) => (
                <div key={t.id} className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-lg p-3">
                  <div>
                    <span className="text-sm font-mono text-cyan-400">{t.name}</span>
                    <p className="text-xs text-gray-500 mt-0.5">{t.description}</p>
                  </div>
                  <button
                    onClick={() => handleDetach(t.id)}
                    className="text-red-500/60 hover:text-red-400 p-1"
                    title="Detach"
                  >
                    <Unlink size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {unattached.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-gray-400 mb-3">Available ({unattached.length})</h3>
              <div className="space-y-2">
                {unattached.map((t) => (
                  <div key={t.id} className="flex items-center justify-between bg-gray-900/50 border border-gray-800/50 rounded-lg p-3">
                    <div>
                      <span className="text-sm font-mono text-gray-400">{t.name}</span>
                      <p className="text-xs text-gray-600 mt-0.5">{t.description}</p>
                    </div>
                    <button
                      onClick={() => handleAttach(t.id)}
                      className="text-cyan-500/60 hover:text-cyan-400 p-1"
                      title="Attach"
                    >
                      <Link2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'env' && (
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-gray-400">Environment Variables</h3>
            <button
              onClick={() => setShowSecrets(!showSecrets)}
              className="text-gray-500 hover:text-gray-300"
            >
              {showSecrets ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
          <div className="space-y-2">
            {Object.entries(editEnv).map(([key, value]) => {
              const isSecret = value === '***'
              return (
                <div key={key} className="flex gap-2">
                  <label className="w-48 text-xs font-mono text-gray-500 py-2 flex-shrink-0 truncate" title={key}>
                    {key}
                  </label>
                  <input
                    value={isSecret && !showSecrets ? '***' : value}
                    onChange={(e) => setEditEnv({ ...editEnv, [key]: e.target.value })}
                    disabled={isSecret && !showSecrets}
                    className="flex-1 bg-gray-950 border border-gray-800 rounded px-2 py-1.5 text-xs font-mono text-gray-300 focus:outline-none focus:border-gray-600 disabled:text-gray-600"
                  />
                </div>
              )
            })}
          </div>
          <div className="flex justify-end mt-4">
            <button
              onClick={handleSaveEnv}
              className="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 rounded text-sm"
            >Save</button>
          </div>
        </div>
      )}
    </div>
  )
}

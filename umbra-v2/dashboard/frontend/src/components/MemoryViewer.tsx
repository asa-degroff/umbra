import { useState, useEffect, useCallback } from 'react'
import { Save, Search, Trash2, RefreshCw } from 'lucide-react'
import { getBlocks, updateBlock, getArchival, deletePassage } from '../lib/api'

interface Block {
  id: string
  label: string
  value: string
  limit: number
  length: number
}

interface Passage {
  id: string
  text: string
  created_at: string | null
}

export default function MemoryViewer() {
  const [blocks, setBlocks] = useState<Block[]>([])
  const [editValues, setEditValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [tab, setTab] = useState<'core' | 'archival'>('core')

  // Archival state
  const [passages, setPassages] = useState<Passage[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [archivalCursor, setArchivalCursor] = useState<string | null>(null)
  const [archivalLoading, setArchivalLoading] = useState(false)

  const loadBlocks = useCallback(async () => {
    try {
      const data = await getBlocks()
      if (Array.isArray(data)) {
        setBlocks(data)
        const edits: Record<string, string> = {}
        data.forEach((b: Block) => { edits[b.id] = b.value })
        setEditValues(edits)
      }
    } catch (e) {
      console.error('Failed to load blocks:', e)
    }
  }, [])

  const handleSave = async (block: Block) => {
    setSaving(block.id)
    try {
      await updateBlock(block.id, editValues[block.id] || '')
      await loadBlocks()
    } catch (e) {
      console.error('Failed to save:', e)
    }
    setSaving(null)
  }

  const loadArchival = useCallback(async (reset = false) => {
    setArchivalLoading(true)
    try {
      const data = await getArchival({
        query: searchQuery || undefined,
        cursor: reset ? undefined : archivalCursor || undefined,
        limit: 50,
      })
      if (reset) {
        setPassages(data.passages)
      } else {
        setPassages((prev) => [...prev, ...data.passages])
      }
      setArchivalCursor(data.next_cursor)
    } catch (e) {
      console.error('Failed to load archival:', e)
    }
    setArchivalLoading(false)
  }, [searchQuery, archivalCursor])

  const handleDelete = async (id: string) => {
    try {
      await deletePassage(id)
      setPassages((prev) => prev.filter((p) => p.id !== id))
    } catch (e) {
      console.error('Failed to delete:', e)
    }
  }

  useEffect(() => { loadBlocks() }, [loadBlocks])

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <h2 className="text-xl font-bold">Memory</h2>
        <div className="flex gap-1 bg-gray-800 rounded-lg p-0.5">
          <button
            onClick={() => setTab('core')}
            className={`px-3 py-1 text-sm rounded-md transition ${tab === 'core' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}
          >Core Blocks</button>
          <button
            onClick={() => { setTab('archival'); if (passages.length === 0) loadArchival(true) }}
            className={`px-3 py-1 text-sm rounded-md transition ${tab === 'archival' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}
          >Archival</button>
        </div>
        <button onClick={loadBlocks} className="ml-auto text-gray-500 hover:text-gray-300">
          <RefreshCw size={16} />
        </button>
      </div>

      {tab === 'core' && (
        <div className="space-y-4">
          {blocks.map((block) => {
            const val = editValues[block.id] || ''
            const dirty = val !== block.value
            return (
              <div key={block.id} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-sm text-cyan-400">{block.label}</span>
                  <span className="text-xs text-gray-500">
                    {val.length}{block.limit ? ` / ${block.limit}` : ''} chars
                  </span>
                </div>
                <textarea
                  value={val}
                  onChange={(e) => setEditValues({ ...editValues, [block.id]: e.target.value })}
                  className="w-full bg-gray-950 border border-gray-800 rounded p-3 text-sm text-gray-200 font-mono resize-y min-h-24 focus:outline-none focus:border-gray-600"
                  rows={6}
                />
                {dirty && (
                  <div className="flex justify-end mt-2">
                    <button
                      onClick={() => handleSave(block)}
                      disabled={saving === block.id}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 rounded text-sm disabled:opacity-50"
                    >
                      <Save size={14} />
                      {saving === block.id ? 'Saving...' : 'Save'}
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {tab === 'archival' && (
        <div>
          <div className="flex gap-2 mb-4">
            <div className="flex-1 relative">
              <Search size={14} className="absolute left-3 top-2.5 text-gray-500" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadArchival(true)}
                placeholder="Search archival memory..."
                className="w-full bg-gray-900 border border-gray-800 rounded pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-gray-600"
              />
            </div>
            <button
              onClick={() => loadArchival(true)}
              className="px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded text-sm"
            >Search</button>
          </div>

          <div className="space-y-2">
            {passages.map((p) => (
              <div key={p.id} className="bg-gray-900 border border-gray-800 rounded-lg p-3 group">
                <p className="text-sm text-gray-300 whitespace-pre-wrap">{p.text}</p>
                <div className="flex items-center justify-between mt-2">
                  <span className="text-xs text-gray-600">
                    {p.created_at ? new Date(p.created_at).toLocaleString() : ''}
                  </span>
                  <button
                    onClick={() => handleDelete(p.id)}
                    className="opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-400 transition"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>

          {archivalCursor && (
            <button
              onClick={() => loadArchival(false)}
              disabled={archivalLoading}
              className="mt-4 w-full py-2 bg-gray-800 hover:bg-gray-700 rounded text-sm disabled:opacity-50"
            >
              {archivalLoading ? 'Loading...' : 'Load more'}
            </button>
          )}

          {passages.length === 0 && !archivalLoading && (
            <p className="text-center text-gray-600 text-sm py-8">
              {searchQuery ? 'No passages match your search' : 'No archival passages'}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

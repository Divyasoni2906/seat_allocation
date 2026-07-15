import { useState, useRef, useEffect } from 'react'
import { askAI } from '../api.js'

const EXAMPLE_QUERIES = [
  'Where is employee Amit seated?',
  'Show all available seats on Floor 3',
  'How many seats are occupied for Project Indigo?',
  'Which project am I assigned to? amit@ethara.ai',
  'Who is sitting near me? amit@ethara.ai',
  'Release seat for amit@ethara.ai',
]

// Chat history is persisted to localStorage (not just React state) so it
// survives navigating to another tab and back -- React Router unmounts
// this component on route change, which was wiping the conversation.
const STORAGE_KEY = 'ethara.ai-assistant.messages'

const DEFAULT_MESSAGES = [
  {
    role: 'assistant',
    text: "Hi! Ask me things like \"Where is employee Amit seated?\", \"Show available seats on Floor 3\", or \"Release my seat\" (include your email or name).",
  },
]

function loadMessages() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_MESSAGES
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) && parsed.length > 0 ? parsed : DEFAULT_MESSAGES
  } catch {
    return DEFAULT_MESSAGES
  }
}

export default function AIAssistant() {
  const [messages, setMessages] = useState(loadMessages)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages))
    } catch {
      // Storage can fail (private browsing, quota) -- chat still works
      // in-memory for this session, it just won't persist across tabs.
    }
  }, [messages])

  const send = async (text) => {
    const query = text ?? input
    if (!query.trim()) return
    setMessages((m) => [...m, { role: 'user', text: query }])
    setInput('')
    setLoading(true)
    try {
      const res = await askAI(query)
      setMessages((m) => [...m, { role: 'assistant', text: res.answer, intent: res.intent }])
    } catch (err) {
      setMessages((m) => [...m, { role: 'assistant', text: 'Something went wrong reaching the assistant.' }])
    } finally {
      setLoading(false)
    }
  }

  const clearChat = () => {
    setMessages(DEFAULT_MESSAGES)
  }

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">AI Assistant</h1>
        <button
          type="button"
          onClick={clearChat}
          className="text-xs text-slate-500 hover:text-rose-600 hover:underline"
        >
          Clear chat
        </button>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 flex flex-col h-[480px]">
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                  m.role === 'user' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-700'
                }`}
              >
                {m.text}
                {m.intent && m.intent !== 'unknown' && (
                  <div className="text-[10px] mt-1 opacity-60">intent: {m.intent}</div>
                )}
              </div>
            </div>
          ))}
          {loading && <div className="text-xs text-slate-400">Thinking...</div>}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-slate-100 p-3 flex flex-wrap gap-2">
          {EXAMPLE_QUERIES.map((q) => (
            <button
              key={q}
              onClick={() => send(q)}
              className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-full px-3 py-1"
            >
              {q}
            </button>
          ))}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            send()
          }}
          className="border-t border-slate-100 p-3 flex gap-2"
        >
          <input
            className="flex-1 border border-slate-300 rounded-md px-3 py-2 text-sm"
            placeholder="Ask about a seat, project, or availability..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button
            type="submit"
            className="bg-brand-600 text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-brand-700"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  )
}

import { useState, useEffect, useRef } from 'react'
import './index.css'

function App() {
  const [command, setCommand] = useState('')
  const [messages, setMessages] = useState([])
  const [isConnected, setIsConnected] = useState(false)
  const [showInfo, setShowInfo] = useState(false)
  const ws = useRef(null)

  useEffect(() => {
    ws.current = new WebSocket('ws://localhost:8000/ws')

    ws.current.onopen = () => {
      setIsConnected(true)
      setMessages(prev => [...prev, { type: 'system', text: 'Connected to Agent Backend' }])
    }

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data)
      setMessages(prev => [...prev, { type: data.type, text: data.content }])
    }

    ws.current.onclose = () => {
      setIsConnected(false)
      setMessages(prev => [...prev, { type: 'system', text: 'Disconnected from Agent Backend' }])
    }

    return () => {
      if (ws.current) ws.current.close()
    }
  }, [])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!command.trim() || !ws.current) return

    setMessages(prev => [...prev, { type: 'user', text: command }])
    ws.current.send(JSON.stringify({ type: 'command', content: command }))
    setCommand('')
  }

  return (
    <div className="app-shell">
      <div className="app-backdrop app-backdrop-left" />
      <div className="app-backdrop app-backdrop-right" />

      <main className="dashboard">
        <button
          type="button"
          className="info-toggle"
          onClick={() => setShowInfo(prev => !prev)}
          aria-pressed={showInfo}
          aria-label="Show how it works"
        >
          i
        </button>

        <section className="hero">
          <h1>
            <span id="title">
              Personal AI Assistant
              <span className={isConnected ? 'status status-online' : 'status status-offline'}>
                {isConnected ? 'Connected' : 'Offline'}
              </span>
            </span>
          </h1>

        </section>

        <section className={showInfo ? 'content-grid content-grid-info-open' : 'content-grid'}>
          <div className={showInfo ? 'card prompt-card prompt-card-wide' : 'card prompt-card'}>

            <form onSubmit={handleSubmit} className="command-form">
              <label htmlFor="command-input" className="sr-only">
                Enter your command
              </label>
              <input
                id="command-input"
                type="text"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                placeholder="Enter prompt here"
                className="command-input"
                disabled={!isConnected}
              />
              <button type="submit" disabled={!isConnected} className="send-button">
                Send
              </button>
            </form>

            <p className="prompt-hint">
              Example: lookup customers by <code>user_id</code>, filter by subscription, or send a bulk
              email to the matching rows.
            </p>
          </div>

          {showInfo && (
            <div className="info-overlay" role="dialog" aria-modal="true" aria-label="How it works">
              <button
                type="button"
                className="info-overlay-backdrop"
                onClick={() => setShowInfo(false)}
                aria-label="Close how it works panel"
              />
              <aside className="card notes-card notes-card-overlay">
                <div className="card-heading notes-heading">
                  <p className="notes-label">How it works</p>
                  <button type="button" className="info-close" onClick={() => setShowInfo(false)}>
                    Close
                  </button>
                </div>
                <ul className="notes-list">
                  <li>The agent reads your request and decides the database filters.</li>
                  <li>It looks up matching customers from PostgreSQL.</li>
                  <li>It sends the email to each matching address using Gmail API.</li>
                </ul>
              </aside>
            </div>
          )}
        </section>

        <section className="feed card">
          <div className="card-heading feed-heading">
            <p>Activity Feed</p>
            <span>{messages.length} updates</span>
          </div>

          <div className="feed-body">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`feed-item ${msg.type === 'user'
                  ? 'feed-user'
                  : msg.type === 'update'
                    ? 'feed-update'
                    : msg.type === 'result'
                      ? 'feed-result'
                      : msg.type === 'error'
                        ? 'feed-error'
                        : 'feed-system'
                  }`}
              >
                {msg.type === 'update' && <span className="feed-arrow">➜</span>}
                <span>{msg.text}</span>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  )
}

export default App

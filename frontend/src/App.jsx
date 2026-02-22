import { useState, useRef, useEffect } from 'react'
import { Send, Settings, Database, MessageSquareText, Menu, ChevronDown, ChevronRight, Check } from 'lucide-react'
import axios from 'axios'
import mermaid from 'mermaid'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

// API URL - should be environment variable in production
const API_URL = "http://localhost:8000/api"

mermaid.initialize({ startOnLoad: false, theme: 'default' });

export default function App() {
  const [activeTab, setActiveTab] = useState('chat')
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [showSettings, setShowSettings] = useState(true)
  const [schema, setSchema] = useState(null)
  const messagesEndRef = useRef(null)

  // Auto-scroll to bottom of chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // Fetch Schema for ER Diagram
  useEffect(() => {
    const fetchSchema = async () => {
      try {
        const res = await axios.get(`${API_URL}/schema`)
        setSchema(res.data.schema)
      } catch (err) {
        console.error("Failed to load schema", err)
      }
    }
    fetchSchema()
  }, [])

  const handleSend = async () => {
    if (!inputValue.trim() || !apiKey) return

    const userMsg = { role: 'user', content: inputValue }
    setMessages(prev => [...prev, userMsg])
    setInputValue('')
    setIsLoading(true)

    try {
      const { data } = await axios.post(`${API_URL}/chat`, {
        query: userMsg.content,
        api_key: apiKey
      })

      const aiMsg = {
        role: 'ai',
        content: data.answer || "No text returned.",
        sql: data.sql_query || null,
        time: data.execution_time || 0,
        tokens: data.tokens || "N/A",
        thoughts: data.thoughts || []
      }
      setMessages(prev => [...prev, aiMsg])
    } catch (err) {
      console.error("Chat API Error:", err);
      const errorMsg = {
        role: 'ai',
        content: `Error: ${err.response?.data?.detail || err.message || "Unknown error occurred"}`,
        thoughts: []
      }
      setMessages(prev => [...prev, errorMsg])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="app-container">
      {/* Settings Modal */}
      {showSettings && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h2 style={{ marginBottom: '1.5rem', color: 'var(--text-primary)' }}>Welcome to Text2SQL</h2>
            <div className="form-group">
              <label className="form-label">Gemini API Key</label>
              <input
                type="password"
                className="form-input"
                placeholder="AIzaSy..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>
            <button
              className="btn-primary"
              onClick={() => {
                if (apiKey) setShowSettings(false)
              }}
              disabled={!apiKey}
              style={{ opacity: apiKey ? 1 : 0.5 }}
            >
              Start Chatting
            </button>
          </div>
        </div>
      )}

      {/* Sidebar */}
      <div className="sidebar">
        <div className="sidebar-header">
          <Database size={28} className="sidebar-logo" />
          <h1 className="sidebar-title">Data Insights</h1>
        </div>

        <nav className="sidebar-nav">
          <button
            className={`nav-item ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            <MessageSquareText size={20} />
            SQL Chat Assistant
          </button>
          <button
            className={`nav-item ${activeTab === 'er' ? 'active' : ''}`}
            onClick={() => setActiveTab('er')}
          >
            <Menu size={20} />
            ER Diagram (Beta)
          </button>
        </nav>

        <button
          className="nav-item"
          style={{ marginTop: 'auto' }}
          onClick={() => setShowSettings(true)}
        >
          <Settings size={20} />
          API Configuration
        </button>
      </div>

      {/* Main Content */}
      <div className="main-content">
        {activeTab === 'chat' ? (
          <>
            <div className="chat-container">
              {messages.length === 0 && (
                <div style={{ textAlign: 'center', marginTop: '10vh', color: 'var(--text-muted)' }}>
                  <Database size={64} style={{ margin: '0 auto 1rem', opacity: 0.2 }} />
                  <h2>Ask me anything about your database!</h2>
                  <p>Try: "Show me the top 5 highest transaction values"</p>
                </div>
              )}

              {messages.map((msg, idx) => (
                <div key={idx} className={`message-wrapper ${msg.role}`}>
                  <div className={`message ${msg.role}`}>
                    {msg.role === 'ai' && msg.thoughts && msg.thoughts.length > 0 && (
                      <ThoughtsAccordion thoughts={msg.thoughts} />
                    )}

                    <div
                      className="markdown-body"
                      dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(marked.parse(String(msg.content || ""))) }}
                    />

                    {msg.role === 'ai' && msg.sql && (
                      <>
                        <div className="metrics-grid">
                          <div className="metric-card">
                            <div className="metric-label">Execution Time</div>
                            <div className="metric-value">{msg.time}s</div>
                          </div>
                          <div className="metric-card" title="Total | Input | Output">
                            <div className="metric-label">Tokens Used</div>
                            <div className="metric-value" style={{ fontSize: '1rem' }}>{msg.tokens}</div>
                          </div>
                        </div>
                        <SqlCodeBlock sql={msg.sql} />
                      </>
                    )}
                  </div>
                </div>
              ))}

              {isLoading && (
                <div className="message-wrapper ai">
                  <div className="message ai" style={{ width: 'auto' }}>
                    <div className="typing-indicator">
                      <div className="typing-dot"></div>
                      <div className="typing-dot"></div>
                      <div className="typing-dot"></div>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <div className="input-area">
              <div className="input-wrapper">
                <input
                  type="text"
                  className="chat-input"
                  placeholder="Ask a question about your data..."
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={isLoading}
                />
                <button
                  className="send-button"
                  onClick={handleSend}
                  disabled={!inputValue.trim() || isLoading}
                >
                  <Send size={18} />
                </button>
              </div>
            </div>
          </>
        ) : (
          <ERDiagram schema={schema} />
        )}
      </div>
    </div>
  )
}

function ThoughtsAccordion({ thoughts }) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className="thoughts-container">
      <div
        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontWeight: 600, color: 'var(--text-secondary)' }}
        onClick={() => setIsOpen(!isOpen)}
      >
        {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        View Agent Reasoning Steps
      </div>
      {isOpen && (
        <div style={{ marginTop: '1rem' }}>
          {thoughts.map((t, i) => {
            const isQuery = t.tool === 'sql_db_query';
            const isAction = t.tool && t.tool !== 'sql_db_query';
            const badgeClass = isQuery ? 'badge-query' : (isAction ? 'badge-action' : 'badge-thought');
            const badgeLabel = isQuery ? 'QUERY' : (isAction ? 'ACTION' : 'THOUGHT');

            return (
              <div key={i} className={`thought-item ${badgeClass}`}>
                <div className="thought-badge">{badgeLabel}</div>
                <div className="thought-content">
                  <strong>{t.tool || "Reasoning"}</strong>
                  <p>{t.log}</p>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function SqlCodeBlock({ sql }) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className="sql-accordion">
      <div className="sql-header" onClick={() => setIsOpen(!isOpen)}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Database size={16} /> Generated SQL
        </span>
        {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </div>
      {isOpen && (
        <div className="sql-content" style={{ margin: 0, padding: 0 }}>
          <SyntaxHighlighter language="sql" style={vscDarkPlus} customStyle={{ margin: 0, borderRadius: '0 0 6px 6px', fontSize: '0.875rem' }}>
            {sql}
          </SyntaxHighlighter>
        </div>
      )}
    </div>
  )
}

function ERDiagram({ schema }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (schema && containerRef.current) {
      let diagramStr = "erDiagram\n"

      // Define Entities and Attributes
      Object.keys(schema).forEach(table => {
        diagramStr += `  ${table} {\n`

        // Extract all FK column names for this table
        const fkColumns = new Set()
        schema[table].foreign_keys.forEach(fk => {
          if (Array.isArray(fk.constrained_columns)) {
            fk.constrained_columns.forEach(c => fkColumns.add(c))
          }
        })

        schema[table].columns.forEach(col => {
          let keys = []
          if (col.primary_key) keys.push("PK")
          if (fkColumns.has(col.name)) keys.push("FK")
          const keyStr = keys.length > 0 ? keys.join(",") : ""

          // Clean type and name for mermaid syntax
          const type = String(col.type).split("(")[0].replace(/[^a-zA-Z0-9_]/g, "_")
          const name = String(col.name).replace(/[^a-zA-Z0-9_]/g, "_")
          diagramStr += `    ${type} ${name} ${keyStr}\n`
        })
        diagramStr += `  }\n`
      })

      // Define Relationships
      Object.keys(schema).forEach(table => {
        schema[table].foreign_keys.forEach(fk => {
          diagramStr += `  ${fk.referred_table} ||--o{ ${table} : references\n`
        })
      })

      const renderDiagram = async () => {
        try {
          if (containerRef.current) {
            containerRef.current.innerHTML = "<div style='color: var(--text-muted);'>Generating diagram components...</div>"
          }
          const { svg } = await mermaid.render('er-graph-' + Date.now(), diagramStr)
          if (containerRef.current) {
            containerRef.current.innerHTML = svg
          }
        } catch (err) {
          console.error("Mermaid Render Error:", err, diagramStr)
          if (containerRef.current) containerRef.current.innerHTML = `<div style="color:var(--danger); padding: 1rem;">Failed to render ER diagram.<br/><pre style="font-size:10px;margin-top:10px">${err.message}</pre></div>`
        }
      }
      renderDiagram()
    }
  }, [schema])

  return (
    <div className="er-diagram-container">
      <div className="er-diagram-header">
        <h2>Entity-Relationship Diagram</h2>
        <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Generated automatically from SQLite schema</span>
      </div>
      <div className="er-diagram-content">
        {!schema ? (
          <div>Loading Schema Data...</div>
        ) : (
          <div ref={containerRef} style={{ width: '100%', height: '100%', display: 'flex', justifyContent: 'center' }}>
            {/* Mermaid SVG injected here */}
          </div>
        )}
      </div>
    </div>
  )
}

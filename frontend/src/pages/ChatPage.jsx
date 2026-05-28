import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useWebSocket } from '../hooks/useWebSocket';
import { getWebSocketUrl } from '../services/api';
import './ChatPage.css';

const SUGGESTED_PROMPTS = [
  'Why were these courses recommended for me?',
  'What should I learn next?',
  'Help me plan study time this week',
  'Compare my top two recommendations',
  'How should I start the first course?',
];

export default function ChatPage({ user }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [streamingMsg, setStreamingMsg] = useState('');
  const [isAITyping, setIsAITyping] = useState(false);
  const [liveEvent, setLiveEvent] = useState(null);
  const streamingMsgRef = useRef('');
  const messagesEndRef = useRef(null);

  const { sendMessage, lastMessage, isConnected } = useWebSocket(getWebSocketUrl(user.id));

  useEffect(() => {
    if (!lastMessage) return;
    if (lastMessage.type === 'token') {
      queueMicrotask(() => {
        setStreamingMsg((previous) => previous + lastMessage.content);
      });
    } else if (lastMessage.type === 'done') {
      const response = lastMessage.full_response || streamingMsgRef.current;
      queueMicrotask(() => {
        setMessages((previous) => [...previous, { role: 'assistant', content: response }]);
        setStreamingMsg('');
        setIsAITyping(false);
      });
    } else if (lastMessage.type === 'error') {
      queueMicrotask(() => {
        setMessages((previous) => [...previous, { role: 'assistant', content: lastMessage.message || 'Something went wrong.' }]);
        setStreamingMsg('');
        setIsAITyping(false);
      });
    } else if (lastMessage.type === 'live_event') {
      queueMicrotask(() => {
        setLiveEvent(lastMessage.message);
        setTimeout(() => setLiveEvent(null), 5000); // hide after 5s
      });
    }
  }, [lastMessage]);

  useEffect(() => {
    streamingMsgRef.current = streamingMsg;
  }, [streamingMsg]);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, streamingMsg]);

  const handleSend = (text = input) => {
    if (!text.trim()) return;
    const trimmed = text.trim();
    const userMessage = { role: 'user', content: trimmed };
    const nextMessages = [...messages, userMessage];

    setMessages(nextMessages);

    if (isConnected) {
      sendMessage({ message: trimmed, history: nextMessages.slice(-10) });
    } else {
      simulateResponse(trimmed);
    }

    setInput(''); setIsAITyping(true); setStreamingMsg('');
  };

  const simulateResponse = () => {
    const response = `Based on your profile and learning goals, I'd recommend focusing on building strong foundations first. Your current recommendations are tailored to your interests in ${user.skill_tags?.slice(0, 3).join(', ') || 'technology'}.\n\nHere's what I suggest:\n1. **Start with Python basics** — this unlocks everything else\n2. **Move to SQL** — essential for data work\n3. **Then tackle Statistics** — the math behind ML\n\nWould you like me to create a detailed study plan for any of these?`;
    let i = 0;
    const interval = setInterval(() => {
      if (i < response.length) { setStreamingMsg(p => p + response[i]); i++; }
      else { clearInterval(interval); setMessages(p => [...p, { role: 'assistant', content: response }]); setStreamingMsg(''); setIsAITyping(false); }
    }, 15);
  };

  const handleKeyDown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } };

  return (
    <div className="chat-page">
      <AnimatePresence>
        {liveEvent && (
          <motion.div 
            className="live-event-toast"
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
          >
            {liveEvent}
          </motion.div>
        )}
      </AnimatePresence>
      <div className="chat-container">
        {/* Sidebar */}
        <div className="chat-sidebar">
          <div className="sidebar-header">
            <h3 className="sidebar-title">Assistant</h3>
            <span className={`connection-dot ${isConnected ? 'connected' : ''}`}>
              {isConnected ? 'Online' : 'Offline'}
            </span>
          </div>

          <div className="context-section">
            <span className="section-label">Included context</span>
            <div className="context-items">
              <span className="context-chip">Skills and goals</span>
              <span className="context-chip">Recommendations list</span>
              <span className="context-chip">Recent feedback</span>
            </div>
          </div>

          <div className="prompts-section">
            <span className="section-label">Suggestions</span>
            {SUGGESTED_PROMPTS.map((prompt, i) => (
              <button key={prompt} type="button" className="prompt-btn" onClick={() => handleSend(prompt)} id={`suggested-${i}`}>
                <span className="prompt-text">{prompt}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Chat area */}
        <div className="chat-main">
          <div className="messages-container">
            {messages.length === 0 && !streamingMsg && (
              <div className="empty-chat">
                <h2>Ask about your plan or recommendations</h2>
                <p>The assistant can use your profile, goals, and latest picks to answer.</p>
                <div className="empty-chips">
                  {SUGGESTED_PROMPTS.slice(0, 3).map((p) => (
                    <button key={p} type="button" className="empty-chip" onClick={() => handleSend(p)}>
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <AnimatePresence>
              {messages.map((msg, i) => (
                <motion.div key={i} className={`message ${msg.role}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
                  <div className={`message-avatar ${msg.role}`}>{msg.role === 'user' ? userInitial(user.name) : 'AI'}</div>
                  <div className="message-bubble">
                    <div className="message-content">{formatMessage(msg.content)}</div>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>

            {streamingMsg && (
              <motion.div className="message assistant" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                <div className="message-avatar assistant">AI</div>
                <div className="message-bubble">
                  <div className="message-content">{formatMessage(streamingMsg)}</div>
                  <span className="typewriter-cursor" />
                </div>
              </motion.div>
            )}

            {isAITyping && !streamingMsg && (
              <div className="message assistant">
                <div className="message-avatar assistant">AI</div>
                <div className="message-bubble typing">
                  <span className="thinking-text">Analyzing profile and formulating plan</span>
                  <span className="dot" /><span className="dot" /><span className="dot" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input-container">
            <div className="chat-input-wrapper">
              <textarea value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown}
                placeholder="Ask about your recommendations, learning path, or skills..."
                className="chat-input" rows={1} id="chat-input" />
              <button type="button" className="send-btn" onClick={() => handleSend()} disabled={!input.trim() || isAITyping} id="send-btn" aria-label="Send message">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M12 19V5M5 12l7-7 7 7" />
                </svg>
              </button>
            </div>
            <p className="input-hint">Answers stream when the live connection is available.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function formatMessage(text) {
  // Safe rendering: split on newlines, then bold **text** via React elements
  const parts = text.split('\n');
  return parts.map((line, i) => {
    // Split on **bold** markers and wrap in <strong>
    const segments = line.split(/(\*\*.*?\*\*)/g).map((seg, j) => {
      if (seg.startsWith('**') && seg.endsWith('**')) {
        return <strong key={j}>{seg.slice(2, -2)}</strong>;
      }
      return seg;
    });
    return (
      <span key={i}>
        {i > 0 && <br />}
        {segments}
      </span>
    );
  });
}

function userInitial(name) {
  const t = String(name || 'U').trim();
  return t ? t.charAt(0).toUpperCase() : 'U';
}

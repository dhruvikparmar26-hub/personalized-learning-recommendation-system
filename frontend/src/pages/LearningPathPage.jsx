import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useSSEStream } from '../hooks/useSSE';
import { getSSELearningPathUrl, updateUser } from '../services/api';
import './LearningPathPage.css';

const MOCK_PATH = [
  { name: 'Python for Everybody', duration: 'Days 1-5', status: 'completed', progress: 100, focus: 'Variables, loops, functions — build a strong foundation', time: '8 hrs', difficulty: 'Beginner', skillGain: '+3 Python' },
  { name: 'SQL for Data Science', duration: 'Days 6-10', status: 'in-progress', progress: 60, focus: 'Querying databases, joins, and aggregations', time: '6 hrs', difficulty: 'Beginner', skillGain: '+2 SQL' },
  { name: 'Statistics with Python', duration: 'Days 11-16', status: 'not-started', progress: 0, focus: 'Hypothesis testing, probability distributions', time: '10 hrs', difficulty: 'Intermediate', skillGain: '+3 Statistics' },
  { name: 'Machine Learning', duration: 'Days 17-24', status: 'not-started', progress: 0, focus: 'Supervised learning, model evaluation, feature engineering', time: '14 hrs', difficulty: 'Intermediate', skillGain: '+4 ML' },
  { name: 'Deep Learning Specialization', duration: 'Days 25-30', status: 'not-started', progress: 0, focus: 'Neural networks, CNNs, intro to TensorFlow', time: '12 hrs', difficulty: 'Advanced', skillGain: '+4 Deep Learning' },
];

const MILESTONES = [
  { day: 7, title: 'Python basics mastered', unlocked: true, reward: 'Badge: foundations' },
  { day: 14, title: 'Data querying proficient', unlocked: false, reward: 'Badge: querying' },
  { day: 21, title: 'Statistical analysis ready', unlocked: false, reward: 'Badge: stats' },
  { day: 30, title: 'ML foundations complete', unlocked: false, reward: 'Badge: ML core' },
];

export default function LearningPathPage({ user }) {
  const [generating, setGenerating] = useState(false);
  const [pathItems] = useState(MOCK_PATH);
  const [showGoalEditor, setShowGoalEditor] = useState(false);
  const [goalText, setGoalText] = useState(user.goal || 'Career change');
  const navigate = useNavigate();

  const { text: generatedText, isStreaming, isDone } = useSSEStream(
    getSSELearningPathUrl(user.id), generating
  );

  const completedCount = pathItems.filter(p => p.status === 'completed').length;
  const totalProgress = Math.round(pathItems.reduce((sum, p) => sum + p.progress, 0) / pathItems.length);
  const totalHours = pathItems.reduce((sum, p) => sum + parseInt(p.time), 0);
  const circumference = 2 * Math.PI * 54;
  const strokeDashoffset = circumference - (totalProgress / 100) * circumference;

  return (
    <div className="path-page page-container">
      {/* ── Header ──────────────────────────────────────── */}
      <div className="path-header animate-fade-in">
        <div>
          <h1>Your Learning Path</h1>
          <p className="path-subtitle">A sequenced 30-day plan tailored to your career goals.</p>
        </div>
        <button type="button" className="btn-primary" onClick={() => setGenerating(true)} disabled={generating} id="generate-path-btn">
          {generating ? 'Generating…' : 'Generate path'}
        </button>
      </div>

      {/* ── Stats Bento Grid ─────────────────────────────── */}
      <div className="stats-bento bento-grid" style={{ gridTemplateColumns: '180px 1fr 1fr 1fr' }}>
        {/* Progress Ring */}
        <div className="bento-card stats-ring-card">
          <div className="stats-ring-wrap">
            <svg viewBox="0 0 120 120" className="stats-ring-svg">
              <circle cx="60" cy="60" r="54" className="ring-bg" />
              <motion.circle cx="60" cy="60" r="54" className="ring-fill"
                strokeDasharray={circumference}
                initial={{ strokeDashoffset: circumference }}
                animate={{ strokeDashoffset }}
                transition={{ duration: 1.2, ease: 'easeOut', delay: 0.3 }}
              />
            </svg>
            <div className="ring-center-text">
              <span className="ring-value">{totalProgress}%</span>
            </div>
          </div>
          <span className="stats-ring-label">Overall</span>
        </div>

        {/* Stat cards */}
        <div className="bento-card stat-card">
          <span className="stat-value">{completedCount}/{pathItems.length}</span>
          <span className="stat-label">Courses done</span>
        </div>
        <div className="bento-card stat-card">
          <span className="stat-figure">{totalHours}h</span>
          <span className="stat-label">Est. hours</span>
        </div>
        <div className="bento-card stat-card goal-card" onClick={() => setShowGoalEditor(!showGoalEditor)}>
          <span className="stat-value-sm">{goalText}</span>
          <span className="stat-label">Goal <span className="goal-edit-hint">Edit</span></span>
        </div>
      </div>

      {/* ── Goal Editor ──────────────────────────────────── */}
      <AnimatePresence>
        {showGoalEditor && (
          <motion.div className="goal-editor bento-card" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
            <h4>Update Career / Skill Goal</h4>
            <p className="goal-hint">Changing your goal immediately alters future recommendations.</p>
            <div className="goal-form">
              <input type="text" value={goalText} onChange={e => setGoalText(e.target.value)} className="goal-input" placeholder="e.g., Full-Stack Developer" />
              <button className="btn-primary" onClick={async () => {
                try {
                  await updateUser(user.id, { goal: goalText });
                } catch {
                  // Persist locally even if backend is unavailable
                }
                setShowGoalEditor(false);
              }}>Save Goal</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Claude streaming output ──────────────────────── */}
      <AnimatePresence>
        {(isStreaming || isDone) && generatedText && (
          <motion.div className="ai-path-output bento-card" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <div className="ai-output-header">
              <span className="badge badge-accent">Generated outline</span>
              {isStreaming && <span className="streaming-dot">Streaming...</span>}
            </div>
            <div className="ai-output-text">
              {generatedText}
              {isStreaming && <span className="typewriter-cursor" />}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Bento Module Cards ───────────────────────────── */}
      <div className="section-header" style={{ marginTop: 'var(--space-10)' }}>
        <h2>Course modules</h2>
        <p className="section-subtitle">Bite-sized modules with estimated time and skill gain.</p>
      </div>

      <div className="modules-grid bento-grid bento-grid-3">
        {pathItems.map((item, idx) => (
          <motion.div
            key={idx}
            className={`bento-card module-card ${item.status}`}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.08 }}
            id={`module-${idx}`}
          >
            {/* Status indicator */}
            <div className="module-status-bar">
              <span className={`badge ${item.status === 'completed' ? 'badge-success' : item.status === 'in-progress' ? 'badge-warning' : 'badge-accent'}`}>
                {item.duration}
              </span>
              {item.status === 'completed' && <span className="module-check">✓</span>}
              {item.status === 'in-progress' && <span className="module-live">Active</span>}
            </div>

            <h3 className="module-title">{item.name}</h3>
            <p className="module-focus">{item.focus}</p>

            {/* Meta pills */}
            <div className="module-meta">
              <span className="meta-pill">{item.time}</span>
              <span className="meta-pill">{item.difficulty}</span>
              <span className="meta-pill skill-gain">{item.skillGain}</span>
            </div>

            {/* Progress */}
            <div className="module-progress-track">
              <motion.div
                className={`module-progress-fill ${item.status}`}
                initial={{ width: 0 }}
                animate={{ width: `${item.progress}%` }}
                transition={{ duration: 0.8, delay: idx * 0.1 + 0.3 }}
              />
            </div>
            <span className="module-progress-text">{item.progress}% complete</span>
          </motion.div>
        ))}
      </div>

      {/* ── Milestones & Rewards ─────────────────────────── */}
      <div className="section-header" style={{ marginTop: 'var(--space-10)' }}>
        <h2>Milestones</h2>
      </div>

      <div className="bento-grid bento-grid-4">
        {MILESTONES.map((m, i) => (
          <motion.div
            key={i}
            className={`bento-card milestone-card ${m.unlocked ? 'unlocked' : 'locked'}`}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
          >
            <span className="milestone-day">Day {m.day}</span>
            <span className="milestone-title">{m.title}</span>
            <span className={`milestone-reward ${m.unlocked ? 'earned' : ''}`}>{m.reward}</span>
            {!m.unlocked && <span className="milestone-lock-label">Locked</span>}
          </motion.div>
        ))}
      </div>

      {/* FAB */}
      <motion.button type="button" className="fab fab--icon" onClick={() => navigate('/chat')} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.96 }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35 }} id="fab-chat-path" title="Open assistant" aria-label="Open assistant">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
        </svg>
      </motion.button>
    </div>
  );
}

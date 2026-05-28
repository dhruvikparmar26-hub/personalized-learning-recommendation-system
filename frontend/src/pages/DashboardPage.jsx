import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence, LayoutGroup } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useSSE, useSSEStream } from '../hooks/useSSE';
import { getRecommendations, submitFeedback, getSSERecommendationsUrl, getSSEExplanationUrl } from '../services/api';
import './DashboardPage.css';

const DAILY_TARGET_MINUTES = 45;
const COMPLETED_MINUTES = 28;


const SMART_FOCUS_ITEMS = [
  { type: 'Micro-lesson', title: 'Python list comprehensions', duration: '8 min', label: 'A' },
  { type: 'Flashcards', title: 'SQL JOIN types review', duration: '5 min', label: 'B' },
  { type: 'Quiz', title: 'Statistics quick check', duration: '10 min', label: 'C' },
];

export default function DashboardPage({ user }) {
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showExplanation, setShowExplanation] = useState(false);
  const [feedbackPending, setFeedbackPending] = useState(null);
  const [whyModal, setWhyModal] = useState(null);
  const navigate = useNavigate();

  // ── SSE is the primary data source. REST is the fallback. ──
  const { data: sseData } = useSSE(getSSERecommendationsUrl(user.id));
  const { text: explanationText, isStreaming } = useSSEStream(
    getSSEExplanationUrl(user.id), showExplanation
  );

  // Track whether SSE has delivered initial data
  const sseDelivered = useRef(false);

  useEffect(() => {
    if (sseData?.type === 'update' && sseData.recommendations) {
      queueMicrotask(() => setRecommendations(sseData.recommendations));
    } else if (sseData?.type === 'initial' && sseData.recommendations) {
      sseDelivered.current = true;
      queueMicrotask(() => {
        setRecommendations(sseData.recommendations);
        setLoading(false);
      });
    }
  }, [sseData]);

  // REST fallback — only fires if SSE hasn't delivered data after 3s
  useEffect(() => {
    const timer = setTimeout(async () => {
      if (sseDelivered.current) return; // SSE already delivered
      try {
        const data = await getRecommendations(user.id);
        if (!sseDelivered.current) {
          setRecommendations(data.recommendations || []);
        }
      } catch {
        if (!sseDelivered.current) {
          setRecommendations(getMockRecommendations());
        }
      } finally {
        if (!sseDelivered.current) setLoading(false);
      }
    }, 3000);

    return () => clearTimeout(timer);
  }, [user.id]);

  const handleFeedback = async (courseId, action) => {
    setFeedbackPending(courseId);
    try { await submitFeedback({ user_id: user.id, course_id: courseId, action }); }
    catch {
      if (action === 'skip') setRecommendations(p => p.filter(r => r.course_id !== courseId));
      if (action === 'like') {
        setRecommendations(p => p.map(r => r.course_id === courseId ? { ...r, topic_weight: (r.topic_weight || 1) + 0.2 } : r));
      }
    }
    setTimeout(() => setFeedbackPending(null), 300);
  };

  const progressPercent = Math.round((COMPLETED_MINUTES / DAILY_TARGET_MINUTES) * 100);
  const circumference = 2 * Math.PI * 54;
  const strokeDashoffset = circumference - (progressPercent / 100) * circumference;

  return (
    <div className="dashboard-page page-container">

      {/* ── Top Bento Grid: Smart Focus + Progress Ring ───── */}
      <div className="top-bento bento-grid" style={{ gridTemplateColumns: '1fr 200px' }}>

        {/* Daily Smart Focus — Bento carousel */}
        <div className="bento-card smart-focus-card">
          <div className="focus-header">
            <div>
              <span className="badge badge-accent">Today</span>
              <h2 className="focus-title">Daily focus</h2>
              <p className="focus-kicker">Short tasks picked for steady progress.</p>
            </div>
            <button type="button" className="btn-secondary" onClick={() => setShowExplanation(!showExplanation)}>
              {showExplanation ? 'Hide explanation' : 'Why these?'}
            </button>
          </div>

          <div className="focus-carousel">
            {SMART_FOCUS_ITEMS.map((item, i) => (
              <motion.div
                key={i}
                className="focus-item bento-card"
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.99 }}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.06 }}
              >
                <div className="focus-item-icon" aria-hidden>
                  {item.label}
                </div>
                <div className="focus-item-info">
                  <span className="focus-item-type">{item.type}</span>
                  <span className="focus-item-title">{item.title}</span>
                  <span className="focus-item-duration">{item.duration}</span>
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        {/* 360° Progress Ring */}
        <div className="bento-card progress-ring-card">
          <span className="ring-label">Daily Target</span>
          <div className="progress-ring-container">
            <svg viewBox="0 0 120 120" className="progress-ring-svg">
              <circle cx="60" cy="60" r="54" className="ring-bg" />
              <motion.circle
                cx="60" cy="60" r="54"
                className="ring-fill"
                strokeDasharray={circumference}
                initial={{ strokeDashoffset: circumference }}
                animate={{ strokeDashoffset }}
                transition={{ duration: 1.2, ease: 'easeOut', delay: 0.3 }}
              />
            </svg>
            <div className="ring-center-text">
              <span className="ring-value">{COMPLETED_MINUTES}</span>
              <span className="ring-unit">min</span>
            </div>
          </div>
          <span className="ring-remaining">{DAILY_TARGET_MINUTES - COMPLETED_MINUTES} min left to hit today&apos;s target</span>
        </div>
      </div>

      {/* ── Claude Explanation Panel ──────────────────────── */}
      <AnimatePresence>
        {showExplanation && (
          <motion.div
            className="explanation-panel bento-card"
            initial={{ opacity: 0, height: 0, marginTop: 0 }}
            animate={{ opacity: 1, height: 'auto', marginTop: 16 }}
            exit={{ opacity: 0, height: 0, marginTop: 0 }}
          >
            <div className="explanation-header">
              <span className="badge badge-accent">How we rank</span>
              {isStreaming && <span className="streaming-dot animate-pulse">Streaming...</span>}
            </div>
            <div className="explanation-text">
              {explanationText || "These courses were selected based on your skill assessment, learning goals, and interaction history. Our TF-IDF similarity engine matched your profile tags against course descriptions and skills, then re-ranked results using your real-time feedback weights and recency factors. Courses you have liked boost similar topics; courses you have skipped reduce their category weight."}
              {isStreaming && <span className="typewriter-cursor" />}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Section Header ───────────────────────────────── */}
      <div className="section-header">
        <h2>Recommended for you</h2>
        <p className="section-subtitle">Ranked from your profile and feedback. Like or skip to tune what comes next.</p>
      </div>

      {/* ── Course Bento Grid ────────────────────────────── */}
      {loading ? (
        <div className="bento-grid bento-grid-3">
          {[...Array(6)].map((_, i) => <div key={i} className="skeleton-card skeleton" />)}
        </div>
      ) : (
        <LayoutGroup>
          <motion.div className="bento-grid bento-grid-3" layout>
            <AnimatePresence>
              {recommendations.map((rec, idx) => (
                <motion.div
                  key={rec.course_id}
                  className="bento-card course-card"
                  layout
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.9, x: 80 }}
                  transition={{ type: 'spring', stiffness: 350, damping: 30, delay: idx * 0.04 }}
                  id={`course-card-${idx}`}
                >
                  {/* Top row: difficulty + score */}
                  <div className="card-top-row">
                    <span className={`badge ${getDifficultyBadge(rec.difficulty)}`}>
                      {rec.difficulty || 'Mixed'}
                    </span>
                    <div className="card-score">
                      <span className="score-value">{((rec.final_score || rec.similarity_score || 0) * 100).toFixed(0)}%</span>
                      <span className="score-label">match</span>
                    </div>
                  </div>

                  <h3 className="card-title">{rec.course_name}</h3>
                  {rec.university && <p className="card-university">{rec.university}</p>}

                  {/* Explainable AI — "Why this?" badge */}
                  <div className="explainable-badges">
                    <span className="badge badge-reason">
                      {getReasonText(rec, user)}
                    </span>
                    {rec.trending && <span className="badge badge-trending">Trending</span>}
                  </div>

                  {/* Rating */}
                  <div className="card-rating">
                    <span className="stars">{'★'.repeat(Math.round(rec.rating || 0))}</span>
                    <span className="rating-num">{rec.rating?.toFixed(1) || 'N/A'}</span>
                  </div>

                  {/* Skills pills */}
                  {rec.skills && (
                    <div className="skills-container">
                      {rec.skills.split(',').slice(0, 3).map(skill => (
                        <span key={skill} className="skill-pill">{skill.trim()}</span>
                      ))}
                    </div>
                  )}

                  {/* Score bars */}
                  <div className="score-breakdown">
                    <div className="score-item">
                      <span className="score-item-label">Similarity</span>
                      <div className="score-bar"><div className="score-bar-fill" style={{ width: `${(rec.similarity_score || 0) * 100}%` }} /></div>
                    </div>
                    <div className="score-item">
                      <span className="score-item-label">Weight</span>
                      <div className="score-bar"><div className="score-bar-fill pref" style={{ width: `${Math.min((rec.topic_weight || 1) / 3 * 100, 100)}%` }} /></div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="card-actions">
                    <motion.button type="button" className="action-btn like-btn" onClick={() => handleFeedback(rec.course_id, 'like')} whileTap={{ scale: 0.98 }} disabled={feedbackPending === rec.course_id} id={`like-${idx}`}>
                      Like
                    </motion.button>
                    <motion.button type="button" className="action-btn save-btn" onClick={() => handleFeedback(rec.course_id, 'save')} whileTap={{ scale: 0.98 }} disabled={feedbackPending === rec.course_id} id={`save-${idx}`}>
                      Save
                    </motion.button>
                    <motion.button type="button" className="action-btn skip-btn" onClick={() => handleFeedback(rec.course_id, 'skip')} whileTap={{ scale: 0.98 }} disabled={feedbackPending === rec.course_id} id={`skip-${idx}`}>
                      Skip
                    </motion.button>
                  </div>

                  {/* "Why am I seeing this?" */}
                  <button className="why-link" onClick={() => setWhyModal(rec)} id={`why-${idx}`}>
                    Why am I seeing this?
                  </button>
                </motion.div>
              ))}
            </AnimatePresence>
          </motion.div>
        </LayoutGroup>
      )}

      {/* ── "Why am I seeing this?" Modal ────────────────── */}
      <AnimatePresence>
        {whyModal && (
          <motion.div className="why-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setWhyModal(null)}>
            <motion.div className="why-modal bento-card" initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.9, opacity: 0 }} onClick={e => e.stopPropagation()}>
              <h3>Why "{whyModal.course_name}"?</h3>
              <div className="why-data">
                <div className="why-row"><span className="why-label">Similarity Score</span><span className="why-val">{((whyModal.similarity_score || 0) * 100).toFixed(1)}%</span></div>
                <div className="why-row"><span className="why-label">Topic Weight</span><span className="why-val">{(whyModal.topic_weight || 1).toFixed(2)}x</span></div>
                <div className="why-row"><span className="why-label">Recency Factor</span><span className="why-val">{(whyModal.recency_factor || 1).toFixed(2)}</span></div>
                <div className="why-row total"><span className="why-label">Final Score</span><span className="why-val">{((whyModal.final_score || 0) * 100).toFixed(1)}%</span></div>
              </div>
              <p className="why-explain">This course matched {((whyModal.similarity_score || 0) * 100).toFixed(0)}% of your skill profile via TF-IDF cosine similarity. Your topic weight of {(whyModal.topic_weight || 1).toFixed(2)}x reflects your recent feedback on related topics.</p>
              <div className="why-actions">
                <button className="btn-ghost" onClick={() => { handleFeedback(whyModal.course_id, 'skip'); setWhyModal(null); }}>
                  Show me less of this
                </button>
                <button className="btn-primary" onClick={() => setWhyModal(null)}>Got it</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Floating AI Chat Button ──────────────────────── */}
      <motion.button
        type="button"
        className="fab fab--icon"
        onClick={() => navigate('/chat')}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.96 }}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35 }}
        id="fab-chat"
        title="Open assistant"
        aria-label="Open assistant"
      >
        <FabChatIcon />
      </motion.button>
    </div>
  );
}

function getDifficultyBadge(d) {
  if (d === 'Beginner') return 'badge-success';
  if (d === 'Intermediate') return 'badge-warning';
  if (d === 'Advanced') return 'badge-muted';
  return 'badge-accent';
}

function FabChatIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
    </svg>
  );
}

function getReasonText(rec, user) {
  const score = ((rec.similarity_score || 0) * 100).toFixed(0);
  if (rec.topic_weight > 1.2) return `Boosted — you liked similar topics (+${((rec.topic_weight - 1) * 100).toFixed(0)}%)`;
  if (score > 80) return `${score}% match with your skill profile`;
  if (user.goal) return `Matches your goal: ${user.goal}`;
  return `Recommended based on your quiz answers`;
}

function getMockRecommendations() {
  return [
    { course_id: '1', course_name: 'Python for Everybody', university: 'University of Michigan', difficulty: 'Beginner', rating: 4.8, skills: 'Python, Programming, Data Structures', similarity_score: 0.92, topic_weight: 1.4, recency_factor: 1.0, final_score: 0.92, trending: false },
    { course_id: '2', course_name: 'Machine Learning', university: 'Stanford University', difficulty: 'Intermediate', rating: 4.9, skills: 'Machine Learning, Python, Statistics', similarity_score: 0.88, topic_weight: 1.0, recency_factor: 1.0, final_score: 0.88, trending: true },
    { course_id: '3', course_name: 'Deep Learning Specialization', university: 'DeepLearning.AI', difficulty: 'Advanced', rating: 4.9, skills: 'Deep Learning, Neural Networks, TensorFlow', similarity_score: 0.85, topic_weight: 1.0, recency_factor: 1.0, final_score: 0.85 },
    { course_id: '4', course_name: 'SQL for Data Science', university: 'UC Davis', difficulty: 'Beginner', rating: 4.6, skills: 'SQL, Database, Data Analysis', similarity_score: 0.78, topic_weight: 1.0, recency_factor: 1.0, final_score: 0.78 },
    { course_id: '5', course_name: 'Statistics with Python', university: 'University of Michigan', difficulty: 'Intermediate', rating: 4.5, skills: 'Statistics, Python, Data Analysis', similarity_score: 0.75, topic_weight: 1.0, recency_factor: 1.0, final_score: 0.75 },
    { course_id: '6', course_name: 'Data Visualization with Tableau', university: 'UC Davis', difficulty: 'Beginner', rating: 4.5, skills: 'Tableau, Data Visualization, Dashboard', similarity_score: 0.71, topic_weight: 1.0, recency_factor: 1.0, final_score: 0.71 },
  ];
}

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { createUser, submitOnboarding } from '../services/api';
import './OnboardingPage.css';

const QUESTIONS = [
  {
    id: 1,
    text: "What's your current experience level?",
    type: 'single',
    options: [
      { label: 'Complete Beginner', desc: 'Never coded before' },
      { label: 'Some Experience', desc: '1–6 months of practice' },
      { label: 'Intermediate', desc: '6+ months, built projects' },
      { label: 'Advanced', desc: 'Professional experience' },
    ],
  },
  {
    id: 2,
    text: 'Which area interests you most?',
    type: 'single',
    options: [
      { label: 'Data Science & ML' },
      { label: 'Web Development' },
      { label: 'Business & Management' },
      { label: 'Computer Science fundamentals' },
      { label: 'Cloud & DevOps' },
    ],
  },
  {
    id: 3,
    text: "What's your primary learning goal?",
    type: 'single',
    options: [
      { label: 'Career change', desc: 'Transition into tech' },
      { label: 'Skill upgrade', desc: 'Level up in your current role' },
      { label: 'Academic learning', desc: 'University or research' },
      { label: 'Personal interest', desc: 'Hobby or curiosity' },
    ],
  },
  {
    id: 4,
    text: 'How much time can you dedicate per week?',
    type: 'single',
    options: [
      { label: '1-3 hours', desc: 'Casual pace' },
      { label: '3-5 hours', desc: 'Moderate commitment' },
      { label: '5-10 hours', desc: 'Focused learning' },
      { label: '10+ hours', desc: 'Intensive schedule' },
    ],
  },
  {
    id: 5,
    text: 'Which skills do you want to learn?',
    type: 'multi',
    options: [
      { label: 'Python' },
      { label: 'SQL & Databases' },
      { label: 'Machine Learning' },
      { label: 'JavaScript / React' },
      { label: 'Data Analysis' },
      { label: 'Project Management' },
    ],
  },
];

export default function OnboardingPage({ onComplete }) {
  const [step, setStep] = useState('welcome');
  const [currentQ, setCurrentQ] = useState(0);
  const [answers, setAnswers] = useState({});
  const [multiSelect, setMultiSelect] = useState([]);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [backendWarning] = useState('');
  const [learningMode, setLearningMode] = useState('gamified');

  const progress = ((currentQ + 1) / QUESTIONS.length) * 100;

  const handleAnswer = (option) => {
    const q = QUESTIONS[currentQ];
    if (q.type === 'multi') return; // multi handled separately

    setAnswers(prev => ({ ...prev, [q.id]: option.label }));
    if (currentQ < QUESTIONS.length - 1) setCurrentQ(p => p + 1);
    else handleSubmit({ ...answers, [q.id]: option.label });
  };

  const handleMultiToggle = (label) => {
    setMultiSelect(prev => prev.includes(label) ? prev.filter(l => l !== label) : [...prev, label]);
  };

  const handleMultiSubmit = () => {
    const q = QUESTIONS[currentQ];
    setAnswers(prev => ({ ...prev, [q.id]: multiSelect.join(', ') }));
    handleSubmit({ ...answers, [q.id]: multiSelect.join(', ') });
  };

  const handleSubmit = async (finalAnswers) => {
    setStep('creating');
    setError('');
    try {
      const user = await createUser({
        email, name, skill_tags: [],
        goal: finalAnswers[3] || '', experience_level: finalAnswers[1] || '',
        weekly_hours: finalAnswers[4] === '10+ hours' ? 12 : finalAnswers[4] === '5-10 hours' ? 7 : finalAnswers[4] === '3-5 hours' ? 4 : 2,
      });
      const quizAnswers = Object.entries(finalAnswers).map(([qId, answer]) => ({ question_id: parseInt(qId), answer, skill_tags: [] }));
      await submitOnboarding({ user_id: user.id, answers: quizAnswers });
      onComplete({ ...user, learningMode });
    } catch (err) {
      // Distinguish between network errors and server errors
      const isNetworkError = !err.response;
      const safeId = `demo-${String(email || name || 'user').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
      const mockUser = { id: safeId, email, name, skill_tags: Object.values(finalAnswers), goal: finalAnswers[3] || '', experience_level: finalAnswers[1] || '', weekly_hours: 5, learningMode, isDemo: true };

      if (isNetworkError) {
        // Backend completely unreachable — fall back to demo mode with a warning
        console.warn('Backend unavailable — using demo mode');
        onComplete(mockUser);
      } else {
        // Server responded with an error — let user retry
        setStep('quiz');
        setCurrentQ(QUESTIONS.length - 1);
        setError(
          err.response?.data?.detail
            || `Server error (${err.response?.status}). Please try again.`
        );
      }
    }
  };

  /* ── Welcome Step ──────────────────────────────────────── */
  if (step === 'welcome') {
    return (
      <div className="onboarding-page">
        <motion.div
          className="welcome-card glass-card"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
        >
          <h1>Welcome to LearnFlow</h1>
          <p className="welcome-subtitle">Tell us a bit about your background so we can shape course suggestions and pacing.</p>

          <div className="welcome-form">
            <input type="text" placeholder="Your name" value={name} onChange={e => setName(e.target.value)} className="onboarding-input" id="onboarding-name" />
            <input type="email" placeholder="Your email" value={email} onChange={e => setEmail(e.target.value)} className="onboarding-input" id="onboarding-email" />

            {/* Pacing & Preferences toggle */}
            <div className="mode-selector">
              <span className="mode-label">Learning Mode</span>
              <div className="mode-options">
                {[
                  { key: 'gamified', letter: 'G', label: 'Gamified', desc: 'Streaks and milestones' },
                  { key: 'professional', letter: 'P', label: 'Professional', desc: 'Credentials and jobs' },
                  { key: 'visual', letter: 'V', label: 'Visual', desc: 'Video-first learning' },
                ].map(m => (
                  <button
                    key={m.key}
                    className={`mode-btn ${learningMode === m.key ? 'active' : ''}`}
                    onClick={() => setLearningMode(m.key)}
                    type="button"
                  >
                    <span className="mode-btn-letter">{m.letter}</span>
                    <span className="mode-btn-label">{m.label}</span>
                    <span className="mode-btn-desc">{m.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            {error && <p className="error-text">{error}</p>}
            <button className="btn-primary start-btn" onClick={() => {
              if (!name.trim() || !email.trim()) { setError('Please fill in both fields'); return; }
              setError(''); setStep('quiz');
            }} id="start-quiz-btn">
              Start Skill Assessment →
            </button>
          </div>
          {backendWarning && <p className="error-text" style={{ color: 'var(--warning)' }}>{backendWarning}</p>}
          <p className="welcome-hint">Five questions — usually under three minutes.</p>
        </motion.div>
      </div>
    );
  }

  /* ── Creating Step ─────────────────────────────────────── */
  if (step === 'creating') {
    return (
      <div className="onboarding-page">
        <motion.div className="creating-card glass-card" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
          <div className="creating-spinner" />
          <h2>Building your learning profile...</h2>
          <p className="text-secondary">Matching your answers to course metadata and your stated goals.</p>
          <div className="creating-steps">
            <motion.div className="creating-step done" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>Assessment saved</motion.div>
            <motion.div className="creating-step done" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}>Topics inferred from responses</motion.div>
            <motion.div className="creating-step active" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.8 }}>Preparing your dashboard…</motion.div>
          </div>
        </motion.div>
      </div>
    );
  }

  /* ── Quiz Step ─────────────────────────────────────────── */
  const question = QUESTIONS[currentQ];

  return (
    <div className="onboarding-page">
      <div className="quiz-container">
        <div className="progress-bar-container">
          <span className="progress-step-label">Step {currentQ + 1} of {QUESTIONS.length}</span>
          <div className="progress-bar-track">
            <motion.div className="progress-bar-fill" initial={{ width: 0 }} animate={{ width: `${progress}%` }} transition={{ type: 'spring', stiffness: 120, damping: 22 }} />
          </div>
          <span className="progress-text">{Math.round(progress)}%</span>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={currentQ}
            className="question-card glass-card"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25 }}
          >
            <div className="question-step">Question {currentQ + 1}</div>
            <h2 className="question-text">{question.text}</h2>

            <div className="options-grid">
              {question.options.map((opt, idx) => {
                const isSelected = question.type === 'multi' && multiSelect.includes(opt.label);
                return (
                  <motion.button
                    key={opt.label}
                    type="button"
                    className={`option-btn ${isSelected ? 'selected' : ''}`}
                    onClick={() => question.type === 'multi' ? handleMultiToggle(opt.label) : handleAnswer(opt)}
                    whileTap={{ scale: 0.995 }}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.04 }}
                    id={`option-${question.id}-${idx}`}
                  >
                    <div className="option-content">
                      <span className="option-label">{opt.label}</span>
                      {opt.desc && <span className="option-desc">{opt.desc}</span>}
                    </div>
                    {isSelected && <span className="option-check" aria-hidden>✓</span>}
                  </motion.button>
                );
              })}
            </div>

            {question.type === 'multi' && (
              <button type="button" className="btn-primary multi-submit" onClick={handleMultiSubmit} disabled={multiSelect.length === 0} style={{ marginTop: 'var(--space-4)' }}>
                Continue ({multiSelect.length} selected)
              </button>
            )}
          </motion.div>
        </AnimatePresence>

        {currentQ > 0 && (
          <button type="button" className="back-btn" onClick={() => setCurrentQ((p) => p - 1)}>
            Back
          </button>
        )}
      </div>
    </div>
  );
}

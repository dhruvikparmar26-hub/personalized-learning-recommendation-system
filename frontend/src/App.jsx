import { BrowserRouter as Router, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import './index.css';
import './App.css';
import './styles/animations.css';

import AuthPage from './pages/AuthPage';
import OnboardingPage from './pages/OnboardingPage';
import DashboardPage from './pages/DashboardPage';
import ChatPage from './pages/ChatPage';
import LearningPathPage from './pages/LearningPathPage';

function App() {
  // FIX [ERROR_HANDLING] — corrupted localStorage JSON would crash the entire app
  const [user, setUser] = useState(() => {
    try {
      const saved = localStorage.getItem('lr_user');
      return saved ? JSON.parse(saved) : null;
    } catch {
      localStorage.removeItem('lr_user');
      return null;
    }
  });

  const handleLogin = (userData, token) => {
    setUser(userData);
    localStorage.setItem('lr_user', JSON.stringify(userData));
    localStorage.setItem('lr_token', token);
  };

  const handleUserSet = (userData) => {
    setUser(userData);
    localStorage.setItem('lr_user', JSON.stringify(userData));
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('lr_user');
    localStorage.removeItem('lr_token');
  };

  return (
    <Router>
      <div className="app-container">
        {user && <NavBar user={user} onLogout={handleLogout} />}
        <Routes>
          <Route path="/" element={user ? <Navigate to="/dashboard" /> : <Navigate to="/auth" />} />
          <Route path="/auth" element={user ? <Navigate to="/dashboard" /> : <AuthPage onLogin={handleLogin} />} />
          <Route path="/onboarding" element={user ? <OnboardingPage onComplete={handleUserSet} /> : <Navigate to="/auth" />} />
          <Route path="/dashboard" element={user ? <DashboardPage user={user} /> : <Navigate to="/auth" />} />
          <Route path="/chat" element={user ? <ChatPage user={user} /> : <Navigate to="/auth" />} />
          <Route path="/learning-path" element={user ? <LearningPathPage user={user} /> : <Navigate to="/auth" />} />
          {/* FIX [ROUTING] — catch-all 404 route for unknown paths */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </Router>
  );
}

function NavBar({ user, onLogout }) {
  const location = useLocation();
  const navigate = useNavigate();

  const initials = String(user?.name || 'U')
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  const links = [
    {
      path: '/dashboard',
      label: 'Dashboard',
      Icon: IconLayout,
    },
    {
      path: '/chat',
      label: 'Assistant',
      Icon: IconMessage,
    },
    {
      path: '/learning-path',
      label: 'Learning path',
      Icon: IconPath,
    },
  ];

  return (
    <nav className="app-nav" aria-label="Main">
      <div className="app-nav__brand-wrap">
        <button type="button" className="app-nav__brand" onClick={() => navigate('/dashboard')}>
          Learn<span className="app-nav__brand-accent">Flow</span>
        </button>
        <div className="app-nav__links">
          {links.map((link) => {
            const isActive = location.pathname === link.path;
            const { Icon } = link;
            return (
              <button
                key={link.path}
                type="button"
                className={`app-nav__link${isActive ? ' app-nav__link--active' : ''}`}
                onClick={() => navigate(link.path)}
                aria-current={isActive ? 'page' : undefined}
              >
                <Icon className="app-nav__link-icon" aria-hidden />
                {link.label}
              </button>
            );
          })}
        </div>
      </div>
      <div className="app-nav__user">
        <div className="app-nav__user-pill">
          <span className="app-nav__user-avatar" aria-hidden>
            {initials}
          </span>
          <span className="app-nav__user-name">{user.name}</span>
        </div>
        <button type="button" className="btn-ghost" onClick={onLogout}>
          Sign out
        </button>
      </div>
    </nav>
  );
}

function IconLayout({ className }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="9" rx="1" />
      <rect x="14" y="3" width="7" height="5" rx="1" />
      <rect x="14" y="12" width="7" height="9" rx="1" />
      <rect x="3" y="16" width="7" height="5" rx="1" />
    </svg>
  );
}

function IconMessage({ className }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
    </svg>
  );
}

function IconPath({ className }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="6" cy="6" r="3" />
      <circle cx="18" cy="18" r="3" />
      <path d="M8.59 13.51l6.83 3.98M15.41 6.51l-6.82 3.98" />
    </svg>
  );
}

export default App;

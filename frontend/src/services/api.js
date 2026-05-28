import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('lr_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Users ──────────────────────────────────────────────────
export const createUser = (userData) =>
  api.post('/users', userData).then((r) => r.data);

export const updateUser = (userId, updates) =>
  api.patch(`/users/${userId}`, updates).then((r) => r.data);

// ── Onboarding ─────────────────────────────────────────────
export const getOnboardingQuestions = () =>
  api.get('/onboarding/questions').then((r) => r.data);

export const submitOnboarding = (data) =>
  api.post('/onboarding/', data).then((r) => r.data);

// ── Recommendations ────────────────────────────────────────
export const getRecommendations = (userId, topN = 10) =>
  api.get(`/recommendations/${userId}?top_n=${topN}`).then((r) => r.data);

// ── Feedback ───────────────────────────────────────────────
export const submitFeedback = (data) =>
  api.post('/feedback/', data).then((r) => r.data);

// ── Learning Path ──────────────────────────────────────────
export const getLearningPath = (userId) =>
  api.get(`/learning-path/${userId}`).then((r) => r.data);

// ── Health ─────────────────────────────────────────────────
export const healthCheck = () =>
  api.get('/health').then((r) => r.data);

// ── SSE URLs (for EventSource) ─────────────────────────────
export const getSSERecommendationsUrl = (userId) =>
  `${API_BASE}/stream/recommendations/${userId}`;

export const getSSEExplanationUrl = (userId) =>
  `${API_BASE}/stream/explanation/${userId}`;

export const getSSELearningPathUrl = (userId) =>
  `${API_BASE}/stream/learning-path/${userId}`;

// ── WebSocket URL ──────────────────────────────────────────
export const getWebSocketUrl = (userId) => {
  const wsBase = API_BASE.replace('http', 'ws').replace('/api', '');
  return `${wsBase}/api/chat/${userId}`;
};

export default api;

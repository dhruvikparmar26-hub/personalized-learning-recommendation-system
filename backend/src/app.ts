import express from 'express';
import cors from 'cors';
import { z } from 'zod';

import { onboardingQuestions } from './data/questions.js';
import { buildExplanation, buildLearningPath, computeRecommendations, getWeightDelta, refreshRecommendationsForUser } from './lib/recommender.js';
import { broadcastUpdate, registerSseClient, sendSseEvent, sseStats, startTextStream } from './lib/realtime.js';
import { store } from './lib/store.js';

const userInputSchema = z.object({
    email: z.string().email(),
    name: z.string().min(1),
    skill_tags: z.array(z.string()).optional().default([]),
    goal: z.string().optional().default(''),
    experience_level: z.string().optional().default('Not specified'),
    weekly_hours: z.number().int().min(1).max(40).optional().default(5),
});

const userUpdateSchema = userInputSchema.partial().extend({
    email: z.string().email().optional(),
    weekly_hours: z.number().int().min(1).max(40).optional(),
});

const onboardingSchema = z.object({
    user_id: z.string().min(1),
    answers: z.array(z.object({
        question_id: z.number().int(),
        answer: z.string(),
        skill_tags: z.array(z.string()).optional().default([]),
    })).default([]),
});

const feedbackSchema = z.object({
    user_id: z.string().min(1),
    course_id: z.string().min(1),
    action: z.enum(['like', 'skip', 'save', 'complete']),
});

function parseOrigins(raw: string | undefined): string[] {
    if (!raw) {
        return ['http://localhost:5173', 'http://localhost:3000'];
    }

    try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
            return parsed.map(String);
        }
    } catch {
        // fall through to comma separated values
    }

    return raw.split(',').map((value) => value.trim()).filter(Boolean);
}

function normalizeSkill(skill: string): string {
    return skill.trim().toLowerCase();
}

function deriveSkillsFromAnswers(answers: Array<{ question_id: number; answer: string; skill_tags?: string[] }>): string[] {
    const skillSet = new Set<string>();

    for (const answer of answers) {
        answer.skill_tags?.forEach((skill) => skillSet.add(normalizeSkill(skill)));

        if (answer.question_id === 2) {
            const value = answer.answer.toLowerCase();
            if (value.includes('data') || value.includes('ml')) skillSet.add('machine learning');
            if (value.includes('web')) skillSet.add('react');
            if (value.includes('cloud')) skillSet.add('cloud');
            if (value.includes('business')) skillSet.add('project management');
        }

        if (answer.question_id === 5) {
            answer.answer.split(',').forEach((skill) => skillSet.add(normalizeSkill(skill)));
        }
    }

    return [...skillSet].filter(Boolean);
}

function deriveExperience(answers: Array<{ question_id: number; answer: string }>): string {
    return answers.find((item) => item.question_id === 1)?.answer ?? 'Not specified';
}

function deriveGoal(answers: Array<{ question_id: number; answer: string }>): string {
    return answers.find((item) => item.question_id === 3)?.answer ?? '';
}

function deriveWeeklyHours(answers: Array<{ question_id: number; answer: string }>): number {
    const answer = answers.find((item) => item.question_id === 4)?.answer ?? '3-5 hours';
    if (answer.includes('10+')) return 12;
    if (answer.includes('5-10')) return 7;
    if (answer.includes('3-5')) return 4;
    return 2;
}

export function createApp() {
    const app = express();
    const allowedOrigins = parseOrigins(process.env.CORS_ORIGINS);

    app.use(cors({ origin: allowedOrigins, credentials: true }));
    app.use(express.json({ limit: '1mb' }));

    app.get('/api/health', (_req, res) => {
        const stats = sseStats();
        res.json({
            status: 'healthy',
            redis: 'disabled',
            model_loaded: true,
            active_connections: stats.wsConnections + stats.sseConnections,
            active_users: store.listUsers().length,
            stack: 'node-typescript',
        });
    });

    app.post('/api/users', (req, res) => {
        const parsed = userInputSchema.safeParse(req.body);
        if (!parsed.success) {
            return res.status(400).json({ detail: parsed.error.flatten().formErrors.join(', ') || 'Invalid user payload' });
        }

        const user = store.upsertUser(parsed.data);
        return res.status(201).json(user);
    });

    app.patch('/api/users/:userId', (req, res) => {
        const parsed = userUpdateSchema.safeParse(req.body);
        if (!parsed.success) {
            return res.status(400).json({ detail: parsed.error.flatten().formErrors.join(', ') || 'Invalid user update payload' });
        }

        const updated = store.updateUser(req.params.userId, parsed.data);
        if (!updated) {
            return res.status(404).json({ detail: 'User not found' });
        }

        return res.json(updated);
    });

    app.get('/api/onboarding/questions', (_req, res) => {
        res.json(onboardingQuestions);
    });

    app.post('/api/onboarding', (req, res) => {
        const parsed = onboardingSchema.safeParse(req.body);
        if (!parsed.success) {
            return res.status(400).json({ detail: parsed.error.flatten().formErrors.join(', ') || 'Invalid onboarding payload' });
        }

        const { user_id: userId, answers } = parsed.data;
        const current = store.getUser(userId) ?? store.ensureDemoUser(userId);
        const skill_tags = deriveSkillsFromAnswers(answers);
        const goal = deriveGoal(answers);
        const experience_level = deriveExperience(answers);
        const weekly_hours = deriveWeeklyHours(answers);

        const updated = store.updateUser(userId, {
            skill_tags: skill_tags.length ? skill_tags : current.skill_tags,
            goal: goal || current.goal,
            experience_level: experience_level || current.experience_level,
            weekly_hours,
        }) ?? current;

        store.saveOnboardingAnswers(userId, answers);
        store.clearRecommendationCache(userId);
        const recommendations = computeRecommendations(updated, 10);

        return res.json({ user_id: userId, saved: true, user: updated, recommendations });
    });

    app.get('/api/recommendations/:userId', (req, res) => {
        const topN = Number(req.query.top_n ?? 10);
        const user = store.getUser(req.params.userId) ?? store.ensureDemoUser(req.params.userId);
        const recommendations = computeRecommendations(user, Number.isFinite(topN) && topN > 0 ? topN : 10);
        res.json({ user_id: user.id, recommendations });
    });

    app.get('/api/stream/recommendations/:userId', (req, res) => {
        const user = store.getUser(req.params.userId) ?? store.ensureDemoUser(req.params.userId);

        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache, no-transform');
        res.setHeader('Connection', 'keep-alive');
        res.flushHeaders?.();

        registerSseClient(user.id, res);
        const initial = computeRecommendations(user, 10);
        sendSseEvent(res, { type: 'initial', recommendations: initial });

        const heartbeat = setInterval(() => {
            try {
                sendSseEvent(res, { type: 'heartbeat', ts: Date.now() });
            } catch {
                clearInterval(heartbeat);
            }
        }, 25_000);

        req.on('close', () => clearInterval(heartbeat));
    });

    app.get('/api/stream/explanation/:userId', (req, res) => {
        const user = store.getUser(req.params.userId) ?? store.ensureDemoUser(req.params.userId);
        const recommendations = store.getRecommendations(user.id) ?? computeRecommendations(user, 5);
        const text = buildExplanation(user, recommendations);

        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache, no-transform');
        res.setHeader('Connection', 'keep-alive');
        res.flushHeaders?.();
        startTextStream(res, text);
    });

    app.get('/api/stream/learning-path/:userId', (req, res) => {
        const user = store.getUser(req.params.userId) ?? store.ensureDemoUser(req.params.userId);
        const recommendations = store.getRecommendations(user.id) ?? computeRecommendations(user, 5);
        const path = buildLearningPath(user, recommendations);
        const text = path.map((module) => `${module.name}: ${module.focus}`).join(' • ');

        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache, no-transform');
        res.setHeader('Connection', 'keep-alive');
        res.flushHeaders?.();
        startTextStream(res, text);
    });

    app.get('/api/learning-path/:userId', (req, res) => {
        const user = store.getUser(req.params.userId) ?? store.ensureDemoUser(req.params.userId);
        const recommendations = store.getRecommendations(user.id) ?? computeRecommendations(user, 5);
        const path = buildLearningPath(user, recommendations);

        res.json({ user_id: user.id, path, exists: true });
    });

    app.post('/api/feedback', (req, res) => {
        const parsed = feedbackSchema.safeParse(req.body);
        if (!parsed.success) {
            return res.status(400).json({ detail: parsed.error.flatten().formErrors.join(', ') || 'Invalid feedback payload' });
        }

        const payload = parsed.data;
        const user = store.getUser(payload.user_id) ?? store.ensureDemoUser(payload.user_id);
        const recs = store.getRecommendations(user.id) ?? computeRecommendations(user, 10);
        const course = recs.find((item) => item.course_id === payload.course_id);

        if (!course) {
            return res.status(404).json({ detail: 'Course not found' });
        }

        const feedbackEntry = {
            id: crypto.randomUUID(),
            user_id: payload.user_id,
            course_id: payload.course_id,
            action: payload.action,
            timestamp: new Date().toISOString(),
        };

        store.addFeedback(payload.user_id, feedbackEntry);

        const delta = getWeightDelta(payload.action);
        for (const skill of course.skills.split(',').map((value) => value.trim().toLowerCase()).filter(Boolean)) {
            store.adjustTopicWeight(payload.user_id, skill, delta);
        }

        const updated = refreshRecommendationsForUser(payload.user_id, 10);
        broadcastUpdate(payload.user_id, { type: 'update', recommendations: updated });

        res.json({
            id: feedbackEntry.id,
            user_id: feedbackEntry.user_id,
            course_id: feedbackEntry.course_id,
            action: feedbackEntry.action,
            timestamp: feedbackEntry.timestamp,
            message: 'Feedback recorded. Recommendations will update in real-time.',
        });
    });

    app.get('/api/feedback', (_req, res) => {
        res.status(405).json({ detail: 'Method not allowed' });
    });

    app.post('/api/onboarding/', (req, res) => app._router.handle(req, res, () => undefined));

    return app;
}
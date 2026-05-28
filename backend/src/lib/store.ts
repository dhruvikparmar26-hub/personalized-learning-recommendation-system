import { randomUUID } from 'node:crypto';

import type { CourseRecord } from '../data/catalog.js';

export type UserRecord = {
    id: string;
    email: string;
    name: string;
    skill_tags: string[];
    goal: string;
    experience_level: string;
    weekly_hours: number;
    created_at: string;
    updated_at: string;
};

export type FeedbackAction = 'like' | 'skip' | 'save' | 'complete';

export type FeedbackRecord = {
    id: string;
    user_id: string;
    course_id: string;
    action: FeedbackAction;
    timestamp: string;
};

export type RecommendationRecord = CourseRecord & {
    similarity_score: number;
    final_score: number;
    topic_weight: number;
    reason: string;
};

export type LearningModule = {
    name: string;
    duration: string;
    status: 'completed' | 'in-progress' | 'not-started';
    progress: number;
    focus: string;
    time: string;
    difficulty: string;
    skillGain: string;
};

export type OnboardingAnswer = {
    question_id: number;
    answer: string;
    skill_tags: string[];
};

class BackendStore {
    private readonly users = new Map<string, UserRecord>();

    private readonly usersByEmail = new Map<string, string>();

    private readonly feedback = new Map<string, FeedbackRecord[]>();

    private readonly topicWeights = new Map<string, Map<string, number>>();

    private readonly recommendationCache = new Map<string, RecommendationRecord[]>();

    private readonly learningPathCache = new Map<string, LearningModule[]>();

    private readonly onboardingAnswers = new Map<string, OnboardingAnswer[]>();

    listUsers(): UserRecord[] {
        return [...this.users.values()];
    }

    countUsers(): number {
        return this.users.size;
    }

    getUser(userId: string): UserRecord | undefined {
        return this.users.get(userId);
    }

    getUserByEmail(email: string): UserRecord | undefined {
        const userId = this.usersByEmail.get(email.toLowerCase());
        return userId ? this.users.get(userId) : undefined;
    }

    ensureDemoUser(userId: string): UserRecord {
        const existing = this.users.get(userId);
        if (existing) {
            return existing;
        }

        const demoUser: UserRecord = {
            id: userId,
            email: `${userId}@demo.local`,
            name: 'Demo Learner',
            skill_tags: ['python', 'sql', 'javascript'],
            goal: 'Career change',
            experience_level: 'Intermediate',
            weekly_hours: 5,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
        };

        this.users.set(userId, demoUser);
        this.usersByEmail.set(demoUser.email.toLowerCase(), userId);
        return demoUser;
    }

    upsertUser(input: {
        id?: string;
        email: string;
        name: string;
        skill_tags?: string[];
        goal?: string;
        experience_level?: string;
        weekly_hours?: number;
    }): UserRecord {
        const now = new Date().toISOString();
        const emailKey = input.email.toLowerCase();
        const existingByEmail = this.usersByEmail.get(emailKey);
        const id = input.id ?? existingByEmail ?? randomUUID();
        const existing = this.users.get(id);

        const user: UserRecord = {
            id,
            email: input.email,
            name: input.name,
            skill_tags: input.skill_tags?.length ? [...new Set(input.skill_tags.map((s) => s.trim().toLowerCase()).filter(Boolean))] : existing?.skill_tags ?? [],
            goal: input.goal ?? existing?.goal ?? '',
            experience_level: input.experience_level ?? existing?.experience_level ?? 'Not specified',
            weekly_hours: input.weekly_hours ?? existing?.weekly_hours ?? 5,
            created_at: existing?.created_at ?? now,
            updated_at: now,
        };

        this.users.set(id, user);
        this.usersByEmail.set(emailKey, id);
        return user;
    }

    updateUser(userId: string, updates: Partial<Pick<UserRecord, 'name' | 'skill_tags' | 'goal' | 'experience_level' | 'weekly_hours' | 'email'>>): UserRecord | undefined {
        const existing = this.users.get(userId);
        if (!existing) {
            return undefined;
        }

        const updated: UserRecord = {
            ...existing,
            ...updates,
            skill_tags: updates.skill_tags ? [...new Set(updates.skill_tags.map((s) => s.trim().toLowerCase()).filter(Boolean))] : existing.skill_tags,
            email: updates.email ?? existing.email,
            updated_at: new Date().toISOString(),
        };

        this.users.set(userId, updated);
        this.usersByEmail.set(updated.email.toLowerCase(), userId);
        return updated;
    }

    saveOnboardingAnswers(userId: string, answers: OnboardingAnswer[]): void {
        this.onboardingAnswers.set(userId, answers);
    }

    getOnboardingAnswers(userId: string): OnboardingAnswer[] | undefined {
        return this.onboardingAnswers.get(userId);
    }

    addFeedback(userId: string, feedback: FeedbackRecord): void {
        const list = this.feedback.get(userId) ?? [];
        list.unshift(feedback);
        this.feedback.set(userId, list.slice(0, 100));
    }

    getFeedback(userId: string): FeedbackRecord[] {
        return this.feedback.get(userId) ?? [];
    }

    getTopicWeights(userId: string): Record<string, number> {
        const weights = this.topicWeights.get(userId);
        if (!weights) {
            return {};
        }

        return Object.fromEntries(weights.entries());
    }

    getTopicWeight(userId: string, topic: string): number {
        return this.topicWeights.get(userId)?.get(topic) ?? 1;
    }

    adjustTopicWeight(userId: string, topic: string, delta: number): number {
        const key = topic.trim().toLowerCase();
        if (!key) {
            return 1;
        }

        const userWeights = this.topicWeights.get(userId) ?? new Map<string, number>();
        const current = userWeights.get(key) ?? 1;
        const next = clamp(current + delta, 0.1, 3);
        userWeights.set(key, next);
        this.topicWeights.set(userId, userWeights);
        return next;
    }

    setRecommendations(userId: string, recommendations: RecommendationRecord[]): void {
        this.recommendationCache.set(userId, recommendations);
    }

    getRecommendations(userId: string): RecommendationRecord[] | undefined {
        return this.recommendationCache.get(userId);
    }

    setLearningPath(userId: string, path: LearningModule[]): void {
        this.learningPathCache.set(userId, path);
    }

    getLearningPath(userId: string): LearningModule[] | undefined {
        return this.learningPathCache.get(userId);
    }

    clearRecommendationCache(userId: string): void {
        this.recommendationCache.delete(userId);
    }

    countFeedbackEntries(): number {
        return [...this.feedback.values()].reduce((sum, items) => sum + items.length, 0);
    }

    countCachedRecommendations(): number {
        return this.recommendationCache.size;
    }

    countCachedLearningPaths(): number {
        return this.learningPathCache.size;
    }
}

export function clamp(value: number, min: number, max: number): number {
    return Math.min(max, Math.max(min, value));
}

export const store = new BackendStore();
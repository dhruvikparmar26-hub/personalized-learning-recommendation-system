import { COURSE_CATALOG, type CourseRecord } from '../data/catalog.js';
import { clamp, store, type LearningModule, type RecommendationRecord, type UserRecord } from './store.js';

const ACTION_DELTAS: Record<string, number> = {
    like: 0.2,
    skip: -0.3,
    complete: 0.5,
    save: 0.15,
};

export function getCourseSkills(course: CourseRecord): string[] {
    return course.skills
        .split(',')
        .map((skill) => skill.trim().toLowerCase())
        .filter(Boolean);
}

export function getWeightDelta(action: string): number {
    return ACTION_DELTAS[action] ?? 0;
}

export function computeRecommendations(user: UserRecord, topN = 10): RecommendationRecord[] {
    const weights = store.getTopicWeights(user.id);
    const normalizedGoal = user.goal.toLowerCase();
    const normalizedExperience = user.experience_level.toLowerCase();

    const ranked = COURSE_CATALOG.map((course) => {
        const skills = getCourseSkills(course);
        const matchedSkills = skills.filter((skill) => user.skill_tags.includes(skill));
        const topicWeight = matchedSkills.length
            ? matchedSkills.reduce((sum, skill) => sum + (weights[skill] ?? 1), 0) / matchedSkills.length
            : 1;

        const goalMatches = [normalizedGoal, 'career'].some((term) =>
            term && (course.description.toLowerCase().includes(term) || course.skills.toLowerCase().includes(term))
        );

        const experiencePenalty = experiencePenaltyFor(course.difficulty, normalizedExperience);
        const similarityBase = matchedSkills.length * 0.24 + (goalMatches ? 0.18 : 0) + (course.rating / 5) * 0.18 + (course.trending ? 0.1 : 0) - experiencePenalty;
        const similarity_score = clamp(similarityBase, 0, 1);
        const final_score = clamp(similarity_score * (0.7 + topicWeight * 0.3), 0, 1);
        const reason = buildReason(user, course, matchedSkills, goalMatches);

        return {
            ...course,
            similarity_score,
            final_score,
            topic_weight: Number(topicWeight.toFixed(2)),
            reason,
        } satisfies RecommendationRecord;
    });

    ranked.sort((left, right) => right.final_score - left.final_score || right.rating - left.rating);

    const topRecommendations = ranked.slice(0, topN).map((item) => ({
        ...item,
        final_score: Number(item.final_score.toFixed(4)),
        similarity_score: Number(item.similarity_score.toFixed(4)),
    }));

    store.setRecommendations(user.id, topRecommendations);
    return topRecommendations;
}

export function refreshRecommendationsForUser(userId: string, topN = 10): RecommendationRecord[] {
    const user = store.ensureDemoUser(userId);
    return computeRecommendations(user, topN);
}

export function buildLearningPath(user: UserRecord, recommendations: RecommendationRecord[]): LearningModule[] {
    const cached = store.getLearningPath(user.id);
    if (cached) {
        return cached;
    }

    const sequence = recommendations.slice(0, 5);
    const modules: LearningModule[] = sequence.map((course, index) => ({
        name: course.course_name,
        duration: `Days ${index * 5 + 1}-${index * 5 + 5}`,
        status: index === 0 ? 'completed' : index === 1 ? 'in-progress' : 'not-started',
        progress: index === 0 ? 100 : index === 1 ? 60 : 0,
        focus: course.description,
        time: `${Math.max(4, Math.round(course.rating * 2))} hrs`,
        difficulty: course.difficulty,
        skillGain: `+${Math.max(2, Math.round(course.final_score * 5))} ${primarySkillLabel(course)}`,
    }));

    while (modules.length < 5) {
        const fillerIndex = modules.length + 1;
        modules.push({
            name: `Learning milestone ${fillerIndex}`,
            duration: `Days ${fillerIndex * 5 - 4}-${fillerIndex * 5}`,
            status: 'not-started',
            progress: 0,
            focus: 'A guided step in your learning sequence.',
            time: '6 hrs',
            difficulty: 'Mixed',
            skillGain: '+2 Growth',
        });
    }

    store.setLearningPath(user.id, modules);
    return modules;
}

export function buildExplanation(user: UserRecord, recommendations: RecommendationRecord[]): string {
    const top = recommendations[0];
    const skillList = user.skill_tags.length ? user.skill_tags.join(', ') : 'general learning';

    if (!top) {
        return `We used your profile (${skillList}) to rank courses, then tuned the list with your feedback.`;
    }

    return [
        `These recommendations were ranked using your profile, skills, and recent feedback.`,
        `Your current strengths: ${skillList}.`,
        `Top match: ${top.course_name} because it aligns with ${top.skills}.`,
        `Liked courses raise related topic weights, and skipped courses reduce them.`,
    ].join(' ');
}

export function buildChatReply(user: UserRecord, message: string, recommendations: RecommendationRecord[]): string {
    const top = recommendations[0];
    const focus = top ? `I would start with ${top.course_name} because it has the strongest match score.` : 'I would start with a beginner-friendly course.';
    return [
        `You asked: "${message}"`,
        `Based on ${user.experience_level.toLowerCase()} level and your goal of ${user.goal || 'learning more'},`,
        focus,
        `If you want, I can also explain why specific courses appear on your dashboard.`,
    ].join(' ');
}

function buildReason(user: UserRecord, course: CourseRecord, matchedSkills: string[], goalMatches: boolean): string {
    if (matchedSkills.length > 0) {
        return `Matches your ${matchedSkills.slice(0, 2).join(' and ')} focus${goalMatches ? ' and learning goal' : ''}.`;
    }

    if (goalMatches) {
        return `Fits your stated learning goal.`;
    }

    return `${course.difficulty} course with strong rating and broad utility.`;
}

function primarySkillLabel(course: RecommendationRecord): string {
    const skill = course.skills.split(',')[0]?.trim() || 'skills';
    return skill.replace(/\b\w/g, (match) => match.toUpperCase());
}

function experiencePenaltyFor(difficulty: CourseRecord['difficulty'], experience: string): number {
    if (difficulty === 'Beginner') return 0;
    if (difficulty === 'Intermediate') return experience.includes('advanced') ? 0 : 0.05;
    if (difficulty === 'Advanced') return experience.includes('advanced') ? 0.05 : 0.15;
    return 0.02;
}
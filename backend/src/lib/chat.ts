import type WebSocket from 'ws';

import { buildChatReply } from './recommender.js';
import { registerWsClient } from './realtime.js';
import { store } from './store.js';
import { computeRecommendations } from './recommender.js';

export function attachChatSocket(userId: string, ws: WebSocket): void {
    const user = store.ensureDemoUser(userId);
    registerWsClient(userId, ws);

    ws.send(JSON.stringify({ type: 'connected', user_id: userId }));

    ws.on('message', (buffer) => {
        const text = buffer.toString();

        if (text.length > 10_000) {
            ws.send(JSON.stringify({ type: 'error', message: 'Message too long (max 10KB)' }));
            return;
        }

        let payload: { message?: string; history?: unknown[] };
        try {
            payload = JSON.parse(text) as { message?: string; history?: unknown[] };
        } catch {
            ws.send(JSON.stringify({ type: 'error', message: 'Invalid JSON' }));
            return;
        }

        const message = payload.message?.trim() ?? '';
        if (!message) {
            ws.send(JSON.stringify({ type: 'error', message: 'Empty message' }));
            return;
        }

        const recommendations = computeRecommendations(user, 5);
        const reply = buildChatReply(user, message, recommendations);
        const chunks = reply.match(/\S+\s*/g) ?? [reply];

        let index = 0;
        const timer = setInterval(() => {
            if (ws.readyState !== ws.OPEN) {
                clearInterval(timer);
                return;
            }

            if (index < chunks.length) {
                ws.send(JSON.stringify({ type: 'token', content: chunks[index] }));
                index += 1;
                return;
            }

            ws.send(JSON.stringify({ type: 'done', full_response: reply }));
            clearInterval(timer);
        }, 18);

        ws.once('close', () => clearInterval(timer));
    });
}
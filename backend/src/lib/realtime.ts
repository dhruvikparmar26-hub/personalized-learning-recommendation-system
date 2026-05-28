import type { Response } from 'express';
import type WebSocket from 'ws';

type ClientSet<T> = Map<string, Set<T>>;

const sseClients: ClientSet<Response> = new Map();
const wsClients: ClientSet<WebSocket> = new Map();

export function registerSseClient(userId: string, res: Response): void {
    const clients = sseClients.get(userId) ?? new Set<Response>();
    clients.add(res);
    sseClients.set(userId, clients);

    res.on('close', () => {
        const bucket = sseClients.get(userId);
        if (!bucket) return;
        bucket.delete(res);
        if (bucket.size === 0) {
            sseClients.delete(userId);
        }
    });
}

export function registerWsClient(userId: string, ws: WebSocket): void {
    const clients = wsClients.get(userId) ?? new Set<WebSocket>();
    clients.add(ws);
    wsClients.set(userId, clients);

    ws.on('close', () => {
        const bucket = wsClients.get(userId);
        if (!bucket) return;
        bucket.delete(ws);
        if (bucket.size === 0) {
            wsClients.delete(userId);
        }
    });
}

export function broadcastUpdate(userId: string, payload: object): void {
    const message = JSON.stringify(payload);

    for (const client of wsClients.get(userId) ?? []) {
        try {
            client.send(message);
        } catch {
            // ignore dead sockets
        }
    }

    for (const client of sseClients.get(userId) ?? []) {
        try {
            client.write(`data: ${message}\n\n`);
        } catch {
            // ignore dead streams
        }
    }
}

export function sendSseEvent(res: Response, payload: object): void {
    res.write(`data: ${JSON.stringify(payload)}\n\n`);
}

export function startTextStream(res: Response, text: string): void {
    const chunks = text.match(/\S+\s*/g) ?? [text];
    let index = 0;

    const timer = setInterval(() => {
        if (index < chunks.length) {
            sendSseEvent(res, { type: 'token', content: chunks[index] });
            index += 1;
            return;
        }

        sendSseEvent(res, { type: 'done', full_response: text });
        clearInterval(timer);
        res.end();
    }, 18);

    res.on('close', () => clearInterval(timer));
}

export function sseStats(): { sseConnections: number; wsConnections: number } {
    const sseConnections = [...sseClients.values()].reduce((sum, set) => sum + set.size, 0);
    const wsConnections = [...wsClients.values()].reduce((sum, set) => sum + set.size, 0);
    return { sseConnections, wsConnections };
}
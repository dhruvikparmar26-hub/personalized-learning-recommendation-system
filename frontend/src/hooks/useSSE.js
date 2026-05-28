import { useState, useEffect, useRef } from 'react';

/**
 * Custom hook for Server-Sent Events (SSE).
 *
 * Features:
 *   - Subscribe to SSE stream
 *   - Auto-reconnect (built into EventSource)
 *   - Parse JSON data events
 *   - Connection state tracking
 *
 * Used by: RecommendationGrid for live re-ranking updates
 */
export function useSSE(url) {
  const [data, setData] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const eventSourceRef = useRef(null);

  useEffect(() => {
    if (!url) return undefined;

    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    es.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        if (parsed.type !== 'heartbeat') {
          setData(parsed);
        }
      } catch {
        console.warn('Failed to parse SSE data:', event.data);
      }
    };

    es.onerror = () => {
      setIsConnected(false);
      setError('Connection lost. Reconnecting...');
      // EventSource auto-reconnects
    };

    return () => {
      es.close();
    };
  }, [url]);

  return { data, isConnected, error };
}

/**
 * Hook for streaming text via SSE (Claude explanations).
 * Accumulates tokens into a growing text string.
 */
export function useSSEStream(url, enabled = false) {
  const [text, setText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isDone, setIsDone] = useState(false);

  useEffect(() => {
    if (!url || !enabled) return;

    queueMicrotask(() => {
      setText('');
      setIsDone(false);
      setIsStreaming(true);
    });

    const es = new EventSource(url);

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'token') {
          setText((prev) => prev + data.content);
        } else if (data.type === 'done') {
          setIsStreaming(false);
          setIsDone(true);
          es.close();
        }
      } catch {
        // skip
      }
    };

    es.onerror = () => {
      setIsStreaming(false);
      es.close();
    };

    return () => es.close();
  }, [url, enabled]);

  return { text, isStreaming, isDone };
}

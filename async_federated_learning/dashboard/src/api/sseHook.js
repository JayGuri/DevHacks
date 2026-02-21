// dashboard/src/api/sseHook.js — SSE feed hook for real-time telemetry
import { useEffect, useRef, useCallback } from "react";

/**
 * useSSEFeed(url, onEvent)
 * Opens EventSource. On message: JSON.parse, call onEvent.
 * On error: close, reopen after 3 seconds.
 * Cleanup on unmount via useEffect return.
 */
export function useSSEFeed(url, onEvent) {
  const eventSourceRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const onEventRef = useRef(onEvent);

  // Keep the callback ref current
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  const connect = useCallback(() => {
    // Clean up existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        if (onEventRef.current) {
          onEventRef.current(parsed);
        }
      } catch (err) {
        console.warn("SSE parse error:", err);
      }
    };

    es.onerror = (err) => {
      console.warn("SSE connection error, reconnecting in 3s...", err);
      es.close();
      eventSourceRef.current = null;

      // Reconnect after 3 seconds
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, 3000);
    };

    es.onopen = () => {
      console.log("SSE connected to", url);
    };
  }, [url]);

  useEffect(() => {
    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };
  }, [connect]);
}

export default useSSEFeed;

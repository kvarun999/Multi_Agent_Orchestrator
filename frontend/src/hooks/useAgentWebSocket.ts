import { useEffect, useRef, useState, useCallback } from "react";

export interface AgentEvent {
  task_id?: string;
  agent: string;
  event_type: string;
  message: string;
  payload?: Record<string, unknown>;
  timestamp?: string;
}

interface UseAgentWebSocketReturn {
  events: AgentEvent[];
  isConnected: boolean;
  isCompleted: boolean;
  error: string | null;
}

/**
 * Custom React hook that manages a WebSocket connection for streaming
 * agent events from the backend. Connects when a taskId is provided.
 */
export function useAgentWebSocket(taskId: string | null): UseAgentWebSocketReturn {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ws = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);

  const reset = useCallback(() => {
    setEvents([]);
    setIsCompleted(false);
    setError(null);
  }, []);

  useEffect(() => {
    if (!taskId) return;

    reset();

    const wsUrl = process.env.REACT_APP_WS_URL || "ws://localhost:8000";
    const connect = () => {
      const socket = new WebSocket(`${wsUrl}/api/ws/${taskId}`);
      ws.current = socket;

      socket.onopen = () => {
        setIsConnected(true);
        setError(null);
        reconnectAttempts.current = 0;
      };

      socket.onmessage = (event) => {
        try {
          const data: AgentEvent = JSON.parse(event.data);

          // Skip heartbeat messages
          if (data.event_type === "HEARTBEAT") return;

          setEvents((prev) => [...prev, data]);

          if (data.event_type === "COMPLETED" || data.event_type === "FAILED") {
            setIsCompleted(true);
          }
        } catch (err) {
          console.warn("Failed to parse WebSocket message:", err);
        }
      };

      socket.onclose = () => {
        setIsConnected(false);
        ws.current = null;

        // Auto-reconnect if not completed (max 3 attempts)
        if (!isCompleted && reconnectAttempts.current < 3) {
          reconnectAttempts.current += 1;
          setTimeout(connect, 1000 * reconnectAttempts.current);
        }
      };

      socket.onerror = () => {
        setError("WebSocket connection error");
        socket.close();
      };
    };

    connect();

    return () => {
      if (ws.current) {
        ws.current.close();
        ws.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  return { events, isConnected, isCompleted, error };
}

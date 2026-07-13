import React, { useEffect, useRef } from "react";
import { AgentEvent } from "../hooks/useAgentWebSocket";

interface TimelineProps {
  events: AgentEvent[];
  isConnected: boolean;
}

/** Map agent names to emoji icons */
function getAgentIcon(agent: string): string {
  const name = agent.toLowerCase();
  if (name.includes("planner")) return "🧠";
  if (name.includes("researcher")) return "🔍";
  if (name.includes("synthesizer")) return "✍️";
  if (name.includes("system")) return "⚙️";
  return "🤖";
}

/** Map event types to emoji icons */
function getEventIcon(eventType: string): string {
  const type = eventType.toUpperCase();
  if (type === "TOOL_CALL") return "🔧";
  if (type === "TOOL_RESULT") return "📊";
  if (type === "ERROR" || type === "FAILED") return "❌";
  if (type === "COMPLETED") return "✅";
  return "";
}

/** Build CSS class names for the event based on agent and type */
function getEventClasses(event: AgentEvent): string {
  const classes = ["timeline-event"];
  const agent = event.agent?.toLowerCase() || "";
  const type = event.event_type?.toUpperCase() || "";

  if (agent.includes("planner")) classes.push("agent-planner");
  else if (agent.includes("researcher")) classes.push("agent-researcher");
  else if (agent.includes("synthesizer")) classes.push("agent-synthesizer");
  else classes.push("agent-system");

  if (type === "TOOL_CALL") classes.push("event-tool-call");
  else if (type === "TOOL_RESULT") classes.push("event-tool-result");
  else if (type === "ERROR") classes.push("event-error");
  else if (type === "FAILED") classes.push("event-failed");

  return classes.join(" ");
}

/** Format the timestamp for display */
function formatTime(timestamp?: string): string {
  if (!timestamp) return "";
  try {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

export default function Timeline({ events, isConnected }: TimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new events
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [events]);

  if (events.length === 0) {
    return (
      <div className="glass-card">
        <div className="empty-state">
          <div className="empty-icon">🤖</div>
          <p className="empty-text">
            Submit a task above to watch the AI agents collaborate in real-time.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="timeline-section">
      <div className="status-bar">
        <span
          className={`status-dot ${isConnected ? "connected" : "disconnected"}`}
        />
        <span className="status-text">
          {isConnected ? "Connected — streaming events" : "Disconnected"}
        </span>
      </div>

      <p className="section-title">Agent Activity Timeline</p>

      <div className="timeline-container" ref={containerRef}>
        <div className="timeline">
          {events.map((event, idx) => (
            <div
              key={idx}
              className={getEventClasses(event)}
              style={{ animationDelay: `${Math.min(idx * 0.05, 0.3)}s` }}
            >
              <div className="event-dot">
                {getEventIcon(event.event_type)}
              </div>
              <div className="event-card">
                <div className="event-header">
                  <span className="event-agent">
                    {getAgentIcon(event.agent)} {event.agent}
                  </span>
                  <span className="event-badge">{event.event_type}</span>
                </div>
                <p className="event-message">{event.message}</p>
                {event.timestamp && (
                  <p className="event-time">{formatTime(event.timestamp)}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

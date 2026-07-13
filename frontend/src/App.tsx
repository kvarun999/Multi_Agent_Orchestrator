import React, { useState, useMemo } from "react";
import TaskForm from "./components/TaskForm";
import Timeline from "./components/Timeline";
import FinalResult from "./components/FinalResult";
import { useAgentWebSocket } from "./hooks/useAgentWebSocket";

export default function App() {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { events, isConnected, isCompleted } = useAgentWebSocket(taskId);

  /** Extract the final result from the COMPLETED event payload */
  const finalResult = useMemo(() => {
    const completedEvent = events.find(
      (e) => e.event_type === "COMPLETED" && e.payload?.final_result
    );
    if (completedEvent && completedEvent.payload) {
      return completedEvent.payload.final_result as string;
    }
    return "";
  }, [events]);

  /** When the workflow completes or fails, stop the loading state */
  React.useEffect(() => {
    if (isCompleted) {
      setIsLoading(false);
    }
  }, [isCompleted]);

  const handleSubmit = async (prompt: string) => {
    setIsLoading(true);
    setTaskId(null); // Reset previous task

    try {
      const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      const data = await res.json();
      setTaskId(data.task_id);
    } catch (err) {
      console.error("Failed to start task:", err);
      setIsLoading(false);
      alert("Failed to connect to the backend. Make sure the API is running on port 8000.");
    }
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1 className="app-title">Multi-Agent Orchestrator</h1>
        <p className="app-subtitle">
          Specialized AI agents collaborate to solve complex, multi-step problems
        </p>
      </header>

      <TaskForm onSubmit={handleSubmit} isLoading={isLoading} />

      {finalResult && <FinalResult result={finalResult} />}

      <Timeline events={events} isConnected={isConnected} />
    </div>
  );
}
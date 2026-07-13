import React, { useState } from "react";

interface TaskFormProps {
  onSubmit: (prompt: string) => void;
  isLoading: boolean;
}

const EXAMPLE_PROMPTS = [
  "What's the weather in Tokyo and what should I pack?",
  "Compare weather in London and Paris, convert temps to Fahrenheit",
  "Search for the latest AI trends and summarize key findings",
];

export default function TaskForm({ onSubmit, isLoading }: TaskFormProps) {
  const [prompt, setPrompt] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (prompt.trim() && !isLoading) {
      onSubmit(prompt.trim());
    }
  };

  const handleExampleClick = (example: string) => {
    setPrompt(example);
  };

  return (
    <div className="glass-card task-form">
      <form onSubmit={handleSubmit}>
        <label className="form-label" htmlFor="prompt-input">
          Describe your task
        </label>
        <textarea
          id="prompt-input"
          className="prompt-textarea"
          rows={4}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Enter a complex, multi-step task for the AI agents to solve..."
          disabled={isLoading}
        />

        <div className="form-actions">
          <span className="char-count">{prompt.length} characters</span>
          <button
            type="submit"
            className="submit-btn"
            disabled={!prompt.trim() || isLoading}
            id="start-workflow-btn"
          >
            {isLoading ? (
              <>
                <span className="loading-spinner" />
                Running...
              </>
            ) : (
              <>
                <span className="btn-icon">▶</span>
                Start Workflow
              </>
            )}
          </button>
        </div>
      </form>

      <div className="examples-section">
        <p className="examples-label">Try an example</p>
        <div className="example-chips">
          {EXAMPLE_PROMPTS.map((example, idx) => (
            <button
              key={idx}
              type="button"
              className="example-chip"
              onClick={() => handleExampleClick(example)}
              disabled={isLoading}
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

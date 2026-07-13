import React from "react";

interface FinalResultProps {
  result: string;
}

export default function FinalResult({ result }: FinalResultProps) {
  if (!result) return null;

  return (
    <div className="final-result-section">
      <div className="final-result-card">
        <div className="final-result-header">
          <span className="final-result-icon">✨</span>
          <h3 className="final-result-title">Final Result</h3>
        </div>
        <div className="final-result-content">{result}</div>
      </div>
    </div>
  );
}

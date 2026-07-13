"""
SQLAlchemy ORM models for persisting agent workflow state.
TaskRun tracks the overall lifecycle; AgentEvent captures every discrete action.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _utcnow():
    return datetime.now(timezone.utc)


class TaskRun(Base):
    """Represents a single user request and its overall workflow lifecycle."""

    __tablename__ = "task_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    prompt = Column(Text, nullable=False)
    status = Column(String(20), default="PENDING")  # PENDING | RUNNING | COMPLETED | FAILED
    final_result = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationship to child events
    events = relationship("AgentEvent", back_populates="task_run", order_by="AgentEvent.timestamp")

    def __repr__(self):
        return f"<TaskRun id={self.id} status={self.status}>"


class AgentEvent(Base):
    """Tracks every discrete action within a TaskRun for full auditability."""

    __tablename__ = "agent_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    task_run_id = Column(String, ForeignKey("task_runs.id"), nullable=False, index=True)
    agent_name = Column(String(50), nullable=False)   # e.g. 'Planner', 'Researcher', 'Synthesizer'
    event_type = Column(String(30), nullable=False)    # THOUGHT | TOOL_CALL | TOOL_RESULT | ERROR | STATUS
    payload = Column(JSON, nullable=False)             # Arbitrary JSON data for the event
    timestamp = Column(DateTime(timezone=True), default=_utcnow)

    # Relationship back to parent
    task_run = relationship("TaskRun", back_populates="events")

    def __repr__(self):
        return f"<AgentEvent agent={self.agent_name} type={self.event_type}>"
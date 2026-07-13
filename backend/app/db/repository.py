"""
Async repository functions for TaskRun and AgentEvent CRUD operations.
All functions accept an AsyncSession and perform non-blocking DB access.
"""

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TaskRun, AgentEvent


async def create_task_run(session: AsyncSession, task_id: str, prompt: str) -> TaskRun:
    """Insert a new TaskRun with PENDING status."""
    task_run = TaskRun(id=task_id, prompt=prompt, status="PENDING")
    session.add(task_run)
    await session.commit()
    await session.refresh(task_run)
    return task_run


async def update_task_status(
    session: AsyncSession,
    task_id: str,
    status: str,
    final_result: str | None = None,
) -> TaskRun | None:
    """Update the status (and optionally final_result) of a TaskRun."""
    result = await session.execute(select(TaskRun).where(TaskRun.id == task_id))
    task_run = result.scalar_one_or_none()
    if task_run is None:
        return None
    task_run.status = status
    task_run.updated_at = datetime.now(timezone.utc)
    if final_result is not None:
        task_run.final_result = final_result
    await session.commit()
    await session.refresh(task_run)
    return task_run


async def create_agent_event(
    session: AsyncSession,
    task_run_id: str,
    agent_name: str,
    event_type: str,
    payload: dict,
) -> AgentEvent:
    """Insert a new AgentEvent linked to a TaskRun."""
    event = AgentEvent(
        task_run_id=task_run_id,
        agent_name=agent_name,
        event_type=event_type,
        payload=payload,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def get_task_run(session: AsyncSession, task_id: str) -> TaskRun | None:
    """Retrieve a TaskRun with all its AgentEvents eagerly loaded."""
    result = await session.execute(
        select(TaskRun)
        .where(TaskRun.id == task_id)
        .options(selectinload(TaskRun.events))
    )
    return result.scalar_one_or_none()


async def list_task_runs(session: AsyncSession, limit: int = 50) -> list[TaskRun]:
    """List recent TaskRuns ordered by creation time (newest first)."""
    result = await session.execute(
        select(TaskRun).order_by(TaskRun.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())

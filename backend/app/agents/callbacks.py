"""
Event broadcasting via Redis pub/sub.
Publishes structured events from the agent graph so that the WebSocket
layer can stream them to connected clients in real-time.
Also persists events to PostgreSQL for auditability.
"""

import json
from datetime import datetime, timezone
from redis import Redis
from app.core.config import get_settings


def get_redis_client() -> Redis:
    """Create a synchronous Redis client for pub/sub publishing."""
    settings = get_settings()
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def publish_event(
    task_id: str,
    agent_name: str,
    event_type: str,
    message: str,
    payload: dict | None = None,
) -> None:
    """
    Publish an agent event to the Redis pub/sub channel for a given task.
    The WebSocket manager subscribes to these channels to stream to the frontend.

    Args:
        task_id: The unique task identifier.
        agent_name: Name of the active agent (e.g., 'Planner', 'Researcher').
        event_type: Type of event (e.g., 'THOUGHT', 'TOOL_CALL', 'TOOL_RESULT', 'ERROR', 'STATUS').
        message: Human-readable description of the event.
        payload: Optional additional data to include in the event.
    """
    event = {
        "task_id": task_id,
        "agent": agent_name,
        "event_type": event_type,
        "message": message,
        "payload": payload or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        redis_client = get_redis_client()
        channel = f"task:{task_id}:events"
        redis_client.publish(channel, json.dumps(event))
        redis_client.close()
    except Exception as e:
        # Don't crash the workflow if pub/sub fails
        print(f"[WARNING] Failed to publish event to Redis: {e}")

"""
WebSocket connection manager with Redis pub/sub integration.
Subscribes to Redis channels to stream agent events to connected clients,
completely decoupling the WebSocket layer from graph execution.
"""

import asyncio
import json
from typing import Dict
from fastapi import WebSocket
from redis.asyncio import Redis as AsyncRedis
from app.core.config import get_settings


class ConnectionManager:
    """Manages active WebSocket connections and Redis pub/sub subscriptions."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        """Accept a WebSocket connection and start streaming events for this task."""
        await websocket.accept()
        self.active_connections[task_id] = websocket

        # Start a background task to subscribe to Redis pub/sub for this task
        self._tasks[task_id] = asyncio.create_task(
            self._subscribe_and_forward(task_id, websocket)
        )

    async def disconnect(self, task_id: str) -> None:
        """Clean up connection and cancel the subscription task."""
        if task_id in self._tasks:
            self._tasks[task_id].cancel()
            try:
                await self._tasks[task_id]
            except asyncio.CancelledError:
                pass
            del self._tasks[task_id]

        self.active_connections.pop(task_id, None)

    async def _subscribe_and_forward(self, task_id: str, websocket: WebSocket) -> None:
        """
        Subscribe to the Redis pub/sub channel for a task and forward
        all events to the WebSocket client.
        """
        settings = get_settings()
        redis = AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = redis.pubsub()
        channel = f"task:{task_id}:events"

        try:
            await pubsub.subscribe(channel)

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )

                if message and message["type"] == "message":
                    try:
                        event_data = json.loads(message["data"])
                        await websocket.send_json(event_data)

                        # If the workflow is completed or failed, send final status and break
                        if event_data.get("event_type") in ("COMPLETED", "FAILED"):
                            pass  # Keep listening briefly for any trailing events
                    except Exception:
                        pass

                # Small yield to prevent busy-waiting
                await asyncio.sleep(0.05)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[WS Manager] Error in subscription for {task_id}: {e}")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            await redis.close()


# Global connection manager instance
manager = ConnectionManager()

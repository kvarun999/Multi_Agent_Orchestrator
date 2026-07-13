"""
FastAPI route definitions for the multi-agent orchestrator API.
Includes REST endpoints for task management and a WebSocket endpoint
for real-time event streaming.
"""

import asyncio
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, get_db
from app.db.repository import create_task_run, update_task_status, create_agent_event, get_task_run
from app.agents.graph import build_graph, AgentState
from app.agents.callbacks import publish_event
from app.api.ws_manager import manager
from langchain_core.messages import HumanMessage

router = APIRouter()


class TaskRequest(BaseModel):
    """Request schema for creating a new task."""
    prompt: str


class TaskResponse(BaseModel):
    """Response schema after task creation."""
    task_id: str


# ---------------------------------------------------------------------------
# Background workflow executor
# ---------------------------------------------------------------------------
async def run_agent_workflow(task_id: str, prompt: str) -> None:
    """
    Execute the full LangGraph agent workflow for a given task.
    Runs as a background coroutine — does not block the HTTP response.
    Persists all state transitions to PostgreSQL and broadcasts via Redis pub/sub.
    """
    async with AsyncSessionLocal() as session:
        try:
            # Mark task as running
            await update_task_status(session, task_id, "RUNNING")
            publish_event(task_id, "System", "STATUS", "Workflow started. Initializing agents...")

            # Persist the start event
            await create_agent_event(
                session, task_id, "System", "STATUS",
                {"message": "Workflow started", "prompt": prompt},
            )

            # Build and run the graph
            graph = build_graph()
            initial_state: AgentState = {
                "messages": [HumanMessage(content=prompt)],
                "task_id": task_id,
                "plan": [],
                "current_step_index": 0,
                "research_data": [],
                "final_result": "",
                "status": "PENDING",
            }

            # Stream through graph nodes
            final_state = None
            async for event in graph.astream(initial_state):
                for node_name, node_state in event.items():
                    # Persist each agent action to the database
                    messages = node_state.get("messages", [])
                    last_message = messages[-1].content if messages else ""

                    await create_agent_event(
                        session, task_id, node_name,
                        node_state.get("status", "AGENT_ACTION"),
                        {
                            "message": last_message[:2000],
                            "plan": node_state.get("plan"),
                            "current_step_index": node_state.get("current_step_index"),
                            "research_data_count": len(node_state.get("research_data", [])),
                        },
                    )
                    final_state = node_state

            # Extract final result
            final_result = ""
            if final_state:
                final_result = final_state.get("final_result", "")

            # Mark task as completed
            await update_task_status(session, task_id, "COMPLETED", final_result=final_result)

            # Broadcast completion
            publish_event(
                task_id, "System", "COMPLETED",
                "Workflow completed successfully.",
                payload={"final_result": final_result},
            )

            await create_agent_event(
                session, task_id, "System", "COMPLETED",
                {"message": "Workflow completed", "final_result": final_result[:2000]},
            )

        except Exception as e:
            error_msg = f"Workflow failed: {str(e)}"
            await update_task_status(session, task_id, "FAILED", final_result=error_msg)
            publish_event(task_id, "System", "FAILED", error_msg, payload={"error": str(e)})
            await create_agent_event(
                session, task_id, "System", "ERROR",
                {"message": error_msg, "error": str(e)},
            )


# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------
@router.post("/tasks", response_model=TaskResponse)
async def create_task(request: TaskRequest, db: AsyncSession = Depends(get_db)):
    """
    Create a new agent task. Returns the task ID immediately.
    The agent workflow runs asynchronously in the background.
    """
    task_id = str(uuid.uuid4())

    # Persist the task run to the database
    await create_task_run(db, task_id, request.prompt)

    # Launch the workflow as a background coroutine
    asyncio.create_task(run_agent_workflow(task_id, request.prompt))

    return TaskResponse(task_id=task_id)


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a task run with all its agent events.
    Useful for reviewing completed tasks or debugging.
    """
    task_run = await get_task_run(db, task_id)
    if not task_run:
        return {"error": "Task not found"}

    return {
        "id": task_run.id,
        "prompt": task_run.prompt,
        "status": task_run.status,
        "final_result": task_run.final_result,
        "created_at": task_run.created_at.isoformat() if task_run.created_at else None,
        "updated_at": task_run.updated_at.isoformat() if task_run.updated_at else None,
        "events": [
            {
                "id": event.id,
                "agent_name": event.agent_name,
                "event_type": event.event_type,
                "payload": event.payload,
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            }
            for event in task_run.events
        ],
    }


# ---------------------------------------------------------------------------
# WebSocket Endpoint
# ---------------------------------------------------------------------------
@router.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint for real-time task event streaming.
    Subscribes to the Redis pub/sub channel for the given task and
    forwards all events to the connected client.
    """
    await manager.connect(task_id, websocket)
    try:
        # Keep the connection alive by receiving pings/messages from the client
        while True:
            try:
                # Wait for any client message (acts as keepalive)
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a heartbeat ping to keep the connection alive
                try:
                    await websocket.send_json({"event_type": "HEARTBEAT", "message": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect(task_id)

"""
FastAPI application entry point.
Assembles middleware, routes, and lifecycle events.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import init_db
from app.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    # Startup: create database tables
    print("[STARTUP] Initializing database tables...")
    await init_db()
    print("[STARTUP] Database ready.")
    yield
    # Shutdown: cleanup (if needed)
    print("[SHUTDOWN] Application shutting down.")


app = FastAPI(
    title="Multi-Agent Orchestrator API",
    description="A stateful multi-agent AI system for solving complex, multi-step problems.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware — allows the React frontend to make cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes under /api prefix
app.include_router(router, prefix="/api")


@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "ok", "service": "multi-agent-orchestrator"}
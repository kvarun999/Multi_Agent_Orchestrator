# Multi-Agent Orchestrator

A stateful multi-agent AI system that orchestrates specialized AI agents to solve complex, multi-step problems with real-time visualization.

## Architecture

- **Backend**: FastAPI + WebSockets + SQLAlchemy (async) + LangGraph + Celery
- **Frontend**: React + TypeScript + WebSocket client
- **Infrastructure**: Docker Compose with PostgreSQL 15 and Redis 7
- **LLM**: Groq (Llama 3.3 70B Versatile) via LangChain

## Prerequisites

You need API keys for the following services:

| Service | Purpose | Get a key at |
|:---|:---|:---|
| **Groq** | LLM inference | [console.groq.com](https://console.groq.com) |
| **OpenWeatherMap** | Weather tool | [openweathermap.org/api](https://openweathermap.org/api) |
| **Brave Search** | Web search tool | [brave.com/search/api](https://brave.com/search/api) |

## Quick Start

1. **Clone and configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys:
   #   GROQ_API_KEY=gsk_...
   #   OPENWEATHER_API_KEY=...
   #   BRAVE_SEARCH_API_KEY=...
   ```

2. **Start all services**:
   ```bash
   docker compose up --build
   ```

3. **Access the applications**:
   - Frontend: [http://localhost:3000](http://localhost:3000)
   - Backend API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
   - Health check: [http://localhost:8000/health](http://localhost:8000/health)

## Services

| Service | Port | Description |
|:---|:---|:---|
| `ui` | 3000 | React frontend |
| `api` | 8000 | FastAPI backend |
| `db` | 5432 | PostgreSQL 15 |
| `redis` | 6379 | Redis 7 |
| `worker` | — | Celery worker |

## How It Works

1. Submit a complex prompt via the React UI
2. The **Planner** agent decomposes it into research steps
3. The **Researcher** agent executes each step using tools (weather, search, calculator)
4. Tools run asynchronously via Celery workers
5. The **Synthesizer** agent combines findings into a comprehensive response
6. All events stream to the UI in real-time via WebSocket
7. Every action is logged to PostgreSQL for full auditability

## Testing

```bash
# Submit a task via curl
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the weather in Tokyo and what should I pack?"}'

# Check the database
docker compose exec db psql -U admin -d agent_db \
  -c "SELECT id, status, prompt FROM task_runs ORDER BY created_at DESC LIMIT 5;"

# View worker logs
docker compose logs worker -f
```

## Documentation

See [EVALUATION.md](./EVALUATION.md) for the full system design document, including:
- Orchestration pattern rationale (LangGraph vs AutoGen)
- Agent roles and system prompts
- Tool schemas, expected outputs, and error handling strategies

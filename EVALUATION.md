# System Design Document — Multi-Agent Orchestrator

## 1. Orchestration Pattern: LangGraph

### Why LangGraph over AutoGen

We chose **LangGraph** (part of the LangChain ecosystem) for the following reasons:

| Criteria | LangGraph | AutoGen |
|:---|:---|:---|
| **State Machine Model** | Explicit `StateGraph` with typed state, nodes, and edges | Conversation-based — agents chat with each other |
| **Control Flow** | Deterministic edges + conditional routing functions | Emergent from agent conversations — harder to debug |
| **Streaming** | Native `astream()` yields per-node updates | Requires custom callbacks for streaming |
| **Tool Integration** | First-class via `bind_tools()` and `ToolNode` | Supported, but tool schemas are less integrated |
| **State Persistence** | TypedDict state flows through every node, easily serializable | Shared context is less structured |
| **Debugging** | Each node transition is explicit and auditable | Conversation traces can be verbose and hard to parse |

LangGraph's explicit state machine model ensures:
- **Predictable execution**: We define exactly which agent runs when
- **Conditional looping**: The Researcher loops through plan steps via `add_conditional_edges`
- **Full auditability**: Every state transition is logged to PostgreSQL
- **Streaming support**: `astream()` yields events per node for WebSocket delivery

### Graph Architecture

```
START → Planner → Researcher ←─(loop if more steps)
                            └─→ Synthesizer → END
```

The `should_continue_research()` routing function checks `current_step_index` against `len(plan)` to decide whether to loop back to the Researcher or advance to the Synthesizer.

### Shared State Schema

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # Message history
    task_id: str                   # Unique task identifier
    plan: list[str]                # Steps produced by the Planner
    current_step_index: int        # Which step the Researcher is on
    research_data: list[dict]      # Accumulated research findings
    final_result: str              # Synthesized final response
    status: str                    # Current workflow status
```

---

## 2. Agent Roles & System Prompts

### Agent 1: Planner (🧠)

**Responsibility**: Analyze the user's complex request and decompose it into 2-4 specific, actionable research steps.

**System Prompt** (abbreviated):
```
You are the Planner Agent. Analyze the user's request and break it down
into 2-4 distinct research steps. Output a JSON object with:
{
  "analysis": "Brief analysis of the request",
  "steps": ["Step 1: ...", "Step 2: ..."]
}
```

**Key behaviors**:
- Uses `with_structured_output` pattern (JSON output format)
- Does NOT call any tools — purely analytical
- Falls back to a single-step plan if JSON parsing fails

---

### Agent 2: Researcher (🔍)

**Responsibility**: Execute a single research step by selecting and invoking the appropriate tool from the available toolkit.

**System Prompt** (abbreviated):
```
You are the Researcher Agent. You have three tools: weather_lookup,
search_web, and calculator. Read the research step, determine which
tool is most appropriate, and call it with well-formed arguments.
```

**Key behaviors**:
- Has tools bound via `llm.bind_tools(ALL_TOOLS)`
- The LLM autonomously decides which tool to call based on the step description
- After receiving tool results, summarizes findings
- Called once per plan step (the graph loops it)

---

### Agent 3: Synthesizer (✍️)

**Responsibility**: Combine all research findings into a comprehensive, well-structured final response.

**System Prompt** (abbreviated):
```
You are the Synthesizer Agent. Take all research data and the original
request, then compose a comprehensive final response. Include specific
data points, organize logically, and provide actionable recommendations.
```

**Key behaviors**:
- Receives the full `research_data` list from all completed steps
- Does NOT call any tools — purely generative
- Produces the `final_result` that is sent to the user

---

## 3. Custom Tool Specifications

### Tool 1: Weather Lookup (`weather_lookup`)

**External API**: OpenWeatherMap (Geocoding API + Current Weather API)

**Input Schema**:
```python
class WeatherSearchInput(BaseModel):
    location: str = Field(
        description="City and ISO country code, e.g., 'Tokyo, JP'"
    )
    units: str = Field(
        default="metric",
        description="'metric' for Celsius, 'imperial' for Fahrenheit"
    )
```

**Expected Output** (success):
```json
{
  "status": "success",
  "data": {
    "location": "Tokyo, JP",
    "temperature": "15°C",
    "feels_like": "13°C",
    "humidity": "72%",
    "condition": "light rain",
    "wind_speed": "5.2 m/s"
  }
}
```

**Error Handling**:
- Missing API key → returns descriptive error message with setup instructions
- Invalid location → returns "Could not find location" error
- API timeout → returns timeout error with service status note
- HTTP errors → returns status code and response excerpt
- All errors are returned as strings to the agent — never thrown as exceptions

---

### Tool 2: Web Search (`search_web`)

**External API**: Brave Search API (v1 Web Search)

**Input Schema**:
```python
class WebSearchInput(BaseModel):
    query: str = Field(
        description="Specific search query string"
    )
    count: int = Field(
        default=5, ge=1, le=10,
        description="Number of results to return"
    )
```

**Expected Output** (success):
```json
{
  "status": "success",
  "data": {
    "query": "current GDP of Japan 2024",
    "result_count": 5,
    "results": [
      {
        "title": "Japan GDP - Trading Economics",
        "url": "https://...",
        "snippet": "Japan GDP was worth 4.23 trillion..."
      }
    ]
  }
}
```

**Error Handling**:
- Missing API key → descriptive error with setup instructions
- HTTP errors → status code and response body excerpt
- Timeout → service unavailability message
- No results → success with empty results array and explanatory message

---

### Tool 3: Calculator (`calculator`)

**Execution**: Local Python `eval()` with a sandboxed namespace (no imports, no builtins, only math functions)

**Input Schema**:
```python
class CalculatorInput(BaseModel):
    expression: str = Field(
        description="Math expression, e.g., '(25 * 1.8) + 32'"
    )
    description: str = Field(
        default="",
        description="Description of the calculation purpose"
    )
```

**Expected Output** (success):
```json
{
  "status": "success",
  "data": {
    "expression": "(25 * 1.8) + 32",
    "result": 77.0,
    "description": "Convert 25°C to Fahrenheit"
  }
}
```

**Error Handling**:
- Blocked keywords (`import`, `exec`, `eval`, `os.`, `__`) → rejection with explanation
- Division by zero → specific error message
- Syntax errors → descriptive parse error
- All other exceptions → generic error with expression echo

**Safety**: The calculator uses a restricted namespace with `__builtins__: {}` and only allows whitelisted math functions (`sqrt`, `sin`, `cos`, `log`, `abs`, `round`, `pi`, `e`, etc.). No arbitrary code execution is possible.

---

## 4. Asynchronous Execution Model

### Celery Task Queue

All three tools are decorated as Celery tasks (`@celery_app.task`) and executed by the worker process:

- **Broker**: Redis (message transport)
- **Backend**: Redis (result storage)
- **Worker Pool**: Solo (single-threaded, suitable for I/O-bound tasks)

When the Researcher agent's LLM decides to call a tool:
1. The LangChain tool wrapper calls `celery_task.delay(args)`
2. The task is serialized and pushed to Redis
3. The Celery worker picks it up, executes the API call, and stores the result
4. The wrapper calls `result.get(timeout=30)` to retrieve the result
5. The result is fed back to the LLM for summarization

### Event Broadcasting

Agent events flow through Redis pub/sub:
1. Each graph node publishes events to `task:{task_id}:events` channel
2. The WebSocket manager subscribes to this channel per connected client
3. Events are forwarded to the React frontend in real-time

This decouples the graph execution from WebSocket delivery, eliminating race conditions.

---

## 5. Database Auditability

Every workflow produces a complete audit trail in PostgreSQL:

**`task_runs` table**: One row per user request
- `id` (UUID), `prompt`, `status`, `final_result`, `created_at`, `updated_at`

**`agent_events` table**: Multiple rows per task run
- Linked via `task_run_id` foreign key
- Captures: `agent_name`, `event_type` (THOUGHT, TOOL_CALL, TOOL_RESULT, ERROR, STATUS, COMPLETED), `payload` (JSONB), `timestamp`

To review a task's execution history:
```sql
SELECT agent_name, event_type, payload, timestamp
FROM agent_events
WHERE task_run_id = '<uuid>'
ORDER BY timestamp;
```

---

## 6. Technology Stack Summary

| Component | Technology | Version |
|:---|:---|:---|
| API Server | FastAPI | 0.115.0 |
| LLM Provider | Groq (Llama 3.3 70B) | via langchain-groq |
| Agent Framework | LangGraph | 0.2.58 |
| Task Queue | Celery | 5.5.2 |
| Message Broker | Redis | 7 (Alpine) |
| Database | PostgreSQL | 15 (Alpine) |
| ORM | SQLAlchemy (async) | 2.0.36 |
| DB Driver | asyncpg | 0.30.0 |
| Frontend | React + TypeScript | 18.3.1 |
| Containerization | Docker Compose | v3.8 |

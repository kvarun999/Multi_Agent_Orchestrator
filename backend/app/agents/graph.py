"""
LangGraph state machine for multi-agent orchestration.

Defines a graph with three specialized agents (Planner, Researcher, Synthesizer)
that collaborate to solve complex, multi-step problems. The graph uses conditional
edges to loop the Researcher through each plan step before routing to the Synthesizer.

State flows:  START → Planner → Researcher (loops per step) → Synthesizer → END
"""

import json
import os
from typing import TypedDict, Annotated, Literal

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages

from app.agents.prompts import (
    PLANNER_SYSTEM_PROMPT,
    RESEARCHER_SYSTEM_PROMPT,
    SYNTHESIZER_SYSTEM_PROMPT,
)
from app.agents.callbacks import publish_event
from app.tools.definitions import ALL_TOOLS
from app.core.config import get_settings


# ---------------------------------------------------------------------------
# Shared State
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    """Shared state passed between all agent nodes in the graph."""
    messages: Annotated[list[BaseMessage], add_messages]
    task_id: str
    plan: list[str]
    current_step_index: int
    research_data: list[dict]
    final_result: str
    status: str


# ---------------------------------------------------------------------------
# LLM initialization (reads API key from environment, never hardcoded)
# ---------------------------------------------------------------------------
def _get_llm():
    settings = get_settings()
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model="llama-3.3-70b-versatile",
        temperature=0.1,
        max_tokens=4096,
    )


# ---------------------------------------------------------------------------
# Agent Node: Planner
# ---------------------------------------------------------------------------
def planner_node(state: AgentState) -> dict:
    """
    Analyzes the user request and produces a structured multi-step plan.
    Outputs a JSON plan with 2-4 research steps.
    """
    task_id = state["task_id"]
    user_message = state["messages"][0].content

    publish_event(task_id, "Planner", "STATUS", "Planner agent is analyzing your request...")

    llm = _get_llm()
    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=f"User request: {user_message}"),
    ]

    response = llm.invoke(messages)
    response_text = response.content

    # Parse the JSON plan from the LLM response
    plan = []
    analysis = ""
    try:
        # Try to extract JSON from the response
        json_str = response_text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        parsed = json.loads(json_str.strip())
        plan = parsed.get("steps", [])
        analysis = parsed.get("analysis", "")
    except (json.JSONDecodeError, IndexError, KeyError):
        # Fallback: treat the whole response as a single step
        plan = [f"Research: {user_message}"]
        analysis = response_text

    # Ensure we have at least one step
    if not plan:
        plan = [f"Research: {user_message}"]

    publish_event(
        task_id, "Planner", "THOUGHT",
        f"Analysis: {analysis}\n\nPlan ({len(plan)} steps):\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(plan)),
        payload={"plan": plan, "analysis": analysis},
    )

    return {
        "plan": plan,
        "current_step_index": 0,
        "research_data": [],
        "status": "PLANNING_COMPLETE",
        "messages": [AIMessage(content=f"Plan created with {len(plan)} steps: {json.dumps(plan)}")],
    }


# ---------------------------------------------------------------------------
# Agent Node: Researcher
# ---------------------------------------------------------------------------
def researcher_node(state: AgentState) -> dict:
    """
    Executes a single research step by selecting and invoking the appropriate tool.
    Called once per plan step via the conditional looping edge.
    """
    task_id = state["task_id"]
    plan = state.get("plan", [])
    step_index = state.get("current_step_index", 0)
    research_data = list(state.get("research_data", []))

    if step_index >= len(plan):
        return {
            "status": "RESEARCH_COMPLETE",
            "messages": [AIMessage(content="All research steps completed.")],
        }

    current_step = plan[step_index]

    publish_event(
        task_id, "Researcher", "STATUS",
        f"Working on step {step_index + 1}/{len(plan)}: {current_step}",
    )

    llm = _get_llm()
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    messages = [
        SystemMessage(content=RESEARCHER_SYSTEM_PROMPT),
        HumanMessage(content=f"Execute this research step: {current_step}"),
    ]

    # First LLM call — may produce a tool_call
    response = llm_with_tools.invoke(messages)

    tool_result_data = None

    if response.tool_calls:
        tool_call = response.tool_calls[0]
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        publish_event(
            task_id, "Researcher", "TOOL_CALL",
            f"Calling tool: {tool_name} with args: {json.dumps(tool_args)}",
            payload={"tool": tool_name, "args": tool_args},
        )

        # Execute the tool
        tool_map = {t.name: t for t in ALL_TOOLS}
        selected_tool = tool_map.get(tool_name)

        if selected_tool:
            try:
                tool_output = selected_tool.invoke(tool_args)
                tool_result_data = json.loads(tool_output) if isinstance(tool_output, str) else tool_output

                publish_event(
                    task_id, "Researcher", "TOOL_RESULT",
                    f"Tool '{tool_name}' returned: {str(tool_result_data)[:500]}",
                    payload={"tool": tool_name, "result": tool_result_data},
                )
            except Exception as e:
                tool_result_data = {"status": "error", "message": str(e)}
                publish_event(
                    task_id, "Researcher", "ERROR",
                    f"Tool '{tool_name}' failed: {str(e)}",
                    payload={"tool": tool_name, "error": str(e)},
                )

        # Feed the tool result back to the LLM for summarization
        messages.append(response)
        messages.append(ToolMessage(
            content=json.dumps(tool_result_data or {"status": "error", "message": "Tool not found"}),
            tool_call_id=tool_call["id"],
        ))
        summary_response = llm.invoke(messages)
        step_summary = summary_response.content
    else:
        # No tool call — the LLM answered directly
        step_summary = response.content
        tool_result_data = {"direct_response": step_summary}

    research_data.append({
        "step": current_step,
        "step_index": step_index,
        "result": tool_result_data,
        "summary": step_summary,
    })

    publish_event(
        task_id, "Researcher", "THOUGHT",
        f"Step {step_index + 1} findings: {step_summary[:500]}",
        payload={"step_index": step_index, "summary": step_summary},
    )

    return {
        "current_step_index": step_index + 1,
        "research_data": research_data,
        "status": "RESEARCHING",
        "messages": [AIMessage(content=f"Step {step_index + 1} complete: {step_summary[:300]}")],
    }


# ---------------------------------------------------------------------------
# Agent Node: Synthesizer
# ---------------------------------------------------------------------------
def synthesizer_node(state: AgentState) -> dict:
    """
    Combines all research findings into a comprehensive final response.
    """
    task_id = state["task_id"]
    research_data = state.get("research_data", [])
    original_prompt = state["messages"][0].content

    publish_event(
        task_id, "Synthesizer", "STATUS",
        "Synthesizing research findings into a final response...",
    )

    # Format research data for the LLM
    research_summary = ""
    for item in research_data:
        research_summary += f"\n--- Step: {item['step']} ---\n"
        research_summary += f"Findings: {item['summary']}\n"

    llm = _get_llm()
    messages = [
        SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"ORIGINAL USER REQUEST:\n{original_prompt}\n\n"
            f"RESEARCH DATA GATHERED:\n{research_summary}\n\n"
            f"Please synthesize all the above into a comprehensive final response."
        )),
    ]

    response = llm.invoke(messages)
    final_result = response.content

    publish_event(
        task_id, "Synthesizer", "THOUGHT",
        f"Final response composed ({len(final_result)} characters).",
        payload={"final_result_preview": final_result[:500]},
    )

    return {
        "final_result": final_result,
        "status": "COMPLETED",
        "messages": [AIMessage(content=final_result)],
    }


# ---------------------------------------------------------------------------
# Routing Logic
# ---------------------------------------------------------------------------
def should_continue_research(state: AgentState) -> Literal["Researcher", "Synthesizer"]:
    """
    Conditional edge: routes back to Researcher if more plan steps remain,
    otherwise advances to Synthesizer.
    """
    plan = state.get("plan", [])
    current_index = state.get("current_step_index", 0)

    if current_index < len(plan):
        return "Researcher"
    return "Synthesizer"


# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------
def build_graph():
    """
    Construct and compile the LangGraph state machine.

    Graph structure:
        START → Planner → Researcher ←─(loop if more steps)
                                    └─→ Synthesizer → END
    """
    workflow = StateGraph(AgentState)

    # Add agent nodes
    workflow.add_node("Planner", planner_node)
    workflow.add_node("Researcher", researcher_node)
    workflow.add_node("Synthesizer", synthesizer_node)

    # Define edges
    workflow.add_edge(START, "Planner")
    workflow.add_edge("Planner", "Researcher")

    # Conditional loop: Researcher → (more steps? → Researcher, done → Synthesizer)
    workflow.add_conditional_edges(
        "Researcher",
        should_continue_research,
        {
            "Researcher": "Researcher",
            "Synthesizer": "Synthesizer",
        },
    )

    workflow.add_edge("Synthesizer", END)

    return workflow.compile()
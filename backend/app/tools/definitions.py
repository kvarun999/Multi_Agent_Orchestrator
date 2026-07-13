"""
LangChain tool wrappers that bridge the LLM's tool-calling interface
to the Celery task queue. Each tool dispatches work to Celery and
waits for the result, keeping the async event loop free.
"""

import json
from langchain_core.tools import tool
from app.worker.tasks import fetch_weather, web_search, calculate_expression


@tool
def weather_lookup(location: str, units: str = "metric") -> str:
    """Look up the current weather conditions for a given city.

    Use this tool when you need real-time weather information such as
    temperature, humidity, wind speed, or general conditions (sunny, rainy, etc.).
    Provide the city name and optional ISO country code.

    Args:
        location: The city and country code, e.g. 'Tokyo, JP' or 'London, GB'.
        units: Temperature units — 'metric' for Celsius or 'imperial' for Fahrenheit.

    Returns:
        A JSON string with weather data or an error message.
    """
    try:
        result = fetch_weather.delay(location=location, units=units)
        data = result.get(timeout=30)
        return json.dumps(data, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Failed to execute weather lookup: {str(e)}"
        })


@tool
def search_web(query: str, count: int = 5) -> str:
    """Search the web for current information on any topic.

    Use this tool when you need to find up-to-date information, facts,
    news, or data that may not be in your training data. Be specific
    with your search query for the best results.

    Args:
        query: The search query string. Be specific and descriptive.
        count: Number of results to return (1-10, default 5).

    Returns:
        A JSON string with search results or an error message.
    """
    try:
        result = web_search.delay(query=query, count=count)
        data = result.get(timeout=30)
        return json.dumps(data, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Failed to execute web search: {str(e)}"
        })


@tool
def calculator(expression: str, description: str = "") -> str:
    """Evaluate a mathematical expression or perform calculations.

    Use this tool when you need to compute numerical results, convert
    units, calculate statistics, or perform any math operations.
    Supports basic arithmetic (+, -, *, /, **), math functions
    (sqrt, sin, cos, log, abs, round), and constants (pi, e).

    Args:
        expression: The math expression to evaluate, e.g. '(25 * 1.8) + 32'.
        description: Brief description of the calculation purpose.

    Returns:
        A JSON string with the computation result or an error message.
    """
    try:
        result = calculate_expression.delay(expression=expression, description=description)
        data = result.get(timeout=15)
        return json.dumps(data, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Failed to evaluate expression: {str(e)}"
        })


# List of all tools for binding to the LLM
ALL_TOOLS = [weather_lookup, search_web, calculator]

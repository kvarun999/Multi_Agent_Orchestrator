"""
Celery task definitions for long-running tool executions.
Each task calls a real external API (driven by environment variables)
and includes robust error handling that returns error strings to the agent
rather than throwing fatal exceptions.
"""

import os
import math
import time
import httpx
from celery import Celery

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "agent_tasks",
    broker=redis_url,
    backend=redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


# ---------------------------------------------------------------------------
# Tool 1: Weather Lookup via OpenWeatherMap
# ---------------------------------------------------------------------------
@celery_app.task(bind=True, max_retries=2, default_retry_delay=3)
def fetch_weather(self, location: str, units: str = "metric") -> dict:
    """
    Fetch current weather data from the OpenWeatherMap API.
    Returns a dict with status and data/message keys.
    """
    api_key = os.getenv("OPENWEATHER_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        return {
            "status": "error",
            "message": (
                f"OpenWeatherMap API key is not configured. "
                f"Cannot retrieve weather for '{location}'. "
                f"Please set the OPENWEATHER_API_KEY environment variable."
            ),
        }

    try:
        # Step 1: Geocode the location to get lat/lon
        geo_url = "http://api.openweathermap.org/geo/1.0/direct"
        geo_params = {"q": location, "limit": 1, "appid": api_key}

        with httpx.Client(timeout=10.0) as client:
            geo_resp = client.get(geo_url, params=geo_params)
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()

        if not geo_data:
            return {
                "status": "error",
                "message": f"Could not find location '{location}'. Please try a different city name.",
            }

        lat = geo_data[0]["lat"]
        lon = geo_data[0]["lon"]
        resolved_name = geo_data[0].get("name", location)
        country = geo_data[0].get("country", "")

        # Step 2: Fetch current weather
        weather_url = "https://api.openweathermap.org/data/2.5/weather"
        weather_params = {
            "lat": lat,
            "lon": lon,
            "units": units,
            "appid": api_key,
        }

        with httpx.Client(timeout=10.0) as client:
            weather_resp = client.get(weather_url, params=weather_params)
            weather_resp.raise_for_status()
            weather_data = weather_resp.json()

        temp = weather_data["main"]["temp"]
        feels_like = weather_data["main"]["feels_like"]
        humidity = weather_data["main"]["humidity"]
        description = weather_data["weather"][0]["description"]
        wind_speed = weather_data["wind"]["speed"]
        unit_label = "°C" if units == "metric" else "°F"
        speed_label = "m/s" if units == "metric" else "mph"

        return {
            "status": "success",
            "data": {
                "location": f"{resolved_name}, {country}",
                "temperature": f"{temp}{unit_label}",
                "feels_like": f"{feels_like}{unit_label}",
                "humidity": f"{humidity}%",
                "condition": description,
                "wind_speed": f"{wind_speed} {speed_label}",
            },
        }

    except httpx.HTTPStatusError as e:
        return {
            "status": "error",
            "message": f"Weather API returned HTTP {e.response.status_code}: {e.response.text[:200]}",
        }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "message": f"Weather API request timed out for '{location}'. The service may be temporarily unavailable.",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Unexpected error fetching weather for '{location}': {str(e)}",
        }


# ---------------------------------------------------------------------------
# Tool 2: Web Search via Brave Search API
# ---------------------------------------------------------------------------
@celery_app.task(bind=True, max_retries=2, default_retry_delay=3)
def web_search(self, query: str, count: int = 5) -> dict:
    """
    Perform a web search using the Brave Search API.
    Returns a dict with status and data/message keys.
    """
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        return {
            "status": "error",
            "message": (
                f"Brave Search API key is not configured. "
                f"Cannot search for '{query}'. "
                f"Please set the BRAVE_SEARCH_API_KEY environment variable."
            ),
        }

    try:
        search_url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }
        params = {"q": query, "count": min(count, 10)}

        with httpx.Client(timeout=15.0) as client:
            resp = client.get(search_url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("web", {}).get("results", [])[:count]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            })

        if not results:
            return {
                "status": "success",
                "data": {
                    "query": query,
                    "results": [],
                    "summary": f"No results found for '{query}'.",
                },
            }

        return {
            "status": "success",
            "data": {
                "query": query,
                "result_count": len(results),
                "results": results,
            },
        }

    except httpx.HTTPStatusError as e:
        return {
            "status": "error",
            "message": f"Search API returned HTTP {e.response.status_code}: {e.response.text[:200]}",
        }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "message": f"Search API request timed out for query '{query}'. The service may be temporarily unavailable.",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Unexpected error searching for '{query}': {str(e)}",
        }


# ---------------------------------------------------------------------------
# Tool 3: Safe Mathematical Calculator
# ---------------------------------------------------------------------------
@celery_app.task(bind=True)
def calculate_expression(self, expression: str, description: str = "") -> dict:
    """
    Safely evaluate a mathematical expression.
    Uses a restricted namespace with only math functions — no arbitrary code execution.
    """
    # Allowed functions/constants for safe evaluation
    safe_namespace = {
        "__builtins__": {},
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": pow,
        "int": int,
        "float": float,
        # Math module functions
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "log10": math.log10,
        "log2": math.log2,
        "ceil": math.ceil,
        "floor": math.floor,
        "pi": math.pi,
        "e": math.e,
    }

    # Basic security: block dangerous patterns
    blocked_keywords = ["import", "exec", "eval", "open", "os.", "sys.", "__", "lambda"]
    expression_lower = expression.lower()
    for keyword in blocked_keywords:
        if keyword in expression_lower:
            return {
                "status": "error",
                "message": f"Expression contains blocked keyword '{keyword}'. Only mathematical expressions are allowed.",
            }

    try:
        result = eval(expression, safe_namespace)
        return {
            "status": "success",
            "data": {
                "expression": expression,
                "result": result,
                "description": description or f"Evaluated: {expression}",
            },
        }
    except ZeroDivisionError:
        return {
            "status": "error",
            "message": f"Division by zero in expression: '{expression}'.",
        }
    except (SyntaxError, TypeError, NameError) as e:
        return {
            "status": "error",
            "message": f"Invalid expression '{expression}': {str(e)}. Use standard math notation.",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error evaluating '{expression}': {str(e)}",
        }
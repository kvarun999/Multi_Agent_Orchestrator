"""
Pydantic input schemas for all custom tools.
These schemas enforce strict validation and provide rich descriptions
that are passed directly to the LLM for tool-use reasoning.
"""

from pydantic import BaseModel, Field


class WeatherSearchInput(BaseModel):
    """Input schema for the Weather Lookup tool."""

    location: str = Field(
        description=(
            "The city name and optional country code for the weather lookup. "
            "Use the format 'City, CountryCode' where CountryCode is an ISO 3166-1 "
            "alpha-2 code. Examples: 'Tokyo, JP', 'San Francisco, US', 'London, GB'."
        )
    )
    units: str = Field(
        default="metric",
        description=(
            "Temperature units for the response. "
            "'metric' returns Celsius, 'imperial' returns Fahrenheit. "
            "Default is 'metric'."
        ),
    )


class WebSearchInput(BaseModel):
    """Input schema for the Web Search tool."""

    query: str = Field(
        description=(
            "The search query string. Be specific and descriptive to get "
            "the most relevant results. For example: 'current GDP of Japan 2024' "
            "instead of just 'Japan GDP'."
        )
    )
    count: int = Field(
        default=5,
        ge=1,
        le=10,
        description=(
            "The number of search results to return. "
            "Must be between 1 and 10. Default is 5."
        ),
    )


class CalculatorInput(BaseModel):
    """Input schema for the Data Calculator / Analysis tool."""

    expression: str = Field(
        description=(
            "A mathematical expression to evaluate. Supports basic arithmetic "
            "(+, -, *, /, **), common functions (sqrt, sin, cos, log, abs, round), "
            "and constants (pi, e). Examples: '(25 * 1.8) + 32', 'sqrt(144)', "
            "'round(3.14159, 2)'. Do NOT include variable assignments or imports."
        )
    )
    description: str = Field(
        default="",
        description=(
            "A brief human-readable description of what this calculation represents. "
            "For example: 'Convert 25°C to Fahrenheit' or 'Calculate area of circle with radius 7'."
        ),
    )

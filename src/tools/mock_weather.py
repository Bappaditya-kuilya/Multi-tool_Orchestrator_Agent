from __future__ import annotations

import random
from typing import Any

from .base import BaseTool


class MockWeatherTool(BaseTool):
    CITIES = {
        "London": {"temperature_c": 15, "condition": "Cloudy", "humidity": 80},
        "New York": {"temperature_c": 22, "condition": "Sunny", "humidity": 65},
        "Tokyo": {"temperature_c": 18, "condition": "Rainy", "humidity": 90},
        "Paris": {"temperature_c": 16, "condition": "Partly Cloudy", "humidity": 75},
        "Sydney": {"temperature_c": 25, "condition": "Clear", "humidity": 60},
    }

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        location = input_data.get("location", "London")
        city_data = self.CITIES.get(location, self.CITIES["London"])
        return {
            "location": location,
            "temperature_c": city_data["temperature_c"] + random.randint(-3, 3),
            "condition": city_data["condition"],
            "humidity": city_data["humidity"],
        }
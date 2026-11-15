"""Live wind conditions from Open-Meteo for emergency context."""

import requests
from typing import Dict, Any

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def get_current_wind(lat: float, lon: float) -> Dict[str, Any]:
    try:
        response = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "wind_speed_10m,wind_direction_10m",
                "wind_speed_unit": "kmh",
                "timezone": "UTC",
            },
            timeout=15,
        )
        response.raise_for_status()
        current = response.json()["current"]
        speed = float(current["wind_speed_10m"])
        direction = float(current["wind_direction_10m"])
        return {
            "source": "Open-Meteo current weather",
            "time": current.get("time"),
            "wind_speed_10m_kmh": round(speed, 1),
            "wind_direction_10m_degrees": round(direction, 1),
            "wind_direction_10m_cardinal": _cardinal(direction),
        }
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Live wind lookup failed: {exc}") from exc


def _cardinal(degrees: float) -> str:
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return names[int((degrees + 22.5) // 45) % 8]

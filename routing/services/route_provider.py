
import requests
from django.conf import settings


def get_route(start, finish):
    """Fetch a driving route from OpenRouteService."""

    api_key = settings.OPENROUTESERVICE_API_KEY
    if not api_key:
        raise RuntimeError("OpenRouteService API key is not configured.")

    url = f"{settings.ORS_BASE_URL.rstrip('/')}/v2/directions/driving-car/geojson"

    payload = {
        "coordinates": [
            [start["longitude"], start["latitude"]],
            [finish["longitude"], finish["latitude"]],
        ]
    }

    response = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
        timeout=(5, 20),
    )
    response.raise_for_status()

    data = response.json()
    features = data.get("features", [])

    if not features:
        raise ValueError("Routing provider returned no route.")

    properties = features[0].get("properties", {})
    summary = properties.get("summary", {})

    return {
        "geometry": features[0]["geometry"],
        "distance_meters": summary["distance"],
        "duration_seconds": summary["duration"],
    }

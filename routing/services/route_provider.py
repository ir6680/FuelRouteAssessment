
import logging
import re

import requests
from django.conf import settings


logger = logging.getLogger(__name__)


class RouteProviderError(RuntimeError):
    def __init__(self, message, provider_calls=0):
        super().__init__(message)
        self.provider_calls = provider_calls


def _safe_response_excerpt(response, api_key):
    """Return a short provider response excerpt with credentials/coordinates redacted."""
    if response is None:
        return ""
    try:
        body = response.text or ""
    except Exception:
        return ""
    if api_key:
        body = body.replace(api_key, "[REDACTED]")
    body = re.sub(
        r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*",
        r"\1[REDACTED]",
        body,
    )
    body = re.sub(
        r"(?i)((?:api[_ -]?key|authorization|access[_ -]?token|token|client[_ -]?secret)\s*[\"']?\s*[:=]\s*[\"']?)[^\s,\"'&}]+",
        r"\1[REDACTED]",
        body,
    )
    body = re.sub(
        r'(?i)("coordinates"\s*:\s*)\[[^\]]*(?:\][^\]]*)?\]',
        r'\1[REDACTED]',
        body,
    )
    body = re.sub(r"[\r\n\t]+", " ", body)
    body = " ".join(body.split())
    return body[:500]


def _log_provider_failure(exc, api_key):
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    excerpt = _safe_response_excerpt(response, api_key)
    logger.warning(
        "OpenRouteService request failed exception_type=%s http_status=%s response_excerpt=%r",
        type(exc).__name__,
        status_code,
        excerpt,
    )


def get_route(start, finish):
    """Fetch a driving route from OpenRouteService."""

    api_key = settings.OPENROUTESERVICE_API_KEY
    if not api_key:
        raise RouteProviderError("OpenRouteService API key is not configured.")

    url = f"{settings.ORS_BASE_URL.rstrip('/')}/v2/directions/driving-car/geojson"

    payload = {
        "coordinates": [
            [start["longitude"], start["latitude"]],
            [finish["longitude"], finish["latitude"]],
        ]
    }

    try:
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
    except requests.RequestException as exc:
        _log_provider_failure(exc, api_key)
        raise RouteProviderError("OpenRouteService route request failed.", 1) from exc
    except ValueError as exc:
        _log_provider_failure(exc, api_key)
        raise RouteProviderError("OpenRouteService returned invalid JSON.", 1) from exc
    features = data.get("features", [])

    if not features:
        raise ValueError("Routing provider returned no route.")

    properties = features[0].get("properties", {})
    summary = properties.get("summary", {})

    try:
        return {
            "geometry": features[0]["geometry"],
            "distance_meters": summary["distance"],
            "duration_seconds": summary["duration"],
        }
    except (KeyError, TypeError) as exc:
        raise RouteProviderError("OpenRouteService returned an incomplete route.", 1) from exc

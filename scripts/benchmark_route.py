"""Repeatable, network-free POST benchmark for /api/v1/route/.

Run from the repository root with:
    .\\venv\\Scripts\\python.exe scripts\\benchmark_route.py

Only OpenRouteService is mocked. CSV processing, Gazetteer centroids, station
filtering, route-mile projection, optimization, response rendering, and the
configured file cache all run through the Django endpoint.
"""
import json
import argparse
import logging
import os
import sys
import statistics
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.core.cache import cache
from django.test import Client

from routing.services import route_service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Make exactly one live cold routing request, then measure a warm cache hit.")
    args = parser.parse_args()
    # Mock benchmark inputs remain distinct from a user's real route cache key.
    start = {"lat": 40.7129, "lng": -74.0061}
    finish = {"lat": 41.8782, "lng": -87.6299}
    if args.live:
        start = {"lat": 40.7128, "lng": -74.0060}
        finish = {"lat": 41.8781, "lng": -87.6298}
    coordinates = [
        [
            -74.006 + (-87.6298 + 74.006) * index / 200,
            40.7128 + (41.8781 - 40.7128) * index / 200,
        ]
        for index in range(201)
    ]
    route_fixture = {
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "distance_meters": 802.76 * 1609.344,
        "duration_seconds": 48000,
    }
    cache.delete(
        route_service._cache_key(
            route_service.resolve_location(start),
            route_service.resolve_location(finish),
        )
    )
    client = Client()
    payload = {"start": start, "finish": finish}
    warm_samples = []
    stage_records = []

    class StageHandler(logging.Handler):
        def emit(self, record):
            if record.name.startswith("routing."):
                stage_records.append(record.getMessage())

    handler = StageHandler()
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    stage_logger = logging.getLogger("routing")
    previous_level = stage_logger.level
    stage_logger.setLevel(logging.INFO)

    provider_mock = patch.object(route_service, "get_route", return_value=route_fixture)
    routing_mock = None
    if not args.live:
        routing_mock = provider_mock.start()
    try:
        started = time.perf_counter()
        cold_response = client.post(
            "/api/v1/route/", payload, content_type="application/json"
        )
        cold_seconds = time.perf_counter() - started
        if cold_response.status_code != 200:
            raise RuntimeError(
                f"Cold benchmark request returned HTTP {cold_response.status_code}: "
                f"{cold_response.content[:300]!r}"
            )

        warm_response = None
        for _ in range(5):
            started = time.perf_counter()
            warm_response = client.post(
                "/api/v1/route/", payload, content_type="application/json"
            )
            warm_samples.append(time.perf_counter() - started)
            if warm_response.status_code != 200:
                raise RuntimeError(
                    f"Warm benchmark request returned HTTP {warm_response.status_code}"
                )

    finally:
        root_logger.removeHandler(handler)
        stage_logger.setLevel(previous_level)
        if not args.live:
            provider_mock.stop()

    print(json.dumps({
        "mode": "live OpenRouteService once" if args.live else "local Django endpoint; OpenRouteService mocked",
        "cold_seconds": round(cold_seconds, 5),
        "warm_seconds_median_5": round(statistics.median(warm_samples), 5),
        "warm_seconds_samples": [round(sample, 5) for sample in warm_samples],
        "nearby_candidates": cold_response.json()["data_quality"]["stations_near_route_count"],
        "cold_cache": cold_response.json()["cache"],
        "warm_cache": warm_response.json()["cache"],
        "warm_api_calls": warm_response.json()["api_calls"],
        "routing_provider_mock_calls": routing_mock.call_count if routing_mock else None,
        "stage_timings": stage_records,
    }, indent=2))


if __name__ == "__main__":
    main()

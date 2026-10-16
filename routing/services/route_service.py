"""Cached route and offline fuel-price orchestration."""
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

from routing.services.fuel_optimizer import optimize_fuel_stops
from routing.services.gazetteer import resolve_place
from routing.services.route_geometry import geometry_length_miles, station_route_position
from routing.services.route_provider import get_route
from routing.services.station_provider import FUEL_CSV_PATH, get_fuel_stations_near_route


def resolve_location(value):
    """Resolve explicit coordinates or a unique Gazetteer city/state centroid."""
    if isinstance(value, dict):
        return {"latitude": value["lat"], "longitude": value["lng"], "geocode_precision": "user_coordinates"}
    parts = [part.strip() for part in value.split(",")]
    if len(parts) >= 2:
        place, result = resolve_place(parts[0], parts[-1].upper())
        if place and result == "matched":
            return {"latitude": place["latitude"], "longitude": place["longitude"], "geocode_precision": place["geocode_precision"]}
        if result == "ambiguous":
            raise ValueError("Location is ambiguous in the Census Gazetteer; provide coordinates.")
    raise ValueError("Location could not be resolved. Provide a US city/state or lat/lng coordinates.")


def _cache_key(start, finish):
    data = {"start": start, "finish": finish, "csv_mtime": FUEL_CSV_PATH.stat().st_mtime_ns if FUEL_CSV_PATH.exists() else None}
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return "fuelroute:v2:" + digest


def build_route_result(start_value, finish_value):
    start = resolve_location(start_value)
    finish = resolve_location(finish_value)
    key = _cache_key(start, finish)
    cached = cache.get(key)
    if cached is not None:
        result = cached
        result["api_calls"] = {"routing": 0, "geocoding": 0, "station_discovery": 0}
        result["cache"] = {"hit": True}
        return result

    route = get_route(start, finish)
    geometry = route["geometry"]
    route_miles = route["distance_meters"] / 1609.344
    geometry_miles = geometry_length_miles(geometry)
    route_mile_scale = route_miles / geometry_miles if geometry_miles else 0
    nearby, coverage = get_fuel_stations_near_route(geometry)
    matched = []
    for station in nearby:
        position = station_route_position(station, geometry)
        matched.append({**station, "route_mile": min(route_miles, position["route_mile"] * route_mile_scale), "distance_to_route_miles": position["distance_to_route_miles"]})
    optimized = optimize_fuel_stops(route_miles, matched)
    result = {
        "route": {"type": "Feature", "geometry": geometry, "properties": {"distance_miles": round(route_miles, 2), "duration_minutes": round(route["duration_seconds"] / 60, 2)}},
        "fuel": optimized,
        "data_quality": {
            "station_source": "fuel-price CSV with US Census Gazetteer centroids",
            "station_coordinates_warning": "Centroids represent city/place locations, not verified station locations; route proximity and route-mile positions are approximate.",
            "route_mile_method": "Centroid projection onto route geometry, scaled proportionally to OpenRouteService driving distance; this is an estimate, not exact along-road station mileage.",
            "station_coverage": coverage,
            "stations_near_route_count": len(nearby),
            "price_policy": "minimum price per consistent station ID",
            "price_unit_assumption": "USD per gallon",
        },
        "api_calls": {"routing": 1, "geocoding": 0, "station_discovery": 0},
        "cache": {"hit": False},
    }
    cache.set(key, result, timeout=60 * 60 * 24)
    return result

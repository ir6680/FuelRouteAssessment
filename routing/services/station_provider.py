"""Offline fuel station locations derived from the Census Gazetteer.

Coordinates are city/place centroids, not verified station entrances. This
provider deliberately makes no OSM requests and never manufactures prices.
"""
from functools import lru_cache
import logging
from math import cos, radians
from pathlib import Path
import time

from django.conf import settings

from routing.services.csv_cleaner import clean_csv
from routing.services.gazetteer import (
    COUNTY_SUBDIVISIONS_PATH,
    PLACES_PATH,
    load_county_subdivisions,
    load_gazetteer,
    resolve_place,
)


FUEL_CSV_PATH = Path(settings.BASE_DIR) / "data" / "fuel-prices-for-be-assessment.csv"
logger = logging.getLogger(__name__)


def _file_signature(path):
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def source_data_signature():
    """Signatures for inputs that affect station coordinates or prices."""
    return (
        _file_signature(FUEL_CSV_PATH),
        _file_signature(PLACES_PATH),
        _file_signature(COUNTY_SUBDIVISIONS_PATH),
    )


_gazetteer_signature = None


@lru_cache(maxsize=2)
def _load_fuel_stations_cached(signature):
    csv_stations, csv_report, excluded = clean_csv(FUEL_CSV_PATH)
    stations = []
    unmatched = {"not_found": 0, "ambiguous": 0}
    place_cache = {}
    for station in csv_stations:
        place_key = (station["city"].casefold(), station["state"])
        if place_key not in place_cache:
            place_cache[place_key] = resolve_place(
                station["city"], station["state"]
            )
        place, result = place_cache[place_key]
        if not place:
            unmatched[result] = unmatched.get(result, 0) + 1
            continue
        stations.append({
            **station,
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "geocode_precision": place["geocode_precision"],
            "geocode_source": "US Census Gazetteer",
            "coordinate_warning": (
                "City/state centroid; not the verified fuel station location."
            ),
        })
    coverage = {
        "csv_unique_stations": len(csv_stations),
        "located_stations": len(stations),
        "unmatched_stations": len(csv_stations) - len(stations),
        "coverage_percent": round(100 * len(stations) / len(csv_stations), 2) if csv_stations else 0,
        "unmatched_by_reason": unmatched,
        "excluded_csv_rows": csv_report["excluded_rows"],
        "excluded_csv_reasons": csv_report["excluded_by_reason"],
    }
    return stations, coverage, csv_report


def load_fuel_stations():
    """Load cleaned CSV stations and centroids once per source-data version."""
    global _gazetteer_signature
    signature = source_data_signature()
    previous_hits = _load_fuel_stations_cached.cache_info().hits
    gazetteer_signature = signature[1:]
    if _gazetteer_signature is None or gazetteer_signature != _gazetteer_signature:
        load_gazetteer.cache_clear()
        load_county_subdivisions.cache_clear()
        _load_fuel_stations_cached.cache_clear()
    _gazetteer_signature = gazetteer_signature
    started = time.perf_counter()
    result = _load_fuel_stations_cached(signature)
    cache_hit = _load_fuel_stations_cached.cache_info().hits > previous_hits
    logger.info(
        "station_data_load duration_seconds=%.6f cache_hit=%s station_count=%s",
        time.perf_counter() - started,
        cache_hit,
        len(result[0]),
    )
    return result


def _route_bounds(route_geometry, radius_miles):
    coordinates = route_geometry.get("coordinates", [])
    if not coordinates:
        raise ValueError("Route geometry has no coordinates.")

    latitudes = [point[1] for point in coordinates]
    longitudes = [point[0] for point in coordinates]
    lat_margin = radius_miles / 68.0
    min_lat = min(latitudes) - lat_margin
    max_lat = max(latitudes) + lat_margin

    max_abs_lat = max(abs(min_lat), abs(max_lat))
    if max_abs_lat >= 89.9:
        lon_margin = None
    else:
        lon_margin = radius_miles / (69.0 * cos(radians(max_abs_lat)))

    min_lon = min(longitudes)
    max_lon = max(longitudes)
    if max_lon - min_lon > 180:
        lon_margin = None

    return min_lat, max_lat, min_lon, max_lon, lon_margin


def get_fuel_stations_near_route(route_geometry, radius_miles=3.0):
    """Return Gazetteer-located CSV stations near the route, with coverage."""
    from routing.services.route_geometry import distance_to_route

    started = time.perf_counter()
    stations, coverage, _report = load_fuel_stations()
    min_lat, max_lat, min_lon, max_lon, lon_margin = _route_bounds(
        route_geometry, radius_miles
    )
    nearby = []
    bounding_box_candidates = 0
    exact_distance_checks = 0
    for station in stations:
        latitude = station["latitude"]
        longitude = station["longitude"]
        if not min_lat <= latitude <= max_lat:
            continue
        if lon_margin is not None and not (
            min_lon - lon_margin <= longitude <= max_lon + lon_margin
        ):
            continue
        bounding_box_candidates += 1
        exact_distance_checks += 1
        distance = distance_to_route(station, route_geometry)
        if distance <= radius_miles:
            nearby.append({**station, "distance_to_route_miles": distance})
    logger.info(
        "station_candidate_filter duration_seconds=%.6f located_station_count=%s bounding_box_candidates=%s exact_distance_checks=%s nearby_count=%s",
        time.perf_counter() - started,
        len(stations),
        bounding_box_candidates,
        exact_distance_checks,
        len(nearby),
    )
    return nearby, coverage

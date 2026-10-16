"""Offline fuel station locations derived from the Census Gazetteer.

Coordinates are city/place centroids, not verified station entrances. This
provider deliberately makes no OSM requests and never manufactures prices.
"""
from pathlib import Path

from django.conf import settings

from routing.services.csv_cleaner import clean_csv
from routing.services.gazetteer import resolve_place


FUEL_CSV_PATH = Path(settings.BASE_DIR) / "data" / "fuel-prices-for-be-assessment.csv"


def load_fuel_stations():
    csv_stations, csv_report, excluded = clean_csv(FUEL_CSV_PATH)
    stations = []
    unmatched = {"not_found": 0, "ambiguous": 0}
    for station in csv_stations:
        place, result = resolve_place(station["city"], station["state"])
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


def get_fuel_stations_near_route(route_geometry, radius_miles=3.0):
    """Return Gazetteer-located CSV stations near the route, with coverage."""
    from routing.services.route_geometry import distance_to_route

    stations, coverage, _report = load_fuel_stations()
    nearby = []
    for station in stations:
        distance = distance_to_route(station, route_geometry)
        if distance <= radius_miles:
            nearby.append({**station, "distance_to_route_miles": distance})
    return nearby, coverage

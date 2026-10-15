
import requests
from django.conf import settings


def geocode_address(station_name, address, city, state):
    """Return coordinates only when the result matches the requested city/state."""

    api_key = settings.OPENROUTESERVICE_API_KEY
    if not api_key:
        raise RuntimeError("OpenRouteService API key is not configured.")

    url = f"{settings.GEOCODING_BASE_URL.rstrip('/')}/search"

    response = requests.get(
        url,
        headers={"Authorization": api_key},
        params={
            "text": f"{station_name}, {address}, {city}, {state}, USA",
            "size": 5,
            "boundary.country": "USA",
            "layers": "address,venue",
            "sources": "osm",
        },
        timeout=(5, 20),
    )
    response.raise_for_status()

    features = response.json().get("features", [])

    expected_city = city.casefold().strip()
    expected_state = state.upper().strip()

    for feature in features:
        props = feature.get("properties", {})
        label = (props.get("label") or "").casefold()
        locality = (props.get("locality") or "").casefold()
        region_code = (props.get("region_a") or "").upper()
        country_code = (props.get("country_a") or "").upper()

        # Reject results outside the United States or wrong state.
        if country_code and country_code not in {"USA", "US"}:
            continue
        if region_code and region_code != expected_state:
            continue

        # Require the requested city to be present in the result.
        if expected_city not in locality and expected_city not in label:
            continue

        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if len(coordinates) != 2:
            continue

        # Reject city-level matches; they are not station-level locations.
        if props.get("layer") not in {"address", "venue"}:
            continue

        return {
            "longitude": coordinates[0],
            "latitude": coordinates[1],
            "matched_label": props.get("label"),
            "verified_city_state": True,
            "exact_station_verified": False,
        }

    return None
# new addition


def geocode_city_state(city, state):
    """Return a unique city-level coordinate candidate when unambiguous."""

    api_key = settings.OPENROUTESERVICE_API_KEY
    if not api_key:
        raise RuntimeError("OpenRouteService API key is not configured.")

    url = f"{settings.GEOCODING_BASE_URL.rstrip('/')}/search"

    response = requests.get(
        url,
        headers={"Authorization": api_key},
        params={
            "text": f"{city}, {state}, USA",
            "size": 10,
            "boundary.country": "USA",
        },
        timeout=(5, 20),
    )
    response.raise_for_status()

    features = response.json().get("features", [])
    expected_city = city.casefold().strip()
    expected_state = state.upper().strip()

    candidates = {}

    for feature in features:
        props = feature.get("properties", {})
        country = (props.get("country_a") or "").upper()
        region = (props.get("region_a") or "").upper()

        if country not in {"USA", "US"}:
            continue
        if region != expected_state:
            continue

        locality = (props.get("locality") or "").casefold().strip()
        name = (props.get("name") or "").casefold().strip()

        if expected_city not in {locality, name}:
            continue

        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if len(coordinates) != 2:
            continue

        longitude, latitude = coordinates

        # Collapse duplicate provider results for the same coordinates.
        key = (round(longitude, 5), round(latitude, 5))

        candidates[key] = {
            "longitude": longitude,
            "latitude": latitude,
            "matched_label": props.get("label"),
            "verified_city_state": True,
            "exact_station_verified": False,
            "geocode_precision": "city_level_candidate",
        }

    # Do not arbitrarily choose between distinct coordinate candidates.
    if len(candidates) != 1:
        return None

    return next(iter(candidates.values()))

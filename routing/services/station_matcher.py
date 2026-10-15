
import re
import unicodedata
from decimal import Decimal


def normalize_name(value):
    """Normalize station names for conservative comparison."""
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def extract_station_number(value):
    """Extract a trailing station number, when present."""
    match = re.search(r"#\s*(\d+)\s*$", value or "")
    return match.group(1) if match else None


def match_station_price(osm_station, csv_stations):
    """
    Return a CSV station only when name/brand and location evidence
    are sufficiently strong. Otherwise return None.
    """
    osm_name = normalize_name(osm_station.get("name"))
    osm_brand = normalize_name(osm_station.get("brand"))
    osm_operator = normalize_name(osm_station.get("operator"))

    osm_names = {name for name in (osm_name, osm_brand, osm_operator) if name}

    candidates = []

    for station in csv_stations:
        csv_name = normalize_name(station.get("name"))
        csv_number = extract_station_number(station.get("name"))

        # Avoid treating a generic brand match as proof of a specific store.
        if not csv_name or not osm_names:
            continue

        name_match = any(
            csv_name == name
            or csv_name.startswith(name + " ")
            or name.startswith(csv_name + " ")
            for name in osm_names
        )

        if not name_match:
            continue

        # If CSV has a store number, OSM must also explicitly contain it.
        osm_number = extract_station_number(
            osm_station.get("name") or ""
        )
        if csv_number and csv_number != osm_number:
            continue

        # City/state must be available and consistent for a safe match.
        osm_city = normalize_name(osm_station.get("city"))
        osm_state = normalize_name(osm_station.get("state"))

        if not osm_city or not osm_state:
            continue

        if osm_city != normalize_name(station.get("city")):
            continue

        if osm_state != normalize_name(station.get("state")):
            continue

        candidates.append(station)

    if len(candidates) != 1:
        return None

    return {
        "station_id": candidates[0]["station_id"],
        "name": candidates[0]["name"],
        "price": Decimal(str(candidates[0]["price"])),
        "match_status": "candidate_match",
    }

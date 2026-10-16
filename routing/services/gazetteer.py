"""Census Gazetteer location resolver for fuel-route stations.

Uses Census Places first, then County Subdivisions. Ambiguous matches are
rejected rather than choosing a potentially incorrect coordinate.
"""

import csv
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

REFERENCE_DIR = Path(settings.BASE_DIR) / "data" / "reference"
PLACES_PATH = REFERENCE_DIR / "2026_Gaz_place_national.txt"
COUNTY_SUBDIVISIONS_PATH = REFERENCE_DIR / "2026_Gaz_cousubs_national.txt"

CENSUS_SUFFIXES = (
    " city",
    " town",
    " village",
    " borough",
    " cdp",
    " municipality",
)


def normalize_place_name(value):
    """Normalize common spelling/punctuation differences in place names."""
    value = (value or "").strip().casefold()
    value = re.sub(r"\bst\.?\s+", "saint ", value)
    value = re.sub(r"\bft\.?\s+", "fort ", value)
    value = re.sub(r"\bmt\.?\s+", "mount ", value)
    value = value.replace("&", " and ")
    value = re.sub(r"[’'`.]", "", value)
    value = re.sub(r"[^a-z0-9\s-]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _load_census_file(path, source, required_columns):
    if not path.exists():
        raise FileNotFoundError(f"Census Gazetteer file not found: {path}")

    index = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="|")
        if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
            raise ValueError(f"Unexpected Census Gazetteer columns in {path.name}")

        for row in reader:
            state = (row.get("USPS") or "").strip().upper()
            name = normalize_place_name(row.get("NAME"))
            if not state or not name:
                continue
            try:
                latitude = float(row["INTPTLAT"])
                longitude = float(row["INTPTLONG"])
            except (TypeError, ValueError):
                continue

            candidate = {
                "latitude": latitude,
                "longitude": longitude,
                "census_name": (row.get("NAME") or "").strip(),
                "state": state,
                "geocode_precision": "city_or_place_centroid" if source == "places" else "county_subdivision_centroid",
                "match_source": source,
                "geoid": (row.get("GEOID") or "").strip(),
            }
            index.setdefault((name, state), []).append(candidate)
    return index


def _file_signature(path):
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=2)
def _load_gazetteer_cached(_signature):
    return _load_census_file(
        PLACES_PATH,
        "places",
        {"USPS", "NAME", "INTPTLAT", "INTPTLONG"},
    )


def load_gazetteer():
    """Load Places indexed by normalized name, refreshing when the file changes."""
    return _load_gazetteer_cached(_file_signature(PLACES_PATH))


load_gazetteer.cache_clear = _load_gazetteer_cached.cache_clear


@lru_cache(maxsize=2)
def _load_county_subdivisions_cached(_signature):
    return _load_census_file(
        COUNTY_SUBDIVISIONS_PATH,
        "county_subdivision",
        {"USPS", "NAME", "INTPTLAT", "INTPTLONG", "GEOID"},
    )


def load_county_subdivisions():
    """Load subdivisions, refreshing when the file changes."""
    return _load_county_subdivisions_cached(
        _file_signature(COUNTY_SUBDIVISIONS_PATH)
    )


load_county_subdivisions.cache_clear = _load_county_subdivisions_cached.cache_clear


def _candidate_keys(city):
    """Names worth trying without fuzzy or prefix-based guessing."""
    names = [city]
    for suffix in CENSUS_SUFFIXES:
        if city.endswith(suffix):
            names.append(city[: -len(suffix)].strip())
        else:
            names.append(city + suffix)
    return list(dict.fromkeys(name for name in names if name))


def _resolve_from_index(city, state, index, source):
    found = []
    for name in _candidate_keys(city):
        found.extend(index.get((name, state), []))

    # Deduplicate identical Census records/coordinates, but do not merge distinct places.
    unique = {}
    for item in found:
        key = (item["geoid"] or item["census_name"], item["latitude"], item["longitude"])
        unique[key] = item

    if len(unique) == 1:
        result = next(iter(unique.values())).copy()
        result["match_source"] = source
        return result, "matched"
    if len(unique) > 1:
        return None, "ambiguous"
    return None, "not_found"


def resolve_place(city, state):
    """Resolve a city/state to a Census centroid and explain the result status."""
    normalized_city = normalize_place_name(city)
    normalized_state = (state or "").strip().upper()
    if not normalized_city or len(normalized_state) != 2:
        return None, "invalid_input"

    result, status = _resolve_from_index(
        normalized_city, normalized_state, load_gazetteer(), "places"
    )
    if result is not None or status == "ambiguous":
        return result, status

    result, status = _resolve_from_index(
        normalized_city,
        normalized_state,
        load_county_subdivisions(),
        "county_subdivision",
    )
    return result, status


def find_place(city, state):
    """Backward-compatible API: return a unique place or None."""
    result, _status = resolve_place(city, state)
    return result

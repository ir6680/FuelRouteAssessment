"""One-pass Census location coverage report. Does not call external APIs."""

import os
from collections import defaultdict, Counter
from pathlib import Path
import csv

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from routing.services.csv_cleaner import clean_csv
from routing.services.gazetteer import normalize_place_name, resolve_place

DATA_PATH = Path("data/fuel-prices-for-be-assessment.csv")
REPORT_PATH = Path("data/reference/location_match_report.csv")

stations, cleaning_report, excluded = clean_csv(str(DATA_PATH))
city_pairs = defaultdict(list)
for station in stations:
    key = (normalize_place_name(station["city"]), station["state"].strip().upper())
    city_pairs[key].append(station)

results = []
matched_pair_count = 0
matched_station_count = 0
status_pairs = Counter()
status_stations = Counter()
source_pairs = Counter()
source_stations = Counter()

for (city, state), records in sorted(city_pairs.items()):
    place, status = resolve_place(city, state)
    count = len(records)
    status_pairs[status] += 1
    status_stations[status] += count

    if place is not None:
        matched_pair_count += 1
        matched_station_count += count
        source = place["match_source"]
        source_pairs[source] += 1
        source_stations[source] += count
        latitude = place["latitude"]
        longitude = place["longitude"]
        census_name = place["census_name"]
        precision = place["geocode_precision"]
    else:
        source = "unresolved"
        latitude = longitude = census_name = precision = ""

    results.append({
        "city": city,
        "state": state,
        "station_count": count,
        "status": status,
        "match_source": source,
        "census_name": census_name,
        "latitude": latitude,
        "longitude": longitude,
        "geocode_precision": precision,
    })

pair_total = len(city_pairs)
station_total = len(stations)
pair_rate = matched_pair_count / pair_total * 100 if pair_total else 0
station_rate = matched_station_count / station_total * 100 if station_total else 0

REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
with REPORT_PATH.open("w", encoding="utf-8", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=list(results[0].keys()) if results else [
        "city", "state", "station_count", "status", "match_source", "census_name",
        "latitude", "longitude", "geocode_precision",
    ])
    writer.writeheader()
    writer.writerows(results)

print("\n--- CENSUS LOCATION MATCH REPORT ---")
print(f"Cleaned US stations: {station_total}")
print(f"Unique city/state pairs: {pair_total}")
print(f"Matched city/state pairs: {matched_pair_count} ({pair_rate:.2f}%)")
print(f"Stations with coordinates: {matched_station_count} ({station_rate:.2f}%)")
print("\n--- MATCH SOURCES ---")
for source in ("places", "county_subdivision"):
    print(f"{source}: {source_pairs[source]} pairs, {source_stations[source]} stations")
print("\n--- UNRESOLVED STATUSES ---")
for status in ("not_found", "ambiguous", "invalid_input"):
    print(f"{status}: {status_pairs[status]} pairs, {status_stations[status]} stations")
print(f"\nDetailed report saved to: {REPORT_PATH}")
print("No external geocoding API calls were made.")

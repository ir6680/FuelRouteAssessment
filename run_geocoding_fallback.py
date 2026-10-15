"""Run a resumable, city-level geocoding fallback for unmatched Census locations.

Run from the project root:
    python run_geocoding_fallback.py

The original location_match_report.csv is never modified. Results are checkpointed
in geocoding_city_fallback.csv and merged into location_match_report_with_fallback.csv.
"""

import csv
import os
import time
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from routing.services.geocoder import geocode_city_state  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
REPORT_PATH = BASE_DIR / "data" / "reference" / "location_match_report.csv"
CHECKPOINT_PATH = BASE_DIR / "data" / "reference" / "geocoding_city_fallback.csv"
MERGED_PATH = BASE_DIR / "data" / "reference" / "location_match_report_with_fallback.csv"

CHECKPOINT_FIELDS = [
    "city", "state", "station_count", "status", "matched_label",
    "latitude", "longitude", "geocode_precision", "exact_station_verified", "error",
]


def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_checkpoint_row(row):
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not CHECKPOINT_PATH.exists() or CHECKPOINT_PATH.stat().st_size == 0
    with CHECKPOINT_PATH.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CHECKPOINT_FIELDS)
        if needs_header:
            writer.writeheader()
        writer.writerow(row)
        file.flush()
        os.fsync(file.fileno())


def main():
    if not REPORT_PATH.exists():
        raise FileNotFoundError(f"Matching report not found: {REPORT_PATH}")

    report_rows = read_csv(REPORT_PATH)
    not_found = [row for row in report_rows if row.get("status", "").strip() == "not_found"]

    previous = {}
    if CHECKPOINT_PATH.exists():
        for row in read_csv(CHECKPOINT_PATH):
            key = (row.get("city", "").strip().casefold(), row.get("state", "").strip().upper())
            previous[key] = row

    pending = []
    for row in not_found:
        key = (row.get("city", "").strip().casefold(), row.get("state", "").strip().upper())
        if key not in previous:
            pending.append(row)

    print("--- CITY GEOCODING FALLBACK ---")
    print("Original report rows:", len(report_rows))
    print("Not-found pairs:", len(not_found))
    print("Already checkpointed:", len(not_found) - len(pending))
    print("Pairs remaining:", len(pending))
    print("Checkpoint:", CHECKPOINT_PATH)
    print("Merged report:", MERGED_PATH)

    for index, row in enumerate(pending, start=1):
        city = row["city"].strip()
        state = row["state"].strip().upper()
        result_row = {
            "city": city,
            "state": state,
            "station_count": row.get("station_count", "0"),
            "status": "unresolved",
            "matched_label": "",
            "latitude": "",
            "longitude": "",
            "geocode_precision": "",
            "exact_station_verified": "False",
            "error": "",
        }

        try:
            result = geocode_city_state(city, state)
            if result:
                result_row.update({
                    "status": "candidate",
                    "matched_label": result.get("matched_label", ""),
                    "latitude": result.get("latitude", ""),
                    "longitude": result.get("longitude", ""),
                    "geocode_precision": result.get("geocode_precision", "city_level_candidate"),
                    "exact_station_verified": str(bool(result.get("exact_station_verified", False))),
                })
        except Exception as exc:  # record failures and continue with the batch
            result_row["status"] = "error"
            result_row["error"] = type(exc).__name__

        write_checkpoint_row(result_row)
        previous[(city.casefold(), state)] = result_row

        if index == 1 or index % 25 == 0 or index == len(pending):
            print(f"Processed {index}/{len(pending)}: {city}, {state} -> {result_row['status']}")

        # Keep requests below typical free-tier rate limits.
        if index < len(pending):
            time.sleep(0.7)

    # Merge fallback candidates into a new report; leave the original untouched.
    merged_rows = []
    candidate_count = 0
    unresolved_count = 0
    error_count = 0

    for original in report_rows:
        row = dict(original)
        key = (row.get("city", "").strip().casefold(), row.get("state", "").strip().upper())
        fallback = previous.get(key)
        if row.get("status", "").strip() == "not_found" and fallback:
            row["fallback_status"] = fallback.get("status", "")
            if fallback.get("status") == "candidate":
                row["status"] = "fallback_candidate"
                row["match_source"] = "city_geocoder_fallback"
                row["census_name"] = fallback.get("matched_label", "")
                row["latitude"] = fallback.get("latitude", "")
                row["longitude"] = fallback.get("longitude", "")
                row["geocode_precision"] = fallback.get("geocode_precision", "city_level_candidate")
                candidate_count += 1
            elif fallback.get("status") == "error":
                error_count += 1
                unresolved_count += int(row.get("station_count") or 0)
            else:
                unresolved_count += int(row.get("station_count") or 0)
        merged_rows.append(row)

    fieldnames = list(merged_rows[0].keys()) if merged_rows else []
    with MERGED_PATH.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged_rows)

    matched_pairs = sum(row.get("status") in {"matched", "fallback_candidate"} for row in merged_rows)
    total_pairs = len(merged_rows)
    total_stations = sum(int(row.get("station_count") or 0) for row in merged_rows)
    stations_with_coords = sum(
        int(row.get("station_count") or 0)
        for row in merged_rows
        if row.get("status") in {"matched", "fallback_candidate"}
        and row.get("latitude") not in (None, "")
        and row.get("longitude") not in (None, "")
    )

    print("\n--- FINAL FALLBACK SUMMARY ---")
    print("Fallback candidates:", candidate_count)
    print("Pairs still unresolved/errors:", sum(row.get("status") in {"not_found", "ambiguous"} for row in merged_rows))
    print("Geocoding errors in checkpoint:", error_count)
    print("City/state match rate:", f"{matched_pairs / total_pairs * 100:.2f}%" if total_pairs else "0.00%")
    print("Stations with coordinates:", f"{stations_with_coords}/{total_stations}")
    print("Station coverage:", f"{stations_with_coords / total_stations * 100:.2f}%" if total_stations else "0.00%")
    print("Saved merged report:", MERGED_PATH)
    print("Note: fallback candidates are city-level, not exact fuel-station coordinates.")


if __name__ == "__main__":
    main()

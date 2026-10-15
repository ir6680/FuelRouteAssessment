
import csv
import unicodedata
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path


REQUIRED_COLUMNS = {
    "OPIS Truckstop ID",
    "Truckstop Name",
    "Address",
    "City",
    "State",
    "Rack ID",
    "Retail Price",
}

US_STATES = {
    "AL", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY", "AK", "HI", "DC",
}

NON_US_PROVINCES = {
    "AB", "BC", "MB", "NB", "NL", "NS", "ON", "PE", "QC", "SK","YT",
}


def normalize_text(value):
    """Normalize Unicode and whitespace without losing original data."""
    value = unicodedata.normalize("NFKC", value or "")
    return " ".join(value.split())


def clean_csv(file_path):
    """Validate CSV rows and select one price per consistent US station ID."""
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Fuel-price CSV not found: {path}")

    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("CSV exceeds the 20 MB import limit.")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError("CSV is empty or has no header.")

        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("CSV contains duplicate column names.")

        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")

        groups = defaultdict(list)
        excluded = []
        exact_rows = set()
        exact_duplicate_rows = 0
        source_rows = 0

        for line_number, raw in enumerate(reader, start=2):
            source_rows += 1
            row = {
                key: normalize_text(value)
                for key, value in raw.items()
                if key is not None
            }

            fingerprint = tuple(
                row.get(column, "") for column in sorted(REQUIRED_COLUMNS)
            )

            if fingerprint in exact_rows:
                exact_duplicate_rows += 1
            exact_rows.add(fingerprint)

            station_id = row.get("OPIS Truckstop ID", "")
            state = row.get("State", "").upper()
            price_text = row.get("Retail Price", "")

            if not station_id or not row.get("City") or not state:
                excluded.append({
                    "line": line_number,
                    "reason": "missing_required_value",
                    "station_id": station_id,
                })
                continue

            if state in NON_US_PROVINCES:
                excluded.append({
                    "line": line_number,
                    "reason": "non_us_province",
                    "station_id": station_id,
                })
                continue

            if state not in US_STATES:
                excluded.append({
                    "line": line_number,
                    "reason": "unknown_state",
                    "station_id": station_id,
                })
                continue

            try:
                price = Decimal(price_text)
            except InvalidOperation:
                price = Decimal("NaN")

            if not price.is_finite() or price <= 0 or price > 10:
                excluded.append({
                    "line": line_number,
                    "reason": "invalid_price",
                    "station_id": station_id,
                })
                continue

            row["State"] = state
            row["_price"] = price
            row["_line"] = line_number
            groups[station_id].append(row)

    stations = []
    conflicting_ids = []
    repeated_ids = 0
    differing_price_ids = 0

    for station_id, records in sorted(groups.items()):
        locations = {
            (
                record["Address"].casefold(),
                record["City"].casefold(),
                record["State"],
            )
            for record in records
        }

        if len(locations) > 1:
            conflicting_ids.append(station_id)
            for record in records:
                excluded.append({
                    "line": record["_line"],
                    "reason": "conflicting_station_location",
                    "station_id": station_id,
                })
            continue

        prices = [record["_price"] for record in records]

        if len(records) > 1:
            repeated_ids += 1

        if len(set(prices)) > 1:
            differing_price_ids += 1

        # Assessment policy: choose the lowest listed price per station ID.
        chosen = min(
            records,
            key=lambda record: (
                record["_price"],
                record["Truckstop Name"].casefold(),
                record["_line"],
            ),
        )

        stations.append({
            "station_id": station_id,
            "name": chosen["Truckstop Name"],
            "address": chosen["Address"],
            "city": chosen["City"],
            "state": chosen["State"],
            "rack_id": chosen["Rack ID"],
            "price": chosen["_price"],
            "source_record_count": len(records),
            "source_price_min": min(prices),
            "source_price_max": max(prices),
        })

    excluded_counts = {}
    for record in excluded:
        reason = record["reason"]
        excluded_counts[reason] = excluded_counts.get(reason, 0) + 1

    report = {
        "source_rows": source_rows,
        "exact_duplicate_rows": exact_duplicate_rows,
        "unique_us_stations": len(stations),
        "repeated_station_ids": repeated_ids,
        "differing_price_station_ids": differing_price_ids,
        "conflicting_station_ids": len(conflicting_ids),
        "excluded_rows": len(excluded),
        "excluded_by_reason": excluded_counts,
        "price_policy": "minimum price per consistent station ID",
    }

    return stations, report, excluded

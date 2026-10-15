
import csv
import tempfile
from pathlib import Path
from decimal import Decimal

from django.test import SimpleTestCase

from routing.services.csv_cleaner import clean_csv


class CSVCleanerTests(SimpleTestCase):
    def create_csv(self, rows):
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            encoding="utf-8",
            newline="",
            delete=False,
        )
        self.addCleanup(Path(temp_file.name).unlink, missing_ok=True)

        fieldnames = [
            "OPIS Truckstop ID",
            "Truckstop Name",
            "Address",
            "City",
            "State",
            "Rack ID",
            "Retail Price",
        ]

        with temp_file:
            writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return temp_file.name

    def station(self, **overrides):
        row = {
            "OPIS Truckstop ID": "100",
            "Truckstop Name": "Test Fuel Station",
            "Address": "Main Road",
            "City": "Dallas",
            "State": "TX",
            "Rack ID": "123",
            "Retail Price": "3.50",
        }
        row.update(overrides)
        return row

    def test_valid_us_station_is_kept(self):
        path = self.create_csv([self.station()])

        stations, report, excluded = clean_csv(path)

        self.assertEqual(len(stations), 1)
        self.assertEqual(stations[0]["station_id"], "100")
        self.assertEqual(stations[0]["price"], Decimal("3.50"))
        self.assertEqual(report["unique_us_stations"], 1)
        self.assertEqual(excluded, [])

    def test_canadian_station_is_excluded(self):
        path = self.create_csv([
            self.station(State="YT", City="Whitehorse")
        ])

        stations, report, excluded = clean_csv(path)

        self.assertEqual(stations, [])
        self.assertEqual(report["excluded_rows"], 1)
        self.assertEqual(
            excluded[0]["reason"], "non_us_province"
        )

    def test_lowest_price_is_selected_for_same_station(self):
        path = self.create_csv([
            self.station(**{"Retail Price": "3.80"}),
            self.station(**{"Retail Price": "3.20"}),
        ])

        stations, report, excluded = clean_csv(path)

        self.assertEqual(len(stations), 1)
        self.assertEqual(stations[0]["price"], Decimal("3.20"))
        self.assertEqual(report["repeated_station_ids"], 1)
        self.assertEqual(report["differing_price_station_ids"], 1)

    def test_conflicting_locations_are_excluded(self):
        path = self.create_csv([
            self.station(),
            self.station(City="Houston"),
        ])

        stations, report, excluded = clean_csv(path)

        self.assertEqual(stations, [])
        self.assertEqual(report["conflicting_station_ids"], 1)
        self.assertEqual(report["excluded_rows"], 2)

    def test_invalid_price_is_excluded(self):
        path = self.create_csv([
            self.station(**{"Retail Price": "-2.00"})
        ])

        stations, report, excluded = clean_csv(path)

        self.assertEqual(stations, [])
        self.assertEqual(excluded[0]["reason"], "invalid_price")

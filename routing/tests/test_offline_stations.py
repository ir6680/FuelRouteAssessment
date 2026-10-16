from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from routing.services.station_provider import load_fuel_stations


class OfflineStationTests(SimpleTestCase):
    @patch("routing.services.station_provider.resolve_place")
    @patch("routing.services.station_provider.clean_csv")
    def test_coverage_reports_unmatched_records_and_centroid_warning(self, clean, resolve):
        clean.return_value = ([
            {"station_id": "1", "city": "A", "state": "TX", "price": Decimal("3.00")},
            {"station_id": "2", "city": "B", "state": "TX", "price": Decimal("3.10")},
        ], {"excluded_rows": 0, "excluded_by_reason": {}}, [])
        resolve.side_effect = [({"latitude": 30.0, "longitude": -97.0, "geocode_precision": "city_or_place_centroid"}, "matched"), (None, "ambiguous")]
        stations, coverage, _ = load_fuel_stations()
        self.assertEqual(len(stations), 1)
        self.assertIn("not the verified fuel station", stations[0]["coordinate_warning"])
        self.assertEqual(coverage["located_stations"], 1)
        self.assertEqual(coverage["unmatched_by_reason"]["ambiguous"], 1)

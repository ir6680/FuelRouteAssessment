from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from routing.services.station_provider import load_fuel_stations
from routing.services import station_provider
from routing.services.route_geometry import distance_to_route as actual_distance_to_route


class OfflineStationTests(SimpleTestCase):
    def setUp(self):
        station_provider._load_fuel_stations_cached.cache_clear()
        station_provider._gazetteer_signature = None

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

    @patch("routing.services.station_provider.source_data_signature")
    @patch("routing.services.station_provider.resolve_place")
    @patch("routing.services.station_provider.clean_csv")
    def test_cleaned_stations_are_cached_until_source_files_change(self, clean, resolve, signature):
        records = [{"station_id": "1", "city": "A", "state": "TX", "price": Decimal("3.00")}]
        clean.return_value = (records, {"excluded_rows": 0, "excluded_by_reason": {}}, [])
        resolve.return_value = ({"latitude": 30.0, "longitude": -97.0, "geocode_precision": "city_or_place_centroid"}, "matched")
        signature.return_value = ((1, 100), (2, 200), (3, 300))

        load_fuel_stations()
        load_fuel_stations()
        self.assertEqual(clean.call_count, 1)
        self.assertEqual(resolve.call_count, 1)

        signature.return_value = ((4, 101), (2, 200), (3, 300))
        load_fuel_stations()
        self.assertEqual(clean.call_count, 2)
        self.assertEqual(resolve.call_count, 2)

    @patch("routing.services.route_geometry.distance_to_route")
    @patch("routing.services.station_provider.load_fuel_stations")
    def test_route_bounds_prefilter_matches_exhaustive_distance_filter(self, load, distance):
        from routing.services.station_provider import get_fuel_stations_near_route

        distance.side_effect = actual_distance_to_route
        geometry = {"type": "LineString", "coordinates": [[-100.0, 40.0], [-99.0, 40.0]]}
        candidates = [
            {"station_id": "on-route", "latitude": 40.0, "longitude": -99.5},
            {"station_id": "near-edge", "latitude": 40.0, "longitude": -100.01},
            {"station_id": "outside", "latitude": 40.1, "longitude": -99.5},
        ]
        load.return_value = (candidates, {}, {})
        actual, _ = get_fuel_stations_near_route(geometry)
        self.assertLess(distance.call_count, len(candidates))
        expected_ids = {
            station["station_id"] for station in candidates
            if actual_distance_to_route(station, geometry) <= 3.0
        }
        self.assertEqual({station["station_id"] for station in actual}, expected_ids)

    @patch("routing.services.station_provider.resolve_place")
    @patch("routing.services.station_provider.clean_csv")
    def test_centroid_is_resolved_once_per_distinct_city_state(self, clean, resolve):
        clean.return_value = ([
            {"station_id": "1", "city": "Springfield", "state": "IL", "price": Decimal("3.00")},
            {"station_id": "2", "city": "Springfield", "state": "IL", "price": Decimal("3.10")},
            {"station_id": "3", "city": "Peoria", "state": "IL", "price": Decimal("3.20")},
        ], {"excluded_rows": 0, "excluded_by_reason": {}}, [])
        resolve.side_effect = [
            ({"latitude": 40.0, "longitude": -89.0, "geocode_precision": "city_or_place_centroid"}, "matched"),
            ({"latitude": 40.7, "longitude": -89.6, "geocode_precision": "city_or_place_centroid"}, "matched"),
        ]
        stations, _, _ = load_fuel_stations()
        self.assertEqual(len(stations), 3)
        self.assertEqual(resolve.call_count, 2)

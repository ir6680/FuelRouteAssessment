from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient


class RouteApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.url = "/api/v1/route/"
        self.payload = {"start": {"lat": 30.0, "lng": -97.0}, "finish": {"lat": 31.0, "lng": -96.0}}

    @patch("routing.services.route_service.get_route")
    @patch("routing.services.route_service.get_fuel_stations_near_route")
    @patch("routing.services.route_service.optimize_fuel_stops")
    def test_successful_response_is_cached_and_reports_provider_calls(self, optimize, stations, route):
        route.return_value = {"geometry": {"type": "LineString", "coordinates": [[-97, 30], [-96, 31]]}, "distance_meters": 10000, "duration_seconds": 600}
        stations.return_value = ([{"station_id": "csv-1", "name": "Candidate", "price": 3.0, "latitude": 30.5, "longitude": -96.5, "geocode_precision": "city_or_place_centroid", "coordinate_warning": "Centroid coordinate; not physical station location."}], {"csv_unique_stations": 1, "located_stations": 1, "unmatched_stations": 0, "coverage_percent": 100, "unmatched_by_reason": {}})
        optimize.return_value = {"fuel_purchase_cost": 3.0, "stops": []}
        first = self.client.post(self.url, self.payload, format="json")
        second = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["api_calls"]["routing"], 1)
        self.assertTrue(second.data["cache"]["hit"])
        self.assertEqual(second.data["api_calls"]["routing"], 0)
        self.assertIn("not verified station locations", first.data["data_quality"]["station_coordinates_warning"])
        candidate = optimize.call_args.args[1][0]
        self.assertLessEqual(candidate["route_mile"], first.data["route"]["properties"]["distance_miles"])
        route.assert_called_once()
        stations.assert_called_once()
        optimize.assert_called_once()
        self.assertEqual(
            route.call_args.args,
            (
                {"latitude": 30.0, "longitude": -97.0, "geocode_precision": "user_coordinates"},
                {"latitude": 31.0, "longitude": -96.0, "geocode_precision": "user_coordinates"},
            ),
        )

    def test_invalid_request_has_structured_validation_error(self):
        response = self.client.post(self.url, {"start": "", "finish": {}}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("start", response.data)

    @patch("routing.services.route_service.source_data_signature")
    def test_route_cache_key_changes_when_any_input_dataset_changes(self, signature):
        from routing.services.route_service import _cache_key

        start = {"latitude": 40.7, "longitude": -74.0}
        finish = {"latitude": 41.8, "longitude": -87.6}
        signature.return_value = ((1, 10), (2, 20), (3, 30))
        first = _cache_key(start, finish)
        signature.return_value = ((1, 10), (2, 20), (4, 31))
        second = _cache_key(start, finish)
        self.assertNotEqual(first, second)

    @patch("routing.services.route_service.resolve_location", side_effect=ValueError("bad location"))
    def test_unresolvable_location_returns_422(self, _resolve):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data["error"], "INVALID_ROUTE_REQUEST")

    @patch("routing.services.route_service.resolve_location", side_effect=RuntimeError("provider down"))
    def test_provider_failure_returns_503(self, _resolve):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["error"], "ROUTE_SERVICE_UNAVAILABLE")

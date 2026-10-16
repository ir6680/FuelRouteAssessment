import logging
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from routing.services.route_provider import RouteProviderError, get_route


@override_settings(
    ORS_BASE_URL="https://api.heigit.org/openrouteservice",
    OPENROUTESERVICE_API_KEY="test-secret-key",
)
class RouteProviderTests(SimpleTestCase):
    def setUp(self):
        self.start = {"longitude": -74.0, "latitude": 40.7}
        self.finish = {"longitude": -75.1, "latitude": 39.9}

    @patch("routing.services.route_provider.requests.post")
    def test_success_uses_expected_url_key_and_lon_lat_payload(self, post):
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "features": [{
                "geometry": {"type": "LineString", "coordinates": [[-74.0, 40.7], [-75.1, 39.9]]},
                "properties": {"summary": {"distance": 12345, "duration": 678}},
            }]
        }
        post.return_value = response

        with self.assertLogs("routing.services.route_provider", logging.INFO) as captured:
            result = get_route(self.start, self.finish)

        post.assert_called_once_with(
            "https://api.heigit.org/openrouteservice/v2/directions/driving-car/geojson",
            json={"coordinates": [[-74.0, 40.7], [-75.1, 39.9]]},
            headers={"Authorization": "test-secret-key", "Content-Type": "application/json"},
            timeout=(5, 20),
        )
        self.assertEqual(result["distance_meters"], 12345)
        self.assertEqual(result["duration_seconds"], 678)
        self.assertIn("routing_provider_request duration_seconds=", captured.output[0])
        self.assertIn("http_status=200", captured.output[0])
        self.assertNotIn("test-secret-key", captured.output[0])

    @patch("routing.services.route_provider.requests.post")
    def test_http_error_is_logged_safely_and_public_error_stays_generic(self, post):
        response = requests.Response()
        response.status_code = 403
        response._content = (
            b'{"error":"invalid key test-secret-key",'
            b'"coordinates":[[-74.0,40.7],[-75.1,39.9],'
            b'"authorization":"Bearer another-secret"}'
        )
        error = requests.HTTPError("403 Client Error", response=response)
        post.return_value.raise_for_status.side_effect = error

        with self.assertLogs("routing.services.route_provider", logging.WARNING) as captured:
            with self.assertRaises(RouteProviderError) as raised:
                get_route(self.start, self.finish)

        log_output = "\n".join(captured.output)
        self.assertIn("exception_type=HTTPError", log_output)
        self.assertIn("http_status=403", log_output)
        self.assertIn("invalid key [REDACTED]", log_output)
        self.assertNotIn("test-secret-key", log_output)
        self.assertNotIn("another-secret", log_output)
        self.assertNotIn("40.7", log_output)
        self.assertEqual(str(raised.exception), "OpenRouteService route request failed.")
        self.assertEqual(raised.exception.provider_calls, 1)

    @patch("routing.services.route_provider.requests.post", side_effect=requests.Timeout("request timed out"))
    def test_timeout_is_logged_without_exception_details_and_remains_generic(self, post):
        with self.assertLogs("routing.services.route_provider", logging.WARNING) as captured:
            with self.assertRaises(RouteProviderError) as raised:
                get_route(self.start, self.finish)

        self.assertIn("exception_type=Timeout", captured.output[0])
        self.assertIn("http_status=None", captured.output[0])
        self.assertNotIn("request timed out", captured.output[0])
        self.assertEqual(str(raised.exception), "OpenRouteService route request failed.")
        self.assertEqual(raised.exception.provider_calls, 1)

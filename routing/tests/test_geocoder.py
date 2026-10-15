
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from routing.services.geocoder import geocode_address


class GeocoderTests(SimpleTestCase):
    @patch("routing.services.geocoder.requests.get")
    def test_matching_city_state_returns_coordinates(self, mock_get):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "features": [
                {
                    "properties": {
                        "label": "Sudden Service, Nashville, TN, USA",
                        "locality": "Nashville",
                        "region_a": "TN",
                        "country_a": "USA",
                        "layer": "venue",
                    },
                    "geometry": {
                        "coordinates": [-86.599889, 36.169133]
                    },
                }
            ]
        }
        mock_get.return_value = mock_response

        result = geocode_address(
            "Sudden Service",
            "601 Fesslers Ln",
            "Nashville",
            "TN",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["longitude"], -86.599889)
        self.assertEqual(result["latitude"], 36.169133)
        self.assertTrue(result["verified_city_state"])
        self.assertFalse(result["exact_station_verified"])

    @patch("routing.services.geocoder.requests.get")
    def test_wrong_state_is_rejected(self, mock_get):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "features": [
                {
                    "properties": {
                        "label": "Nashville, TN, USA",
                        "locality": "Nashville",
                        "region_a": "TN",
                        "country_a": "USA",
                        "layer": "venue",
                    },
                    "geometry": {
                        "coordinates": [-86.599889, 36.169133]
                    },
                }
            ]
        }
        mock_get.return_value = mock_response

        result = geocode_address(
            "Test Fuel Station",
            "123 Main Street",
            "Austin",
            "TX",
        )

        self.assertIsNone(result)

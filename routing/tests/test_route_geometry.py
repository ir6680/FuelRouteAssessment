
from django.test import SimpleTestCase

from routing.services.route_geometry import (
    distance_to_route,
    haversine_miles,
    sample_route,
    station_route_position,
)


class RouteGeometryTests(SimpleTestCase):
    def setUp(self):
        self.route = {
            "type": "LineString",
            "coordinates": [
                [-74.0, 40.0],
                [-73.99, 40.0],
                [-73.98, 40.0],
            ],
        }

    def test_same_coordinate_distance_is_zero(self):
        distance = haversine_miles(
            -74.0, 40.0, -74.0, 40.0
        )
        self.assertEqual(distance, 0.0)

    def test_station_on_route_has_zero_distance(self):
        station = {
            "longitude": -73.99,
            "latitude": 40.0,
        }
        distance = distance_to_route(station, self.route)
        self.assertAlmostEqual(distance, 0.0, places=6)

    def test_sample_route_returns_ordered_mile_markers(self):
        samples = sample_route(
            self.route,
            interval_miles=0.5,
        )

        self.assertGreater(len(samples), 1)

        mile_markers = [
            point["route_mile"] for point in samples
        ]

        self.assertEqual(mile_markers, sorted(mile_markers))
        self.assertEqual(mile_markers[0], 0.0)

    def test_sample_route_rejects_invalid_interval(self):
        with self.assertRaises(ValueError):
            sample_route(self.route, interval_miles=0)

    def test_empty_geometry_is_rejected(self):
        with self.assertRaises(ValueError):
            sample_route({"coordinates": []})

    def test_station_route_position_returns_mile_marker(self):
        station = {
            "longitude": -73.99,
            "latitude": 40.0,
        }

        result = station_route_position(station, self.route)

        self.assertIn("route_mile", result)
        self.assertIn("distance_to_route_miles", result)
        self.assertGreaterEqual(result["route_mile"], 0.0)
        self.assertAlmostEqual(
            result["distance_to_route_miles"],
            0.0,
            places=6,
        )

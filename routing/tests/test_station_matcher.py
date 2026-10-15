
from decimal import Decimal

from django.test import SimpleTestCase

from routing.services.station_matcher import match_station_price


class StationMatcherTests(SimpleTestCase):
    def setUp(self):
        self.csv_stations = [
            {
                "station_id": "1001",
                "name": "Sudden Service #6604",
                "city": "Nashville",
                "state": "TN",
                "price": Decimal("3.399"),
            }
        ]

    def test_exact_station_number_and_location_match(self):
        osm_station = {
            "name": "Sudden Service #6604",
            "brand": "Sudden Service",
            "operator": None,
            "city": "Nashville",
            "state": "TN",
        }

        result = match_station_price(osm_station, self.csv_stations)

        self.assertIsNotNone(result)
        self.assertEqual(result["station_id"], "1001")
        self.assertEqual(result["price"], Decimal("3.399"))

    def test_generic_brand_without_station_number_is_rejected(self):
        osm_station = {
            "name": "Sudden Service",
            "brand": "Sudden Service",
            "operator": None,
            "city": "Nashville",
            "state": "TN",
        }

        result = match_station_price(osm_station, self.csv_stations)

        self.assertIsNone(result)

    def test_missing_city_and_state_is_rejected(self):
        osm_station = {
            "name": "Sudden Service #6604",
            "brand": "Sudden Service",
            "operator": None,
            "city": None,
            "state": None,
        }

        result = match_station_price(osm_station, self.csv_stations)

        self.assertIsNone(result)

    def test_wrong_city_is_rejected(self):
        osm_station = {
            "name": "Sudden Service #6604",
            "brand": "Sudden Service",
            "operator": None,
            "city": "Memphis",
            "state": "TN",
        }

        result = match_station_price(osm_station, self.csv_stations)

        self.assertIsNone(result)

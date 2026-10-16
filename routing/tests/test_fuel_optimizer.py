
from decimal import Decimal

from django.test import SimpleTestCase

from routing.services.fuel_optimizer import optimize_fuel_stops
from routing.services.csv_cleaner import clean_csv
from routing.services.station_provider import FUEL_CSV_PATH


def station(station_id, mile, price):
    return {
        "station_id": station_id,
        "name": f"Station {station_id}",
        "route_mile": mile,
        "price": Decimal(str(price)),
    }


class FuelOptimizerTests(SimpleTestCase):
    def test_zero_distance_has_zero_cost(self):
        result = optimize_fuel_stops(0, [])

        self.assertEqual(result["fuel_purchase_cost"], 0.0)
        self.assertEqual(result["stops"], [])

    def test_rejects_negative_distance(self):
        with self.assertRaises(ValueError):
            optimize_fuel_stops(-10, [])

    def test_rejects_unreachable_route(self):
        with self.assertRaises(ValueError):
            optimize_fuel_stops(600, [])

    def test_starting_fuel_cost_is_included(self):
        result = optimize_fuel_stops(
            100,
            [station("A", 10, "3.00")],
        )

        self.assertTrue(result["starting_fuel_cost_included"])
        self.assertEqual(result["initial_fuel_policy"], "departure_fill")
        self.assertEqual(result["fuel_purchase_cost"], 30.0)
        self.assertEqual(result["purchased_gallons"], 10.0)

    def test_exactly_500_miles_is_feasible(self):
        result = optimize_fuel_stops(
            500,
            [station("A", 10, "3.00")],
        )

        self.assertEqual(result["fuel_used_gallons"], 50.0)
        self.assertEqual(result["fuel_purchase_cost"], 150.0)
        self.assertLessEqual(
            max(stop["gallons_purchased"] for stop in result["stops"]),
            50.0,
        )

    def test_short_route_cost_matches_rounded_departure_fill_and_csv_reference(self):
        csv_stations, _, _ = clean_csv(FUEL_CSV_PATH)
        reference = next(s for s in csv_stations if s["station_id"] == "192")
        candidate = {
            **station(reference["station_id"], 8, reference["price"]),
            "name": reference["name"],
            "city": reference["city"],
            "state": reference["state"],
        }
        result = optimize_fuel_stops(93.42, [candidate])
        departure = result["stops"][0]
        self.assertEqual(departure["price_per_gallon"], 3.099)
        self.assertEqual(departure["price_reference"]["station_id"], "192")
        self.assertEqual(departure["price_reference"]["price_per_gallon"], float(reference["price"]))
        self.assertEqual(departure["price_reference"]["csv_source"], "fuel-price CSV")
        self.assertEqual(result["fuel_purchase_cost"], 28.95)
        self.assertEqual(result["fuel_purchase_cost"], sum(s["cost"] for s in result["stops"]))
        self.assertEqual(result["fuel_used_gallons"], 9.342)

    def test_departure_reference_is_cheapest_within_policy_window(self):
        result = optimize_fuel_stops(
            100,
            [station("far-cheap", 26, "1.00"), station("near-expensive", 3, "4.00"), station("near-cheapest", 20, "3.00")],
        )
        self.assertEqual(result["stops"][0]["price_reference_station_id"], "near-cheapest")

    def test_long_route_requires_multiple_refuels_within_range(self):
        result = optimize_fuel_stops(
            1200,
            [station("start", 10, "3.00"), station("middle-1", 500, "3.00"), station("middle-2", 900, "3.00")],
        )
        fuel_stops = [s for s in result["stops"] if s["stop_type"] == "fuel_stop"]
        self.assertEqual([s["station_id"] for s in fuel_stops], ["middle-1", "middle-2"])
        positions = [0.0] + [s["route_mile"] for s in fuel_stops] + [1200.0]
        self.assertTrue(all(b - a <= 500 for a, b in zip(positions, positions[1:])))

    def test_new_york_chicago_regression_skips_redundant_near_full_stop(self):
        # Recreates the suspicious sequence: 50 gallons at 75.203 leaves the
        # tank almost full at 77.034, so buying another 0.183 gallons there is
        # unnecessary. The optimizer should proceed to the next useful stop.
        candidates = [
            station("68102", 10, "4.00"),
            station("at-55.205", 55.205, "3.00"),
            station("at-75.203", 75.203, "2.00"),
            station("at-77.034", 77.034, "2.10"),
            station("at-401.870", 401.870, "2.50"),
        ]
        result = optimize_fuel_stops(802.77, candidates)
        stops = result["stops"]

        self.assertEqual(
            [stop["station_id"] for stop in stops],
            ["68102", "at-55.205", "at-75.203", "at-401.870"],
        )
        self.assertEqual(stops[0]["price_reference_station_id"], "68102")
        for stop in stops[1:]:
            self.assertEqual(
                stop["price_reference_station_id"], stop["station_id"]
            )
            self.assertEqual(
                stop["price_reference"]["price_per_gallon"],
                stop["price_per_gallon"],
            )
        self.assertFalse(any(
            stop["station_id"] == "at-77.034" for stop in stops
        ))
        self.assertEqual(
            result["fuel_purchase_cost"],
            sum(stop["cost"] for stop in stops),
        )
        self.assertEqual(result["purchased_gallons"], 80.277)
        self.assertEqual(result["fuel_used_gallons"], 80.277)

    def test_live_new_york_chicago_balances_using_unrounded_positions(self):
        # Exact positions that round to the reported 55.205, 75.203, and
        # 401.870 route-mile labels. The reported purchases correspond to
        # these full-precision locations and a 802.76311-mile route.
        candidates = [
            station("68102", 10, "4.00"),
            station("csv-55", "55.20529", "3.00"),
            station("csv-75", "75.20313", "2.00"),
            station("csv-77", "77.034", "2.10"),
            station("csv-401", "401.870", "2.50"),
        ]
        result = optimize_fuel_stops("802.76311", candidates)
        stops = result["stops"]

        self.assertEqual(
            [stop["gallons_purchased"] for stop in stops],
            [5.520529, 1.999784, 50.0, 22.755998],
        )
        self.assertEqual(
            [stop["fuel_on_arrival_gallons"] for stop in stops],
            [0.0, 0.0, 0.0, 17.333313],
        )
        self.assertEqual(
            [stop["fuel_on_departure_gallons"] for stop in stops],
            [5.520529, 1.999784, 50.0, 40.089311],
        )
        self.assertEqual(stops[0]["marker_type"], "virtual_route_start")
        self.assertEqual(stops[0]["price_reference_station_id"], "68102")
        self.assertEqual(stops[0]["route_mile"], 0.0)
        self.assertEqual(stops[0]["price_reference"]["route_mile_estimate"], 10.0)

        # The mile-77 candidate is crossed with fuel in hand, not refueled.
        fuel_at_77 = Decimal("50") - (Decimal("77.034") - Decimal("75.20313")) / 10
        self.assertEqual(fuel_at_77, Decimal("49.816913"))
        fuel_at_401 = fuel_at_77 - (Decimal("401.870") - Decimal("77.034")) / 10
        self.assertEqual(fuel_at_401, Decimal("17.333313"))
        final_fuel = Decimal("40.089311") - (Decimal("802.76311") - Decimal("401.870")) / 10
        self.assertEqual(final_fuel, Decimal("0.000000"))

        self.assertEqual(result["purchased_gallons"], 80.276311)
        self.assertEqual(result["fuel_used_gallons"], 80.276311)
        self.assertTrue(all(stop["fuel_on_departure_gallons"] <= 50 for stop in stops))
        self.assertEqual(result["fuel_purchase_cost"], sum(s["cost"] for s in stops))

    def test_500_mile_legs_are_feasible_without_exceeding_tank_capacity(self):
        result = optimize_fuel_stops(
            1010,
            [station("mile-10", 10, "3.00"), station("mile-510", 510, "3.00")],
        )
        stops = result["stops"]
        positions = [0] + [stop["route_mile"] for stop in stops] + [1010]
        self.assertTrue(all(b - a <= 500 for a, b in zip(positions, positions[1:])))
        self.assertTrue(all(stop["gallons_purchased"] <= 50 for stop in stops))
        self.assertEqual(result["fuel_used_gallons"], 101.0)
        self.assertEqual(result["purchased_gallons"], 101.0)

    def test_valid_but_unreachable_candidates_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "NO_FEASIBLE_FUEL_PLAN"):
            optimize_fuel_stops(1000, [station("only", 10, "3.00")])

    def test_missing_fuel_candidates_fail_without_inventing_price(self):
        with self.assertRaisesRegex(ValueError, "No valid fuel-price reference"):
            optimize_fuel_stops(30, [])

    def test_gap_over_500_miles_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "NO_FEASIBLE_FUEL_PLAN"):
            optimize_fuel_stops(
                510.01,
                [station("A", 10, "3.00")],
            )

    def test_buys_only_enough_to_reach_cheaper_station(self):
        result = optimize_fuel_stops(
            150,
            [
                station("A", 10, "4.00"),
                station("B", 100, "2.00"),
            ],
        )

        departure = result["stops"][0]
        self.assertEqual(departure["stop_type"], "departure_fill")
        self.assertEqual(departure["gallons_purchased"], 10.0)

        cheaper_stop = next(
            stop for stop in result["stops"]
            if stop["station_id"] == "B"
        )
        self.assertEqual(cheaper_stop["gallons_purchased"], 5.0)
        self.assertEqual(result["fuel_purchase_cost"], 50.0)

    def test_equal_price_prefers_farthest_reachable_station(self):
        result = optimize_fuel_stops(
            800,
            [
                station("A", 10, "3.00"),
                station("B", 300, "3.00"),
                station("C", 490, "3.00"),
                station("D", 700, "3.00"),
            ],
        )

        real_stops = [
            stop["station_id"]
            for stop in result["stops"]
            if stop["stop_type"] == "fuel_stop"
        ]
        self.assertIn("C", real_stops)
        self.assertNotIn("B", real_stops)

    def test_purchased_fuel_matches_consumption(self):
        result = optimize_fuel_stops(
            800,
            [
                station("A", 10, "3.00"),
                station("B", 300, "3.00"),
                station("C", 490, "3.00"),
                station("D", 700, "3.00"),
            ],
        )

        self.assertAlmostEqual(
            result["purchased_gallons"],
            result["fuel_used_gallons"],
            places=3,
        )

        self.assertAlmostEqual(
            result["fuel_purchase_cost"],
            sum(stop["cost"] for stop in result["stops"]),
            places=2,
        )
        self.assertEqual(
            result["fuel_purchase_cost"],
            sum(stop["cost"] for stop in result["stops"]),
        )
        self.assertEqual(
            result["fuel_used_gallons"],
            round(result["route_distance_miles"] / 10, 3),
        )

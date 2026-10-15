
from decimal import Decimal

MPG = Decimal("10")
MAX_RANGE_MILES = Decimal("500")
TANK_CAPACITY_GALLONS = MAX_RANGE_MILES / MPG


def optimize_fuel_stops(route_distance_miles, stations):
    """
    Greedy fuel-stop planner.

    Each station must contain:
      - station_id
      - name
      - route_mile: distance from route start
      - price: price per gallon

    Assumptions:
      - Vehicle starts with a full tank.
      - Initial fuel cost is excluded.
      - Station prices are assumed to be dollars per gallon.
      - Route positions and driving distances are already calculated.
    """
    distance = Decimal(str(route_distance_miles))

    if distance < 0:
        raise ValueError("Route distance cannot be negative.")

    if distance == 0:
        return {
            "route_distance_miles": 0.0,
            "fuel_used_gallons": 0.0,
            "purchased_gallons": 0.0,
            "fuel_purchase_cost": 0.0,
            "stops": [],
        }

    capacity = TANK_CAPACITY_GALLONS
    fuel = capacity
    position = Decimal("0")
    purchase_cost = Decimal("0")
    purchased_gallons = Decimal("0")
    fuel_used = distance / MPG
    stops = []

    clean_stations = []

    for station in stations:
        station_position = Decimal(str(station["route_mile"]))
        price = Decimal(str(station["price"]))

        if not price.is_finite() or price <= 0:
            continue

        if not Decimal("0") <= station_position <= distance:
            continue

        clean_stations.append({
            **station,
            "route_mile": station_position,
            "price": price,
        })

    clean_stations.sort(key=lambda item: item["route_mile"])

    # Stations at the same route position can cause ambiguous choices.
    positions = [item["route_mile"] for item in clean_stations]
    if len(positions) != len(set(positions)):
        raise ValueError(
            "Stations must have unique route positions. "
            "Deduplicate stations before optimization."
        )

    remaining = clean_stations[:]
    current_station = None

    while distance - position > fuel * MPG:
        reachable = [
            station
            for station in remaining
            if position < station["route_mile"]
            and station["route_mile"] - position <= fuel * MPG
        ]

        if not reachable:
            raise ValueError(
                "No fuel station is reachable with the remaining fuel."
            )

        # At the start, use the furthest reachable station.
        target = None

        if current_station is not None:
            cheaper = [
                station
                for station in remaining
                if station["route_mile"] > position
                and station["route_mile"] - position <= MAX_RANGE_MILES
                and station["price"] < current_station["price"]
            ]

            if cheaper:
                target = min(
                    cheaper,
                    key=lambda station: station["route_mile"],
                )

        if target is None:
            # No cheaper station is reachable on a full tank.
            # Fill up at the current station when one is available.
            if current_station is not None:
                gallons_to_buy = capacity - fuel

                if gallons_to_buy > 0:
                    cost = gallons_to_buy * current_station["price"]
                    purchase_cost += cost
                    purchased_gallons += gallons_to_buy
                    fuel += gallons_to_buy

                    stops.append({
                        "station_id": current_station["station_id"],
                        "name": current_station["name"],
                        "route_mile": float(position),
                        "price_per_gallon": float(current_station["price"]),
                        "gallons_purchased": float(gallons_to_buy),
                        "cost": float(cost),
                    })

            reachable = [
                station
                for station in remaining
                if position < station["route_mile"]
                and station["route_mile"] - position <= fuel * MPG
            ]

            if not reachable:
                raise ValueError(
                    "No fuel station is reachable after refueling."
                )

            target = max(
                reachable,
                key=lambda station: station["route_mile"],
            )

        miles_to_target = target["route_mile"] - position
        gallons_needed = miles_to_target / MPG

        if gallons_needed > fuel:
            # Buy only enough to reach the cheaper target.
            if current_station is None:
                raise ValueError(
                    "Starting fuel is insufficient to reach a station."
                )

            gallons_to_buy = min(
                capacity - fuel,
                gallons_needed - fuel,
            )

            cost = gallons_to_buy * current_station["price"]
            purchase_cost += cost
            purchased_gallons += gallons_to_buy
            fuel += gallons_to_buy

            if gallons_to_buy > 0:
                stops.append({
                    "station_id": current_station["station_id"],
                    "name": current_station["name"],
                    "route_mile": float(position),
                    "price_per_gallon": float(current_station["price"]),
                    "gallons_purchased": float(gallons_to_buy),
                    "cost": float(cost),
                })

        fuel -= gallons_needed
        position = target["route_mile"]
        current_station = target
        remaining.remove(target)

    return {
        "route_distance_miles": float(distance),
        "fuel_used_gallons": float(fuel_used),
        "purchased_gallons": float(purchased_gallons),
        "fuel_purchase_cost": float(purchase_cost),
        "starting_fuel_cost_included": False,
        "stops": stops,
    }

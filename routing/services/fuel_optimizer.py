
from bisect import bisect_right
from decimal import Decimal, ROUND_HALF_UP

MPG = Decimal("10")
MAX_RANGE_MILES = Decimal("500")
TANK_CAPACITY_GALLONS = MAX_RANGE_MILES / MPG
DEPARTURE_REFERENCE_MILES = Decimal("25")
STATION_MERGE_MILES = Decimal("0.05")
CENT = Decimal("0.01")
GALLON_PRECISION = Decimal("0.000001")


def _money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _gallons(value):
    return value.quantize(GALLON_PRECISION, rounding=ROUND_HALF_UP)


def _clean_stations(route_distance, stations):
    cleaned = []

    for station in stations:
        mile = Decimal(str(station["route_mile"]))
        price = Decimal(str(station["price"]))

        if not mile.is_finite() or not price.is_finite():
            continue
        if price <= 0 or mile < 0 or mile > route_distance:
            continue

        cleaned.append({
            **station,
            "route_mile": mile,
            "price": price,
            "station_id": str(station["station_id"]),
            "name": str(station["name"]),
        })

    cleaned.sort(
        key=lambda s: (s["route_mile"], s["price"], s["station_id"])
    )

    # Collapse stations less than 0.05 miles apart.
    merged = []

    for station in cleaned:
        if (
            merged
            and station["route_mile"] - merged[-1]["route_mile"]
            < STATION_MERGE_MILES
        ):
            if (
                station["price"],
                station["station_id"],
            ) < (
                merged[-1]["price"],
                merged[-1]["station_id"],
            ):
                merged[-1] = station
        else:
            merged.append(station)

    return merged


def optimize_fuel_stops(route_distance_miles, stations):
    """
    Blueprint v2 departure_fill optimizer.

    Stations require:
      station_id, name, route_mile, price

    Assumptions:
      - Empty tank at departure.
      - Virtual departure fill at mile 0.
      - 10 MPG and 500-mile maximum range.
      - No detour cost; arrival fuel may be zero.
      - Fuel prices are assumed to be USD per gallon.
      - Departure price reference is the cheapest valid station within 25
        route miles, falling back to the cheapest valid candidate on route.
    """
    distance = Decimal(str(route_distance_miles))

    if not distance.is_finite() or distance < 0:
        raise ValueError("Route distance must be a finite non-negative number.")

    if distance == 0:
        return {
            "route_distance_miles": 0.0,
            "fuel_used_gallons": 0.0,
            "purchased_gallons": 0.0,
            "fuel_purchase_cost": 0.0,
            "starting_fuel_cost_included": True,
            "initial_fuel_policy": "departure_fill",
            "stops": [],
        }

    clean = _clean_stations(distance, stations)

    if not clean:
        raise ValueError(
            "No valid fuel-price reference is available for departure_fill."
        )

    # Prefer the cheapest station within the first 25 miles.
    nearby = [
        s for s in clean
        if s["route_mile"] <= DEPARTURE_REFERENCE_MILES
    ]
    reference = min(
        nearby or clean,
        key=lambda s: (s["price"], s["route_mile"], s["station_id"]),
    )

    # Virtual departure station. It is priced using the reference station.
    departure = {
        **reference,
        "route_mile": Decimal("0"),
        "is_departure_fill": True,
    }

    # Keep the virtual departure separate from real stations.
    candidates = [departure] + [
        {**s, "is_departure_fill": False}
        for s in clean
        if s["route_mile"] > 0
    ]
    candidates.sort(
        key=lambda s: (
            s["route_mile"],
            s["price"],
            s["station_id"],
        )
    )

    # The virtual departure must be the first position.
    candidates = [departure] + [
        s for s in candidates
        if not s["is_departure_fill"]
    ]

    # Destination sentinel: zero price means buy only what is needed.
    destination = {
        "station_id": "__destination__",
        "name": "Destination",
        "route_mile": distance,
        "price": Decimal("0"),
        "is_destination": True,
    }

    stops = []
    total_cost = Decimal("0")
    purchased = Decimal("0")
    fuel = Decimal("0")
    index = 0

    while True:
        current = candidates[index]
        position = current["route_mile"]

        if position == distance:
            break

        # Tank capacity is a hard limit; no epsilon may extend a 500-mile leg.
        limit = position + MAX_RANGE_MILES
        miles = [s["route_mile"] for s in candidates]
        end = bisect_right(miles, limit, lo=index + 1)

        reachable = candidates[index + 1:end]

        if distance <= limit:
            reachable.append(destination)

        if not reachable:
            raise ValueError(
                f"NO_FEASIBLE_FUEL_PLAN: gap starts at mile {position}."
            )

        # First strictly cheaper reachable stop, in route order.
        cheaper = next(
            (s for s in reachable if s["price"] < current["price"]),
            None,
        )

        if cheaper is not None:
            target = cheaper
            needed = (target["route_mile"] - position) / MPG
            buy = max(Decimal("0"), needed - fuel)
        else:
            # Cheapest reachable stop; ties go to the farthest.
            target = min(
                reachable,
                key=lambda s: (
                    s["price"],
                    -s["route_mile"],
                    s["station_id"],
                ),
            )
            distance_to_target = target["route_mile"] - position
            if distance_to_target <= fuel * MPG:
                # Reach this waypoint with fuel on hand; don't top off by a
                # small amount just because we selected it as the next waypoint.
                buy = Decimal("0")
            elif target.get("is_destination"):
                needed = distance_to_target / MPG
                buy = max(Decimal("0"), needed - fuel)
            else:
                buy = TANK_CAPACITY_GALLONS - fuel

        buy = min(buy, TANK_CAPACITY_GALLONS - fuel)

        if buy < 0:
            raise AssertionError("Optimizer produced a negative purchase.")

        fuel_on_arrival = fuel
        fuel_on_departure = fuel + buy
        stop_cost = _money(buy * current["price"])

        if buy > 0:
            stop_reference = (
                reference
                if current.get("is_departure_fill")
                else current
            )
            stops.append({
                "station_id": current["station_id"],
                "name": (
                    "Departure fill"
                    if current.get("is_departure_fill")
                    else current["name"]
                ),
                "route_mile": float(position),
                "price_per_gallon": float(current["price"]),
                "gallons_purchased": float(_gallons(buy)),
                "fuel_on_arrival_gallons": float(_gallons(fuel_on_arrival)),
                "fuel_on_departure_gallons": float(_gallons(fuel_on_departure)),
                "cost": float(stop_cost),
                "stop_type": (
                    "departure_fill"
                    if current.get("is_departure_fill")
                    else "fuel_stop"
                ),
                "price_reference_station_id": stop_reference["station_id"],
                "price_reference": {
                    "station_id": stop_reference["station_id"],
                    "name": stop_reference["name"],
                    "city": stop_reference.get("city"),
                    "state": stop_reference.get("state"),
                    "price_per_gallon": float(stop_reference["price"]),
                    "csv_source": "fuel-price CSV",
                    "coordinate_precision": stop_reference.get("geocode_precision"),
                    "latitude": stop_reference.get("latitude"),
                    "longitude": stop_reference.get("longitude"),
                    "route_mile_estimate": float(stop_reference["route_mile"]),
                },
                "marker_type": (
                    "virtual_route_start"
                    if current.get("is_departure_fill")
                    else "station_centroid_estimate"
                ),
                "route_mile_accuracy": "approximate_geometry_based_estimate",
                "coordinate_warning": (
                    "Virtual route start; the price reference is a separate CSV station."
                    if current.get("is_departure_fill")
                    else current.get("coordinate_warning")
                    or "Centroid coordinate, not a verified physical station location."
                ),
                "station_coordinate": (
                    {
                        "latitude": current.get("latitude"),
                        "longitude": current.get("longitude"),
                        "precision": current.get("geocode_precision"),
                        "is_verified_station_location": False,
                    }
                    if not current.get("is_departure_fill")
                    and current.get("latitude") is not None
                    and current.get("longitude") is not None
                    else None
                ),
            })

        total_cost += stop_cost
        purchased += buy
        fuel += buy

        distance_to_target = target["route_mile"] - position
        if distance_to_target > fuel * MPG:
            raise ValueError(
                f"NO_FEASIBLE_FUEL_PLAN: insufficient fuel for leg "
                f"from mile {position} to {target['route_mile']}."
            )
        fuel -= distance_to_target / MPG

        if fuel < 0:
            raise AssertionError("Fuel became negative.")
        if fuel > TANK_CAPACITY_GALLONS:
            raise AssertionError("Tank capacity exceeded.")

        if target.get("is_destination"):
            break

        index = candidates.index(target)

    consumed = distance / MPG
    leftover = purchased - consumed

    if abs(leftover) > Decimal("0.005"):
        raise AssertionError(
            f"Fuel invariant failed: purchased={purchased}, "
            f"consumed={consumed}, leftover={leftover}"
        )

    return {
        "route_distance_miles": float(distance),
        "fuel_used_gallons": float(_gallons(consumed)),
        "purchased_gallons": float(_gallons(purchased)),
        "fuel_purchase_cost": float(total_cost),
        "starting_fuel_cost_included": True,
        "initial_fuel_policy": "departure_fill",
        "stops": stops,
    }

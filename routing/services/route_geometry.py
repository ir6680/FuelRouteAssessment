
from math import radians, sin, cos, asin, sqrt

EARTH_RADIUS_MILES = 3958.7613


def haversine_miles(lon1, lat1, lon2, lat2):
    """Calculate great-circle distance between two coordinates."""
    lon1, lat1, lon2, lat2 = map(
        radians, [lon1, lat1, lon2, lat2]
    )

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )

    return 2 * EARTH_RADIUS_MILES * asin(
        min(1, sqrt(a))
    )


def geometry_length_miles(route_geometry):
    """Return geometric LineString length; driving length comes from routing provider."""
    coordinates = route_geometry.get("coordinates", [])
    return sum(
        haversine_miles(*start, *end)
        for start, end in zip(coordinates, coordinates[1:])
    )


def _project(point, reference_lon, reference_lat):
    """Project coordinates into a local mile-based coordinate system."""
    lon, lat = point

    miles_per_lon_degree = (
        69.172 * cos(radians(reference_lat))
    )

    return (
        (lon - reference_lon) * miles_per_lon_degree,
        (lat - reference_lat) * 69.0,
    )


def distance_to_route(station, route_geometry):
    """Return approximate distance from a station to the route."""
    coordinates = route_geometry.get("coordinates", [])

    if not coordinates:
        raise ValueError("Route geometry has no coordinates.")

    station_lon = float(station["longitude"])
    station_lat = float(station["latitude"])

    points = [
        _project(point, station_lon, station_lat)
        for point in coordinates
    ]

    if len(points) == 1:
        return haversine_miles(
            station_lon,
            station_lat,
            coordinates[0][0],
            coordinates[0][1],
        )

    minimum_distance = float("inf")

    for index in range(len(points) - 1):
        ax, ay = points[index]
        bx, by = points[index + 1]

        dx = bx - ax
        dy = by - ay
        length_squared = dx * dx + dy * dy

        if length_squared == 0:
            nearest_x, nearest_y = ax, ay
        else:
            t = max(
                0.0,
                min(
                    1.0,
                    -(ax * dx + ay * dy) / length_squared,
                ),
            )
            nearest_x = ax + t * dx
            nearest_y = ay + t * dy

        distance = sqrt(nearest_x**2 + nearest_y**2)
        minimum_distance = min(minimum_distance, distance)

    return minimum_distance


def sample_route(route_geometry, interval_miles=0.5):
    """
    Sample a GeoJSON LineString approximately every interval_miles.

    Returns points with longitude, latitude and cumulative
    geometric distance along the route.
    """
    if interval_miles <= 0:
        raise ValueError("interval_miles must be greater than zero.")

    coordinates = route_geometry.get("coordinates", [])

    if not coordinates:
        raise ValueError("Route geometry has no coordinates.")

    if len(coordinates) == 1:
        lon, lat = coordinates[0]
        return [{
            "longitude": lon,
            "latitude": lat,
            "route_mile": 0.0,
        }]

    sampled = []
    cumulative_miles = 0.0
    next_sample_mile = 0.0

    for index in range(len(coordinates) - 1):
        start = coordinates[index]
        end = coordinates[index + 1]

        segment_miles = haversine_miles(
            start[0], start[1], end[0], end[1]
        )

        if segment_miles == 0:
            continue

        while next_sample_mile <= cumulative_miles + segment_miles:
            fraction = (
                next_sample_mile - cumulative_miles
            ) / segment_miles

            if fraction < 0:
                fraction = 0.0

            if fraction > 1:
                break

            lon = start[0] + fraction * (end[0] - start[0])
            lat = start[1] + fraction * (end[1] - start[1])

            sampled.append({
                "longitude": lon,
                "latitude": lat,
                "route_mile": next_sample_mile,
            })

            next_sample_mile += interval_miles

        cumulative_miles += segment_miles

    final_lon, final_lat = coordinates[-1]

    if (
        not sampled
        or sampled[-1]["route_mile"] < cumulative_miles
    ):
        sampled.append({
            "longitude": final_lon,
            "latitude": final_lat,
            "route_mile": cumulative_miles,
        })

    return sampled


def station_route_position(station, route_geometry):
    """
    Find a station's nearest route segment and approximate
    cumulative mile marker along the route.
    """
    coordinates = route_geometry.get("coordinates", [])

    if not coordinates:
        raise ValueError("Route geometry has no coordinates.")

    station_lon = float(station["longitude"])
    station_lat = float(station["latitude"])

    if len(coordinates) == 1:
        distance = haversine_miles(
            station_lon,
            station_lat,
            coordinates[0][0],
            coordinates[0][1],
        )
        return {
            "distance_to_route_miles": distance,
            "route_mile": 0.0,
        }

    cumulative_miles = 0.0
    best_distance = float("inf")
    best_route_mile = 0.0

    projected_station = (0.0, 0.0)

    for index in range(len(coordinates) - 1):
        start = coordinates[index]
        end = coordinates[index + 1]

        a = _project(start, station_lon, station_lat)
        b = _project(end, station_lon, station_lat)

        dx = b[0] - a[0]
        dy = b[1] - a[1]
        length_squared = dx * dx + dy * dy

        if length_squared == 0:
            t = 0.0
        else:
            t = max(
                0.0,
                min(
                    1.0,
                    -(a[0] * dx + a[1] * dy) / length_squared,
                ),
            )

        nearest_x = a[0] + t * dx
        nearest_y = a[1] + t * dy
        distance = sqrt(nearest_x**2 + nearest_y**2)

        segment_miles = haversine_miles(
            start[0], start[1], end[0], end[1]
        )

        if distance < best_distance:
            best_distance = distance
            best_route_mile = cumulative_miles + t * segment_miles

        cumulative_miles += segment_miles

    return {
        "distance_to_route_miles": best_distance,
        "route_mile": best_route_mile,
    }

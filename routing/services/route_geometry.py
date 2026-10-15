
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

    return 2 * EARTH_RADIUS_MILES * asin(min(1, sqrt(a)))


def distance_to_route(station, route_geometry):
    """Approximate distance to the nearest route segment."""
    coordinates = route_geometry.get("coordinates", [])

    if not coordinates:
        raise ValueError("Route geometry has no coordinates.")

    station_lon = station["longitude"]
    station_lat = station["latitude"]

    # Local planar projection for approximate segment distance.
    reference_lat = radians(station_lat)
    miles_per_lon_degree = (
        69.172 * cos(reference_lat)
    )
    miles_per_lat_degree = 69.0

    def project(point):
        lon, lat = point
        return (
            (lon - station_lon) * miles_per_lon_degree,
            (lat - station_lat) * miles_per_lat_degree,
        )

    points = [project(point) for point in coordinates]

    if len(points) == 1:
        return haversine_miles(
            station_lon, station_lat,
            coordinates[0][0], coordinates[0][1],
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
                min(1.0, -(ax * dx + ay * dy) / length_squared),
            )
            nearest_x = ax + t * dx
            nearest_y = ay + t * dy

        distance = sqrt(nearest_x**2 + nearest_y**2)
        minimum_distance = min(minimum_distance, distance)

    return minimum_distance

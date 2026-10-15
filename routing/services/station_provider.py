
import requests

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
]

MAX_ROUTE_POINTS = 60


def get_fuel_stations_near_route(
    route_geometry,
    radius_meters=5000,
):
    """Fetch OSM fuel stations near sampled route points."""

    if not 1000 <= radius_meters <= 30000:
        raise ValueError("Radius must be between 1,000 and 30,000 meters.")

    coordinates = route_geometry.get("coordinates", [])

    if len(coordinates) < 2:
        raise ValueError("Route must contain at least two coordinates.")

    if len(coordinates) > MAX_ROUTE_POINTS:
        step = (len(coordinates) - 1) / (MAX_ROUTE_POINTS - 1)
        coordinates = [
            coordinates[round(i * step)]
            for i in range(MAX_ROUTE_POINTS)
        ]

    route_points = ",".join(
        f"{lat},{lon}" for lon, lat in coordinates
    )

    query = f"""
    [out:json][timeout:45];
    nwr["amenity"="fuel"]
      (around:{radius_meters},{route_points});
    out center tags;
    """

    errors = []

    for url in OVERPASS_URLS:
        try:
            response = requests.post(
                url,
                data={"data": query},
                headers={"User-Agent": "FuelRouteAssessment/1.0"},
                timeout=(5, 55),
            )
            response.raise_for_status()
            elements = response.json().get("elements", [])

            stations = []

            for element in elements:
                tags = element.get("tags", {})

                if "lat" in element and "lon" in element:
                    latitude = element["lat"]
                    longitude = element["lon"]
                else:
                    center = element.get("center", {})
                    latitude = center.get("lat")
                    longitude = center.get("lon")

                if latitude is None or longitude is None:
                    continue

                stations.append({
                    "osm_type": element.get("type"),
                    "osm_id": element.get("id"),
                    "name": tags.get("name"),
                    "brand": tags.get("brand"),
                    "operator": tags.get("operator"),
                    "latitude": latitude,
                    "longitude": longitude,
                    "address": tags.get("addr:street"),
                    "city": tags.get("addr:city") or tags.get("addr:town"),
                    "state": tags.get("addr:state"),
                })

            return stations

        except (requests.RequestException, ValueError) as exc:
            errors.append(f"{url}: {exc}")

    raise RuntimeError(
        "All Overpass endpoints failed. " + " | ".join(errors)
    )

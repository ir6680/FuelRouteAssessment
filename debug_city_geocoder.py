
import os
import requests
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings

url = f"{settings.GEOCODING_BASE_URL.rstrip('/')}/search"


for city, state in [("Antioch", "TN")]:
    print(f"\n--- {city}, {state} ---")

    response = requests.get(
        url,
        headers={"Authorization": settings.OPENROUTESERVICE_API_KEY},
        params={
            "text": f"{city}, {state}, USA",
            "size": 10,
            "boundary.country": "USA",
        },
        timeout=(5, 20),
    )
    response.raise_for_status()

    features = response.json().get("features", [])
    unique_coordinates = {}

    for feature in features:
        props = feature.get("properties", {})
        coords = feature.get("geometry", {}).get("coordinates", [])

        if len(coords) != 2:
            continue

        key = (round(coords[0], 5), round(coords[1], 5))

        unique_coordinates[key] = {
            "coordinates": coords,
            "label": props.get("label"),
            "layer": props.get("layer"),
            "state": props.get("region_a"),
            "locality": props.get("locality"),
        }

    print("Total results:", len(features))
    print("Unique coordinates:", len(unique_coordinates))

    for item in unique_coordinates.values():
        print(item)

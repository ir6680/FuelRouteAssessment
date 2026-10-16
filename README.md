# Fuel Route API

Django REST API that requests driving geometry from OpenRouteService and estimates fuel purchases using the supplied fuel-price CSV. Station coordinates are derived offline from the US Census Gazetteer by exact city/state match. Gazetteer centroids are not verified fuel station locations; proximity and route-mile estimates are consequently approximate. The API reports location coverage and unmatched counts and does not use OSM name matching or Overpass.

## Setup

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `OPENROUTESERVICE_API_KEY` and `DJANGO_SECRET_KEY` in `.env`. Keep `.env` out of Git. Provide the assessment fuel CSV at `data/fuel-prices-for-be-assessment.csv` and Census Gazetteer files under `data/reference/`.

## Run

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py runserver
.\venv\Scripts\python.exe manage.py test
.\venv\Scripts\python.exe scripts\benchmark_route.py
```

`GET /api/v1/health/` checks liveness; `GET /api/v1/readiness/` checks configuration and source data. `POST /api/v1/route/` accepts JSON:

```json
{"start":"Austin, TX","finish":{"lat":29.7604,"lng":-95.3698}}
```

Each location may be a US city/state string or `{ "lat": number, "lng": number }`. Place-name resolution requires one unambiguous Gazetteer centroid. Route results are cached on disk for 24 hours; only successful responses are cached. A cache hit reports zero external calls for that request. File cache is stored under ignored `data/cache/`.

Errors use structured codes: invalid input or infeasible route is HTTP 422, missing prices is HTTP 422, and unavailable routing provider/configuration is HTTP 503. `api_calls` counts actual route provider calls; offline station lookup and Census geocoding make no external calls.

## Accuracy notes

The optimizer assumes 10 MPG, 500-mile tank range, and an empty tank at departure. Its virtual departure fill uses the lowest valid CSV price within 25 route miles, falling back to the lowest valid candidate along the route when none is in that window. That virtual fill references the selected departure-price station. Each later physical purchase uses that stop's own CSV station ID and price as its price reference. The response includes the reference station's ID, name, city/state, price, and CSV provenance. The virtual departure marker is at route mile 0 and is not the physical location of the reference station. At a selected waypoint, the optimizer travels on existing fuel when that waypoint is already reachable rather than stopping to top off by a small amount.

A city centroid is not a station coordinate, so stations sharing a city may share one coordinate. Stop route miles come from centroid projection onto route geometry, scaled proportionally to OpenRouteService driving distance. Treat proximity, route-mile placement, and stop choices as estimates pending station-level coordinates. Stop metadata labels centroid estimates and marks coordinates as unverified. Prices use the minimum listed price per consistent station ID, in assumed USD/gallon. Missing and ambiguous Gazetteer city/state records are excluded, never assigned guessed coordinates or prices. Fuel consumption is route driving distance / 10 MPG; reported cost is the sum of each stop purchase rounded to cents.

## Postman

For a repeatable, network-free cold/warm endpoint benchmark, run `scripts/benchmark_route.py`. It mocks only OpenRouteService and does not enforce timing thresholds. Use `scripts/benchmark_route.py --live` to make exactly one uncached OpenRouteService request followed by cached repeats. This requires the configured API key and reports provider, station-load, filtering, route-positioning, optimization, and total request timings. Timing logs contain durations, status, and counts; they omit API credentials and request coordinates.

Import `postman/FuelRouteAPI.postman_collection.json`. Configure `baseUrl` to `http://127.0.0.1:8000` and `start`/`finish` as city/state strings or coordinate objects.

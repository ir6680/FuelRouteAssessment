from django.shortcuts import render

# Create your views here.

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from routing.serializers import RouteRequestSerializer
from routing.services.route_service import build_route_result


@api_view(["GET"])
def health_check(request):
    """Basic liveness check."""
    return Response({
        "status": "ok",
        "service": "fuel-route-api",
    })


@api_view(["GET"])
def readiness_check(request):
    """Check whether required routing configuration exists."""
    checks = {
        "openrouteservice_api_key": bool(
            settings.OPENROUTESERVICE_API_KEY
        ),
        "fuel_price_csv": (
            settings.BASE_DIR / "data" / "fuel-prices-for-be-assessment.csv"
        ).is_file(),
    }

    ready = all(checks.values())

    return Response(
        {
            "status": "ready" if ready else "not_ready",
            "checks": checks,
        },
        status=(
            status.HTTP_200_OK
            if ready
            else status.HTTP_503_SERVICE_UNAVAILABLE
        ),
    )
@api_view(["POST"])
def route_view(request):
    """Calculate a driving route and estimate fuel costs."""
    serializer = RouteRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        result = build_route_result(
            serializer.validated_data["start"],
            serializer.validated_data["finish"],
        )
        return Response(result, status=status.HTTP_200_OK)

    except ValueError as exc:
        message = str(exc)
        error_code = (
            "NO_FEASIBLE_FUEL_PLAN"
            if "NO_FEASIBLE_FUEL_PLAN" in message
            else "NO_STATIONS_WITH_PRICES"
            if "No valid fuel-price reference" in message
            else "INVALID_ROUTE_REQUEST"
        )
        return Response(
            {"error": error_code, "detail": message},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    except RuntimeError as exc:
        return Response(
            {
                "error": "ROUTE_SERVICE_UNAVAILABLE",
                "detail": str(exc),
                "api_calls": {
                    "routing": getattr(exc, "provider_calls", 0),
                    "geocoding": 0,
                    "station_discovery": 0,
                },
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    except Exception:
        return Response(
            {"error": "INTERNAL_ERROR", "detail": "The route could not be calculated."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

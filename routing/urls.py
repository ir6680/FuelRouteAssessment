
from django.urls import path

from routing.views import (
    health_check,
    readiness_check,
    route_view,
)

urlpatterns = [
    path("health/", health_check, name="health"),
    path("readiness/", readiness_check, name="readiness"),
    path("healthz", health_check, name="healthz"),
    path("readyz", readiness_check, name="readyz"),
    path("route/", route_view, name="route"),
]

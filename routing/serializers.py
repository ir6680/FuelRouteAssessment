
import json

from rest_framework import serializers


class LocationInputSerializer(serializers.Serializer):
    lat = serializers.FloatField(
        min_value=-90,
        max_value=90,
        required=False,
    )
    lng = serializers.FloatField(
        min_value=-180,
        max_value=180,
        required=False,
    )

    def validate(self, attrs):
        if set(attrs.keys()) != {"lat", "lng"}:
            raise serializers.ValidationError(
                "Provide both lat and lng coordinates."
            )
        return attrs


class LocationField(serializers.Field):
    """Accept a location string or a JSON-encoded coordinate object."""

    default_error_messages = {
        "invalid": "Provide a location string or lat/lng object.",
    }

    def to_internal_value(self, data):
        if isinstance(data, str):
            value = data.strip()
            if not value:
                raise serializers.ValidationError(
                    "Provide a non-empty location up to 200 characters."
                )
            try:
                decoded = json.loads(value)
            except (TypeError, ValueError):
                decoded = value

            # JSON strings and coordinate objects are useful in form inputs,
            # while a normal JSON request already supplies strings as Python
            # strings and should not need another layer of JSON quoting.
            data = decoded

        if isinstance(data, str):
            value = data.strip()
            if not value or len(value) > 200:
                raise serializers.ValidationError(
                    "Provide a non-empty location up to 200 characters."
                )
            return value

        if isinstance(data, dict):
            location = LocationInputSerializer(data=data)
            location.is_valid(raise_exception=True)
            return location.validated_data

        self.fail("invalid")


class RouteRequestSerializer(serializers.Serializer):
    start = LocationField()
    finish = LocationField()

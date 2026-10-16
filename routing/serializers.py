
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


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.JSONField()
    finish = serializers.JSONField()

    def validate(self, attrs):
        for field in ("start", "finish"):
            value = attrs[field]

            if isinstance(value, str):
                value = value.strip()
                if not value or len(value) > 200:
                    raise serializers.ValidationError({
                        field: "Provide a non-empty location up to 200 characters."
                    })
                attrs[field] = value

            elif isinstance(value, dict):
                location = LocationInputSerializer(data=value)
                location.is_valid(raise_exception=True)
                attrs[field] = location.validated_data

            else:
                raise serializers.ValidationError({
                    field: "Provide a location string or lat/lng object."
                })

        return attrs

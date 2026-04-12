from rest_framework import serializers
from .models import JobEngagement, JobStatusLog


class JobStatusLogSerializer(serializers.ModelSerializer):
    changed_by = serializers.StringRelatedField()

    class Meta:
        model = JobStatusLog
        fields = ["id", "status", "changed_by", "timestamp", "note"]


class JobEngagementSerializer(serializers.ModelSerializer):
    client = serializers.StringRelatedField(read_only=True)
    driver = serializers.StringRelatedField(read_only=True)
    status_logs = JobStatusLogSerializer(many=True, read_only=True)

    class Meta:
        model = JobEngagement
        fields = [
            "id",
            "client",
            "driver",
            "employment_type",
            "status",
            "work_location",
            "location_latitude",
            "location_longitude",
            "requirements",
            "agreed_rate",
            "total_earned",
            "created_at",
            "hired_at",
            "started_at",
            "ended_at",
            "client_rating",
            "driver_rating",
            "status_logs",
        ]
        read_only_fields = [
            "id", "client", "driver", "status",
            "hired_at", "started_at", "ended_at",
            "client_rating", "driver_rating", "status_logs",
        ]


class JobCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobEngagement
        fields = [
            "employment_type",
            "work_location",
            "location_latitude",
            "location_longitude",
            "requirements",
            "agreed_rate",
        ]

from rest_framework import serializers

from .models import OperationLogEntry


class OperationLogEntryListSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", default="", label="操作人")
    content_type = serializers.CharField()

    class Meta:
        model = OperationLogEntry
        fields = [
            "id",
            "action_name",
            "action_time",
            "username",
            "object_id",
            "content_type",
            "change_message",
        ]


class OperationLogEntryDetailSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", default="", label="操作人")
    content_type = serializers.CharField()

    class Meta:
        model = OperationLogEntry
        fields = "__all__"

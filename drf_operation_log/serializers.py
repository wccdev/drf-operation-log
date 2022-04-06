from rest_framework import serializers

from .models import OperationLogEntry


class OperationLogEntrySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", default="", label="操作人")
    content_type = serializers.CharField()

    class Meta:
        model = OperationLogEntry
        fields = "__all__"

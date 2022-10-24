from rest_framework import serializers

from .models import OperationLogEntry


class OperationLogEntrySerializer(serializers.ModelSerializer):
    operator = serializers.CharField(source="user.username", default="", label="操作人")
    change_message = serializers.ListField(
        source="get_change_message", child=serializers.CharField(), label="操作内容"
    )
    content_type_name = serializers.CharField(source="object_repr", label="操作对象")
    domain_content_type_name = serializers.CharField(
        source="domain_content_type.name", default="", label="域对象名称"
    )
    change_message_raw = serializers.JSONField(source="change_message")

    class Meta:
        model = OperationLogEntry
        exclude = [
            "object_repr",
            "domain_object_id",
            "object_id",
            "domain_content_type",
            "content_type",
            "user",
            "action_flag",
        ]

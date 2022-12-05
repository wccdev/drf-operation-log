from rest_framework import serializers

from .models import OperationLogEntry
from .utils import clean_deep_data, clean_excluded_fields, format_excluded_fields


class OperationLogEntrySerializer(serializers.ModelSerializer):
    operator = serializers.CharField(source="user.username", default="", label="操作人")
    change_message = serializers.JSONField()
    content_type_name = serializers.CharField(source="object_repr", label="操作对象")
    domain_content_type_name = serializers.CharField(
        source="domain_content_type.name", default="", label="域对象名称"
    )

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

    def to_representation(self, instance):
        excluded_log_fields = self.context.get("excluded_log_fields", [])
        if instance.change_message:
            if excluded_log_fields:
                formatted_excluded_fields = format_excluded_fields(excluded_log_fields)
                clean_excluded_fields(
                    instance.change_message,
                    formatted_excluded_fields[0],
                    formatted_excluded_fields[1],
                )

            clean_deep_data(instance.change_message)

        ret = super().to_representation(instance)
        return ret

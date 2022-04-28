from rest_framework import serializers

from .models import OperationLogEntry


class OperationLogEntrySerializer(serializers.ModelSerializer):
    operator = serializers.CharField(default="", label="操作人")
    change_message = serializers.ListField(source="get_change_message", child=serializers.CharField(), label="操作内容")
    content_type_name = serializers.CharField(source="content_type.name", label="对象名称")
    domain_content_type_name = serializers.CharField(source="domain_content_type.name", default="",  label="域对象名称")

    class Meta:
        model = OperationLogEntry
        fields = "__all__"

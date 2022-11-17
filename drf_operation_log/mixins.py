import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ADDITION, CHANGE, DELETION, OperationLogEntry
from .serializers import OperationLogEntrySerializer
from .signals import operation_logs_pre_save
from .utils import (
    clean_data,
    clean_excluded_fields,
    flatten_dict,
    format_excluded_fields,
    serializer_changed_data_diff,
    serializer_data_diff,
)

logger = logging.getLogger(__name__)


class OperationLogMixin:
    """
    DRF 操作日志Mixin
    必须同时满足如下三个要求的操作才会记录
    1. 写操作(POST, PUT, PATCH, DELETE)
    2. 未被包含在`operationlog_action_exclude`中的action
    3. action 为 create, update, partial_update 或 destroy

    自定义action需要自己创建operation_log
    """

    operationlog_action_exclude = []
    operationlog_domain_field: str = None

    def initial(self, request, *args, **kwargs):
        self.operation_logs = []  # noqa
        super().initial(request, *args, **kwargs)  # noqa

    def _get_view_method(self, request):
        """Get view method."""
        if hasattr(self, "action"):
            return self.action or None
        return request.method.lower()

    @staticmethod
    def _get_user(request):
        """Get user."""
        user = request.user
        if user.is_anonymous:
            return None
        return user

    def _get_action_name(self, serializer) -> str:
        """
        获取动作名称
        """
        if self.action == "create":  # noqa
            return "新增"
        elif self.action in ("update", "partial_update"):  # noqa
            return "编辑"
        elif self.action == "destroy":  # noqa
            return "删除"

        if (
            self._get_action_flag(self.request) == CHANGE
            and "action" in serializer.fields
        ):
            if isinstance(serializer.fields["action"], serializers.ChoiceField):
                action_choices = serializer.fields["action"].choices
                return action_choices.get(serializer.validated_data["action"])

        return getattr(self, self.action).kwargs["name"]  # noqa

    @staticmethod
    def _get_action_flag(request) -> int:
        if request.method == "POST":
            return ADDITION
        elif request.method in ("PUT", "PATCH"):
            return CHANGE
        elif request.method == "DELETE":
            return DELETION

    def perform_create(self, serializer):
        super().perform_create(serializer)  # noqa

        request = self.request  # noqa
        if self.should_log(request):
            operation_log = self._initial_log(
                request,
                serializer.instance,
                new_message=flatten_dict(serializer.validated_data),
            )
            self.operation_logs.append(operation_log)

    def perform_update(self, serializer):
        request = self.request  # noqa
        if self.should_log(request):
            change_message = serializer_data_diff(serializer)

            operation_log = self._initial_log(
                request,
                serializer.instance,
                change_message=change_message,
                serializer=serializer,
            )
            self.operation_logs.append(operation_log)

        super().perform_update(serializer)  # noqa

    def perform_destroy(self, instance):
        request = self.request  # noqa
        if self.should_log(request):
            operation_log = self._initial_log(request, instance)
            self.operation_logs.append(operation_log)

        super().perform_destroy(instance)  # noqa

    def get_excluded_log_fields(self, request) -> list:
        return []

    @action(
        detail=True,
        name="操作日志",
        serializer_class=OperationLogEntrySerializer,
    )
    def operationlogs(self, request, pk):
        """
        获取该资源操作日志接口
        :param request:
        :param pk: 主键
        :return:
        """
        excluded_fields = self.get_excluded_log_fields(request)
        queryset = OperationLogEntry.objects.select_related(
            "user", "content_type", "domain_content_type"
        ).filter(
            domain_object_id=pk,
            domain_content_type=ContentType.objects.get_for_model(self.queryset.model),
        )  # noqa

        queryset = self.filter_queryset(queryset)  # noqa
        page = self.paginate_queryset(queryset)  # noqa
        if page is not None:
            serializer = self.get_serializer(page, many=True)  # noqa
            return self.get_paginated_response(serializer.data)  # noqa

        if excluded_fields:
            formatted_excludes_fields = format_excluded_fields(excluded_fields)
            for q in queryset:
                q.changed_message = clean_excluded_fields(
                    q.changed_message,
                    formatted_excludes_fields[0],
                    formatted_excludes_fields[1],
                )

        serializer = self.get_serializer(queryset, many=True)  # noqa
        return Response(serializer.data)

    def should_log(self, request) -> bool:
        """
        是否记录操作日志, 可以覆盖此方法来自定义控制
        :param request:
        :return:
        """
        return (
            request.method.upper() in ("POST", "PUT", "PATCH", "DELETE")
            and self.action not in self.operationlog_action_exclude  # noqa
        )

    def _initial_log(
        self,
        request,
        instance,
        old_message=None,
        new_message=None,
        change_message=None,
        serializer=None,
    ) -> OperationLogEntry:
        if change_message is None and old_message and new_message and serializer:
            change_message = [
                serializer_changed_data_diff(old_message, new_message, serializer)
            ]

        action_flag = self._get_action_flag(request)

        if change_message:
            change_message = clean_data(change_message)
        else:
            if action_flag == ADDITION:
                change_message = [{"added": []}]
            elif action_flag == DELETION:
                change_message = [{"deleted": []}]

        operation_log = OperationLogEntry(
            user=request.user,
            action=self.action,  # noqa
            action_name=self._get_action_name(serializer),
            action_flag=action_flag,
            content_type=ContentType.objects.get_for_model(instance),
            object_id=instance.pk,
            object_repr=ContentType.objects.get_for_model(instance).name,
            domain_content_type=ContentType.objects.get_for_model(instance),
            domain_object_id=instance.pk,
            change_message=change_message or [],
        )

        if self.operationlog_domain_field:
            attrs = self.operationlog_domain_field.split("__")
            obj = instance
            for attr in attrs:
                obj = getattr(obj, attr)

            if not isinstance(obj, Model):
                raise ValueError("'operationlog_domain_field' must refer to a model!")

            operation_log.domain_content_type = ContentType.objects.get_for_model(obj)
            operation_log.domain_object_id = obj.pk
            operation_log.object_repr = (ContentType.objects.get_for_model(obj).name,)

        return operation_log

    def finalize_response(self, request, response, *args, **kwargs):
        if hasattr(self, "operation_logs") and not getattr(response, "exception", False):
            operation_logs_pre_save.send(
                sender="operation_logs_pre_save",
                request=request,
                operation_logs=self.operation_logs,
            )
            OperationLogEntry.objects.bulk_create(self.operation_logs)
            self.operation_logs.clear()

        return super().finalize_response(request, response, *args, **kwargs)  # noqa

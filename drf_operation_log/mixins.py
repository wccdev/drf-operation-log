import ast
import logging

from django.contrib.contenttypes.models import ContentType
from rest_framework.decorators import action
from rest_framework.response import Response

from .utils import flatten_dict, serializer_data_diff, split_get
from .models import ADDITION, CHANGE, DELETION, OperationLogEntry
from .serializers import OperationLogEntrySerializer

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

    CLEANED_SUBSTITUTE = "********************"
    sensitive_fields = {}
    operationlog_action_exclude = []

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

    def _clean_data(self, data):
        """
        Clean a dictionary of data of potentially sensitive info before
        sending to the database.
        Function based on the "_clean_credentials" function of django
        (https://github.com/django/django/blob/stable/1.11.x/django/contrib/auth/__init__.py#L50)
        Fields defined by django are by default cleaned with this function
        You can define your own sensitive fields in your view by defining a set
        eg: sensitive_fields = {'field1', 'field2'}
        """
        if isinstance(data, bytes):
            data = data.decode(errors="replace")

        if isinstance(data, list):
            return [self._clean_data(d) for d in data]

        if isinstance(data, dict):
            SENSITIVE_FIELDS: set = {
                "api",
                "token",
                "key",
                "secret",
                "password",
                "signature",
            }

            data = dict(data)
            if self.sensitive_fields:
                SENSITIVE_FIELDS = SENSITIVE_FIELDS | {field.lower() for field in self.sensitive_fields}

            for key, value in data.items():
                try:
                    value = ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    pass
                if isinstance(value, (list, dict)):
                    data[key] = self._clean_data(value)
                if key.lower() in SENSITIVE_FIELDS:
                    data[key] = self.CLEANED_SUBSTITUTE
        return data

    def perform_create(self, serializer):
        super().perform_create(serializer)  # noqa

        request = self.request  # noqa
        if self.should_log(request):
            self._initial_log(request, serializer.instance, new_message=flatten_dict(serializer.validated_data))

    def perform_update(self, serializer):
        request = self.request  # noqa
        if self.should_log(request):
            new_message = flatten_dict(serializer.validated_data)
            old_message = {}
            for k in new_message.keys():
                old_message[k] = split_get(serializer.instance, k)

            self._initial_log(
                request,
                serializer.instance,
                old_message=old_message,
                new_message=new_message,
                serializer=serializer,
            )

        super().perform_update(serializer)  # noqa

    def perform_destroy(self, instance):
        request = self.request  # noqa
        if self.should_log(request):
            self._initial_log(request, instance)

        super().perform_destroy(instance)  # noqa

    @action(
        detail=True,
        name="操作日志",
        serializer_class=OperationLogEntrySerializer,
    )
    def operationlog(self, request, pk):
        """
        获取该资源操作日志接口
        :param request:
        :param pk: 主键
        :return:
        """
        queryset = OperationLogEntry.objects.select_related("user", "content_type").filter(
            object_id=pk, content_type=ContentType.objects.get_for_model(self.queryset.model)
        )  # noqa
        queryset = self.filter_queryset(queryset)  # noqa
        page = self.paginate_queryset(queryset)  # noqa
        if page is not None:
            serializer = self.get_serializer(page, many=True)  # noqa
            return self.get_paginated_response(serializer.data)  # noqa

        serializer = self.get_serializer(queryset, many=True)  # noqa
        return Response(serializer.data)

    def should_log(self, request) -> bool:
        """
        是否记录操作日志, 可以覆盖此方法来自定义控制
        :param request:
        :return:
        """
        return (
            request.method in ("POST", "PUT", "PATCH", "DELETE") and self.action not in self.operationlog_action_exclude
        )

    def _get_action_name(self) -> str:
        """
        获取动作名称
        """
        if self.action == "create":
            return "新增"
        elif self.action in ("update", "partial_update"):
            return "编辑"
        elif self.action == "destroy":
            return "删除"
        else:
            return getattr(self, self.action).kwargs["name"]

    @staticmethod
    def _get_action_flag(request) -> int:
        if request.method == "POST":
            return ADDITION
        elif request.method in ("PUT", "PATCH"):
            return CHANGE
        elif request.method == "DELETE":
            return DELETION

    def _initial_log(
        self, request, instance, old_message=None, new_message=None, change_message=None, serializer=None
    ) -> None:
        if change_message is None and old_message and new_message and serializer:
            change_message = serializer_data_diff(old_message, new_message, serializer)

        self.operation_log = OperationLogEntry(
            user=request.user,
            action=self.action,
            action_name=self._get_action_name(),
            action_flag=self._get_action_flag(request),
            content_type=ContentType.objects.get_for_model(instance),
            object_id=instance.pk,
            change_message=change_message or {},
        )

    def finalize_response(self, request, response, *args, **kwargs):
        if (
            hasattr(self, "operation_log")
            and self.operation_log.action
            and self.operation_log.object_id
            and self.operation_log.content_type
            and not getattr(response, "exception", False)
        ):
            self.operation_log.save()

        return super().finalize_response(request, response, *args, **kwargs)

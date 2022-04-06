from drfexts.viewsets import ExtGenericViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAdminUser

from scf.operationlog.models import OperationLogEntry
from scf.operationlog.serializers import (
    OperationLogEntryDetailSerializer,
    OperationLogEntryListSerializer,
)


class OperationlogViewSet(
    ListModelMixin,
    RetrieveModelMixin,
    ExtGenericViewSet,
):
    queryset = OperationLogEntry.objects.select_related("user", "content_type")
    permission_classes = (IsAdminUser,)
    serializer_class = {
        "default": OperationLogEntryListSerializer,
        "retrieve": OperationLogEntryDetailSerializer,
    }

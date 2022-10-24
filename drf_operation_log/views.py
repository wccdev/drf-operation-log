from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAdminUser
from rest_framework.viewsets import GenericViewSet

from .models import OperationLogEntry
from .serializers import OperationLogEntrySerializer


class OperationlogViewSet(
    ListModelMixin,
    RetrieveModelMixin,
    GenericViewSet,
):
    queryset = OperationLogEntry.objects.select_related(
        "user", "content_type", "domain_content_type"
    )
    permission_classes = (IsAdminUser,)
    serializer_class = OperationLogEntrySerializer
    search_fields = ["user__username", "object_repr"]

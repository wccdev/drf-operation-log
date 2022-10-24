from rest_framework.routers import SimpleRouter

from .views import OperationlogViewSet

router = SimpleRouter()

router.register("operationlogs", OperationlogViewSet, basename="operationlogs")
urlpatterns = router.urls

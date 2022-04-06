from rest_framework.routers import SimpleRouter

from .views import OperationlogViewSet

router = SimpleRouter()

router.register("operationlogs", OperationlogViewSet)
urlpatterns = router.urls

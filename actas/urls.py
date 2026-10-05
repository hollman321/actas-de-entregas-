from rest_framework.routers import DefaultRouter
from .views import ActaViewSet, FormFieldDefinitionViewSet

router = DefaultRouter()
router.register("field-definitions", FormFieldDefinitionViewSet, basename="field-definition")
router.register("", ActaViewSet, basename="acta")
urlpatterns = router.urls

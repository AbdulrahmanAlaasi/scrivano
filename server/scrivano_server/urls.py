from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from groups.api import GroupViewSet
from tenancy.api import WorkspaceViewSet

router = DefaultRouter()
router.register("workspaces", WorkspaceViewSet, basename="workspace")
router.register("groups", GroupViewSet, basename="group")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
]

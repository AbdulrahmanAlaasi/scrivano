from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from groups.api import GroupViewSet
from groups.context_api import GroupContextViewSet
from groups.documents_api import GroupDocumentViewSet
from chat.api import MeetingChatViewSet
from intelligence.api import MeetingIntelligenceViewSet, TaskViewSet
from meetings.api import MeetingViewSet
from tenancy.api import WorkspaceViewSet

router = DefaultRouter()
router.register("workspaces", WorkspaceViewSet, basename="workspace")
router.register("groups", GroupViewSet, basename="group")
router.register("documents", GroupDocumentViewSet, basename="document")
router.register("meetings", MeetingViewSet, basename="meeting")
router.register("tasks", TaskViewSet, basename="task")

intelligence_view = MeetingIntelligenceViewSet.as_view({"get": "list", "post": "create"})

context_list = GroupContextViewSet.as_view({"get": "list"})
context_set = GroupContextViewSet.as_view({"put": "set"})
context_history = GroupContextViewSet.as_view({"get": "history"})

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/groups/<uuid:group_pk>/context/", context_list),
    path("api/groups/<uuid:group_pk>/context/set/", context_set),
    path("api/groups/<uuid:group_pk>/context/history/", context_history),
    path("api/meetings/<uuid:meeting_pk>/intelligence/", intelligence_view),
    path("api/meetings/<uuid:meeting_pk>/chat/", MeetingChatViewSet.as_view({"get": "list"})),
    path("api/meetings/<uuid:meeting_pk>/chat/ask/", MeetingChatViewSet.as_view({"post": "ask"})),
    path("api/meetings/<uuid:meeting_pk>/chat/answer/", MeetingChatViewSet.as_view({"post": "answer"})),
]

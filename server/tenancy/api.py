from django.db import transaction
from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied

from groups.models import Group, GroupMember
from .models import Workspace, WorkspaceMember


class WorkspaceSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ["id", "name", "logo_url", "settings", "role", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_role(self, obj) -> str | None:
        user = self.context["request"].user
        member = next((m for m in obj.members.all() if m.user_id == user.id), None)
        return member.role if member else None


class WorkspaceViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceSerializer

    def get_queryset(self):
        return (
            Workspace.objects.filter(
                members__user=self.request.user, deleted_at__isnull=True
            )
            .prefetch_related("members")
            .distinct()
        )

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        workspace = serializer.save(owner=user)
        WorkspaceMember.objects.create(
            workspace=workspace, user=user, role=WorkspaceMember.Role.OWNER
        )
        # Every workspace gets the undeletable default Group (spec §2).
        inbox = Group.objects.create(
            workspace=workspace,
            name="Meeting Inbox",
            owner=user,
            created_by=user,
            is_inbox=True,
            description="Meetings the system could not confidently classify.",
        )
        GroupMember.objects.create(group=inbox, user=user, role=GroupMember.Role.OWNER)

    def perform_destroy(self, instance):
        member = instance.members.filter(user=self.request.user).first()
        if not member or member.role != WorkspaceMember.Role.OWNER:
            raise PermissionDenied("Only the workspace owner can delete a workspace.")
        from django.utils import timezone

        instance.deleted_at = timezone.now()
        instance.save(update_fields=["deleted_at"])

from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError

from tenancy.models import Workspace
from .models import Group, GroupMember


class GroupSerializer(serializers.ModelSerializer):
    workspace = serializers.PrimaryKeyRelatedField(queryset=Workspace.objects.none())

    class Meta:
        model = Group
        fields = [
            "id",
            "workspace",
            "name",
            "group_type",
            "description",
            "purpose",
            "status",
            "start_date",
            "target_date",
            "default_language",
            "is_inbox",
            "created_at",
        ]
        read_only_fields = ["id", "is_inbox", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            self.fields["workspace"].queryset = Workspace.objects.filter(
                members__user=request.user
            )


class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer

    def get_queryset(self):
        qs = Group.objects.visible_to(self.request.user).filter(deleted_at__isnull=True)
        workspace_id = self.request.query_params.get("workspace")
        if workspace_id:
            qs = qs.filter(workspace_id=workspace_id)
        return qs.distinct()

    def perform_create(self, serializer):
        group = serializer.save(owner=self.request.user, created_by=self.request.user)
        GroupMember.objects.create(
            group=group, user=self.request.user, role=GroupMember.Role.OWNER
        )

    def perform_destroy(self, instance):
        if instance.is_inbox:
            raise ValidationError("The Meeting Inbox group cannot be deleted.")
        member = instance.members.filter(user=self.request.user).first()
        if not member or member.role != GroupMember.Role.OWNER:
            raise PermissionDenied("Only the group owner can delete a group.")
        from django.utils import timezone

        instance.deleted_at = timezone.now()
        instance.save(update_fields=["deleted_at"])

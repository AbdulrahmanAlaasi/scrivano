import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class TimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class User(AbstractUser):
    """Mirrors Supabase Auth users; `supabase_id` links the JWT subject."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supabase_id = models.UUIDField(null=True, blank=True, unique=True)
    display_name = models.CharField(max_length=200, blank=True)
    language = models.CharField(max_length=10, default="en")
    timezone = models.CharField(max_length=64, default="UTC")


class Workspace(TimeStampedModel):
    name = models.CharField(max_length=200)
    logo_url = models.URLField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_workspaces"
    )
    settings = models.JSONField(default=dict, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.name


class WorkspaceMember(TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "owner"
        ADMIN = "admin"
        MEMBER = "member"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspace_memberships"
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "user"], name="uniq_workspace_member")
        ]


class Invitation(TimeStampedModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(
        max_length=16, choices=WorkspaceMember.Role.choices, default=WorkspaceMember.Role.MEMBER
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)


class WorkspaceScopedManager(models.Manager):
    """Every workspace-owned model queries through this manager so cross-tenant
    leaks are structurally impossible (docs/ARCHITECTURE.md §7)."""

    def visible_to(self, user):
        return self.get_queryset().filter(workspace__members__user=user)


class WorkspaceScopedModel(TimeStampedModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="+")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    objects = WorkspaceScopedManager()

    class Meta:
        abstract = True

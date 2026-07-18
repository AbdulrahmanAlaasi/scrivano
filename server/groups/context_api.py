"""Versioned structured Group Context (spec §5, §6 'Structured Group Context').

Each context field ('business_description', 'scope', 'glossary',
'task_standards', …) is append-only versioned: writing a field creates a new
version row; reads return the latest version of every field. History is never
lost, satisfying the spec's versioning and audit requirements.
"""

from django.db import models, transaction
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Group, GroupContextValue

# Stable field keys for the guided setup steps 1–6. Free-form keys are also
# allowed (prefixed 'custom_') so groups can extend their context.
KNOWN_FIELDS = {
    "business_description",
    "project_objective",
    "problem",
    "products_services",
    "client",
    "target_audience",
    "business_model",
    "scope",
    "out_of_scope",
    "current_phase",
    "success_metrics",
    "deliverables",
    "milestones",
    "deadlines",
    "constraints",
    "risks",
    "dependencies",
    "blockers",
    "architecture",
    "tech_stack",
    "requirements",
    "brand_guidelines",
    "communication_guidelines",
    "client_context",
    "glossary",
    "task_standards",
}


class ContextValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupContextValue
        fields = ["field", "value", "version", "updated_at"]


class GroupContextViewSet(viewsets.ViewSet):
    """/api/groups/<group_id>/context/ — GET latest snapshot, PUT field values."""

    def _group_for(self, request, group_pk) -> Group:
        group = (
            Group.objects.visible_to(request.user)
            .filter(pk=group_pk, deleted_at__isnull=True)
            .first()
        )
        if group is None:
            raise PermissionDenied("Group not found or not accessible.")
        return group

    def _can_edit(self, request, group: Group) -> bool:
        member = group.members.filter(user=request.user).first()
        return bool(member and member.role in ("owner", "member"))

    def list(self, request, group_pk=None):
        group = self._group_for(request, group_pk)
        latest = (
            GroupContextValue.objects.filter(group=group)
            .order_by("field", "-version")
            .distinct("field")
            if _supports_distinct_on()
            else _latest_per_field(group)
        )
        return Response({v.field: ContextValueSerializer(v).data for v in latest})

    @action(detail=False, methods=["put"])
    def set(self, request, group_pk=None):
        """PUT {"values": {"scope": …, "glossary": …}} — versions each field."""
        group = self._group_for(request, group_pk)
        if not self._can_edit(request, group):
            raise PermissionDenied("Viewers cannot edit group context.")
        values = request.data.get("values")
        if not isinstance(values, dict) or not values:
            return Response({"detail": "Provide a non-empty 'values' object."}, status=400)
        for field in values:
            if field not in KNOWN_FIELDS and not field.startswith("custom_"):
                return Response(
                    {"detail": f"Unknown context field '{field}'. Use a known field or 'custom_*'."},
                    status=400,
                )
        written = {}
        with transaction.atomic():
            for field, value in values.items():
                current = (
                    GroupContextValue.objects.filter(group=group, field=field)
                    .order_by("-version")
                    .first()
                )
                row = GroupContextValue.objects.create(
                    workspace=group.workspace,
                    group=group,
                    field=field,
                    value=value,
                    version=(current.version + 1) if current else 1,
                    created_by=request.user,
                )
                written[field] = ContextValueSerializer(row).data
        return Response(written)

    @action(detail=False, methods=["get"])
    def history(self, request, group_pk=None):
        group = self._group_for(request, group_pk)
        field = request.query_params.get("field")
        qs = GroupContextValue.objects.filter(group=group).order_by("field", "-version")
        if field:
            qs = qs.filter(field=field)
        return Response(ContextValueSerializer(qs, many=True).data)


def _supports_distinct_on() -> bool:
    from django.db import connection

    return connection.vendor == "postgresql"


def _latest_per_field(group):
    latest_versions = (
        GroupContextValue.objects.filter(group=group)
        .values("field")
        .annotate(max_version=models.Max("version"))
    )
    rows = []
    for entry in latest_versions:
        rows.append(
            GroupContextValue.objects.get(
                group=group, field=entry["field"], version=entry["max_version"]
            )
        )
    return rows

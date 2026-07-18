"""Meetings API (spec §23) + transcript ingestion.

Scrivano's STT provider is the browser (local Whisper, spec §41), so the
client posts finished transcript segments here. Ingestion is idempotent:
each segment carries a deterministic dedupe_key, and re-posting the same
batch never duplicates rows (spec §22).
"""

import hashlib

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from groups.models import Group
from .models import Meeting, ProcessingJob, TranscriptSegment


class MeetingSerializer(serializers.ModelSerializer):
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.none())
    segment_count = serializers.IntegerField(source="segments.count", read_only=True)

    class Meta:
        model = Meeting
        fields = [
            "id",
            "group",
            "title",
            "meeting_type",
            "scheduled_start",
            "started_at",
            "ended_at",
            "duration_seconds",
            "status",
            "language",
            "segment_count",
            "created_at",
        ]
        read_only_fields = ["id", "status", "segment_count", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            self.fields["group"].queryset = Group.objects.visible_to(request.user).filter(
                deleted_at__isnull=True
            )


class SegmentInSerializer(serializers.Serializer):
    sequence = serializers.IntegerField(min_value=0)
    start_ms = serializers.IntegerField(min_value=0)
    end_ms = serializers.IntegerField(min_value=0)
    text = serializers.CharField()
    speaker_label = serializers.CharField(required=False, allow_blank=True, default="")
    language = serializers.CharField(required=False, default="en")
    confidence = serializers.FloatField(required=False, allow_null=True, default=None)


class SegmentOutSerializer(serializers.ModelSerializer):
    text = serializers.CharField(read_only=True)

    class Meta:
        model = TranscriptSegment
        fields = [
            "id",
            "sequence",
            "speaker_label",
            "start_ms",
            "end_ms",
            "text",
            "language",
            "confidence",
        ]


class MeetingViewSet(viewsets.ModelViewSet):
    serializer_class = MeetingSerializer
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        qs = Meeting.objects.visible_to(self.request.user).filter(deleted_at__isnull=True)
        group_id = self.request.query_params.get("group")
        if group_id:
            qs = qs.filter(group_id=group_id)
        return qs.select_related("group").prefetch_related("segments").distinct()

    def perform_create(self, serializer):
        group = serializer.validated_data["group"]
        member = group.members.filter(user=self.request.user).first()
        if not member or member.role == "viewer":
            raise PermissionDenied("Viewers cannot create meetings.")
        serializer.save(
            workspace=group.workspace,
            created_by=self.request.user,
            started_at=timezone.now(),
        )

    def perform_destroy(self, instance):
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["deleted_at"])
        # Deleted meetings leave every retrieval index immediately (spec §47).
        instance.segments.all().delete()

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def segments(self, request, pk=None):
        """POST {"segments": [...]} — idempotent transcript ingestion."""
        meeting = self.get_object()
        member = meeting.group.members.filter(user=request.user).first()
        if not member or member.role == "viewer":
            raise PermissionDenied("Viewers cannot edit transcripts.")
        ser = SegmentInSerializer(data=request.data.get("segments", []), many=True)
        ser.is_valid(raise_exception=True)
        created = 0
        for seg in ser.validated_data:
            content = f"{seg['sequence']}|{seg['start_ms']}|{seg['end_ms']}|{seg['text']}"
            dedupe = f"{meeting.id}:{hashlib.sha256(content.encode()).hexdigest()[:32]}"
            _, was_created = TranscriptSegment.objects.get_or_create(
                dedupe_key=dedupe,
                defaults=dict(
                    workspace=meeting.workspace,
                    meeting=meeting,
                    created_by=request.user,
                    sequence=seg["sequence"],
                    start_ms=seg["start_ms"],
                    end_ms=seg["end_ms"],
                    original_text=seg["text"],
                    speaker_label=seg["speaker_label"],
                    language=seg["language"],
                    confidence=seg["confidence"],
                ),
            )
            created += int(was_created)
        job, _ = ProcessingJob.objects.get_or_create(
            meeting=meeting,
            stage=ProcessingJob.Stage.TRANSCRIBED,
            defaults={"workspace": meeting.workspace, "created_by": request.user},
        )
        job.status = ProcessingJob.Status.COMPLETE
        job.attempt += 1
        job.save(update_fields=["status", "attempt"])
        if meeting.status == Meeting.Status.DRAFT:
            meeting.status = Meeting.Status.PROCESSING
            meeting.save(update_fields=["status"])
        total = TranscriptSegment.objects.filter(meeting=meeting).count()
        return Response({"created": created, "total": total})

    @segments.mapping.get
    def list_segments(self, request, pk=None):
        meeting = self.get_object()
        return Response(SegmentOutSerializer(meeting.segments.all(), many=True).data)

    @action(detail=True, methods=["post"])
    def finish(self, request, pk=None):
        """Mark the meeting ended; duration derived from the last segment."""
        meeting = self.get_object()
        last = meeting.segments.order_by("-end_ms").first()
        meeting.ended_at = timezone.now()
        meeting.duration_seconds = (last.end_ms // 1000) if last else 0
        meeting.status = Meeting.Status.COMPLETE
        meeting.save(update_fields=["ended_at", "duration_seconds", "status"])
        return Response(MeetingSerializer(meeting, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def jobs(self, request, pk=None):
        meeting = self.get_object()
        return Response(
            [
                {"stage": j.stage, "status": j.status, "attempt": j.attempt, "error": j.error}
                for j in meeting.jobs.all()
            ]
        )

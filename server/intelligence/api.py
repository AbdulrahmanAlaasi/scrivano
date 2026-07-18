"""Derived-intelligence ingestion + read API (spec §24–25).

The LLM runs client-side (the local provider layer in src/lib/llm.ts, spec
§41), so the backend's contract is *validated ingestion*:

- every artifact must cite real transcript segments **of the same meeting**;
- owners and deadlines are never invented: at ingestion they are accepted
  only with source="stated" (grounded in the transcript, citation required);
  humans set them later via PATCH /api/tasks/{id}/ (source="manual");
- everything is idempotent: the server derives a deterministic dedupe_key,
  so re-running the pipeline upserts instead of duplicating (spec §22).
"""

import hashlib

from django.db import transaction
from django.http import Http404
from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from groups.models import Person
from meetings.models import Meeting, ProcessingJob, TranscriptSegment
from .models import (
    ActionItem,
    Commitment,
    Decision,
    DiscussionTopic,
    Question,
    Risk,
    SummarySection,
)


class CitationSerializer(serializers.Serializer):
    segment_id = serializers.UUIDField()
    quote = serializers.CharField(required=False, allow_blank=True, default="")


def _dedupe(meeting, kind: str, text: str) -> str:
    digest = hashlib.sha256(f"{kind}|{text.strip().lower()}".encode()).hexdigest()[:32]
    return f"{meeting.id}:{kind}:{digest}"


class TaskSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.name", read_only=True, default=None)
    meeting_title = serializers.CharField(source="meeting.title", read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True)

    class Meta:
        model = ActionItem
        fields = [
            "id", "title", "description", "owner", "owner_name", "owner_source",
            "owner_suggested", "due_date", "due_source", "priority", "status",
            "definition_of_done", "why", "risk_if_delayed", "citations",
            "meeting", "meeting_title", "group", "group_name", "created_at",
        ]
        read_only_fields = [
            "id", "owner_name", "owner_source", "due_source", "citations",
            "meeting", "meeting_title", "group", "group_name", "created_at",
        ]


class MeetingIntelligenceViewSet(viewsets.ViewSet):
    """POST = bulk idempotent ingestion, GET = full read. Nested under
    /api/meetings/<meeting_pk>/intelligence/."""

    def _meeting(self, request, meeting_pk):
        meeting = (
            Meeting.objects.visible_to(request.user)
            .filter(deleted_at__isnull=True, pk=meeting_pk)
            .select_related("group", "workspace")
            .first()
        )
        if meeting is None:
            raise Http404
        return meeting

    def _require_editor(self, meeting, user):
        member = meeting.group.members.filter(user=user).first()
        if not member or member.role == "viewer":
            raise PermissionDenied("Viewers cannot write intelligence artifacts.")

    def _validate_citations(self, item, kind, idx, segment_ids):
        raw = item.get("citations") or []
        ser = CitationSerializer(data=raw, many=True, allow_empty=False)
        if not ser.is_valid():
            raise ValidationError({kind: {idx: ser.errors}})
        cites = ser.validated_data
        for c in cites:
            if str(c["segment_id"]) not in segment_ids:
                raise ValidationError(
                    {kind: {idx: f"citation segment {c['segment_id']} is not a segment of this meeting"}}
                )
        return [{"segment_id": str(c["segment_id"]), "quote": c["quote"]} for c in cites]

    def _person(self, meeting, person_id, kind, idx):
        if not person_id:
            return None
        person = Person.objects.filter(pk=person_id, workspace=meeting.workspace).first()
        if person is None:
            raise ValidationError({kind: {idx: "unknown person for this workspace"}})
        return person

    @transaction.atomic
    def create(self, request, meeting_pk=None):
        meeting = self._meeting(request, meeting_pk)
        self._require_editor(meeting, request.user)
        segment_ids = set(
            str(pk)
            for pk in TranscriptSegment.objects.filter(meeting=meeting).values_list("pk", flat=True)
        )
        common = dict(
            workspace=meeting.workspace,
            meeting=meeting,
            group=meeting.group,
            created_by=request.user,
        )
        created = {}

        def upsert(model, artifact_kind, key_text, item, idx, **fields):
            cites = self._validate_citations(item, artifact_kind, idx, segment_ids)
            _, was_created = model.objects.get_or_create(
                dedupe_key=_dedupe(meeting, artifact_kind, key_text),
                defaults=dict(common, citations=cites, **fields),
            )
            created[artifact_kind] = created.get(artifact_kind, 0) + int(was_created)

        for i, item in enumerate(request.data.get("summary_sections", [])):
            kind = item.get("kind")
            if kind not in SummarySection.Kind.values:
                raise ValidationError({"summary_sections": {i: "invalid kind"}})
            body = str(item.get("body", "")).strip()
            if not body:
                raise ValidationError({"summary_sections": {i: "body required"}})
            upsert(
                SummarySection, "summary", f"{kind}|{body}", item, i,
                kind=kind, order=int(item.get("order", 0)), body=body,
            )

        for i, item in enumerate(request.data.get("topics", [])):
            title = str(item.get("title", "")).strip()
            if not title:
                raise ValidationError({"topics": {i: "title required"}})
            upsert(DiscussionTopic, "topic", title, item, i, title=title, body=item.get("body", ""))

        for i, item in enumerate(request.data.get("decisions", [])):
            statement = str(item.get("statement", "")).strip()
            if not statement:
                raise ValidationError({"decisions": {i: "statement required"}})
            status_ = item.get("status", Decision.Status.DISCUSSED)
            if status_ not in Decision.Status.values:
                raise ValidationError({"decisions": {i: "invalid status"}})
            upsert(
                Decision, "decision", statement, item, i,
                statement=statement, status=status_,
                reason=item.get("reason", ""), impact=item.get("impact", ""),
                confidence=item.get("confidence"),
            )

        for i, item in enumerate(request.data.get("tasks", [])):
            title = str(item.get("title", "")).strip()
            if not title:
                raise ValidationError({"tasks": {i: "title required"}})
            owner = self._person(meeting, item.get("owner"), "tasks", i)
            # Prime rule: owners/deadlines are never invented. At ingestion the
            # only acceptable source is the transcript itself ("stated").
            if owner is not None and item.get("owner_source") != ActionItem.Source.STATED:
                raise ValidationError(
                    {"tasks": {i: "owner may only be set at ingestion with owner_source='stated' (cited in the transcript); otherwise leave it null for a human to assign"}}
                )
            if item.get("due_date") and item.get("due_source") != ActionItem.Source.STATED:
                raise ValidationError(
                    {"tasks": {i: "due_date may only be set at ingestion with due_source='stated'"}}
                )
            upsert(
                ActionItem, "task", title, item, i,
                title=title, description=item.get("description", ""),
                owner=owner, owner_source=item.get("owner_source", "") if owner else "",
                owner_suggested=bool(item.get("owner_suggested", False)),
                due_date=item.get("due_date") or None,
                due_source=item.get("due_source", "") if item.get("due_date") else "",
                priority=item.get("priority", ""),
                definition_of_done=item.get("definition_of_done", ""),
                why=item.get("why", ""), risk_if_delayed=item.get("risk_if_delayed", ""),
            )

        for i, item in enumerate(request.data.get("commitments", [])):
            text = str(item.get("text", "")).strip()
            if not text:
                raise ValidationError({"commitments": {i: "text required"}})
            person = self._person(meeting, item.get("person"), "commitments", i)
            if item.get("due_date") and item.get("due_source") != ActionItem.Source.STATED:
                raise ValidationError(
                    {"commitments": {i: "due_date requires due_source='stated'"}}
                )
            upsert(
                Commitment, "commitment", text, item, i,
                text=text, person=person, due_date=item.get("due_date") or None,
                due_source=item.get("due_source", "") if item.get("due_date") else "",
            )

        for i, item in enumerate(request.data.get("questions", [])):
            text = str(item.get("text", "")).strip()
            if not text:
                raise ValidationError({"questions": {i: "text required"}})
            status_ = item.get("status", Question.Status.UNANSWERED)
            if status_ not in Question.Status.values:
                raise ValidationError({"questions": {i: "invalid status"}})
            upsert(Question, "question", text, item, i, text=text, status=status_, answer=item.get("answer", ""))

        for i, item in enumerate(request.data.get("risks", [])):
            text = str(item.get("risk", "")).strip()
            if not text:
                raise ValidationError({"risks": {i: "risk required"}})
            owner = self._person(meeting, item.get("owner"), "risks", i)
            upsert(
                Risk, "risk", text, item, i,
                risk=text, impact=item.get("impact", ""),
                mitigation=item.get("mitigation", ""), owner=owner,
            )

        for stage in (ProcessingJob.Stage.SUMMARIZED, ProcessingJob.Stage.ENTITIES_EXTRACTED):
            job, _ = ProcessingJob.objects.get_or_create(
                meeting=meeting, stage=stage,
                defaults={"workspace": meeting.workspace, "created_by": request.user},
            )
            job.status = ProcessingJob.Status.COMPLETE
            job.attempt += 1
            job.save(update_fields=["status", "attempt"])
        return Response({"created": created})

    def list(self, request, meeting_pk=None):
        meeting = self._meeting(request, meeting_pk)

        def ser(qs, fields):
            return [
                {"id": str(o.pk), **{f: getattr(o, f) for f in fields}, "citations": o.citations}
                for o in qs
            ]

        return Response(
            {
                "summary_sections": ser(meeting.summarysections.all(), ["kind", "order", "body"]),
                "topics": ser(meeting.discussiontopics.all(), ["title", "body"]),
                "decisions": ser(
                    meeting.decisions.all(), ["statement", "status", "reason", "impact", "confidence"]
                ),
                "tasks": TaskSerializer(meeting.actionitems.all(), many=True).data,
                "commitments": ser(meeting.commitments.all(), ["text", "person_id", "due_date", "due_source", "status"]),
                "questions": ser(meeting.questions.all(), ["text", "status", "answer"]),
                "risks": ser(meeting.risks.all(), ["risk", "impact", "mitigation", "owner_id"]),
            }
        )


class TaskViewSet(viewsets.ModelViewSet):
    """/api/tasks/ — the cross-meeting task list (spec §36 /app/tasks).
    Humans may set owner/due_date here; those writes are recorded as
    source='manual' so grounded and human-entered values stay distinguishable."""

    serializer_class = TaskSerializer
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        qs = ActionItem.objects.visible_to(self.request.user).select_related(
            "owner", "meeting", "group"
        )
        params = self.request.query_params
        if params.get("group"):
            qs = qs.filter(group_id=params["group"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("unassigned") == "1":
            qs = qs.filter(owner__isnull=True)
        return qs.distinct()

    def perform_update(self, serializer):
        instance = serializer.instance
        member = instance.group.members.filter(user=self.request.user).first()
        if not member or member.role == "viewer":
            raise PermissionDenied("Viewers cannot edit tasks.")
        updates = {}
        if "owner" in serializer.validated_data:
            owner = serializer.validated_data["owner"]
            if owner is not None and owner.workspace_id != instance.workspace_id:
                raise ValidationError({"owner": "unknown person for this workspace"})
            updates["owner_source"] = ActionItem.Source.MANUAL if owner else ""
        if "due_date" in serializer.validated_data:
            updates["due_source"] = (
                ActionItem.Source.MANUAL if serializer.validated_data["due_date"] else ""
            )
        serializer.save(**updates)

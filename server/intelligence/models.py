"""Derived intelligence artifacts (spec §24–25, docs/DATA-MODEL.md).

Every artifact is *cited* (list of transcript-segment references) and
*idempotent* (unique dedupe_key). The prime rule applies: the transcript
determines what happened — the API layer rejects any artifact whose
citations do not resolve to real segments of the same meeting, and any
owner/deadline that is not grounded in the transcript or entered by a human.
"""

from django.db import models

from groups.models import Group, Person
from meetings.models import Meeting
from tenancy.models import WorkspaceScopedModel


class DerivedArtifact(WorkspaceScopedModel):
    """Common shape: meeting + group denormalized, citations, dedupe_key."""

    meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="%(class)ss"
    )
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="%(class)ss")
    # JSON list of {"segment_id": uuid str, "quote": str} — validated in the API.
    citations = models.JSONField(default=list)
    dedupe_key = models.CharField(max_length=128, unique=True)

    class Meta:
        abstract = True
        ordering = ["created_at"]


class SummarySection(DerivedArtifact):
    class Kind(models.TextChoices):
        OVERVIEW = "overview"
        EXECUTIVE = "executive"
        OBJECTIVES = "objectives"
        FOLLOW_UP = "follow_up"
        CONTEXT_CONNECTIONS = "context_connections"

    kind = models.CharField(max_length=32, choices=Kind.choices)
    order = models.PositiveIntegerField(default=0)
    body = models.TextField()

    class Meta(DerivedArtifact.Meta):
        abstract = False
        ordering = ["order"]


class DiscussionTopic(DerivedArtifact):
    title = models.CharField(max_length=300)
    body = models.TextField(blank=True)


class Decision(DerivedArtifact):
    class Status(models.TextChoices):
        PROPOSED = "proposed"
        DISCUSSED = "discussed"
        TENTATIVE = "tentative"
        APPROVED = "approved"
        REJECTED = "rejected"
        DEFERRED = "deferred"
        REVERSED = "reversed"

    statement = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DISCUSSED)
    reason = models.TextField(blank=True)
    impact = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)


class ActionItem(DerivedArtifact):
    """Context-aware task (spec §25). `owner` is nullable and NEVER invented:
    it is set only when the transcript states it (owner_source="stated", with
    citation) or a human assigns it (owner_source="manual"). Same contract for
    due_date/due_source."""

    class Status(models.TextChoices):
        OPEN = "open"
        IN_PROGRESS = "in_progress"
        DONE = "done"
        CANCELLED = "cancelled"

    class Source(models.TextChoices):
        STATED = "stated"  # grounded in the transcript, citation required
        MANUAL = "manual"  # a human set it in the UI

    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        Person, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
    )
    owner_source = models.CharField(max_length=16, choices=Source.choices, blank=True)
    owner_suggested = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)
    due_source = models.CharField(max_length=16, choices=Source.choices, blank=True)
    priority = models.CharField(max_length=16, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    definition_of_done = models.TextField(blank=True)
    why = models.TextField(blank=True)
    risk_if_delayed = models.TextField(blank=True)


class Commitment(DerivedArtifact):
    class Status(models.TextChoices):
        OPEN = "open"
        KEPT = "kept"
        MISSED = "missed"
        CANCELLED = "cancelled"

    text = models.TextField()
    person = models.ForeignKey(
        Person, on_delete=models.SET_NULL, null=True, blank=True, related_name="commitments"
    )
    due_date = models.DateField(null=True, blank=True)
    due_source = models.CharField(max_length=16, choices=ActionItem.Source.choices, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)


class Question(DerivedArtifact):
    class Status(models.TextChoices):
        ANSWERED = "answered"
        UNANSWERED = "unanswered"
        DEFERRED = "deferred"
        NEEDS_EXTERNAL = "needs_external"
        NEEDS_CLIENT = "needs_client"

    text = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UNANSWERED)
    answer = models.TextField(blank=True)


class Risk(DerivedArtifact):
    risk = models.TextField()
    impact = models.TextField(blank=True)
    mitigation = models.TextField(blank=True)
    owner = models.ForeignKey(
        Person, on_delete=models.SET_NULL, null=True, blank=True, related_name="risks"
    )

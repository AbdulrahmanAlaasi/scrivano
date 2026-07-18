from django.conf import settings
from django.db import models

from tenancy.models import TimeStampedModel, WorkspaceScopedModel


class Group(WorkspaceScopedModel):
    """The central context container (spec §4). Every meeting belongs to a
    Group; each workspace has one undeletable `is_inbox` Group ("Meeting
    Inbox") for meetings the system cannot confidently classify."""

    class GroupType(models.TextChoices):
        COMPANY = "company"
        DEPARTMENT = "department"
        CLIENT = "client"
        PRODUCT = "product"
        PROJECT = "project"
        CAMPAIGN = "campaign"
        HIRING = "hiring"
        RECURRING_MEETING = "recurring_meeting"
        EVENT = "event"
        PERSONAL = "personal"
        OTHER = "other"

    name = models.CharField(max_length=200)
    group_type = models.CharField(
        max_length=32, choices=GroupType.choices, default=GroupType.PROJECT
    )
    description = models.TextField(blank=True)
    purpose = models.TextField(blank=True)
    status = models.CharField(max_length=64, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_groups"
    )
    start_date = models.DateField(null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)
    default_language = models.CharField(max_length=10, default="en")
    is_inbox = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace"],
                condition=models.Q(is_inbox=True),
                name="uniq_inbox_group_per_workspace",
            )
        ]

    def __str__(self) -> str:
        return self.name


class GroupMember(TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "owner"
        MEMBER = "member"
        VIEWER = "viewer"

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_memberships"
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "user"], name="uniq_group_member")
        ]


class GroupContextValue(WorkspaceScopedModel):
    """Versioned structured Group context (spec §5 steps 1–6). `field` is a
    stable key like 'business_description', 'scope', 'glossary',
    'task_standards'; values are versioned, latest = highest version."""

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="context_values")
    field = models.CharField(max_length=100)
    value = models.JSONField()
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["group", "field", "version"], name="uniq_context_field_version"
            )
        ]


class Person(WorkspaceScopedModel):
    """People directory (spec §5 step 3) — participants who may not be users."""

    name = models.CharField(max_length=200)
    preferred_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    organization = models.CharField(max_length=200, blank=True)
    job_title = models.CharField(max_length=200, blank=True)
    timezone = models.CharField(max_length=64, blank=True)
    is_external = models.BooleanField(default=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self) -> str:
        return self.name


class GroupDocument(WorkspaceScopedModel):
    """Uploaded knowledge (spec §5 step 7). Files live in private storage;
    chunks are indexed for Group Intelligence retrieval only — never for
    Meeting Chat (spec §26)."""

    class Status(models.TextChoices):
        UPLOADED = "uploaded"
        INDEXING = "indexing"
        INDEXED = "indexed"
        FAILED = "failed"

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="documents")
    filename = models.CharField(max_length=300)
    mime_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField(default=0)
    storage_path = models.CharField(max_length=500)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPLOADED)
    error = models.TextField(blank=True)
    embedding_provider = models.CharField(max_length=32, blank=True)
    is_superseded = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.filename


class DocumentChunk(WorkspaceScopedModel):
    document = models.ForeignKey(
        GroupDocument, on_delete=models.CASCADE, related_name="chunks"
    )
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="chunks")
    sequence = models.PositiveIntegerField()
    text = models.TextField()
    heading = models.CharField(max_length=300, blank=True)
    # JSON list of floats; mirrored into a pgvector column on Postgres for ANN
    # search. Keeping the JSON copy means SQLite dev keeps working.
    embedding = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "sequence"], name="uniq_document_chunk_sequence"
            )
        ]


class GroupPerson(TimeStampedModel):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="people")
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="groups")
    role_in_group = models.CharField(max_length=200, blank=True)
    responsibilities = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "person"], name="uniq_group_person")
        ]

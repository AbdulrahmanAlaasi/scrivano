"""Group document upload + indexing (spec §5 step 7).

Upload validation follows the ECC django-security skill: magic-byte type
check cross-referenced with the extension, plus a hard size limit. Text is
extracted, chunked, embedded through the provider registry, and indexed
synchronously (uploads are small; the meeting pipeline gets the async
state machine).
"""

from __future__ import annotations

import os
import uuid

from django.conf import settings
from django.db import transaction
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from scrivano_server.providers import get_embedder
from .models import DocumentChunk, Group, GroupDocument

ALLOWED_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Magic-byte signatures for the binary formats we accept.
MAGIC = {
    ".pdf": b"%PDF",
    ".docx": b"PK\x03\x04",
}

CHUNK_CHARS = 1500
CHUNK_OVERLAP = 200


def validate_upload(name: str, head: bytes, size: int) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_TYPES:
        raise serializers.ValidationError(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_TYPES))}"
        )
    if size > settings.MAX_DOCUMENT_BYTES:
        raise serializers.ValidationError("File too large (max 25 MB).")
    signature = MAGIC.get(ext)
    if signature and not head.startswith(signature):
        raise serializers.ValidationError("File content does not match its extension.")
    if signature is None and b"\x00" in head:
        raise serializers.ValidationError("File content does not match its extension.")
    return ALLOWED_TYPES[ext]


def extract_text(ext: str, data: bytes) -> str:
    if ext in (".txt", ".md", ".csv", ".json"):
        return data.decode("utf-8", errors="replace")
    if ext == ".docx":
        import io
        import re
        import zipfile

        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml)
    if ext == ".pdf":
        # Minimal text-layer extraction; scanned PDFs report as unindexable
        # rather than silently indexing nothing (spec §49: no hidden failures).
        import re

        chunks = re.findall(rb"\(((?:[^()\\]|\\.)*)\)\s*Tj", data)
        text = b"\n".join(chunks).decode("latin-1", errors="replace")
        if len(text.strip()) < 40:
            raise serializers.ValidationError(
                "Could not extract text from this PDF (it may be scanned). "
                "Upload a text-based export instead."
            )
        return text
    raise serializers.ValidationError("Unsupported file type.")


def chunk_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        if end < len(text):
            breakpoint_ = text.rfind("\n", start + CHUNK_CHARS // 2, end)
            if breakpoint_ > start:
                end = breakpoint_
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return [c for c in chunks if c]


class GroupDocumentSerializer(serializers.ModelSerializer):
    chunk_count = serializers.IntegerField(source="chunks.count", read_only=True)

    class Meta:
        model = GroupDocument
        fields = [
            "id",
            "group",
            "filename",
            "mime_type",
            "size_bytes",
            "status",
            "error",
            "embedding_provider",
            "chunk_count",
            "created_at",
        ]
        read_only_fields = fields


class GroupDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = GroupDocumentSerializer
    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "upload"
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        qs = GroupDocument.objects.visible_to(self.request.user).filter(
            deleted_at__isnull=True
        )
        group_id = self.request.query_params.get("group")
        if group_id:
            qs = qs.filter(group_id=group_id)
        return qs.distinct()

    def create(self, request, *args, **kwargs):
        group_id = request.data.get("group")
        upload = request.FILES.get("file")
        if not group_id or not upload:
            return Response(
                {"detail": "Provide 'group' and 'file'."}, status=status.HTTP_400_BAD_REQUEST
            )
        group = (
            Group.objects.visible_to(request.user)
            .filter(pk=group_id, deleted_at__isnull=True)
            .first()
        )
        if group is None:
            raise PermissionDenied("Group not found or not accessible.")
        member = group.members.filter(user=request.user).first()
        if not member or member.role == "viewer":
            raise PermissionDenied("Viewers cannot upload documents.")

        data = upload.read()
        ext = os.path.splitext(upload.name)[1].lower()
        mime = validate_upload(upload.name, data[:2048], len(data))

        storage_dir = settings.MEDIA_ROOT / "documents" / str(group.workspace_id)
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage_path = storage_dir / f"{uuid.uuid4()}{ext}"
        storage_path.write_bytes(data)

        doc = GroupDocument.objects.create(
            workspace=group.workspace,
            group=group,
            created_by=request.user,
            filename=upload.name,
            mime_type=mime,
            size_bytes=len(data),
            storage_path=str(storage_path),
            status=GroupDocument.Status.INDEXING,
        )
        try:
            self._index(doc, ext, data)
        except serializers.ValidationError as err:
            doc.status = GroupDocument.Status.FAILED
            doc.error = "; ".join(str(d) for d in err.detail)
            doc.save(update_fields=["status", "error"])
        return Response(
            GroupDocumentSerializer(doc).data,
            status=status.HTTP_201_CREATED
            if doc.status != GroupDocument.Status.FAILED
            else status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    @transaction.atomic
    def _index(self, doc: GroupDocument, ext: str, data: bytes) -> None:
        text = extract_text(ext, data)
        chunks = chunk_text(text)
        embedder = get_embedder()
        vectors = embedder.embed(chunks) if chunks else []
        DocumentChunk.objects.bulk_create(
            DocumentChunk(
                workspace=doc.workspace,
                group=doc.group,
                document=doc,
                created_by=doc.created_by,
                sequence=i,
                text=chunk,
                embedding=vector,
            )
            for i, (chunk, vector) in enumerate(zip(chunks, vectors))
        )
        doc.status = GroupDocument.Status.INDEXED
        doc.embedding_provider = embedder.name
        doc.save(update_fields=["status", "embedding_provider"])

    def perform_destroy(self, instance):
        from django.utils import timezone

        member = instance.group.members.filter(user=self.request.user).first()
        if not member or member.role == "viewer":
            raise PermissionDenied("Viewers cannot delete documents.")
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["deleted_at"])
        # Deleted documents leave the retrieval index immediately (spec §47).
        instance.chunks.all().delete()

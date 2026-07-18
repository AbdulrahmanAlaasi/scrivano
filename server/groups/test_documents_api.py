import uuid

import jwt
import pytest
from django.conf import settings as dj_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from groups.models import DocumentChunk


@pytest.fixture(autouse=True)
def test_env(settings, tmp_path):
    settings.SUPABASE_JWT_SECRET = "test-secret-0123456789abcdef0123456789abcdef"
    settings.MEDIA_ROOT = tmp_path
    settings.EMBEDDINGS_PROVIDER = "mock"


def bearer():
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "aud": "authenticated"},
        dj_settings.SUPABASE_JWT_SECRET,
        algorithm="HS256",
    )
    return f"Bearer {token}"


@pytest.fixture
def ctx(db):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=bearer())
    ws = c.post("/api/workspaces/", {"name": "W"}, format="json").data
    g = c.post(
        "/api/groups/", {"workspace": ws["id"], "name": "Docs Group"}, format="json"
    ).data
    return {"client": c, "group": g}


def upload(client, group_id, name="notes.md", content=b"# Scope\nBuild the pricing page.\n"):
    return client.post(
        "/api/documents/",
        {"group": group_id, "file": SimpleUploadedFile(name, content)},
        format="multipart",
    )


def test_upload_indexes_and_labels_provider(ctx):
    r = upload(ctx["client"], ctx["group"]["id"])
    assert r.status_code == 201, r.content
    assert r.data["status"] == "indexed"
    assert r.data["embedding_provider"] == "mock"
    assert r.data["chunk_count"] == 1
    chunk = DocumentChunk.objects.get()
    assert chunk.embedding and len(chunk.embedding) == 768


def test_long_documents_are_chunked_with_overlap(ctx):
    body = ("Paragraph about the client.\n" * 300).encode()
    r = upload(ctx["client"], ctx["group"]["id"], content=body)
    assert r.data["chunk_count"] > 1


def test_disallowed_extension_rejected(ctx):
    r = upload(ctx["client"], ctx["group"]["id"], name="malware.exe", content=b"MZ\x00\x00")
    assert r.status_code == 400


def test_binary_masquerading_as_text_rejected(ctx):
    r = upload(ctx["client"], ctx["group"]["id"], name="fake.txt", content=b"\x00\x01\x02binary")
    assert r.status_code == 400


def test_pdf_magic_bytes_enforced(ctx):
    r = upload(ctx["client"], ctx["group"]["id"], name="fake.pdf", content=b"not a pdf at all")
    assert r.status_code == 400


def test_outsider_cannot_upload_or_list(ctx):
    outsider = APIClient()
    outsider.credentials(HTTP_AUTHORIZATION=bearer())
    r = upload(outsider, ctx["group"]["id"])
    assert r.status_code == 403
    assert outsider.get(f"/api/documents/?group={ctx['group']['id']}").data == []


def test_delete_removes_chunks_from_index(ctx):
    r = upload(ctx["client"], ctx["group"]["id"])
    doc_id = r.data["id"]
    assert DocumentChunk.objects.count() == 1
    assert ctx["client"].delete(f"/api/documents/{doc_id}/").status_code == 204
    assert DocumentChunk.objects.count() == 0
    assert ctx["client"].get(f"/api/documents/?group={ctx['group']['id']}").data == []

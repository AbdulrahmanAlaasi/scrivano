import uuid

import jwt
import pytest
from django.conf import settings as dj_settings
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def jwt_secret(settings):
    settings.SUPABASE_JWT_SECRET = "test-secret-0123456789abcdef0123456789abcdef"


def bearer():
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "aud": "authenticated"},
        dj_settings.SUPABASE_JWT_SECRET,
        algorithm="HS256",
    )
    return f"Bearer {token}"


SEGMENTS = [
    {"sequence": 0, "start_ms": 0, "end_ms": 4000, "text": "Welcome to the sync.", "speaker_label": "Abdulrahman"},
    {"sequence": 1, "start_ms": 4000, "end_ms": 9000, "text": "Lana will update the website.", "speaker_label": "Ahmad"},
]


@pytest.fixture
def ctx(db):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=bearer())
    ws = c.post("/api/workspaces/", {"name": "W"}, format="json").data
    g = c.post(
        "/api/groups/", {"workspace": ws["id"], "name": "OneShot"}, format="json"
    ).data
    m = c.post(
        "/api/meetings/", {"group": g["id"], "title": "Weekly Sync"}, format="json"
    ).data
    return {"client": c, "group": g, "meeting": m}


def test_create_and_list_meeting(ctx):
    listed = ctx["client"].get(f"/api/meetings/?group={ctx['group']['id']}").data
    assert [m["title"] for m in listed] == ["Weekly Sync"]


def test_segment_ingestion_is_idempotent(ctx):
    c, mid = ctx["client"], ctx["meeting"]["id"]
    r1 = c.post(f"/api/meetings/{mid}/segments/", {"segments": SEGMENTS}, format="json")
    assert r1.status_code == 200 and r1.data == {"created": 2, "total": 2}
    r2 = c.post(f"/api/meetings/{mid}/segments/", {"segments": SEGMENTS}, format="json")
    assert r2.data == {"created": 0, "total": 2}
    jobs = c.get(f"/api/meetings/{mid}/jobs/").data
    assert jobs[0]["stage"] == "transcribed" and jobs[0]["status"] == "complete"


def test_finish_derives_duration(ctx):
    c, mid = ctx["client"], ctx["meeting"]["id"]
    c.post(f"/api/meetings/{mid}/segments/", {"segments": SEGMENTS}, format="json")
    r = c.post(f"/api/meetings/{mid}/finish/")
    assert r.data["status"] == "complete"
    assert r.data["duration_seconds"] == 9


def test_outsider_cannot_touch_meeting(ctx):
    outsider = APIClient()
    outsider.credentials(HTTP_AUTHORIZATION=bearer())
    mid = ctx["meeting"]["id"]
    assert outsider.get(f"/api/meetings/{mid}/").status_code == 404
    assert (
        outsider.post(
            f"/api/meetings/{mid}/segments/", {"segments": SEGMENTS}, format="json"
        ).status_code
        == 404
    )


def test_delete_meeting_removes_segments_from_index(ctx):
    from meetings.models import TranscriptSegment

    c, mid = ctx["client"], ctx["meeting"]["id"]
    c.post(f"/api/meetings/{mid}/segments/", {"segments": SEGMENTS}, format="json")
    assert TranscriptSegment.objects.count() == 2
    assert c.delete(f"/api/meetings/{mid}/").status_code == 204
    assert TranscriptSegment.objects.count() == 0

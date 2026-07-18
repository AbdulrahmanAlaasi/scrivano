"""Increment 6 — derived intelligence: citations enforced, dedupe idempotent,
owners/deadlines never invented (spec §24–25, §47)."""

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
    {"sequence": 0, "start_ms": 0, "end_ms": 4000, "text": "We decided to launch on Friday.", "speaker_label": "Abdulrahman"},
    {"sequence": 1, "start_ms": 4000, "end_ms": 9000, "text": "Lana will update the website by Thursday.", "speaker_label": "Ahmad"},
]


@pytest.fixture
def ctx(db):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=bearer())
    ws = c.post("/api/workspaces/", {"name": "W"}, format="json").data
    g = c.post("/api/groups/", {"workspace": ws["id"], "name": "Site"}, format="json").data
    m = c.post("/api/meetings/", {"group": g["id"], "title": "Sync"}, format="json").data
    c.post(f"/api/meetings/{m['id']}/segments/", {"segments": SEGMENTS}, format="json")
    segs = c.get(f"/api/meetings/{m['id']}/segments/").data
    from groups.models import Person
    from tenancy.models import Workspace

    person = Person.objects.create(
        workspace=Workspace.objects.get(pk=ws["id"]), name="Lana"
    )
    return {"client": c, "ws": ws, "group": g, "meeting": m, "segs": segs, "person": person}


def cite(ctx, i=0, quote=""):
    return [{"segment_id": ctx["segs"][i]["id"], "quote": quote}]


def test_ingest_is_idempotent_and_cited(ctx):
    c, mid = ctx["client"], ctx["meeting"]["id"]
    payload = {
        "summary_sections": [{"kind": "overview", "body": "Launch planning.", "citations": cite(ctx)}],
        "decisions": [{"statement": "Launch on Friday.", "status": "approved", "citations": cite(ctx, 0, "We decided to launch on Friday.")}],
        "questions": [{"text": "Is the copy final?", "citations": cite(ctx, 1)}],
        "risks": [{"risk": "Website may slip.", "citations": cite(ctx, 1)}],
    }
    r1 = c.post(f"/api/meetings/{mid}/intelligence/", payload, format="json")
    assert r1.status_code == 200, r1.data
    assert r1.data["created"] == {"summary": 1, "decision": 1, "question": 1, "risk": 1}
    r2 = c.post(f"/api/meetings/{mid}/intelligence/", payload, format="json")
    assert r2.data["created"] == {"summary": 0, "decision": 0, "question": 0, "risk": 0}
    full = c.get(f"/api/meetings/{mid}/intelligence/").data
    assert full["decisions"][0]["statement"] == "Launch on Friday."
    assert full["decisions"][0]["citations"][0]["segment_id"] == ctx["segs"][0]["id"]
    jobs = {j["stage"]: j["status"] for j in c.get(f"/api/meetings/{mid}/jobs/").data}
    assert jobs["summarized"] == "complete" and jobs["entities_extracted"] == "complete"


def test_citation_must_belong_to_same_meeting(ctx):
    c = ctx["client"]
    m2 = c.post(
        "/api/meetings/", {"group": ctx["group"]["id"], "title": "Other"}, format="json"
    ).data
    r = c.post(
        f"/api/meetings/{m2['id']}/intelligence/",
        {"decisions": [{"statement": "X", "citations": cite(ctx)}]},
        format="json",
    )
    assert r.status_code == 400
    assert "not a segment of this meeting" in str(r.data)


def test_uncited_artifacts_are_rejected(ctx):
    r = ctx["client"].post(
        f"/api/meetings/{ctx['meeting']['id']}/intelligence/",
        {"decisions": [{"statement": "Uncited claim.", "citations": []}]},
        format="json",
    )
    assert r.status_code == 400


def test_owner_and_deadline_are_never_invented(ctx):
    c, mid = ctx["client"], ctx["meeting"]["id"]
    # owner without stated source → rejected
    r = c.post(
        f"/api/meetings/{mid}/intelligence/",
        {"tasks": [{"title": "Update website", "owner": str(ctx["person"].pk), "citations": cite(ctx, 1)}]},
        format="json",
    )
    assert r.status_code == 400 and "owner" in str(r.data)
    # due_date without stated source → rejected
    r = c.post(
        f"/api/meetings/{mid}/intelligence/",
        {"tasks": [{"title": "Update website", "due_date": "2026-07-24", "citations": cite(ctx, 1)}]},
        format="json",
    )
    assert r.status_code == 400 and "due_date" in str(r.data)
    # stated owner + deadline with citation → accepted
    r = c.post(
        f"/api/meetings/{mid}/intelligence/",
        {"tasks": [{
            "title": "Update website", "owner": str(ctx["person"].pk),
            "owner_source": "stated", "due_date": "2026-07-23", "due_source": "stated",
            "citations": cite(ctx, 1, "Lana will update the website by Thursday."),
        }]},
        format="json",
    )
    assert r.status_code == 200, r.data
    tasks = c.get("/api/tasks/").data
    assert tasks[0]["owner_name"] == "Lana" and tasks[0]["due_source"] == "stated"


def test_manual_owner_assignment_via_tasks_api(ctx):
    c, mid = ctx["client"], ctx["meeting"]["id"]
    c.post(
        f"/api/meetings/{mid}/intelligence/",
        {"tasks": [{"title": "Write launch email", "citations": cite(ctx, 0)}]},
        format="json",
    )
    task = c.get("/api/tasks/?unassigned=1").data[0]
    r = c.patch(
        f"/api/tasks/{task['id']}/",
        {"owner": str(ctx["person"].pk), "status": "in_progress"},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["owner_source"] == "manual" and r.data["status"] == "in_progress"


def test_intelligence_is_workspace_isolated(ctx):
    outsider = APIClient()
    outsider.credentials(HTTP_AUTHORIZATION=bearer())
    mid = ctx["meeting"]["id"]
    assert outsider.get(f"/api/meetings/{mid}/intelligence/").status_code == 404
    assert (
        outsider.post(
            f"/api/meetings/{mid}/intelligence/",
            {"decisions": [{"statement": "X", "citations": cite(ctx)}]},
            format="json",
        ).status_code
        == 404
    )
    assert outsider.get("/api/tasks/").data == []

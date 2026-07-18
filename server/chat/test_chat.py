"""Increment 7 — Meeting Chat: strict meeting isolation, citation validation,
honest not-found (spec §26–27, §47)."""

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


def seg(i, text):
    return {"sequence": i, "start_ms": i * 5000, "end_ms": (i + 1) * 5000, "text": text}


@pytest.fixture
def ctx(db):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=bearer())
    ws = c.post("/api/workspaces/", {"name": "W"}, format="json").data
    g = c.post("/api/groups/", {"workspace": ws["id"], "name": "Site"}, format="json").data
    m1 = c.post("/api/meetings/", {"group": g["id"], "title": "Budget"}, format="json").data
    m2 = c.post("/api/meetings/", {"group": g["id"], "title": "Hiring"}, format="json").data
    c.post(
        f"/api/meetings/{m1['id']}/segments/",
        {"segments": [
            seg(0, "Our marketing budget for the launch is twenty thousand."),
            seg(1, "We can extend the budget if conversion is strong."),
        ]},
        format="json",
    )
    c.post(
        f"/api/meetings/{m2['id']}/segments/",
        {"segments": [
            seg(0, "The hiring budget covers two senior engineers."),
        ]},
        format="json",
    )
    return {"client": c, "m1": m1, "m2": m2}


def test_retrieval_is_hard_scoped_to_the_meeting(ctx):
    c = ctx["client"]
    r = c.post(
        f"/api/meetings/{ctx['m1']['id']}/chat/ask/",
        {"question": "What is the budget?"},
        format="json",
    )
    assert r.status_code == 200
    texts = [e["text"] for e in r.data["excerpts"]]
    assert any("marketing budget" in t for t in texts)
    # "budget" also appears in meeting 2 — it must never leak into meeting 1.
    assert not any("hiring budget" in t for t in texts)


def test_retrieval_layer_cannot_return_foreign_rows(ctx):
    """§47: assert at the retrieval layer itself, below the API."""
    from chat.retrieval import retrieve_meeting_segments
    from meetings.models import Meeting

    m1 = Meeting.objects.get(pk=ctx["m1"]["id"])
    hits = retrieve_meeting_segments(m1, "budget engineers hiring senior")
    assert all(str(s.meeting_id) == ctx["m1"]["id"] for s in hits)


def test_answer_requires_valid_same_meeting_citations(ctx):
    c = ctx["client"]
    ask = c.post(
        f"/api/meetings/{ctx['m1']['id']}/chat/ask/",
        {"question": "What is the budget?"},
        format="json",
    ).data
    foreign = c.get(f"/api/meetings/{ctx['m2']['id']}/segments/").data[0]["id"]
    r = c.post(
        f"/api/meetings/{ctx['m1']['id']}/chat/answer/",
        {"thread": ask["thread"], "text": "It is twenty thousand.",
         "citations": [{"segment_id": foreign}]},
        format="json",
    )
    assert r.status_code == 400 and "not part of this meeting" in str(r.data)
    # uncited non-not_found answer rejected
    r = c.post(
        f"/api/meetings/{ctx['m1']['id']}/chat/answer/",
        {"thread": ask["thread"], "text": "It is twenty thousand.", "citations": []},
        format="json",
    )
    assert r.status_code == 400
    # properly cited answer stored
    good = ask["excerpts"][0]["segment_id"]
    r = c.post(
        f"/api/meetings/{ctx['m1']['id']}/chat/answer/",
        {"thread": ask["thread"], "text": "The marketing budget is twenty thousand.",
         "citations": [{"segment_id": good, "quote": "twenty thousand"}]},
        format="json",
    )
    assert r.status_code == 200 and r.data["citations"][0]["segment_id"] == good


def test_honest_not_found_flow(ctx):
    c = ctx["client"]
    ask = c.post(
        f"/api/meetings/{ctx['m1']['id']}/chat/ask/",
        {"question": "Did anyone mention the office relocation?"},
        format="json",
    ).data
    r = c.post(
        f"/api/meetings/{ctx['m1']['id']}/chat/answer/",
        {"thread": ask["thread"],
         "text": "This meeting's transcript does not contain that information.",
         "not_found": True, "citations": []},
        format="json",
    )
    assert r.status_code == 200 and r.data["not_found"] is True
    history = c.get(f"/api/meetings/{ctx['m1']['id']}/chat/?thread={ask['thread']}").data
    assert [m["role"] for m in history] == ["user", "assistant"]


def test_chat_is_workspace_isolated(ctx):
    outsider = APIClient()
    outsider.credentials(HTTP_AUTHORIZATION=bearer())
    r = outsider.post(
        f"/api/meetings/{ctx['m1']['id']}/chat/ask/",
        {"question": "What is the budget?"},
        format="json",
    )
    assert r.status_code == 404
    assert outsider.get(f"/api/meetings/{ctx['m1']['id']}/chat/").status_code == 404

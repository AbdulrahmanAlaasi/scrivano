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


@pytest.fixture
def group(db):
    c = APIClient()
    auth = bearer()
    c.credentials(HTTP_AUTHORIZATION=auth)
    ws = c.post("/api/workspaces/", {"name": "W"}, format="json").data
    g = c.post(
        "/api/groups/",
        {"workspace": ws["id"], "name": "OneShot Website", "group_type": "client"},
        format="json",
    ).data
    return {"client": c, "auth": auth, "group": g}


def test_set_and_read_context(group):
    c = group["client"]
    gid = group["group"]["id"]
    r = c.put(
        f"/api/groups/{gid}/context/set/",
        {"values": {"scope": "Rebuild pricing page", "glossary": {"OneShot": "KSA client"}}},
        format="json",
    )
    assert r.status_code == 200, r.content
    snapshot = c.get(f"/api/groups/{gid}/context/").data
    assert snapshot["scope"]["value"] == "Rebuild pricing page"
    assert snapshot["scope"]["version"] == 1


def test_updates_create_new_versions_and_keep_history(group):
    c = group["client"]
    gid = group["group"]["id"]
    c.put(f"/api/groups/{gid}/context/set/", {"values": {"scope": "v1"}}, format="json")
    c.put(f"/api/groups/{gid}/context/set/", {"values": {"scope": "v2"}}, format="json")
    snapshot = c.get(f"/api/groups/{gid}/context/").data
    assert snapshot["scope"]["value"] == "v2"
    assert snapshot["scope"]["version"] == 2
    history = c.get(f"/api/groups/{gid}/context/history/?field=scope").data
    assert [h["value"] for h in history] == ["v2", "v1"]


def test_unknown_field_is_rejected(group):
    c = group["client"]
    gid = group["group"]["id"]
    r = c.put(
        f"/api/groups/{gid}/context/set/", {"values": {"nonsense": 1}}, format="json"
    )
    assert r.status_code == 400
    r = c.put(
        f"/api/groups/{gid}/context/set/", {"values": {"custom_thing": 1}}, format="json"
    )
    assert r.status_code == 200


def test_outsider_cannot_read_or_write_context(group):
    gid = group["group"]["id"]
    outsider = APIClient()
    outsider.credentials(HTTP_AUTHORIZATION=bearer())
    assert outsider.get(f"/api/groups/{gid}/context/").status_code == 403
    assert (
        outsider.put(
            f"/api/groups/{gid}/context/set/", {"values": {"scope": "x"}}, format="json"
        ).status_code
        == 403
    )

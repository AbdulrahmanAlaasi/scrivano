import uuid

import jwt
import pytest
from django.conf import settings
from rest_framework.test import APIClient

from groups.models import Group
from tenancy.models import User, Workspace


def bearer_for(supabase_id: str, email: str = "u@example.com") -> str:
    token = jwt.encode(
        {"sub": supabase_id, "aud": "authenticated", "email": email},
        settings.SUPABASE_JWT_SECRET,
        algorithm="HS256",
    )
    return f"Bearer {token}"


@pytest.fixture(autouse=True)
def jwt_secret(settings):
    settings.SUPABASE_JWT_SECRET = "test-secret-0123456789abcdef0123456789abcdef"


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
def test_supabase_jwt_creates_mirrored_user(client):
    sid = str(uuid.uuid4())
    client.credentials(HTTP_AUTHORIZATION=bearer_for(sid, "lana@example.com"))
    resp = client.get("/api/workspaces/")
    assert resp.status_code == 200
    user = User.objects.get(supabase_id=sid)
    assert user.email == "lana@example.com"


@pytest.mark.django_db
def test_invalid_jwt_is_rejected(client):
    client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")
    assert client.get("/api/workspaces/").status_code == 401


@pytest.mark.django_db
def test_unauthenticated_request_is_rejected(client):
    assert client.get("/api/workspaces/").status_code in (401, 403)


@pytest.mark.django_db
def test_workspace_create_bootstraps_owner_and_inbox(client):
    client.credentials(HTTP_AUTHORIZATION=bearer_for(str(uuid.uuid4())))
    resp = client.post("/api/workspaces/", {"name": "Alaasi Dev"}, format="json")
    assert resp.status_code == 201, resp.content
    assert resp.data["role"] == "owner"
    ws = Workspace.objects.get(id=resp.data["id"])
    inbox = Group.objects.get(workspace=ws, is_inbox=True)
    assert inbox.name == "Meeting Inbox"


@pytest.mark.django_db
def test_workspaces_are_tenant_isolated(client):
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    client.credentials(HTTP_AUTHORIZATION=bearer_for(a))
    created = client.post("/api/workspaces/", {"name": "A space"}, format="json")
    ws_id = created.data["id"]

    client.credentials(HTTP_AUTHORIZATION=bearer_for(b))
    assert client.get("/api/workspaces/").data == []
    assert client.get(f"/api/workspaces/{ws_id}/").status_code == 404
    # B cannot create a group inside A's workspace either.
    resp = client.post(
        "/api/groups/", {"workspace": ws_id, "name": "Intrusion"}, format="json"
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_inbox_group_cannot_be_deleted(client):
    client.credentials(HTTP_AUTHORIZATION=bearer_for(str(uuid.uuid4())))
    ws = client.post("/api/workspaces/", {"name": "W"}, format="json").data
    inbox_id = client.get(f"/api/groups/?workspace={ws['id']}").data[0]["id"]
    assert client.delete(f"/api/groups/{inbox_id}/").status_code == 400


@pytest.mark.django_db
def test_group_crud_within_workspace(client):
    client.credentials(HTTP_AUTHORIZATION=bearer_for(str(uuid.uuid4())))
    ws = client.post("/api/workspaces/", {"name": "W"}, format="json").data
    resp = client.post(
        "/api/groups/",
        {"workspace": ws["id"], "name": "OneShot Website", "group_type": "client"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    names = {g["name"] for g in client.get(f"/api/groups/?workspace={ws['id']}").data}
    assert names == {"Meeting Inbox", "OneShot Website"}

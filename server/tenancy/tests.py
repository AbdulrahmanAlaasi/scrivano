from django.db import IntegrityError

import pytest

from groups.models import Group, GroupMember
from meetings.models import Meeting, TranscriptSegment
from tenancy.models import User, Workspace, WorkspaceMember


@pytest.fixture
def tenants(db):
    """Two isolated workspaces, one user in each (spec §47 'Permissions')."""
    alice = User.objects.create_user("alice")
    bob = User.objects.create_user("bob")
    out = {}
    for name, user in (("A", alice), ("B", bob)):
        ws = Workspace.objects.create(name=f"WS {name}", owner=user)
        WorkspaceMember.objects.create(workspace=ws, user=user, role="owner")
        group = Group.objects.create(
            workspace=ws, name="Meeting Inbox", owner=user, is_inbox=True
        )
        GroupMember.objects.create(group=group, user=user, role="owner")
        meeting = Meeting.objects.create(workspace=ws, group=group, title=f"Kickoff {name}")
        TranscriptSegment.objects.create(
            workspace=ws,
            meeting=meeting,
            sequence=1,
            start_ms=0,
            end_ms=1000,
            original_text=f"secret {name}",
            dedupe_key=f"{meeting.id}-1",
        )
        out[name] = {"user": user, "ws": ws, "group": group, "meeting": meeting}
    return out


def test_user_cannot_see_other_workspace_meetings(tenants):
    visible = Meeting.objects.visible_to(tenants["A"]["user"])
    assert list(visible) == [tenants["A"]["meeting"]]


def test_user_cannot_see_other_workspace_groups(tenants):
    visible = Group.objects.visible_to(tenants["B"]["user"])
    assert list(visible) == [tenants["B"]["group"]]


def test_transcript_segments_are_workspace_scoped(tenants):
    texts = {s.original_text for s in TranscriptSegment.objects.visible_to(tenants["A"]["user"])}
    assert texts == {"secret A"}


def test_meeting_chat_retrieval_is_meeting_isolated(tenants):
    """Meeting Chat's hard filter: even inside the same workspace, retrieval
    scoped to one meeting must never return another meeting's segments."""
    ws = tenants["A"]["ws"]
    other = Meeting.objects.create(
        workspace=ws, group=tenants["A"]["group"], title="Second meeting"
    )
    TranscriptSegment.objects.create(
        workspace=ws,
        meeting=other,
        sequence=1,
        start_ms=0,
        end_ms=500,
        original_text="other meeting secret",
        dedupe_key=f"{other.id}-1",
    )
    scoped = TranscriptSegment.objects.visible_to(tenants["A"]["user"]).filter(
        meeting=tenants["A"]["meeting"]
    )
    assert all(s.meeting_id == tenants["A"]["meeting"].id for s in scoped)
    assert "other meeting secret" not in {s.original_text for s in scoped}


def test_inbox_group_is_unique_per_workspace(tenants):
    with pytest.raises(IntegrityError):
        Group.objects.create(
            workspace=tenants["A"]["ws"],
            name="Another inbox",
            owner=tenants["A"]["user"],
            is_inbox=True,
        )


def test_reprocessing_segments_is_idempotent(tenants):
    m = tenants["A"]["meeting"]
    with pytest.raises(IntegrityError):
        TranscriptSegment.objects.create(
            workspace=m.workspace,
            meeting=m,
            sequence=1,
            start_ms=0,
            end_ms=1000,
            original_text="duplicate",
            dedupe_key=f"{m.id}-1",
        )

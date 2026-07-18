"""Meeting Chat API (spec §26–27).

Flow (generation is client-side, on the user's local LLM):
1. POST  /api/meetings/{id}/chat/ask/     {question, thread?}
     → stores the user turn, runs meeting-isolated retrieval, returns the
       excerpts the client may use — transcript of THIS meeting only.
2. POST  /api/meetings/{id}/chat/answer/  {thread, text, citations, not_found}
     → validates every citation resolves to a segment of THIS meeting;
       a non-not_found answer with zero valid citations is rejected —
       the honest fallback is not_found=true (spec §27).
3. GET   /api/meetings/{id}/chat/?thread= → history.
"""

from django.http import Http404
from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from meetings.models import Meeting
from .models import MeetingChatMessage, MeetingChatThread
from .retrieval import retrieve_meeting_segments


class ChatCitationSerializer(serializers.Serializer):
    segment_id = serializers.UUIDField()
    quote = serializers.CharField(required=False, allow_blank=True, default="")


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingChatMessage
        fields = ["id", "thread", "role", "text", "citations", "not_found", "created_at"]


class MeetingChatViewSet(viewsets.ViewSet):
    def _meeting(self, request, meeting_pk):
        meeting = (
            Meeting.objects.visible_to(request.user)
            .filter(deleted_at__isnull=True, pk=meeting_pk)
            .select_related("group", "workspace")
            .first()
        )
        if meeting is None:
            raise Http404
        return meeting

    def _thread(self, request, meeting, thread_id, create_title=""):
        if thread_id:
            thread = meeting.chat_threads.filter(pk=thread_id).first()
            if thread is None:
                raise ValidationError({"thread": "unknown thread for this meeting"})
            return thread
        return MeetingChatThread.objects.create(
            workspace=meeting.workspace,
            meeting=meeting,
            created_by=request.user,
            title=create_title[:300],
        )

    def list(self, request, meeting_pk=None):
        meeting = self._meeting(request, meeting_pk)
        qs = MeetingChatMessage.objects.filter(meeting=meeting)
        if request.query_params.get("thread"):
            qs = qs.filter(thread_id=request.query_params["thread"])
        return Response(MessageSerializer(qs, many=True).data)

    def ask(self, request, meeting_pk=None):
        meeting = self._meeting(request, meeting_pk)
        member = meeting.group.members.filter(user=request.user).first()
        if not member:
            raise PermissionDenied("Not a member of this meeting's group.")
        question = str(request.data.get("question", "")).strip()
        if not question:
            raise ValidationError({"question": "required"})
        thread = self._thread(request, meeting, request.data.get("thread"), question)
        segments = retrieve_meeting_segments(meeting, question)
        msg = MeetingChatMessage.objects.create(
            workspace=meeting.workspace,
            meeting=meeting,
            thread=thread,
            created_by=request.user,
            role=MeetingChatMessage.Role.USER,
            text=question,
            retrieved_segment_ids=[str(s.pk) for s in segments],
        )
        return Response(
            {
                "thread": str(thread.pk),
                "message": str(msg.pk),
                # Meeting Chat context = this meeting's transcript, nothing else
                # (no documents, no Group Memory, no other meetings — spec §26).
                "excerpts": [
                    {
                        "segment_id": str(s.pk),
                        "sequence": s.sequence,
                        "speaker_label": s.speaker_label,
                        "start_ms": s.start_ms,
                        "end_ms": s.end_ms,
                        "text": s.text,
                    }
                    for s in segments
                ],
            }
        )

    def answer(self, request, meeting_pk=None):
        meeting = self._meeting(request, meeting_pk)
        thread = self._thread(request, meeting, request.data.get("thread"))
        text = str(request.data.get("text", "")).strip()
        not_found = bool(request.data.get("not_found", False))
        if not text:
            raise ValidationError({"text": "required"})
        ser = ChatCitationSerializer(data=request.data.get("citations", []), many=True)
        ser.is_valid(raise_exception=True)
        valid_ids = set(
            str(pk) for pk in meeting.segments.values_list("pk", flat=True)
        )
        citations = []
        for c in ser.validated_data:
            if str(c["segment_id"]) not in valid_ids:
                raise ValidationError(
                    {"citations": f"segment {c['segment_id']} is not part of this meeting"}
                )
            citations.append({"segment_id": str(c["segment_id"]), "quote": c["quote"]})
        if not not_found and not citations:
            raise ValidationError(
                {"citations": "an answer must cite this meeting's transcript; if the transcript does not contain the answer, set not_found=true"}
            )
        msg = MeetingChatMessage.objects.create(
            workspace=meeting.workspace,
            meeting=meeting,
            thread=thread,
            created_by=request.user,
            role=MeetingChatMessage.Role.ASSISTANT,
            text=text,
            citations=citations,
            not_found=not_found,
        )
        return Response(MessageSerializer(msg).data)

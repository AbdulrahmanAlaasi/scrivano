"""Meeting-isolated retrieval (spec §26, docs/ARCHITECTURE.md §4).

The ONLY query path starts from `meeting.segments` — a relation manager that
cannot produce rows of another meeting. Isolation is structural, not a
filter bolted on afterwards; test_chat.py asserts it.

Scoring is a lexical hybrid that works identically on SQLite and Postgres:
token-overlap (keyword) + phrase bonus, then neighbor expansion (prev/next
sequence) so the client's LLM sees local context around each hit. On
Postgres the same interface can be upgraded to pgvector + FTS fusion
without changing callers.
"""

import re

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "to", "of", "and",
    "or", "in", "on", "at", "for", "we", "i", "you", "it", "this", "that",
    "did", "do", "does", "what", "who", "when", "where", "why", "how", "will",
}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[\w']+", text.lower()) if t not in STOPWORDS]


def retrieve_meeting_segments(meeting, question: str, k: int = 6):
    """Return top-k scored segments of THIS meeting only, with prev/next
    neighbors merged in, ordered by sequence. Empty list = nothing relevant."""

    q_token_list = _tokens(question)
    q_tokens = set(q_token_list)
    if not q_tokens:
        return []
    q_joined = " ".join(q_token_list)

    scored = []
    segments = list(meeting.segments.all())  # structural meeting isolation
    for seg in segments:
        s_token_list = _tokens(seg.text)
        if not s_token_list:
            continue
        overlap = q_tokens & set(s_token_list)
        if not overlap:
            continue
        score = len(overlap) / (len(q_tokens) ** 0.5 * len(set(s_token_list)) ** 0.5)
        # phrase bonus: consecutive query-word pairs appearing in the segment
        s_joined = " ".join(s_token_list)
        for a, b in zip(q_token_list, q_token_list[1:]):
            if f"{a} {b}" in s_joined:
                score += 0.15
        scored.append((score, seg))
    scored.sort(key=lambda t: -t[0])
    hits = [seg for _, seg in scored[:k]]
    if not hits:
        return []

    by_seq = {s.sequence: s for s in segments}
    keep = set()
    for seg in hits:
        keep.update({seg.sequence - 1, seg.sequence, seg.sequence + 1})
    return [by_seq[i] for i in sorted(keep) if i in by_seq]

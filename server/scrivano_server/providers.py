"""AI provider registry (spec §41, docs/ARCHITECTURE.md §2).

Providers are selected by configuration, never imported directly by product
code. The mock embedder exists so development works with zero credentials —
its output is deterministic and every record it produces is labeled
`provider="mock"` so it can never masquerade as a real embedding.
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.request

from django.conf import settings

EMBEDDING_DIM = 768


class MockEmbedder:
    """Deterministic hash-based embeddings. Clearly labeled; dev/test only."""

    name = "mock"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            # Expand the 32-byte digest into a unit vector of EMBEDDING_DIM.
            vals = [
                (digest[(i * 7) % 32] + digest[(i * 13 + 5) % 32] * 0.5) - 190
                for i in range(EMBEDDING_DIM)
            ]
            norm = math.sqrt(sum(v * v for v in vals)) or 1.0
            out.append([v / norm for v in vals])
        return out


class OllamaEmbedder:
    """Local embeddings via any Ollama-compatible /api/embed endpoint."""

    name = "ollama"

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        req = urllib.request.Request(
            f"{self.base_url}/api/embed",
            data=json.dumps({"model": self.model, "input": texts}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read())
        return payload["embeddings"]


def get_embedder():
    provider = settings.EMBEDDINGS_PROVIDER
    if provider == "ollama":
        return OllamaEmbedder(settings.EMBEDDINGS_URL, settings.EMBEDDINGS_MODEL)
    if provider == "mock":
        return MockEmbedder()
    raise ValueError(f"Unknown EMBEDDINGS_PROVIDER '{provider}'")

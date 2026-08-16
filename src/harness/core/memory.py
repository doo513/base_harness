from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .retrieval import (
    LocalLexicalRetrievalGateway,
    RetrievalRequest,
    RetrievalSourceItem,
    normalize_retrieval_query,
)
from .storage import IntegrityError, canonical_hash


@dataclass(frozen=True)
class MemoryItem:
    """Compatibility source-memory record.

    This is untrusted retrieval input only. It intentionally has no mutable
    authority/recall counters and cannot represent verified state.
    """

    id: str
    text: str
    scope: str = "project"
    source: str = "local"
    source_revision: str = "legacy-v1"
    source_locator: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def authority(self) -> str:
        return "untrusted_retrieval"

    @property
    def instruction_authority(self) -> str:
        return "none"

    def as_source_item(self) -> RetrievalSourceItem:
        return RetrievalSourceItem(
            source_id=self.id,
            source_revision=self.source_revision,
            source_locator=self.source_locator or self.id,
            content=self.text,
            scope=self.scope,
            metadata={"source": self.source, **dict(self.metadata)},
        )


class MemoryStore:
    """Read-only-search compatibility facade over deterministic lexical retrieval."""

    def __init__(self):
        self.items: dict[str, MemoryItem] = {}

    def add(self, item: MemoryItem) -> None:
        if not isinstance(item, MemoryItem):
            raise ValueError("MemoryStore accepts MemoryItem objects only")
        existing = self.items.get(item.id)
        if existing is not None and existing != item:
            raise IntegrityError("memory item id collision with different content/provenance")
        self.items[item.id] = item

    def search(self, query: str, limit: int = 5) -> list[MemoryItem]:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise ValueError("memory search limit must be a non-negative integer")
        normalized = normalize_retrieval_query(query)
        if not normalized or limit == 0:
            return []
        gateway = LocalLexicalRetrievalGateway(
            [item.as_source_item() for item in self.items.values()],
            index_revision=f"compat:{canonical_hash(sorted(self.items))[:16]}",
        )
        request = RetrievalRequest(
            request_id=canonical_hash({"query": normalized, "limit": limit}),
            query=normalized,
            normalized_query=normalized,
            scope="project",
            top_k=limit,
            requested_step=0,
            strategy_generation=0,
        )
        candidates = gateway.search(request)
        return [self.items[candidate.source_id] for candidate in candidates]

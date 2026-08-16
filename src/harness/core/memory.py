from dataclasses import dataclass, field
from typing import Any

@dataclass
class MemoryItem:
    id: str
    text: str
    scope: str = "project"
    authority: str = "unknown"
    source: str = "local"
    valid_until: str | None = None
    superseded_by: str | None = None
    ttl_seconds: int | None = None
    criticality: str = "normal"
    pinned: bool = False
    recall_count: int = 0
    metadata: dict[str,Any] = field(default_factory=dict)

class MemoryStore:
    '''Retrieval memory only; never the source of truth for current execution.'''
    def __init__(self):
        self.items = {}

    def add(self, item: MemoryItem):
        self.items[item.id] = item

    def search(self, query: str, limit=5):
        terms = query.lower().split()
        scored = []
        for item in self.items.values():
            s = sum(t in item.text.lower() for t in terms)
            if s: scored.append((s,item))
        scored.sort(key=lambda x:x[0], reverse=True)
        out = [x[1] for x in scored[:limit]]
        for item in out:
            item.recall_count += 1
        return out

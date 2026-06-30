from __future__ import annotations

from typing import Protocol

from harness.core.types import JsonObject


class ProblemAdapter(Protocol):
    name: str

    def can_handle(self, request: str) -> bool: ...

    def build_context(self, request: str) -> JsonObject: ...

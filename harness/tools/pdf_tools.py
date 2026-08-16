from __future__ import annotations

from pathlib import Path
from typing import Sequence

from harness.core.context_budget import BudgetInput, resolve_budget
from harness.core.types import JsonObject


def inspect_pdf(path: str | Path, budget: BudgetInput = None) -> JsonObject:
    pdf_path = Path(path)
    size = pdf_path.stat().st_size if pdf_path.exists() else 0
    return {
        "path": str(pdf_path),
        "supported": False,
        "reason": "PDF text extraction dependency is not configured",
        "size": size,
        "truncated": False,
    }


def search_pdf(path: str | Path, query: str, budget: BudgetInput = None) -> JsonObject:
    return {
        "path": str(path),
        "query": query,
        "supported": False,
        "reason": "PDF text extraction dependency is not configured",
        "matches": [],
        "truncated": False,
    }


def read_pdf_pages(path: str | Path, pages: Sequence[int], budget: BudgetInput = None) -> JsonObject:
    resolved_budget = resolve_budget(budget)
    selected = list(pages[: resolved_budget.max_pdf_pages_per_read])
    return {
        "path": str(path),
        "supported": False,
        "reason": "PDF text extraction dependency is not configured",
        "pages": selected,
        "text": [],
        "truncated": len(pages) > len(selected),
    }

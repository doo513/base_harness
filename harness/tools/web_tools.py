from __future__ import annotations

from harness.core.context_budget import BudgetInput, resolve_budget
from harness.core.types import JsonObject


def search_web(query: str, max_results: int | None = None, budget: BudgetInput = None) -> JsonObject:
    resolved_budget = resolve_budget(budget)
    limit = min(max_results if max_results is not None else resolved_budget.max_web_results, resolved_budget.max_web_results)
    return {
        "query": query,
        "supported": False,
        "reason": "web search provider is not configured",
        "max_results": limit,
        "results": [],
        "truncated": False,
    }


def fetch_relevant_page(url: str, query: str | None = None, budget: BudgetInput = None) -> JsonObject:
    resolved_budget = resolve_budget(budget)
    return {
        "url": url,
        "query": query or "",
        "supported": False,
        "reason": "web fetch provider is not configured",
        "title": "",
        "passages": [],
        "max_passages": resolved_budget.max_passages_per_page,
        "truncated": False,
    }

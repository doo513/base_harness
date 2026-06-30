from __future__ import annotations

from typing import Mapping

from harness.core.intake import TASK_TOOLS
from harness.core.types import JsonObject, JsonValue


def tools_for_tasks(labels: list[str], workspace_path: str | Path | None = None) -> list[str]:
    from harness.core.config import load_config
    task_tools = load_config(workspace_path).task_tools
    tools: list[str] = []
    seen: set[str] = set()
    for label in labels:
        for tool in task_tools.get(label, ()):
            if tool not in seen:
                seen.add(tool)
                tools.append(tool)
    return tools


def normalize_tool_call(tool: str, arguments: Mapping[str, JsonValue] | None = None) -> JsonObject:
    return {
        "tool": tool,
        "arguments": dict(arguments or {}),
    }

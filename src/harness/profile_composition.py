from __future__ import annotations

from typing import Any, Mapping


class ProfileCompositionError(ValueError):
    pass


class ToolAugmentedProfile:
    """Thin profile proxy that adds integration tools without changing domain semantics."""

    def __init__(self, base_profile: Any, extra_tools: Mapping[str, Any]):
        self._base_profile = base_profile
        self._extra_tools = dict(extra_tools)
        base_tools = base_profile.tools()
        collisions = sorted(set(base_tools) & set(self._extra_tools))
        if collisions:
            raise ProfileCompositionError(
                "tool name collision while composing profile: " + ", ".join(collisions)
            )
        self._base_tools = dict(base_tools)

    def __getattr__(self, name: str):
        return getattr(self._base_profile, name)

    @property
    def name(self):
        return self._base_profile.name

    def tools(self):
        return {**self._base_tools, **self._extra_tools}

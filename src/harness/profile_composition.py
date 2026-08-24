from __future__ import annotations

from types import MethodType
from typing import Any, Mapping
import copy

from harness.core.storage import canonical_hash


class ProfileCompositionError(ValueError):
    pass


def _clone_tool_spec(spec: Any) -> Any:
    """Structural copy of mutable ToolSpec metadata without cloning handlers/backends."""
    cloned = copy.copy(spec)
    for field in (
        "input_schema",
        "output_schema",
        "model_input_schema",
        "model_output_schema",
        "provenance",
    ):
        value = getattr(spec, field, None)
        if isinstance(value, dict):
            setattr(cloned, field, copy.deepcopy(value))
    failure_modes = getattr(spec, "failure_modes", None)
    if isinstance(failure_modes, list):
        cloned.failure_modes = list(failure_modes)
    return cloned


def _stamp_tool_contract_provenance(spec: Any) -> None:
    provenance = dict(getattr(spec, "provenance", {}) or {})
    for field in (
        "input_schema",
        "output_schema",
        "model_input_schema",
        "model_output_schema",
    ):
        value = getattr(spec, field, None)
        if isinstance(value, dict):
            provenance[f"{field}_hash"] = canonical_hash(value)
    spec.provenance = provenance


def augment_profile_tools(profile: Any, extra_tools: Mapping[str, Any]) -> Any:
    """Return a structurally isolated profile snapshot with composed tools.

    The concrete profile class is preserved, but the source profile and its
    ToolSpec objects are not mutated. This prevents tool/provenance state from
    leaking between concurrent runs, retries, or later profile reuse.
    """

    extras = {name: _clone_tool_spec(spec) for name, spec in extra_tools.items()}
    base_tools = {name: _clone_tool_spec(spec) for name, spec in profile.tools().items()}
    collisions = sorted(set(base_tools) & set(extras))
    if collisions:
        raise ProfileCompositionError(
            "tool name collision while composing profile: " + ", ".join(collisions)
        )
    composed = {**base_tools, **extras}
    for spec in composed.values():
        _stamp_tool_contract_provenance(spec)

    profile_snapshot = copy.copy(profile)

    def tools(self):
        # Return fresh structural copies so callers cannot mutate the stored
        # composition through a returned ToolSpec reference.
        return {name: _clone_tool_spec(spec) for name, spec in composed.items()}

    profile_snapshot.tools = MethodType(tools, profile_snapshot)
    return profile_snapshot

from __future__ import annotations

from types import MethodType
from typing import Any, Mapping

from harness.core.storage import canonical_hash


class ProfileCompositionError(ValueError):
    pass


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
    """Add integration tools while preserving the original profile type/identity.

    Runtime provenance records the concrete profile class/source plus each
    resulting tool descriptor. Keeping the original instance avoids replacing
    that profile identity with a generic proxy in resume fingerprints.
    """

    extras = dict(extra_tools)
    base_tools = dict(profile.tools())
    collisions = sorted(set(base_tools) & set(extras))
    if collisions:
        raise ProfileCompositionError(
            "tool name collision while composing profile: " + ", ".join(collisions)
        )
    composed = {**base_tools, **extras}
    for spec in composed.values():
        _stamp_tool_contract_provenance(spec)

    def tools(self):
        return dict(composed)

    profile.tools = MethodType(tools, profile)
    return profile

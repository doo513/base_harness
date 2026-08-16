from __future__ import annotations

from typing import Any

from .context import ContextProjection


class RuntimeContextProjection(ContextProjection):
    """Governed model projection plus non-serialized legacy controller reads.

    The actual dict payload remains the Stage-07 namespaced projection.  The
    legacy snapshot is kept only as a Python attribute and is therefore not
    emitted by json serialization.  This preserves the old trusted Controller
    read API without exposing raw/unbounded legacy fields to the model path.
    """

    def __init__(self, projected: ContextProjection, legacy: dict[str, Any]):
        super().__init__(projected)
        self._runtime_legacy = legacy

    def __getitem__(self, key):
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        if key in self._runtime_legacy:
            return self._runtime_legacy[key]
        return super().__getitem__(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        return (
            dict.__contains__(self, key)
            or key in self._runtime_legacy
            or super().__contains__(key)
        )


class RuntimeContextMixin:
    """Model-visible Context Governor projection boundary."""

    def _legacy_controller_context(self) -> dict[str, Any]:
        """Reconstruct the pre-Stage-07 trusted Controller read schema.

        Values are detached snapshots rather than references into durable
        HarnessState, so compatibility reads cannot mutate kernel state.
        """
        return {
            "step": int(self.state.step),
            "pinned_constraints": list(self.goal.pinned_constraints),
            "acceptance": list(self.goal.acceptance),
            "facts": {k: v.dump() for k, v in self.state.facts.items()},
            "hypotheses": {k: v.dump() for k, v in self.state.hypotheses.items()},
            "refuted_hypotheses": {
                k: v.dump() for k, v in self.state.refuted_hypotheses.items()
            },
            "unknowns": list(self.state.unknowns),
            "observations": [o.dump() for o in self.state.observations],
            "recent_failures": [dict(item) for item in self.state.failures[-5:]],
            "recovery_directive": (
                dict(self.state.recovery_directive)
                if self.state.recovery_directive is not None else None
            ),
            "strategy_generation": int(self.state.strategy_generation),
            "recovery_halted": bool(self.state.recovery_halted),
            "progress": self.state.progress.dump(),
            "tools": {
                name: {
                    "description": spec.description,
                    "side_effect": spec.side_effect.value,
                    "idempotent": bool(spec.idempotent),
                }
                for name, spec in self.actions.tools.items()
            },
        }

    def _context(self) -> dict:
        projected = self.context_projector.project(
            goal=self.goal,
            state=self.state,
            tools=self.actions.tools,
        )
        return RuntimeContextProjection(
            projected,
            self._legacy_controller_context(),
        )

from __future__ import annotations

from typing import Any

from .context import ContextProjection


class RuntimeContextProjection(ContextProjection):
    """Governed model projection plus non-serialized legacy controller reads.

    The actual dict payload remains the Stage-07 namespaced projection. The
    legacy snapshot is kept only as a Python attribute and is therefore not
    emitted by JSON serialization. Legacy aliases are used only for keys that
    moved out of the old top-level schema; real Stage-07 top-level keys such as
    `tools` always resolve to the governed projection to avoid a Python/JSON
    split-brain API.
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
        """Reconstruct moved pre-Stage-07 trusted Controller read fields.

        Values are detached snapshots rather than references into durable
        HarnessState, so compatibility reads cannot mutate kernel state.
        `tools` is intentionally absent because it remains a real Stage-07
        top-level key and must have one consistent governed value for Python
        callers and JSON/model serialization.
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
        }

    def _project_retrieval_context(self, projected):
        """No-op extension hook for runtimes that do not install Stage-08 retrieval.

        HarnessRuntime places RuntimeRetrievalMixin earlier in the MRO, so the
        real retrieval governor overrides this hook. Keeping the neutral hook
        here preserves RuntimeContextMixin's independent Stage-07 contract and
        compatibility test fixtures.
        """
        return projected

    def _context(self) -> dict:
        projected = self.context_projector.project(
            goal=self.goal,
            state=self.state,
            tools=self.actions.tools,
        )
        projected = self._project_retrieval_context(projected)
        # Actor planning state is visible through the same governed model
        # projection boundary, but is explicitly non-authoritative. It is not a
        # trusted fact namespace and cannot grant progress/completion credit.
        projected["agent_workflow"] = self.state.agent_control.context_view()
        return RuntimeContextProjection(
            projected,
            self._legacy_controller_context(),
        )

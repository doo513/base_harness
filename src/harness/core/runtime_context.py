from __future__ import annotations

from typing import Any

from .context import ContextProjection
from .context_relevance import ActiveContextProjector
from .tools import tool_contract_descriptor


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

    def _active_context_projector(self) -> ActiveContextProjector:
        projector = getattr(self, "_integration_active_context_projector", None)
        if projector is None:
            projector = ActiveContextProjector()
            self._integration_active_context_projector = projector
        return projector

    def _domain_contract_context(self) -> dict[str, Any]:
        """Project optional post-Stage08 domain guidance without requiring it.

        RuntimeContextMixin is also the standalone Stage-07 compatibility
        boundary used by legacy/deterministic runtimes. Those runtimes do not
        necessarily install a domain profile, so integration enrichment must
        degrade to an explicit non-authoritative empty contract rather than
        turning `profile` into a new Stage-07 prerequisite.
        """
        profile = getattr(self, "profile", None)
        workflow = profile.workflow_contract() if profile is not None else None
        evaluation = profile.evaluation_contract() if profile is not None else None
        return {
            "profile": getattr(profile, "name", None),
            "authority": "harness_domain_contract",
            "workflow": workflow.dump() if workflow is not None else None,
            "evaluation": evaluation.dump() if evaluation is not None else None,
            "evaluation_truth_authority": "none",
            "evaluation_progress_authority": False,
            "evaluation_completion_authority": False,
        }

    def _context(self) -> dict:
        projected = self.context_projector.project(
            goal=self.goal,
            state=self.state,
            tools=self.actions.tools,
        )
        projected = self._project_retrieval_context(projected)

        # Stage-07 base projection remains backward compatible. Runtime-level
        # integration enriches only tools that explicitly declare schemas.
        for name, spec in self.actions.tools.items():
            visible = projected.get("tools", {}).get(name)
            if isinstance(visible, dict):
                contract = tool_contract_descriptor(spec)
                # External protocols such as MCP can advertise full JSON Schema
                # 2020-12. Preserve that for model/tool-call generation without
                # claiming our local subset validator enforces the entire spec.
                model_input = getattr(spec, "model_input_schema", None)
                model_output = getattr(spec, "model_output_schema", None)
                if isinstance(model_input, dict):
                    contract["input_schema"] = model_input
                    contract["input_schema_validation"] = "provider"
                if isinstance(model_output, dict):
                    contract["output_schema"] = model_output
                    contract["output_schema_validation"] = "provider"
                visible.update(contract)

        projected["domain_contract"] = self._domain_contract_context()

        # Actor planning state is visible through the same governed model
        # projection boundary, but is explicitly non-authoritative. It is not a
        # trusted fact namespace and cannot grant progress/completion credit.
        projected["agent_workflow"] = self.state.agent_control.context_view()

        # Relevance affects visibility priority only. The focused namespace does
        # not rewrite Stage-07 trust/authority or grant progress/completion.
        projected["active_context"] = self._active_context_projector().project(
            goal=self.goal,
            state=self.state,
        )

        # Retrieval/memory is a post-Stage08 integration option. Access the
        # optional runtime member itself defensively so standalone Stage-07
        # runtimes retain their original construction contract.
        retrieval_gateway = getattr(self, "retrieval_gateway", None)
        memory_enabled = getattr(retrieval_gateway, "provider_id", None) == "project_memory"
        projected["project_memory"] = {
            "enabled": memory_enabled,
            "trust": "untrusted_project_memory",
            "instruction_authority": "none",
            "write_protocol": (
                "propose memory_candidate.<label> with exact kind/content/tags and registered evidence_refs; "
                "publication occurs post-run"
                if memory_enabled
                else None
            ),
            "read_protocol": "Stage-08 retrieval only" if memory_enabled else None,
            "progress_authority": False,
            "completion_authority": False,
        }
        return RuntimeContextProjection(
            projected,
            self._legacy_controller_context(),
        )

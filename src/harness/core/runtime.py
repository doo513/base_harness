from pathlib import Path
from typing import Any
import uuid

from harness import __version__

from .state import HarnessState
from .events import EventLog, Event, JsonlLog
from .storage import (
    CheckpointStore, ArtifactStore, RunManifestStore, ReceiptStore,
    ResumeConflict, canonical_hash, atomic_write_json,
)
from .tools import ActionRuntime
from .security import Principal, Capability, CapabilityPolicy, SecurityConfig, SecurityLayout, SecurityViolation
from .sandbox import NetworkPolicy
from .verification import VerifierChain
from .failures import Failure, FailureContext, FailureKind, FailureRouter, RecoveryAction
from .budget import Budget
from .progress import ProgressPolicy
from .context import ContextPolicy, ContextProjector
from .provenance import capture_build_provenance
from .retrieval import RetrievalPolicy
from .workspace import WorkspaceContract, WorkspaceContractError
from .runtime_recovery import RuntimeRecoveryMixin
from .runtime_retrieval_kernel import RuntimeRetrievalMixin
from .runtime_progress import RuntimeProgressMixin
from .runtime_context import RuntimeContextMixin
from .runtime_controller_state import RuntimeControllerStateMixin
from .runtime_persistence import RuntimePersistenceMixin
from .runtime_model_telemetry import RuntimeModelTelemetryMixin
from .runtime_execution import RuntimeExecutionMixin


class HarnessRuntime(
    RuntimeRecoveryMixin,
    RuntimeRetrievalMixin,
    RuntimeProgressMixin,
    RuntimeContextMixin,
    RuntimeControllerStateMixin,
    RuntimePersistenceMixin,
    RuntimeModelTelemetryMixin,
    RuntimeExecutionMixin,
):
    """Single-actor verified-state kernel with recovery, progress, context, and bounded retrieval governance."""

    def __init__(
        self,
        *,
        goal,
        profile,
        controller,
        run_dir,
        budget=None,
        workspace=None,
        workspace_contract: WorkspaceContract | None = None,
        security_config: SecurityConfig | None = None,
        capability_policy: CapabilityPolicy | None = None,
        failure_router: FailureRouter | None = None,
        progress_policy: ProgressPolicy | None = None,
        context_policy: ContextPolicy | None = None,
        retrieval_policy: RetrievalPolicy | None = None,
        retrieval_gateway=None,
        resume: bool = False,
        task_revision: str | None = None,
        model_revision: str | None = None,
        require_complete_provenance: bool = False,
    ):
        self.goal = goal
        self.profile = profile
        self.controller = controller
        self.security_config = security_config or SecurityConfig()
        self.capability_policy = capability_policy or CapabilityPolicy.default()
        self.failure_router = failure_router or FailureRouter()
        self.progress_policy = progress_policy or ProgressPolicy()
        self.context_policy = context_policy or ContextPolicy()
        self.context_projector = ContextProjector(self.context_policy)

        self.retrieval_gateway = retrieval_gateway
        if retrieval_policy is None:
            self.retrieval_policy = RetrievalPolicy(enabled=retrieval_gateway is not None)
        else:
            self.retrieval_policy = retrieval_policy
        if self.retrieval_policy.enabled and self.retrieval_gateway is None:
            raise ValueError("enabled retrieval requires a retrieval_gateway")
        if self.retrieval_gateway is not None and not self.retrieval_policy.enabled:
            raise ValueError("retrieval_gateway cannot be supplied while retrieval policy is disabled")

        self.resume_mode = bool(resume)
        self.task_revision = task_revision
        self.model_revision = model_revision
        self.require_complete_provenance = require_complete_provenance
        self.halted = False
        self.elapsed_before_resume = 0.0

        requested_workspace = Path(workspace or getattr(profile, "workspace", ".")).expanduser().resolve()
        if workspace_contract is None:
            self.workspace_contract = WorkspaceContract.build(requested_workspace)
        else:
            workspace_contract.validate()
            if workspace is not None and workspace_contract.root != requested_workspace:
                raise WorkspaceContractError(
                    "workspace argument and workspace_contract root must identify the same directory"
                )
            self.workspace_contract = workspace_contract
        self.workspace = self.workspace_contract.root
        self.workspace_contract.ensure_managed_dirs()
        self.run_dir = Path(run_dir).resolve()

        self.build_provenance = capture_build_provenance()

        self.oracle = profile.completion_oracle()
        oracle_root = getattr(getattr(self.oracle, "bundle", None), "root", None)
        self.security_layout = SecurityLayout.build(
            workspace=self.workspace,
            run_dir=self.run_dir,
            oracle_root=oracle_root,
        )
        if self.security_config.strict_layout:
            self.security_layout.validate_strict()
        if self.security_config.require_sealed_oracle and not getattr(self.oracle, "is_sealed", False):
            raise SecurityViolation("strict configuration requires SealedCommandCompletionOracle")

        try:
            network_policy = NetworkPolicy(self.security_config.network_policy)
        except ValueError as exc:
            raise SecurityViolation(f"invalid network policy: {self.security_config.network_policy}") from exc

        tool_specs = profile.tools()
        self.workspace_contract.validate_tool_workspaces(tool_specs)
        self.actions = ActionRuntime(
            tool_specs,
            capability_policy=self.capability_policy,
            principal=Principal.ACTOR,
            strict_isolation=self.security_config.strict_tool_isolation,
            network_policy=network_policy,
            allow_test_attestation=self.security_config.allow_test_attestation,
        )
        self.verifiers = VerifierChain(profile.verifiers())
        self.budget = budget or Budget()
        self.started_at = self.budget.start()

        self.run_dir.mkdir(parents=True, exist_ok=True)
        if not self.resume_mode and any(self.run_dir.iterdir()):
            raise ResumeConflict("run directory is not empty; use a fresh directory or resume the existing run")

        self.manifests = RunManifestStore(self.run_dir / "run_manifest.json")
        self.checkpoints = CheckpointStore(self.run_dir / "checkpoint.json")
        self.receipts = ReceiptStore(self.run_dir / "receipts")
        self.artifacts = ArtifactStore(self.run_dir / "artifacts")
        self.events = EventLog(self.run_dir / "events.jsonl")
        self.tool_calls = JsonlLog(self.run_dir / "tool_calls.jsonl")

        self.metrics = {
            "run_id": "",
            "steps": 0,
            "tool_calls": 0,
            "failures": 0,
            "verification_attempts": 0,
            "completion_requests": 0,
            "oracle_checks": 0,
            "completed": False,
            "security_violations": 0,
            "oracle_integrity_rejections": 0,
            "receipt_deduplications": 0,
            "ambiguous_side_effects": 0,
            "resume_count": 0,
            "recovery_transitions": 0,
            "recovery_halts": 0,
            "strategy_switches": 0,
            "progress_evaluations": 0,
            "progress_events": 0,
            "no_progress_triggers": 0,
            "strategy_exhaustions": 0,
            "retrieval_requests": 0,
            "retrieval_results": 0,
            "retrieval_items_admitted": 0,
            "model_attempts": 0,
            "model_protocol_lexical_repairs": 0,
        }

        if self.resume_mode:
            self._restore_run()
        else:
            self.state = HarnessState()
            self.run_id = uuid.uuid4().hex[:12]
            self.metrics["run_id"] = self.run_id
            self.manifest_body, self.manifest_hash = self.manifests.create(self._build_manifest())

    @classmethod
    def resume(cls, **kwargs):
        kwargs["resume"] = True
        return cls(**kwargs)

    def _restore_run(self) -> None:
        persisted, _ = self.manifests.load_verified()
        persisted_version = persisted.get("harness_version")
        if persisted_version != __version__:
            raise ResumeConflict(
                f"harness version differs from persisted run manifest: "
                f"persisted={persisted_version!r}, current={__version__!r}"
            )
        super()._restore_run()
        self._validate_retrieval_state_integrity()
        self.halted = bool(self.state.recovery_halted)

    def _config_descriptor(self) -> dict[str, Any]:
        descriptor = super()._config_descriptor()
        contract = self.profile.verification_contract()
        descriptor["profile"]["verification_contract"] = contract.dump()
        descriptor["profile"]["verifiers"] = [
            {
                "name": getattr(v, "name", type(v).__name__),
                "class": f"{type(v).__module__}.{type(v).__qualname__}",
                "level": int(v.level),
                "coverage": sorted(str(x) for x in getattr(v, "covers", ())),
                "source_hash": self._source_hash(v),
            }
            for v in getattr(self.verifiers, "verifiers", [])
        ]
        registry = self.profile.claim_verification_registry()
        descriptor["profile"]["claim_verification_registry"] = (
            registry.dump() if registry is not None else None
        )
        descriptor["workspace_contract"] = self.workspace_contract.descriptor()
        descriptor["failure_recovery"] = self.failure_router.descriptor()
        descriptor["progress_control"] = self.progress_policy.descriptor()
        descriptor["context_governance"] = self.context_policy.descriptor()
        descriptor["retrieval_memory"] = self._retrieval_config_descriptor()

        model = getattr(self.controller, "model", None)
        model_descriptor = getattr(model, "descriptor", None)
        if callable(model_descriptor):
            raw = model_descriptor()
            if isinstance(raw, dict):
                descriptor["model_gateway"] = {
                    "revision": getattr(model, "revision", None),
                    "descriptor": raw,
                }

        # Only semantic build identity participates in resume equivalence. Git
        # commit/tree and CI presentation metadata stay in the audit manifest so
        # docs-only commits do not manufacture a false runtime conflict.
        descriptor["build_provenance"] = self.build_provenance.semantic_descriptor()
        return descriptor

    def _provenance_warnings(self, *, task_revision: str, model_revision: str) -> list[str]:
        warnings = super()._provenance_warnings(
            task_revision=task_revision,
            model_revision=model_revision,
        )
        warnings.extend(self.build_provenance.warnings)
        return list(dict.fromkeys(warnings))

    def _build_manifest(self) -> dict[str, Any]:
        manifest = super()._build_manifest()
        manifest["build_provenance"] = self.build_provenance.dump()
        return manifest

    def log(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.capability_policy.require(Principal.KERNEL, Capability.LEDGER_WRITE)
        return self.events.append_event(Event(kind, payload, self.state.step))

    def _save_metrics(self) -> None:
        data = dict(self.metrics)
        data["steps"] = self.state.step
        data["completed"] = self.state.completed
        data["wall_seconds"] = round(self._wall_elapsed(), 6)
        atomic_write_json(self.run_dir / "metrics.json", data)

    def fail(self, failure: Failure) -> None:
        if failure.context is None and failure.action == "model_boundary":
            candidate = getattr(self.controller, "last_failure_context", None)
            if isinstance(candidate, FailureContext) and candidate.kind is failure.kind:
                failure.context = candidate
                failure.retry_safe = candidate.retryable

        generation = int(self.state.strategy_generation)
        previous = sum(
            1
            for item in self.state.failures
            if item.get("signature") == failure.signature
            and int(item.get("strategy_generation", 0)) == generation
        )
        repeat_count = previous + 1
        recovery = self.failure_router.route(failure, repeat_count)
        transition = self._schedule_recovery(
            failure,
            repeat_count=repeat_count,
            action=recovery,
        )
        record = {
            "kind": failure.kind.value,
            "message": failure.message,
            "signature": failure.signature,
            "repeat_count": repeat_count,
            "strategy_generation": generation,
            "recommended_recovery": recovery.value,
            "retry_safe": bool(failure.retry_safe),
            "target": failure.action,
            "failure_context": failure.context.dump() if failure.context is not None else None,
            "recovery_transition_id": transition.transition_id,
        }
        self.state.failures.append(record)
        self.metrics["failures"] += 1
        failure_index = len(self.state.failures) - 1

        self._persist_state("failure.recovery.scheduled")
        self.log("failure", record)
        self.log("recovery.scheduled", {
            "failure_index": failure_index,
            "failure_signature": failure.signature,
            "strategy_generation": generation,
            "transition": transition.dump(),
        })

    def _run_budget_terminalization(self) -> None:
        self.fail(Failure(FailureKind.BUDGET_EXCEEDED, "hard budget exceeded"))
        self._apply_pending_recovery()
        self.halted = True
        self._persist_state("halted")
        self._save_metrics()

    def run(self) -> HarnessState:
        self.goal.validate()
        if self.resume_mode:
            self.log(
                "run.resume",
                {
                    "run_id": self.run_id,
                    "restored_step": self.state.step,
                    "state_hash": canonical_hash(self.state.snapshot()),
                    "manifest_hash": self.manifest_hash,
                    "recovery_halted": self.state.recovery_halted,
                    "pending_recovery": (
                        self.state.pending_recovery.dump()
                        if self.state.pending_recovery is not None else None
                    ),
                    "progress": self.state.progress.dump(),
                    "context_governance": self.context_policy.descriptor(),
                    "retrieval_memory": self._retrieval_config_descriptor(),
                    "workspace_contract": self.workspace_contract.descriptor(),
                },
            )
            self._persist_state("resume.start")
        else:
            self.log(
                "run.start",
                {
                    "run_id": self.run_id,
                    "goal": self.goal.goal,
                    "acceptance": self.goal.acceptance,
                    "constraints": self.goal.constraints,
                    "pinned_constraints": self.goal.pinned_constraints,
                    "workspace": str(self.workspace),
                    "workspace_contract": self.workspace_contract.descriptor(),
                    "profile": self.profile.name,
                    "manifest_hash": self.manifest_hash,
                    "provenance_warnings": self.manifest_body.get("provenance_warnings", []),
                    "progress_control": self.progress_policy.descriptor(),
                    "context_governance": self.context_policy.descriptor(),
                    "retrieval_memory": self._retrieval_config_descriptor(),
                    "security": {
                        "strict_layout": self.security_config.strict_layout,
                        "strict_tool_isolation": self.security_config.strict_tool_isolation,
                        "network_policy": self.security_config.network_policy,
                        "require_sealed_oracle": self.security_config.require_sealed_oracle,
                        "oracle_root_present": self.security_layout.oracle_root is not None,
                    },
                },
            )
            self._persist_state("run.start")

        while not self.state.completed and not self.halted:
            pending = self.state.pending_recovery
            if pending is not None and pending.action in {
                RecoveryAction.CHECKPOINT_STOP,
                RecoveryAction.ESCALATE,
            }:
                recovery_applied = self.step_once()
            elif self.budget.hard_exceeded(
                self.state.step, self.started_at, elapsed_before=self.elapsed_before_resume
            ):
                self._run_budget_terminalization()
                break
            else:
                recovery_applied = self.step_once()

            if not recovery_applied and not self.halted:
                self.state.step += 1
            self._persist_state("halted" if self.halted else "step.transition")
            self._save_metrics()

        self.log(
            "run.end",
            {
                "completed": self.state.completed,
                "halted": self.halted,
                "steps": self.state.step,
                "state_hash": canonical_hash(self.state.snapshot()),
                "recovery_halted": self.state.recovery_halted,
                "progress": self.state.progress.dump(),
                "retrieval": {
                    "items": len(self.state.retrieval.items),
                    "snapshots": len(self.state.retrieval.results),
                    "current_items": len(self.state.retrieval.current_item_ids),
                },
            },
        )
        self._persist_state("run.end")
        self._save_metrics()
        return self.state

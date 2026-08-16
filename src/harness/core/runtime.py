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
from .failures import Failure, FailureKind, FailureRouter
from .budget import Budget
from .runtime_controller_state import RuntimeControllerStateMixin
from .runtime_persistence import RuntimePersistenceMixin
from .runtime_execution import RuntimeExecutionMixin


class HarnessRuntime(RuntimeControllerStateMixin, RuntimePersistenceMixin, RuntimeExecutionMixin):
    """Single-actor verified-state kernel.

    Actor output may create hypotheses and request completion, but only the
    configured verifier contract and completion oracle may mutate trusted facts
    or completed=True.
    """

    def __init__(
        self,
        *,
        goal,
        profile,
        controller,
        run_dir,
        budget=None,
        workspace=None,
        security_config: SecurityConfig | None = None,
        capability_policy: CapabilityPolicy | None = None,
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
        self.resume_mode = bool(resume)
        self.task_revision = task_revision
        self.model_revision = model_revision
        self.require_complete_provenance = require_complete_provenance
        self.halted = False
        self.elapsed_before_resume = 0.0

        self.workspace = Path(workspace or getattr(profile, "workspace", ".")).resolve()
        self.run_dir = Path(run_dir).resolve()

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

        self.actions = ActionRuntime(
            profile.tools(),
            capability_policy=self.capability_policy,
            principal=Principal.ACTOR,
            strict_isolation=self.security_config.strict_tool_isolation,
            network_policy=network_policy,
            allow_test_attestation=self.security_config.allow_test_attestation,
        )
        self.verifiers = VerifierChain(profile.verifiers())
        self.failure_router = FailureRouter()
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
        """Fail closed when a persisted run belongs to a different harness version."""
        persisted, _ = self.manifests.load_verified()
        persisted_version = persisted.get("harness_version")
        if persisted_version != __version__:
            raise ResumeConflict(
                f"harness version differs from persisted run manifest: "
                f"persisted={persisted_version!r}, current={__version__!r}"
            )
        super()._restore_run()

    def _config_descriptor(self) -> dict[str, Any]:
        """Extend Stage-03 provenance with the Stage-04 verification contract."""
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
        return descriptor

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
        previous = sum(1 for item in self.state.failures if item.get("signature") == failure.signature)
        repeat_count = previous + 1
        recovery = self.failure_router.route(failure, repeat_count)
        record = {
            "kind": failure.kind.value,
            "message": failure.message,
            "signature": failure.signature,
            "repeat_count": repeat_count,
            "recommended_recovery": recovery.value,
        }
        self.state.failures.append(record)
        self.metrics["failures"] += 1
        self.log("failure", record)

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
                    "workspace": str(self.workspace),
                    "profile": self.profile.name,
                    "manifest_hash": self.manifest_hash,
                    "provenance_warnings": self.manifest_body.get("provenance_warnings", []),
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
            if self.budget.hard_exceeded(
                self.state.step, self.started_at, elapsed_before=self.elapsed_before_resume
            ):
                self.fail(Failure(FailureKind.BUDGET_EXCEEDED, "hard budget exceeded"))
                self.halted = True
                break
            self.step_once()
            if not self.halted:
                self.state.step += 1
            self._persist_state("step.transition" if not self.halted else "halted")
            self._save_metrics()

        self.log(
            "run.end",
            {
                "completed": self.state.completed,
                "halted": self.halted,
                "steps": self.state.step,
                "state_hash": canonical_hash(self.state.snapshot()),
            },
        )
        self._persist_state("run.end")
        self._save_metrics()
        return self.state

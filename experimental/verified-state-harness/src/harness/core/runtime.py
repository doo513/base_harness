from pathlib import Path
from time import monotonic
from typing import Any
import json
import uuid

from .state import HarnessState, Claim, ClaimStatus, Authority, Observation
from .events import EventLog, Event, JsonlLog
from .storage import CheckpointStore, ArtifactStore
from .tools import ActionRuntime, ToolCall
from .security import Principal, Capability, CapabilityPolicy, SecurityConfig, SecurityLayout, SecurityViolation
from .sandbox import NetworkPolicy
from .verification import VerifierChain, VerificationLevel
from .failures import Failure, FailureKind, FailureRouter
from .budget import Budget

class HarnessRuntime:
    """v0.1 single-agent kernel.

    Important invariant: actor output can create hypotheses and request completion,
    but only verifier/oracle results can mutate trusted facts or completed=True.
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
    ):
        self.goal = goal
        self.profile = profile
        self.controller = controller
        self.state = HarnessState()
        self.run_id = uuid.uuid4().hex[:12]
        self.security_config = security_config or SecurityConfig()
        self.capability_policy = capability_policy or CapabilityPolicy.default()

        self.workspace = Path(workspace or getattr(profile, "workspace", ".")).resolve()
        self.run_dir = Path(run_dir).resolve()

        # Construct the oracle before validating layout so a sealed oracle root,
        # if present, becomes part of the trust-boundary topology check.
        self.oracle = profile.completion_oracle()
        oracle_root = getattr(getattr(self.oracle, "bundle", None), "root", None)
        self.security_layout = SecurityLayout.build(
            workspace=self.workspace,
            run_dir=self.run_dir,
            oracle_root=oracle_root,
        )
        if self.security_config.strict_layout:
            self.security_layout.validate_strict()

        if self.security_config.require_sealed_oracle:
            if not getattr(self.oracle, "is_sealed", False):
                raise SecurityViolation(
                    "strict configuration requires SealedCommandCompletionOracle"
                )

        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events = EventLog(self.run_dir / "events.jsonl")
        self.tool_calls = JsonlLog(self.run_dir / "tool_calls.jsonl")
        self.checkpoints = CheckpointStore(self.run_dir / "checkpoint.json")
        self.artifacts = ArtifactStore(self.run_dir / "artifacts")

        try:
            network_policy = NetworkPolicy(self.security_config.network_policy)
        except ValueError as exc:
            raise SecurityViolation(
                f"invalid network policy: {self.security_config.network_policy}"
            ) from exc

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

        self.metrics = {
            "run_id": self.run_id,
            "steps": 0,
            "tool_calls": 0,
            "failures": 0,
            "verification_attempts": 0,
            "completion_requests": 0,
            "oracle_checks": 0,
            "completed": False,
            "security_violations": 0,
            "oracle_integrity_rejections": 0,
        }

    def log(self, kind: str, payload: dict[str, Any]) -> None:
        self.capability_policy.require(Principal.KERNEL, Capability.LEDGER_WRITE)
        self.events.append_event(Event(kind, payload, self.state.step))

    def _save_metrics(self) -> None:
        data = dict(self.metrics)
        data["steps"] = self.state.step
        data["completed"] = self.state.completed
        data["wall_seconds"] = round(monotonic() - self.started_at, 6)
        (self.run_dir / "metrics.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

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

    def _context(self) -> dict:
        return {
            "step": self.state.step,
            "pinned_constraints": list(self.goal.pinned_constraints),
            "acceptance": list(self.goal.acceptance),
            "facts": {k: v.dump() for k, v in self.state.facts.items()},
            "hypotheses": {k: v.dump() for k, v in self.state.hypotheses.items()},
            "refuted_hypotheses": {k: v.dump() for k, v in self.state.refuted_hypotheses.items()},
            "unknowns": list(self.state.unknowns),
            # v0.1 baseline keeps raw recent observations; Observation Gate comes later.
            "observations": [o.dump() for o in self.state.observations],
            "recent_failures": self.state.failures[-5:],
            "tools": {
                name: {
                    "description": spec.description,
                    "side_effect": spec.side_effect.value,
                    "idempotent": spec.idempotent,
                }
                for name, spec in self.actions.tools.items()
            },
        }

    def _store_tool_observation(self, tool: str, result) -> Observation:
        payload = {"ok": result.ok, "output": result.output, "error": result.error}
        ref = self.artifacts.put_json(
            f"step_{self.state.step:04d}_{tool}.json",
            payload,
        )
        self.state.artifacts.append(ref)
        self.state.evidence_refs.append(ref)
        preview = result.output
        if isinstance(preview, str) and len(preview) > 8000:
            preview = preview[:8000] + "\n...[truncated preview; full output in artifact]"
        observation = Observation(
            step=self.state.step,
            source=tool,
            ok=result.ok,
            preview=preview,
            artifact_ref=ref,
            error=result.error,
        )
        self.state.observations.append(observation)
        return observation

    @staticmethod
    def _authority_from_verification(results) -> Authority:
        if not results:
            return Authority.MODEL
        highest = results[-1].level
        if highest >= VerificationLevel.EXTERNAL_ORACLE:
            return Authority.EXTERNAL_ORACLE
        if highest >= VerificationLevel.EXECUTION:
            return Authority.ENVIRONMENT
        return Authority.TRUSTED_TOOL

    def _verify_claim(self, key: str) -> None:
        claim = self.state.hypotheses.get(key)
        if not claim:
            self.fail(Failure(FailureKind.MISSING_INFO, f"missing hypothesis: {key}"))
            return
        self.metrics["verification_attempts"] += 1
        self.capability_policy.require(Principal.VERIFIER, Capability.VERIFY)
        results = self.verifiers.run(
            claim.value,
            {
                "state": self.state.snapshot(),
                "goal": self.goal.goal,
                "claim_key": claim.key,
                "claim_evidence_refs": claim.evidence_refs,
                # Verifier context intentionally omits actor workspace path.
                # Built-in in-process validators receive only the artifact root
                # required for resolving opaque evidence references.
                "artifact_root": str(self.artifacts.root),
            },
        )
        serial = [
            {
                "ok": r.verified,
                "level": int(r.level),
                "level_name": r.level.name,
                "verifier": r.verifier,
                "reason": r.reason,
                "evidence_refs": r.evidence_refs,
                "details": r.details,
            }
            for r in results
        ]
        self.log("verification", {"claim": claim.key, "results": serial})
        if self.verifiers.accepted(results, self.profile.minimum_verification_level()):
            claim.status = ClaimStatus.VERIFIED
            claim.authority = self._authority_from_verification(results)
            for result in results:
                for ref in result.evidence_refs:
                    if ref not in claim.evidence_refs:
                        claim.evidence_refs.append(ref)
            self.capability_policy.require(Principal.KERNEL, Capability.STATE_COMMIT)
            self.state.commit_verified(claim)
            self.log("state.commit", claim.dump())
        else:
            self.fail(Failure(FailureKind.VERIFICATION_FAILED, f"verification failed: {claim.key}"))

    def _check_completion(self, reason: str) -> None:
        self.state.completion_requested = True
        self.metrics["completion_requests"] += 1
        self.metrics["oracle_checks"] += 1
        self.capability_policy.require(Principal.ORACLE, Capability.ORACLE_EXECUTE)
        oracle_state = HarnessState.from_snapshot(self.state.snapshot())
        result = self.oracle.evaluate(goal=self.goal, state=oracle_state, workspace=self.workspace)
        if (not result.accepted) and ("changed" in result.reason or "sealed" in result.reason):
            self.metrics["oracle_integrity_rejections"] += 1
        artifact_ref = self.artifacts.put_json(
            f"step_{self.state.step:04d}_completion_oracle.json",
            {
                "oracle": getattr(self.oracle, "name", type(self.oracle).__name__),
                "accepted": result.accepted,
                "reason": result.reason,
                "evidence": result.evidence,
                "oracle_id": result.oracle_id,
                "independence_level": result.independence_level,
                "evidence_hash": result.evidence_hash,
                "coverage": result.coverage,
                "actor_reason": reason,
            },
        )
        self.state.artifacts.append(artifact_ref)
        self.state.evidence_refs.append(artifact_ref)
        self.log(
            "completion.oracle",
            {
                "accepted": result.accepted,
                "reason": result.reason,
                "oracle_id": result.oracle_id,
                "independence_level": result.independence_level,
                "evidence_hash": result.evidence_hash,
                "artifact_ref": artifact_ref,
            },
        )
        if result.accepted:
            self.state.completed = True
            self.log("completion.accepted", {"reason": result.reason})
        else:
            self.fail(
                Failure(
                    FailureKind.VERIFICATION_FAILED,
                    f"completion oracle rejected: {result.reason}",
                    action="completion_oracle",
                )
            )


    def _dispatch_decision(self, decision) -> None:
        if decision.kind == "propose":
            key = decision.payload["key"]
            # A refuted claim can only be re-opened when the actor supplies at least
            # one new evidence ref not present on the refuted version.
            prior = self.state.refuted_hypotheses.get(key)
            new_refs = list(decision.payload.get("evidence_refs", []))
            if prior is not None:
                prior_refs = set(prior.evidence_refs)
                if not any(ref not in prior_refs for ref in new_refs):
                    self.fail(Failure(
                        FailureKind.HYPOTHESIS_REFUTED,
                        f"refuted hypothesis cannot be re-proposed without new evidence: {key}",
                    ))
                    return
            claim = Claim(
                key,
                decision.payload.get("value"),
                evidence_refs=new_refs,
            )
            self.state.propose(claim)
            self.log("hypothesis.proposed", claim.dump())

        elif decision.kind == "verify_claim":
            self._verify_claim(decision.payload["key"])

        elif decision.kind == "refute":
            key = decision.payload["key"]
            claim = self.state.hypotheses.get(key)
            if not claim:
                self.fail(Failure(FailureKind.MISSING_INFO, f"missing hypothesis: {key}"))
                return
            claim.status = ClaimStatus.REFUTED
            self.log("hypothesis.refuted", {"claim": claim.dump(), "reason": decision.payload.get("reason", "")})
            self.state.refuted_hypotheses[key] = claim
            self.state.hypotheses.pop(key, None)

        elif decision.kind == "tool":
            call = ToolCall(decision.payload["tool"], decision.payload.get("args", {}))
            result = self.actions.execute(call)
            observation = self._store_tool_observation(call.tool, result)
            self.metrics["tool_calls"] += 1
            self.tool_calls.append(
                {
                    "run_id": self.run_id,
                    "step": self.state.step,
                    "tool": call.tool,
                    "args": call.args,
                    "ok": result.ok,
                    "error": result.error,
                    "approval_required": getattr(result, "approval_required", False),
                    "security_violation": getattr(result, "security_violation", False),
                    "isolation": getattr(result, "isolation", None),
                    "artifact_ref": observation.artifact_ref,
                }
            )
            self.log(
                "tool.result",
                {
                    "tool": call.tool,
                    "ok": result.ok,
                    "artifact_ref": observation.artifact_ref,
                    "error": result.error,
                    "approval_required": getattr(result, "approval_required", False),
                    "security_violation": getattr(result, "security_violation", False),
                    "isolation": getattr(result, "isolation", None),
                },
            )
            if getattr(result, "security_violation", False):
                self.metrics["security_violations"] += 1
            if not result.ok:
                self.fail(Failure(FailureKind.TOOL_ERROR, result.error or "tool failed", call.tool))

        elif decision.kind == "complete":
            self._check_completion(decision.payload.get("reason", ""))

    def step_once(self) -> None:
        try:
            actor_state = HarnessState.from_snapshot(self.state.snapshot())
            decision = self.controller.decide(self.goal.goal, actor_state, self._context())
            decision.validate()
        except Exception as exc:
            self.fail(Failure(FailureKind.IMPLEMENTATION_ERROR, f"controller error: {type(exc).__name__}: {exc}"))
            return

        self.log("decision", {"kind": decision.kind, "payload": decision.payload})

        try:
            self._dispatch_decision(decision)
        except Exception as exc:
            # Actor-controlled malformed data or domain bugs must not terminate the kernel.
            self.fail(Failure(
                FailureKind.IMPLEMENTATION_ERROR,
                f"decision dispatch error: {type(exc).__name__}: {exc}",
                action=decision.kind,
            ))

    def run(self) -> HarnessState:
        self.goal.validate()
        self.log(
            "run.start",
            {
                "run_id": self.run_id,
                "goal": self.goal.goal,
                "acceptance": self.goal.acceptance,
                "workspace": str(self.workspace),
                "profile": self.profile.name,
                "security": {
                    "strict_layout": self.security_config.strict_layout,
                    "strict_tool_isolation": self.security_config.strict_tool_isolation,
                    "network_policy": self.security_config.network_policy,
                    "require_sealed_oracle": self.security_config.require_sealed_oracle,
                    "oracle_root_present": self.security_layout.oracle_root is not None,
                },
            },
        )
        while not self.state.completed:
            if self.budget.hard_exceeded(self.state.step, self.started_at):
                self.fail(Failure(FailureKind.BUDGET_EXCEEDED, "hard budget exceeded"))
                break
            self.step_once()
            self.state.step += 1
            self.checkpoints.save(self.state.snapshot())
            self._save_metrics()

        self.checkpoints.save(self.state.snapshot())
        self._save_metrics()
        self.log("run.end", {"completed": self.state.completed, "steps": self.state.step})
        return self.state

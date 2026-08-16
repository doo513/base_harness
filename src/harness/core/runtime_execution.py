from __future__ import annotations

from .state import HarnessState, Claim, ClaimStatus, Authority, Observation
from .storage import PersistenceError, IntegrityError, ResumeConflict
from .tools import ToolCall
from .security import Principal, Capability
from .verification import VerificationLevel
from .failures import Failure, FailureKind


class RuntimeExecutionMixin:
    def _context(self) -> dict:
        return {
            "step": self.state.step,
            "pinned_constraints": list(self.goal.pinned_constraints),
            "acceptance": list(self.goal.acceptance),
            "facts": {k: v.dump() for k, v in self.state.facts.items()},
            "hypotheses": {k: v.dump() for k, v in self.state.hypotheses.items()},
            "refuted_hypotheses": {k: v.dump() for k, v in self.state.refuted_hypotheses.items()},
            "unknowns": list(self.state.unknowns),
            "observations": [o.dump() for o in self.state.observations],
            "recent_failures": self.state.failures[-5:],
            "recovery_directive": (
                dict(self.state.recovery_directive)
                if self.state.recovery_directive is not None else None
            ),
            "strategy_generation": self.state.strategy_generation,
            "recovery_halted": self.state.recovery_halted,
            "progress": self.state.progress.dump(),
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
        ref = self.artifacts.put_json(f"step_{self.state.step:04d}_{tool}.json", payload)
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
        highest = max((r.level for r in results if r.verified), default=VerificationLevel.SCHEMA)
        if highest >= VerificationLevel.EXTERNAL_ORACLE:
            return Authority.EXTERNAL_ORACLE
        if highest >= VerificationLevel.EXECUTION:
            return Authority.ENVIRONMENT
        return Authority.SUPPORTED

    def _verify_claim(self, key: str) -> None:
        claim = self.state.hypotheses.get(key)
        if not claim:
            self.fail(Failure(FailureKind.MISSING_INFO, f"missing hypothesis: {key}", action=key))
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
                "artifact_root": str(self.artifacts.root),
            },
        )
        contract = self.profile.verification_contract()
        assessment = contract.assess(results)
        serial = [
            {
                "ok": r.verified,
                "level": int(r.level),
                "level_name": r.level.name,
                "verifier": r.verifier,
                "reason": r.reason,
                "evidence_refs": r.evidence_refs,
                "details": r.details,
                "coverage": r.coverage,
                "confidence": r.confidence,
            }
            for r in results
        ]
        self.log(
            "verification",
            {"claim": claim.key, "results": serial, "assessment": assessment.dump()},
        )
        if assessment.accepted:
            claim.status = ClaimStatus.VERIFIED
            claim.authority = self._authority_from_verification(results)
            for result in results:
                for ref in result.evidence_refs:
                    if ref not in claim.evidence_refs:
                        claim.evidence_refs.append(ref)
            self.capability_policy.require(Principal.KERNEL, Capability.STATE_COMMIT)
            self.state.commit_verified(claim)
            self.log(
                "state.commit",
                {"claim": claim.dump(), "verification_assessment": assessment.dump()},
            )
        else:
            reason = "; ".join(assessment.reasons) or "verification contract rejected candidate"
            self.fail(Failure(
                FailureKind.VERIFICATION_FAILED,
                f"verification failed: {claim.key}: {reason}",
                action=claim.key,
            ))

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
            self.fail(Failure(
                FailureKind.VERIFICATION_FAILED,
                f"completion oracle rejected: {result.reason}",
                action="completion_oracle",
            ))

    def _dispatch_decision(self, decision) -> None:
        if decision.kind == "propose":
            key = decision.payload["key"]
            prior = self.state.refuted_hypotheses.get(key)
            new_refs = list(decision.payload.get("evidence_refs", []))
            if prior is not None:
                prior_refs = set(prior.evidence_refs)
                if not any(ref not in prior_refs for ref in new_refs):
                    self.fail(Failure(
                        FailureKind.HYPOTHESIS_REFUTED,
                        f"refuted hypothesis cannot be re-proposed without new evidence: {key}",
                        action=key,
                    ))
                    return
            claim = Claim(key, decision.payload.get("value"), evidence_refs=new_refs)
            self.state.propose(claim)
            self.log("hypothesis.proposed", claim.dump())

        elif decision.kind == "verify_claim":
            self._verify_claim(decision.payload["key"])

        elif decision.kind == "refute":
            key = decision.payload["key"]
            claim = self.state.hypotheses.get(key)
            if not claim:
                self.fail(Failure(FailureKind.MISSING_INFO, f"missing hypothesis: {key}", action=key))
                return
            claim.status = ClaimStatus.REFUTED
            self.log("hypothesis.refuted", {"claim": claim.dump(), "reason": decision.payload.get("reason", "")})
            self.state.refuted_hypotheses[key] = claim
            self.state.hypotheses.pop(key, None)

        elif decision.kind == "tool":
            call = ToolCall(decision.payload["tool"], decision.payload.get("args", {}))
            try:
                result, receipt_id, deduplicated = self._execute_tool_durable(call)
            except (PersistenceError, IntegrityError, ResumeConflict) as exc:
                # Persistence ambiguity is terminal, but terminality is owned by
                # the recovery transition rather than an ad-hoc runtime flag.
                # This guarantees CHECKPOINT_STOP is itself persisted/applied.
                self.fail(Failure(FailureKind.PERSISTENCE_ERROR, str(exc), action=call.tool))
                return
            observation = self._store_tool_observation(call.tool, result)
            self.metrics["tool_calls"] += 1
            self.tool_calls.append({
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
                "receipt_id": receipt_id,
                "deduplicated": deduplicated,
            })
            self.log("tool.result", {
                "tool": call.tool,
                "ok": result.ok,
                "artifact_ref": observation.artifact_ref,
                "error": result.error,
                "approval_required": getattr(result, "approval_required", False),
                "security_violation": getattr(result, "security_violation", False),
                "isolation": getattr(result, "isolation", None),
                "receipt_id": receipt_id,
                "deduplicated": deduplicated,
            })
            if getattr(result, "security_violation", False):
                self.metrics["security_violations"] += 1
                self.fail(Failure(
                    FailureKind.SECURITY_VIOLATION,
                    result.error or "tool security policy rejected execution",
                    action=call.tool,
                ))
            elif not result.ok:
                self.fail(Failure(
                    FailureKind.TOOL_ERROR,
                    result.error or "tool failed",
                    action=call.tool,
                ))

        elif decision.kind == "complete":
            self._check_completion(decision.payload.get("reason", ""))

    def step_once(self) -> bool:
        if self._apply_pending_recovery():
            return True

        progress_baseline = self._progress_baseline()
        try:
            actor_state = HarnessState.from_snapshot(self.state.snapshot())
            decision = self.controller.decide(self.goal.goal, actor_state, self._context())
            decision.validate()
        except Exception as exc:
            self.fail(Failure(FailureKind.IMPLEMENTATION_ERROR, f"controller error: {type(exc).__name__}: {exc}"))
            return False

        self._consume_recovery_directive()
        self.log("decision", {"kind": decision.kind, "payload": decision.payload})
        try:
            self._dispatch_decision(decision)
        except Exception as exc:
            self.fail(Failure(
                FailureKind.IMPLEMENTATION_ERROR,
                f"decision dispatch error: {type(exc).__name__}: {exc}",
                action=decision.kind,
            ))

        if self.state.completed or self.halted:
            return False

        # A more specific Stage 05 failure always has precedence. We still
        # account for the Actor sample, but generic no-progress recovery cannot
        # supersede the already scheduled transition.
        allow_progress_trigger = self.state.pending_recovery is None
        try:
            self._evaluate_actor_progress(
                decision,
                progress_baseline,
                allow_trigger=allow_progress_trigger,
            )
        except (PersistenceError, IntegrityError, ResumeConflict) as exc:
            self.fail(Failure(
                FailureKind.PERSISTENCE_ERROR,
                f"progress evidence integrity failure: {exc}",
                action=decision.kind,
                signature_key="stage6:progress_evidence_integrity",
            ))
        except Exception as exc:
            self.fail(Failure(
                FailureKind.IMPLEMENTATION_ERROR,
                f"progress evaluation error: {type(exc).__name__}: {exc}",
                action=decision.kind,
            ))
        return False

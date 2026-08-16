from __future__ import annotations

from .failures import RecoveryAction, RecoveryStatus, RecoveryTransition
from .security import Capability, Principal
from .storage import IntegrityError, canonical_hash


class RuntimeRecoveryMixin:
    """Kernel-owned durable recovery transitions.

    Recovery is control-only: it may issue a directive, remove targeted
    untrusted speculative state, switch a strategy generation, or terminally
    halt. It never executes a tool, writes a verified fact, or attempts to undo
    an external side effect.
    """

    _TERMINAL_ACTIONS = frozenset({
        RecoveryAction.CHECKPOINT_STOP,
        RecoveryAction.ESCALATE,
    })

    def _facts_hash(self) -> str:
        return canonical_hash({k: v.dump() for k, v in self.state.facts.items()})

    def _schedule_recovery(self, failure, *, repeat_count: int, action: RecoveryAction) -> RecoveryTransition:
        transition_id = canonical_hash({
            "run_id": self.run_id,
            "created_step": self.state.step,
            "failure_signature": failure.signature,
            "repeat_count": int(repeat_count),
            "action": action.value,
            "target": failure.action,
        })[:24]

        transition = RecoveryTransition(
            transition_id=transition_id,
            action=action,
            failure_kind=failure.kind,
            failure_signature=failure.signature,
            repeat_count=int(repeat_count),
            created_step=int(self.state.step),
            target=failure.action,
            retry_safe=bool(failure.retry_safe),
        )

        existing = self.state.pending_recovery
        if existing is not None:
            existing.status = RecoveryStatus.SUPERSEDED
            existing.details["superseded_by"] = transition.transition_id
            existing.details["superseded_at_step"] = self.state.step
            self.state.recovery_history.append(existing)

        self.state.pending_recovery = transition
        return transition

    def _directive_for(self, transition: RecoveryTransition) -> dict:
        return {
            "transition_id": transition.transition_id,
            "action": transition.action.value,
            "failure_kind": transition.failure_kind.value,
            "failure_signature": transition.failure_signature,
            "repeat_count": transition.repeat_count,
            "target": transition.target,
            "strategy_generation": self.state.strategy_generation,
            "instruction": {
                RecoveryAction.REPAIR: "repair the failed approach before retrying the task action",
                RecoveryAction.OBSERVE: "gather missing or changed information before acting again",
                RecoveryAction.REPLAN: "form a different plan consistent with current verified state",
                RecoveryAction.RETRY: "retry is permitted but must be explicitly chosen by the Actor through normal tool gates",
                RecoveryAction.ROLLBACK: "the targeted untrusted speculative state was rolled back; choose a new evidence-backed path",
                RecoveryAction.SWITCH_STRATEGY: "switch to a materially different strategy; do not repeat the same failure path",
                RecoveryAction.ESCALATE: "automatic recovery is exhausted; external intervention is required",
                RecoveryAction.CHECKPOINT_STOP: "execution is stopped fail-closed; do not continue automatically",
            }[transition.action],
        }

    def _recovery_has_step_budget(self) -> bool:
        return not self.budget.hard_exceeded(
            self.state.step,
            self.started_at,
            elapsed_before=self.elapsed_before_resume,
        )

    def _apply_pending_recovery(self) -> bool:
        transition = self.state.pending_recovery
        if transition is None:
            return False

        self.capability_policy.require(Principal.KERNEL, Capability.STATE_COMMIT)
        before_facts = self._facts_hash()
        details = dict(transition.details)

        if transition.action == RecoveryAction.ROLLBACK:
            removed = False
            if transition.target:
                removed = self.state.hypotheses.pop(transition.target, None) is not None
            details["logical_hypothesis_removed"] = removed
            details["rollback_scope"] = "untrusted_hypothesis_only"

        elif transition.action == RecoveryAction.SWITCH_STRATEGY:
            self.state.strategy_generation += 1
            details["strategy_generation"] = self.state.strategy_generation
            self.metrics["strategy_switches"] = int(self.metrics.get("strategy_switches", 0)) + 1

        elif transition.action == RecoveryAction.RETRY and not transition.retry_safe:
            raise IntegrityError("unsafe RETRY recovery transition reached application")

        directive = self._directive_for(transition)
        self.state.recovery_directive = directive

        if transition.action in self._TERMINAL_ACTIONS:
            self.state.recovery_halted = True
            self.state.recovery_halt_reason = (
                f"{transition.action.value}:{transition.failure_kind.value}:{transition.failure_signature}"
            )
            self.halted = True
            self.metrics["recovery_halts"] = int(self.metrics.get("recovery_halts", 0)) + 1

        after_facts = self._facts_hash()
        if after_facts != before_facts:
            raise IntegrityError("recovery transition attempted to mutate verified facts")

        transition.details = details
        transition.status = RecoveryStatus.APPLIED

        # Recovery consumes a normal harness step while hard budget remains.
        # If the transition is the terminal fail-closed action at an already
        # exhausted hard budget, it is administrative checkpointing and must not
        # make the persisted step counter exceed the declared hard limit.
        step_consumed = self._recovery_has_step_budget()
        if step_consumed:
            self.state.step += 1
        transition.applied_step = self.state.step
        transition.details["step_consumed"] = step_consumed
        transition.details["budget_exhausted_at_apply"] = not step_consumed

        self.state.recovery_history.append(transition)
        self.state.pending_recovery = None
        self.metrics["recovery_transitions"] = int(self.metrics.get("recovery_transitions", 0)) + 1

        # Persist the applied state before returning to Actor control. A crash
        # after this snapshot cannot cause the same control transition to be
        # invisibly applied again on resume. The later audit event is descriptive;
        # the hash-chained state snapshot remains the authoritative transition.
        self._persist_state("recovery.transition")
        self.log("recovery.transition", {
            "transition": transition.dump(),
            "directive": directive,
            "facts_hash": after_facts,
            "terminal": transition.action in self._TERMINAL_ACTIONS,
        })
        return True

    def _consume_recovery_directive(self) -> None:
        directive = self.state.recovery_directive
        if directive is None:
            return
        self.log("recovery.directive.consumed", {
            "transition_id": directive.get("transition_id"),
            "action": directive.get("action"),
        })
        self.state.recovery_directive = None

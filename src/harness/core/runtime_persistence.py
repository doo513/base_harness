from __future__ import annotations

from time import monotonic
from typing import Any
import hashlib
import inspect
import json
import platform
import sys

from harness import __version__

from .events import Event, utc_now
from .state import HarnessState
from .storage import PersistenceError, IntegrityError, ResumeConflict, canonical_hash
from .tools import ToolCall, ToolResult


class RuntimePersistenceMixin:
    def _goal_descriptor(self) -> dict[str, Any]:
        return {
            "goal": self.goal.goal,
            "acceptance": list(self.goal.acceptance),
            "constraints": list(self.goal.constraints),
            "pinned_constraints": list(self.goal.pinned_constraints),
        }

    def _security_descriptor(self) -> dict[str, Any]:
        return {
            "strict_layout": self.security_config.strict_layout,
            "strict_tool_isolation": self.security_config.strict_tool_isolation,
            "network_policy": self.security_config.network_policy,
            "require_sealed_oracle": self.security_config.require_sealed_oracle,
            "allow_test_attestation": self.security_config.allow_test_attestation,
        }

    @staticmethod
    def _source_hash(obj: Any) -> str | None:
        try:
            target = obj if inspect.isclass(obj) or inspect.isfunction(obj) else type(obj)
            source = inspect.getsource(target)
        except (OSError, TypeError):
            return None
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    def _controller_descriptor(self) -> dict[str, Any]:
        descriptor = {
            "class": f"{type(self.controller).__module__}.{type(self.controller).__qualname__}",
            "source_hash": self._source_hash(self.controller),
        }
        adapter = getattr(self.controller, "model", None)
        if adapter is not None:
            descriptor["adapter_class"] = f"{type(adapter).__module__}.{type(adapter).__qualname__}"
            descriptor["adapter_source_hash"] = self._source_hash(adapter)
            command = getattr(adapter, "command", None)
            if isinstance(command, str):
                descriptor["adapter_command_hash"] = hashlib.sha256(command.encode("utf-8")).hexdigest()
            timeout_seconds = getattr(adapter, "timeout_seconds", None)
            if timeout_seconds is not None:
                descriptor["adapter_timeout_seconds"] = timeout_seconds
        return descriptor

    def _tool_descriptors(self) -> list[dict[str, Any]]:
        return [{
            "name": name,
            "side_effect": spec.side_effect.value,
            "idempotent": bool(spec.idempotent),
            "permission": spec.permission,
            "provenance": dict(spec.provenance),
            "backend": getattr(spec.execution_backend, "name", None),
            "handler_source_hash": self._source_hash(spec.handler),
        } for name, spec in sorted(self.actions.tools.items())]

    def _config_descriptor(self) -> dict[str, Any]:
        verifiers = list(getattr(self.verifiers, "verifiers", []))
        contract = self.profile.verification_contract()
        return {
            "goal": self._goal_descriptor(),
            "profile": {
                "name": self.profile.name,
                "class": f"{type(self.profile).__module__}.{type(self.profile).__qualname__}",
                "source_hash": self._source_hash(self.profile),
                "minimum_verification_level": int(self.profile.minimum_verification_level()),
                "verification_contract": contract.dump(),
                "verifiers": [{
                    "name": getattr(v, "name", type(v).__name__),
                    "class": f"{type(v).__module__}.{type(v).__qualname__}",
                    "level": int(v.level),
                    "coverage": sorted(str(x) for x in getattr(v, "covers", ())),
                    "source_hash": self._source_hash(v),
                } for v in verifiers],
            },
            "controller": self._controller_descriptor(),
            "workspace": str(self.workspace),
            "security": self._security_descriptor(),
            "budget": {
                "hard_max_steps": self.budget.hard_max_steps,
                "hard_wall_seconds": self.budget.hard_wall_seconds,
                "soft_max_steps": self.budget.soft_max_steps,
            },
            "tools": self._tool_descriptors(),
            "oracle": {
                "name": getattr(self.oracle, "name", type(self.oracle).__name__),
                "class": f"{type(self.oracle).__module__}.{type(self.oracle).__qualname__}",
                "oracle_id": getattr(self.oracle, "oracle_id", None),
                "sealed": bool(getattr(self.oracle, "is_sealed", False)),
                "seal_manifest_hash": getattr(getattr(self.oracle, "bundle", None), "manifest_hash", None),
                "backend": getattr(getattr(self.oracle, "backend", None), "name", None),
                "require_filesystem_isolation": bool(getattr(self.oracle, "require_filesystem_isolation", False)),
            },
        }

    def _provenance_warnings(self, *, task_revision: str, model_revision: str) -> list[str]:
        warnings: list[str] = []
        if task_revision == "UNSPECIFIED":
            warnings.append("task_revision is unspecified")
        if type(self.controller).__name__ == "LLMController" and model_revision == "UNSPECIFIED":
            warnings.append("model_revision is unspecified for LLMController")
        for tool in self._tool_descriptors():
            if not tool["provenance"]:
                warnings.append(f"tool provenance missing: {tool['name']}")
        return warnings

    def _build_manifest(self) -> dict[str, Any]:
        task_revision = self.task_revision or "UNSPECIFIED"
        model_revision = self.model_revision or (
            f"not_applicable:{type(self.controller).__name__}"
            if type(self.controller).__name__ != "LLMController" else "UNSPECIFIED"
        )
        warnings = self._provenance_warnings(task_revision=task_revision, model_revision=model_revision)
        if self.require_complete_provenance and warnings:
            raise PersistenceError("incomplete run provenance: " + "; ".join(warnings))
        config = self._config_descriptor()
        return {
            "run_id": self.run_id,
            "created_at": utc_now(),
            "harness_version": __version__,
            "runtime_revision": f"verified-state-harness/{__version__}",
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "task_revision": task_revision,
            "model_revision": model_revision,
            "controller": type(self.controller).__name__,
            "config": config,
            "config_hash": canonical_hash(config),
            "provenance_warnings": warnings,
            "provenance_complete": not warnings,
        }

    def _restore_run(self) -> None:
        self.manifest_body, self.manifest_hash = self.manifests.load_verified()
        self.run_id = str(self.manifest_body.get("run_id", ""))
        if not self.run_id:
            raise IntegrityError("run manifest missing run_id")
        current_config = self._config_descriptor()
        if self.manifest_body.get("config_hash") != canonical_hash(current_config):
            raise ResumeConflict("current goal/profile/security/tool configuration differs from run manifest")
        if self.task_revision is not None and self.task_revision != self.manifest_body.get("task_revision"):
            raise ResumeConflict("task revision differs from persisted run manifest")
        if self.model_revision is not None and self.model_revision != self.manifest_body.get("model_revision"):
            raise ResumeConflict("model revision differs from persisted run manifest")
        warnings = list(self.manifest_body.get("provenance_warnings", []))
        if self.require_complete_provenance and warnings:
            raise PersistenceError("persisted run has incomplete provenance: " + "; ".join(warnings))

        records = self.events.verify_chain()
        checkpoint = self.checkpoints.load_verified()
        if checkpoint is None:
            raise IntegrityError("resume requires a verified checkpoint")
        if checkpoint.get("run_id") != self.run_id:
            raise IntegrityError("checkpoint run_id mismatch")
        if checkpoint.get("manifest_hash") != self.manifest_hash:
            raise IntegrityError("checkpoint manifest hash mismatch")

        anchor = self.events.record_at(int(checkpoint.get("event_seq", 0)))
        if anchor is None or anchor.get("record_hash") != checkpoint.get("event_hash"):
            raise IntegrityError("checkpoint event anchor does not exist or hash does not match")
        if anchor.get("kind") != "state.snapshot":
            raise IntegrityError("checkpoint must anchor a state.snapshot event")
        if anchor.get("payload", {}).get("state_hash") != checkpoint.get("state_hash"):
            raise IntegrityError("checkpoint state hash does not match anchored event")

        replayed, replay_hash, replay_seq, replay_event_hash = self._replay_state_records(records)
        if replay_seq < int(checkpoint.get("event_seq", 0)):
            raise IntegrityError("event replay ended before checkpoint anchor")
        if replay_hash != canonical_hash(replayed.snapshot()):
            raise IntegrityError("replayed state hash is not canonical")

        checkpoint_state = HarnessState.from_snapshot(checkpoint["state"])
        checkpoint_hash = canonical_hash(checkpoint_state.snapshot())
        if checkpoint_hash != checkpoint.get("state_hash"):
            raise IntegrityError("checkpoint state payload hash mismatch")

        if replay_seq == int(checkpoint.get("event_seq", 0)):
            if replay_hash != checkpoint_hash:
                raise IntegrityError("event replay state differs from checkpoint state")
            self.state = checkpoint_state
        else:
            self.state = replayed
            self._write_checkpoint_from_anchor(replay_event_hash, replay_seq, reason="resume.event_ahead_recovery")

        self.metrics["run_id"] = self.run_id
        self.metrics["resume_count"] = 1
        prior_metrics = self._load_prior_metrics()
        self.elapsed_before_resume = float(prior_metrics.get("wall_seconds", 0.0))
        for key in self.metrics:
            if key in prior_metrics and key not in {"run_id", "completed", "resume_count"}:
                self.metrics[key] = prior_metrics[key]
        self.metrics["resume_count"] = int(prior_metrics.get("resume_count", 0)) + 1
        self.metrics["completed"] = self.state.completed
        self._validate_receipts_for_resume()

    def _load_prior_metrics(self) -> dict[str, Any]:
        path = self.run_dir / "metrics.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _wall_elapsed(self) -> float:
        return self.elapsed_before_resume + (monotonic() - self.started_at)

    def _persist_state(self, reason: str) -> None:
        snapshot = self.state.snapshot()
        state_hash = canonical_hash(snapshot)
        event_record = self.log("state.snapshot", {"state": snapshot, "state_hash": state_hash, "reason": reason})
        self._write_checkpoint_from_anchor(event_record["record_hash"], event_record["seq"], reason=reason)

    def _write_checkpoint_from_anchor(self, event_hash: str, event_seq: int, *, reason: str) -> None:
        self.checkpoints.save({
            "run_id": self.run_id,
            "manifest_hash": self.manifest_hash,
            "event_seq": event_seq,
            "event_hash": event_hash,
            "state_hash": canonical_hash(self.state.snapshot()),
            "state": self.state.snapshot(),
            "reason": reason,
        })

    def _replay_state_records(self, records):
        state = None
        state_hash = None
        seq = 0
        event_hash = ""
        for record in records:
            if record.get("kind") != "state.snapshot":
                continue
            payload = record.get("payload", {})
            candidate = HarnessState.from_snapshot(payload.get("state", {}))
            candidate_hash = canonical_hash(candidate.snapshot())
            if candidate_hash != payload.get("state_hash"):
                raise IntegrityError(f"state.snapshot hash mismatch at event seq {record.get('seq')}")
            state = candidate
            state_hash = candidate_hash
            seq = int(record.get("seq", 0))
            event_hash = str(record.get("record_hash", ""))
        if state is None:
            raise IntegrityError("event log contains no state.snapshot records")
        return state, state_hash, seq, event_hash

    def _receipt_id(self, call: ToolCall) -> str:
        return canonical_hash({"tool": call.tool, "args": call.args})

    def _execute_tool_durable(self, call: ToolCall):
        spec = self.actions.tools.get(call.tool)
        if spec is None or spec.idempotent:
            return self.actions.execute(call), None, False

        receipt_id = self._receipt_id(call)
        existing = self.receipts.load(receipt_id)
        if existing:
            status = existing.get("status")
            if status == "COMMITTED":
                self.metrics["receipt_deduplications"] += 1
                return ToolResult.from_dict(existing["result"]), receipt_id, True
            if status == "PREPARED":
                self.metrics["ambiguous_side_effects"] += 1
                raise ResumeConflict(f"non-idempotent action has PREPARED-only receipt and is ambiguous: {call.tool}")
            raise IntegrityError(f"unknown receipt status: {status}")

        self.receipts.prepare(receipt_id, {"run_id": self.run_id, "tool": call.tool, "args": call.args})
        result = self.actions.execute(call)
        self.receipts.commit(receipt_id, {"run_id": self.run_id, "tool": call.tool, "args": call.args, "result": result.to_dict()})
        return result, receipt_id, False

    def _validate_receipts_for_resume(self) -> None:
        ambiguous = self.receipts.prepared_receipts()
        if ambiguous:
            self.metrics["ambiguous_side_effects"] += len(ambiguous)
            raise ResumeConflict("resume blocked by PREPARED-only non-idempotent side-effect receipt(s)")

from __future__ import annotations

from enum import Enum
from pathlib import Path
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

    @staticmethod
    def _source_hash(obj: Any) -> str | None:
        try:
            target = obj if inspect.isclass(obj) or inspect.isfunction(obj) else type(obj)
            source = inspect.getsource(target)
        except (OSError, TypeError):
            return None
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    @classmethod
    def _source_descriptor(cls, obj: Any) -> dict[str, Any]:
        typ = obj if inspect.isclass(obj) else type(obj)
        mro = []
        for base in getattr(typ, "__mro__", (typ,)):
            module = getattr(base, "__module__", "")
            if module == "builtins":
                continue
            mro.append({
                "class": f"{module}.{getattr(base, '__qualname__', getattr(base, '__name__', 'unknown'))}",
                "source_hash": cls._source_hash(base),
            })
        return {
            "class": f"{typ.__module__}.{typ.__qualname__}",
            "source_hash": cls._source_hash(obj),
            "mro": mro,
        }

    @classmethod
    def _stable_value(cls, value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, Path):
            return {"path": str(value.expanduser().resolve())}
        if isinstance(value, Enum):
            return {
                "enum": f"{type(value).__module__}.{type(value).__qualname__}",
                "value": value.value,
            }
        if isinstance(value, bytes):
            return {"bytes_sha256": hashlib.sha256(value).hexdigest(), "size": len(value)}
        if isinstance(value, dict):
            return {
                str(k): cls._stable_value(v)
                for k, v in sorted(value.items(), key=lambda item: str(item[0]))
            }
        if isinstance(value, (list, tuple)):
            return [cls._stable_value(v) for v in value]
        if isinstance(value, (set, frozenset)):
            items = [cls._stable_value(v) for v in value]
            return sorted(
                items,
                key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), default=str),
            )
        if inspect.isfunction(value) or inspect.ismethod(value):
            return cls._callable_descriptor(value)
        return {"type": f"{type(value).__module__}.{type(value).__qualname__}"}

    @classmethod
    def _callable_descriptor(cls, fn: Any) -> dict[str, Any] | None:
        if fn is None:
            return None
        descriptor: dict[str, Any] = {
            "callable": f"{getattr(fn, '__module__', type(fn).__module__)}.{getattr(fn, '__qualname__', type(fn).__qualname__)}",
            "source_hash": cls._source_hash(fn),
        }
        defaults = getattr(fn, "__defaults__", None)
        if defaults:
            descriptor["defaults"] = cls._stable_value(defaults)
        kwdefaults = getattr(fn, "__kwdefaults__", None)
        if kwdefaults:
            descriptor["kwdefaults"] = cls._stable_value(kwdefaults)
        closure = getattr(fn, "__closure__", None)
        freevars = getattr(getattr(fn, "__code__", None), "co_freevars", ())
        if closure:
            descriptor["closure"] = {
                name: cls._stable_value(cell.cell_contents)
                for name, cell in zip(freevars, closure)
            }
        return descriptor

    @classmethod
    def _backend_descriptor(cls, backend: Any) -> dict[str, Any] | None:
        if backend is None:
            return None
        descriptor = cls._source_descriptor(backend)
        descriptor["name"] = getattr(backend, "name", type(backend).__name__)
        config: dict[str, Any] = {}
        for attr in (
            "network_policy",
            "inherit_env",
            "workspace_writable",
            "read_only_paths",
            "runtime_read_only_paths",
        ):
            if hasattr(backend, attr):
                config[attr] = cls._stable_value(getattr(backend, attr))
        outcomes = getattr(backend, "outcomes", None)
        if isinstance(outcomes, dict):
            config["test_outcomes"] = cls._stable_value({
                str(k): {
                    "returncode": getattr(v, "returncode", None),
                    "stdout": getattr(v, "stdout", None),
                    "stderr": getattr(v, "stderr", None),
                    "timed_out": getattr(v, "timed_out", None),
                }
                for k, v in outcomes.items()
            })
        descriptor["config"] = config
        return descriptor

    def _capability_policy_descriptor(self) -> dict[str, list[str]]:
        return {
            principal.value: sorted(capability.value for capability in capabilities)
            for principal, capabilities in sorted(
                self.capability_policy.grants.items(),
                key=lambda item: item[0].value,
            )
        }

    def _security_descriptor(self) -> dict[str, Any]:
        return {
            "strict_layout": self.security_config.strict_layout,
            "strict_tool_isolation": self.security_config.strict_tool_isolation,
            "network_policy": self.security_config.network_policy,
            "require_sealed_oracle": self.security_config.require_sealed_oracle,
            "allow_test_attestation": self.security_config.allow_test_attestation,
            "capability_policy": self._capability_policy_descriptor(),
        }

    def _controller_descriptor(self) -> dict[str, Any]:
        descriptor = self._source_descriptor(self.controller)
        decisions = getattr(self.controller, "decisions", None)
        if isinstance(decisions, list):
            script = [
                {
                    "kind": getattr(decision, "kind", None),
                    "payload": self._stable_value(getattr(decision, "payload", None)),
                }
                for decision in decisions
            ]
            descriptor["decision_script_hash"] = canonical_hash(script)
            descriptor["decision_count"] = len(script)

        adapter = getattr(self.controller, "model", None)
        if adapter is not None:
            descriptor["adapter"] = self._source_descriptor(adapter)
            command = getattr(adapter, "command", None)
            if isinstance(command, str):
                descriptor["adapter"]["command_hash"] = hashlib.sha256(command.encode("utf-8")).hexdigest()
            timeout_seconds = getattr(adapter, "timeout_seconds", None)
            if timeout_seconds is not None:
                descriptor["adapter"]["timeout_seconds"] = timeout_seconds
        return descriptor

    def _tool_descriptors(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "side_effect": spec.side_effect.value,
                "idempotent": bool(spec.idempotent),
                "permission": spec.permission,
                "failure_modes": list(spec.failure_modes),
                "provenance": dict(spec.provenance),
                "handler": self._callable_descriptor(spec.handler),
                "precondition": self._callable_descriptor(spec.precondition),
                "postcondition": self._callable_descriptor(spec.postcondition),
                "backend": self._backend_descriptor(spec.execution_backend),
                "execution_workspace": (
                    str(Path(spec.execution_workspace).expanduser().resolve())
                    if spec.execution_workspace is not None else None
                ),
            }
            for name, spec in sorted(self.actions.tools.items())
        ]

    def _oracle_descriptor(self) -> dict[str, Any]:
        oracle = self.oracle
        descriptor = self._source_descriptor(oracle)
        descriptor.update({
            "name": getattr(oracle, "name", type(oracle).__name__),
            "oracle_id": getattr(oracle, "oracle_id", None),
            "sealed": bool(getattr(oracle, "is_sealed", False)),
            "seal_manifest_hash": getattr(getattr(oracle, "bundle", None), "manifest_hash", None),
            "backend": self._backend_descriptor(getattr(oracle, "backend", None)),
            "require_filesystem_isolation": bool(getattr(oracle, "require_filesystem_isolation", False)),
            "allow_test_attestation": bool(getattr(oracle, "allow_test_attestation", False)),
        })
        commands = getattr(oracle, "commands", None)
        if isinstance(commands, list):
            descriptor["command_hashes"] = [
                hashlib.sha256(str(command).encode("utf-8")).hexdigest()
                for command in commands
            ]
            descriptor["command_count"] = len(commands)
        timeout_seconds = getattr(oracle, "timeout_seconds", None)
        if timeout_seconds is not None:
            descriptor["timeout_seconds"] = timeout_seconds
        predicate = getattr(oracle, "predicate", None)
        if predicate is not None:
            descriptor["predicate"] = self._callable_descriptor(predicate)
        reason = getattr(oracle, "reason", None)
        if isinstance(reason, str):
            descriptor["reason_hash"] = hashlib.sha256(reason.encode("utf-8")).hexdigest()
        return descriptor

    def _config_descriptor(self) -> dict[str, Any]:
        verifiers = list(getattr(self.verifiers, "verifiers", []))
        return {
            "goal": self._goal_descriptor(),
            "profile": {
                "name": self.profile.name,
                "class": f"{type(self.profile).__module__}.{type(self.profile).__qualname__}",
                "source_hash": self._source_hash(self.profile),
                "minimum_verification_level": int(self.profile.minimum_verification_level()),
                "verifiers": [
                    {
                        "class": f"{type(v).__module__}.{type(v).__qualname__}",
                        "source_hash": self._source_hash(v),
                    }
                    for v in verifiers
                ],
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
            "oracle": self._oracle_descriptor(),
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
            if type(self.controller).__name__ != "LLMController"
            else "UNSPECIFIED"
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
            raise IntegrityError("checkpoint event anchor is not a state snapshot")
        anchor_payload = anchor.get("payload", {})
        if anchor_payload.get("manifest_hash") != self.manifest_hash:
            raise IntegrityError("state snapshot manifest hash mismatch")
        if anchor_payload.get("state_hash") != checkpoint.get("state_hash"):
            raise IntegrityError("checkpoint state hash disagrees with anchored event")
        if canonical_hash(anchor_payload.get("state")) != checkpoint.get("state_hash"):
            raise IntegrityError("anchored event state payload hash mismatch")

        latest = self.events.latest_state_snapshot()
        if latest is None:
            raise IntegrityError("event log contains no state snapshot")
        latest_payload = latest.get("payload", {})
        if latest_payload.get("manifest_hash") != self.manifest_hash:
            raise IntegrityError("latest state snapshot manifest hash mismatch")
        if latest_payload.get("state_hash") != canonical_hash(latest_payload.get("state")):
            raise IntegrityError("latest state snapshot payload hash mismatch")
        if int(latest["seq"]) < int(anchor["seq"]):
            raise IntegrityError("event log is behind checkpoint")

        if int(latest["seq"]) > int(anchor["seq"]):
            self.state = HarnessState.from_snapshot(latest_payload["state"])
            runtime_meta = dict(latest_payload.get("runtime_meta", {}))
            self.checkpoints.save(
                self.state.snapshot(), run_id=self.run_id, manifest_hash=self.manifest_hash,
                event_seq=int(latest["seq"]), event_hash=str(latest["record_hash"]),
                runtime_meta=runtime_meta,
            )
        else:
            self.state = HarnessState.from_snapshot(checkpoint["state"])
            runtime_meta = dict(checkpoint.get("runtime_meta", {}))

        persisted_metrics = runtime_meta.get("metrics")
        if isinstance(persisted_metrics, dict):
            self.metrics.update(persisted_metrics)
        self.metrics["run_id"] = self.run_id
        self.metrics["resume_count"] = int(self.metrics.get("resume_count", 0)) + 1
        self.elapsed_before_resume = float(runtime_meta.get("elapsed_wall_seconds", 0.0) or 0.0)

    def _wall_elapsed(self) -> float:
        return self.elapsed_before_resume + (monotonic() - self.started_at)

    def _runtime_meta(self) -> dict[str, Any]:
        return {
            "metrics": dict(self.metrics),
            "elapsed_wall_seconds": self._wall_elapsed(),
        }

    def _persist_state(self, reason: str) -> dict[str, Any]:
        snapshot = self.state.snapshot()
        state_hash = canonical_hash(snapshot)
        runtime_meta = self._runtime_meta()
        record = self.events.append_event(Event(
            "state.snapshot",
            {
                "reason": reason,
                "state_hash": state_hash,
                "state": snapshot,
                "manifest_hash": self.manifest_hash,
                "runtime_meta": runtime_meta,
            },
            self.state.step,
        ))
        self.checkpoints.save(
            snapshot,
            run_id=self.run_id,
            manifest_hash=self.manifest_hash,
            event_seq=int(record["seq"]),
            event_hash=str(record["record_hash"]),
            runtime_meta=runtime_meta,
        )
        return record

    def replay_state(self) -> HarnessState:
        latest_state: dict[str, Any] | None = None
        last_step = -1
        for record in self.events.verify_chain():
            if record.get("kind") != "state.snapshot":
                continue
            payload = record.get("payload", {})
            state = payload.get("state")
            if not isinstance(state, dict):
                raise IntegrityError("state snapshot event has no state object")
            if payload.get("manifest_hash") != self.manifest_hash:
                raise IntegrityError("replay encountered a state snapshot from another manifest")
            actual = canonical_hash(state)
            if payload.get("state_hash") != actual:
                raise IntegrityError("replayed state hash mismatch")
            step = int(state.get("step", -1))
            if step < last_step:
                raise IntegrityError("state snapshot step regressed during replay")
            last_step = step
            latest_state = state
        if latest_state is None:
            raise IntegrityError("event log contains no state snapshot")
        return HarnessState.from_snapshot(latest_state)

    def replay_state_hash(self) -> str:
        return canonical_hash(self.replay_state().snapshot())

    @staticmethod
    def _tool_result_to_dict(result: ToolResult) -> dict[str, Any]:
        return {
            "ok": result.ok,
            "output": result.output,
            "error": result.error,
            "approval_required": result.approval_required,
            "security_violation": result.security_violation,
            "isolation": result.isolation,
        }

    @staticmethod
    def _tool_result_from_dict(raw: dict[str, Any]) -> ToolResult:
        return ToolResult(
            ok=bool(raw.get("ok")),
            output=raw.get("output"),
            error=raw.get("error"),
            approval_required=bool(raw.get("approval_required", False)),
            security_violation=bool(raw.get("security_violation", False)),
            isolation=raw.get("isolation"),
        )

    def _execute_tool_durable(self, call: ToolCall) -> tuple[ToolResult, str | None, bool]:
        spec = self.actions.tools.get(call.tool)
        if spec is None or spec.idempotent:
            return self.actions.execute(call), None, False

        action_id = self.receipts.action_id(
            run_id=self.run_id, step=self.state.step, tool=call.tool, args=call.args
        )
        receipt = self.receipts.load(action_id)
        if receipt is not None:
            if receipt.get("status") == "committed":
                self.metrics["receipt_deduplications"] += 1
                self.log("tool.receipt.deduplicated", {"action_id": action_id, "tool": call.tool})
                return self._tool_result_from_dict(receipt["result"]), action_id, True
            if receipt.get("status") == "prepared":
                self.metrics["ambiguous_side_effects"] += 1
                raise ResumeConflict(
                    f"non-idempotent action {action_id} is PREPARED without COMMITTED result; "
                    "automatic replay is blocked because the external effect is ambiguous"
                )
            raise IntegrityError(f"invalid receipt status: {receipt.get('status')}")

        self.receipts.prepare(
            action_id=action_id, run_id=self.run_id, step=self.state.step, tool=call.tool, args=call.args
        )
        self.log("tool.receipt.prepared", {"action_id": action_id, "tool": call.tool})
        result = self.actions.execute(call)
        normalized = json.loads(json.dumps(self._tool_result_to_dict(result), ensure_ascii=False, default=str))
        self.receipts.commit(action_id=action_id, result=normalized)
        stable_result = self._tool_result_from_dict(normalized)
        self.log("tool.receipt.committed", {"action_id": action_id, "tool": call.tool, "ok": stable_result.ok})
        return stable_result, action_id, False

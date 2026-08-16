from __future__ import annotations

import json

from .storage import IntegrityError, PersistenceError, ResumeConflict


class RuntimeControllerStateMixin:
    """Durable checkpoint protocol for stateful controllers.

    Controllers are normally expected to be pure functions of goal/state/context.
    A controller that keeps a local cursor or other decision state may opt into
    resume by implementing both `snapshot_state()` and `restore_state(raw)`.
    """

    def _controller_descriptor(self):
        descriptor = super()._controller_descriptor()
        snapshotter = getattr(self.controller, "snapshot_state", None)
        restorer = getattr(self.controller, "restore_state", None)
        has_snapshot = callable(snapshotter)
        has_restore = callable(restorer)
        if has_snapshot != has_restore:
            raise PersistenceError(
                "controller checkpoint protocol is incomplete; snapshot_state and restore_state must be provided together"
            )
        descriptor["runtime_state_protocol"] = "checkpoint_v1" if has_snapshot else "stateless_declared_by_interface"
        return descriptor

    def _controller_runtime_state(self):
        snapshotter = getattr(self.controller, "snapshot_state", None)
        restorer = getattr(self.controller, "restore_state", None)
        if not callable(snapshotter) and not callable(restorer):
            return None
        if not callable(snapshotter) or not callable(restorer):
            raise PersistenceError("controller checkpoint protocol is incomplete")
        raw = snapshotter()
        if not isinstance(raw, dict):
            raise PersistenceError("controller snapshot_state() must return a JSON object")
        try:
            # Strict JSON round-trip prevents process-local Python objects from
            # silently becoming lossy string representations in checkpoints.
            return json.loads(json.dumps(raw, ensure_ascii=False, sort_keys=True))
        except (TypeError, ValueError) as exc:
            raise PersistenceError(f"controller runtime state is not JSON-serializable: {exc}") from exc

    def _runtime_meta(self):
        meta = super()._runtime_meta()
        meta["controller_state"] = self._controller_runtime_state()
        return meta

    def _restore_run(self) -> None:
        super()._restore_run()
        checkpoint = self.checkpoints.load_verified()
        if checkpoint is None:
            raise IntegrityError("resume requires controller state checkpoint")
        runtime_meta = dict(checkpoint.get("runtime_meta", {}))
        restorer = getattr(self.controller, "restore_state", None)
        snapshotter = getattr(self.controller, "snapshot_state", None)
        protocol = callable(restorer) and callable(snapshotter)
        has_key = "controller_state" in runtime_meta
        persisted = runtime_meta.get("controller_state")

        if protocol:
            if not has_key or not isinstance(persisted, dict):
                raise IntegrityError("checkpoint is missing state for checkpointable controller")
            try:
                restorer(persisted)
            except Exception as exc:
                raise IntegrityError(
                    f"controller runtime state could not be restored: {type(exc).__name__}: {exc}"
                ) from exc
        elif has_key and persisted is not None:
            raise ResumeConflict(
                "persisted run contains controller state but current controller has no restore protocol"
            )

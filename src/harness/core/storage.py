from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import stat
import tempfile
from typing import Any


class PersistenceError(RuntimeError):
    pass


class IntegrityError(PersistenceError):
    pass


class ResumeConflict(PersistenceError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_text(path: str | Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        finally:
            raise


def atomic_write_json(path: str | Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n")


def _seal_body(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "body": body,
        "integrity": {
            "algorithm": "sha256",
            "sha256": canonical_hash(body),
        },
    }


def _verify_envelope(raw: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or not isinstance(raw.get("body"), dict):
        raise IntegrityError(f"{label} envelope is malformed")
    integrity = raw.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
        raise IntegrityError(f"{label} integrity metadata is missing")
    expected = integrity.get("sha256")
    actual = canonical_hash(raw["body"])
    if not isinstance(expected, str) or expected != actual:
        raise IntegrityError(f"{label} integrity hash mismatch")
    return raw["body"]


class RunManifestStore:
    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def create(self, manifest: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if self.path.exists():
            raise ResumeConflict("run manifest already exists; use resume instead of starting a new run")
        body = dict(manifest)
        body["schema_version"] = self.SCHEMA_VERSION
        manifest_hash = canonical_hash(body)
        atomic_write_json(self.path, _seal_body(body))
        return body, manifest_hash

    def load_verified(self) -> tuple[dict[str, Any], str]:
        if not self.path.exists():
            raise PersistenceError("run manifest is missing")
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrityError(f"run manifest cannot be decoded: {exc}") from exc
        body = _verify_envelope(raw, label="run manifest")
        if body.get("schema_version") != self.SCHEMA_VERSION:
            raise IntegrityError(f"unsupported run manifest schema: {body.get('schema_version')}")
        return body, canonical_hash(body)


class CheckpointStore:
    SCHEMA_VERSION = 2

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        snapshot: dict[str, Any],
        *,
        run_id: str = "",
        manifest_hash: str = "",
        event_seq: int = 0,
        event_hash: str = "",
        runtime_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = {
            "schema_version": self.SCHEMA_VERSION,
            "run_id": run_id,
            "manifest_hash": manifest_hash,
            "event_seq": int(event_seq),
            "event_hash": event_hash,
            "state_hash": canonical_hash(snapshot),
            "state": snapshot,
            "runtime_meta": dict(runtime_meta or {}),
        }
        atomic_write_json(self.path, _seal_body(body))
        return body

    def load_verified(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrityError(f"checkpoint cannot be decoded: {exc}") from exc
        body = _verify_envelope(raw, label="checkpoint")
        if body.get("schema_version") != self.SCHEMA_VERSION:
            raise IntegrityError(f"unsupported checkpoint schema: {body.get('schema_version')}")
        state = body.get("state")
        if not isinstance(state, dict):
            raise IntegrityError("checkpoint state is missing")
        if body.get("state_hash") != canonical_hash(state):
            raise IntegrityError("checkpoint state hash mismatch")
        return body

    def load(self) -> dict[str, Any] | None:
        body = self.load_verified()
        return None if body is None else body["state"]


class ReceiptStore:
    """Durable at-most-once receipts for non-idempotent tool calls.

    PREPARED means execution may or may not have happened.  A resumed run must not
    execute it again automatically.  COMMITTED contains the recorded ToolResult
    and may be replayed without invoking the tool handler.
    """

    SCHEMA_VERSION = 1

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def action_id(*, run_id: str, step: int, tool: str, args: dict[str, Any]) -> str:
        return canonical_hash({"run_id": run_id, "step": int(step), "tool": tool, "args": args})

    def _path(self, action_id: str) -> Path:
        if not action_id or any(ch not in "0123456789abcdef" for ch in action_id):
            raise ValueError("invalid receipt action id")
        return self.root / f"{action_id}.json"

    def _write(self, body: dict[str, Any]) -> None:
        body = dict(body)
        body["schema_version"] = self.SCHEMA_VERSION
        atomic_write_json(self._path(body["action_id"]), _seal_body(body))

    def load(self, action_id: str) -> dict[str, Any] | None:
        path = self._path(action_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrityError(f"receipt cannot be decoded: {exc}") from exc
        body = _verify_envelope(raw, label="receipt")
        if body.get("schema_version") != self.SCHEMA_VERSION:
            raise IntegrityError("unsupported receipt schema")
        if body.get("action_id") != action_id:
            raise IntegrityError("receipt action id mismatch")
        return body

    def for_step(self, *, run_id: str, step: int) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json")):
            body = self.load(path.stem)
            if body and body.get("run_id") == run_id and int(body.get("step", -1)) == int(step):
                found.append(body)
        return found

    def prepare(self, *, action_id: str, run_id: str, step: int, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        existing = self.load(action_id)
        if existing is not None:
            return existing
        conflicts = self.for_step(run_id=run_id, step=step)
        if conflicts:
            raise ResumeConflict(
                f"non-idempotent action conflict at step {step}: existing receipt {conflicts[0]['action_id']}"
            )
        body = {
            "action_id": action_id,
            "run_id": run_id,
            "step": int(step),
            "tool": tool,
            "args_hash": canonical_hash(args),
            "status": "prepared",
            "result": None,
        }
        self._write(body)
        return body

    def commit(self, *, action_id: str, result: dict[str, Any]) -> dict[str, Any]:
        body = self.load(action_id)
        if body is None:
            raise IntegrityError("cannot commit missing receipt")
        if body.get("status") == "committed":
            return body
        if body.get("status") != "prepared":
            raise IntegrityError(f"invalid receipt status: {body.get('status')}")
        body = dict(body)
        body["status"] = "committed"
        body["result"] = result
        self._write(body)
        return body


class ArtifactStore:
    """Content-addressed artifacts with path-only resolution and verified reads."""

    PREFIX = "artifact://"

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _token_from_ref(cls, ref: str) -> str:
        if not isinstance(ref, str) or not ref.startswith(cls.PREFIX):
            raise ValueError("invalid artifact reference")
        token = ref[len(cls.PREFIX):]
        if not token or token != Path(token).name:
            raise ValueError("artifact reference must be an opaque basename token")
        return token

    @classmethod
    def digest_from_ref(cls, ref: str) -> str:
        token = cls._token_from_ref(ref)
        if len(token) < 65 or token[64] != "_":
            raise IntegrityError("artifact reference is not content-addressed")
        digest = token[:64]
        if any(ch not in "0123456789abcdef" for ch in digest):
            raise IntegrityError("artifact reference digest is malformed")
        return digest

    @classmethod
    def resolve_ref_path(cls, root: str | Path, ref: str) -> Path:
        """Resolve path confinement only; no content-integrity guarantee is implied."""
        root = Path(root).resolve()
        token = cls._token_from_ref(ref)
        cls.digest_from_ref(ref)
        path = root / token
        try:
            path.resolve(strict=False).relative_to(root)
        except ValueError as exc:
            raise ValueError("artifact reference escapes artifact root") from exc
        return path

    @classmethod
    def verified_read_bytes_from_root(cls, root: str | Path, ref: str) -> bytes:
        """Open once, hash the exact read buffer, and return that same buffer."""
        root = Path(root).resolve()
        token = cls._token_from_ref(ref)
        expected = cls.digest_from_ref(ref)

        dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            dir_fd = os.open(root, dir_flags)
        except OSError as exc:
            raise IntegrityError(f"artifact root cannot be opened: {exc}") from exc

        file_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            try:
                fd = os.open(token, file_flags, dir_fd=dir_fd)
            except FileNotFoundError as exc:
                raise IntegrityError("artifact file is missing") from exc
            except OSError as exc:
                raise IntegrityError(f"artifact file cannot be opened safely: {exc}") from exc
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode):
                    raise IntegrityError("artifact is not a regular file")
                chunks: list[bytes] = []
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                raw = b"".join(chunks)
            finally:
                os.close(fd)
        finally:
            os.close(dir_fd)

        if hashlib.sha256(raw).hexdigest() != expected:
            raise IntegrityError("artifact content hash mismatch")
        return raw

    def resolve(self, ref: str) -> Path:
        return self.resolve_ref_path(self.root, ref)

    def exists(self, ref: str) -> bool:
        try:
            return self.resolve(ref).is_file()
        except ValueError:
            return False

    def verified_read_bytes(self, ref: str) -> bytes:
        return self.verified_read_bytes_from_root(self.root, ref)

    def verified_read_text(self, ref: str, *, encoding: str = "utf-8") -> str:
        raw = self.verified_read_bytes(ref)
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError as exc:
            raise IntegrityError(f"artifact text cannot be decoded as {encoding}: {exc}") from exc

    def verified_read_json(self, ref: str) -> Any:
        raw = self.verified_read_bytes(ref)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntegrityError(f"artifact JSON cannot be decoded: {exc}") from exc

    def put_text(self, name: str, content: str) -> str:
        digest = hashlib.sha256(content.encode()).hexdigest()
        safe_name = Path(name).name
        token = f"{digest}_{safe_name}"
        p = self.root / token
        atomic_write_text(p, content)
        return f"{self.PREFIX}{token}"

    def put_json(self, name: str, value: Any) -> str:
        return self.put_text(name, json.dumps(value, ensure_ascii=False, indent=2, default=str))

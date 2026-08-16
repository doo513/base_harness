from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import os
import stat
import tempfile


class PersistenceError(RuntimeError):
    pass


class IntegrityError(PersistenceError):
    pass


class ResumeConflict(PersistenceError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def atomic_write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        try:
            dir_fd = os.open(target.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def atomic_write_json(path: str | Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n")


class RunManifestStore:
    def __init__(self, path):
        self.path = Path(path)

    def create(self, body: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if self.path.exists():
            raise ResumeConflict("run manifest already exists")
        normalized = json.loads(json.dumps(body, ensure_ascii=False, default=str))
        digest = canonical_hash(normalized)
        atomic_write_json(self.path, {"manifest": normalized, "manifest_hash": digest})
        return normalized, digest

    def load_verified(self) -> tuple[dict[str, Any], str]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrityError(f"run manifest cannot be read: {exc}") from exc
        body = raw.get("manifest")
        digest = raw.get("manifest_hash")
        if not isinstance(body, dict) or not isinstance(digest, str):
            raise IntegrityError("run manifest envelope is malformed")
        actual = canonical_hash(body)
        if actual != digest:
            raise IntegrityError("run manifest hash mismatch")
        return body, digest


class CheckpointStore:
    def __init__(self, path):
        self.path = Path(path)

    def save(
        self,
        state: dict[str, Any],
        *,
        run_id: str,
        manifest_hash: str,
        event_seq: int,
        event_hash: str,
        runtime_meta: dict[str, Any] | None = None,
    ) -> None:
        envelope = {
            "version": 1,
            "run_id": run_id,
            "manifest_hash": manifest_hash,
            "event_seq": int(event_seq),
            "event_hash": event_hash,
            "state_hash": canonical_hash(state),
            "state": state,
            "runtime_meta": dict(runtime_meta or {}),
        }
        envelope["envelope_hash"] = canonical_hash(envelope)
        atomic_write_json(self.path, envelope)

    def load_verified(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrityError(f"checkpoint cannot be read: {exc}") from exc
        expected = raw.pop("envelope_hash", None)
        if not isinstance(expected, str):
            raise IntegrityError("checkpoint envelope hash is missing")
        if canonical_hash(raw) != expected:
            raise IntegrityError("checkpoint envelope hash mismatch")
        state = raw.get("state")
        if not isinstance(state, dict):
            raise IntegrityError("checkpoint state is missing")
        if raw.get("state_hash") != canonical_hash(state):
            raise IntegrityError("checkpoint state hash mismatch")
        raw["envelope_hash"] = expected
        return raw


class ReceiptStore:
    """Durable at-most-once receipts for non-idempotent tool calls.

    PREPARED means execution may or may not have happened. A resumed run must not
    execute it again automatically. COMMITTED contains the recorded ToolResult
    and may be replayed without invoking the tool handler.
    """

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def action_id(*, run_id: str, step: int, tool: str, args: dict[str, Any]) -> str:
        return canonical_hash({"run_id": run_id, "step": int(step), "tool": tool, "args": args})

    def _path(self, action_id: str) -> Path:
        if not action_id or any(ch not in "0123456789abcdef" for ch in action_id):
            raise ValueError("invalid action id")
        return self.root / f"{action_id}.json"

    def load(self, action_id: str) -> dict[str, Any] | None:
        path = self._path(action_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrityError(f"receipt cannot be read: {exc}") from exc
        expected = raw.pop("receipt_hash", None)
        if not isinstance(expected, str) or canonical_hash(raw) != expected:
            raise IntegrityError("receipt hash mismatch")
        raw["receipt_hash"] = expected
        return raw

    def prepare(self, *, action_id: str, run_id: str, step: int, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        existing = self.load(action_id)
        if existing is not None:
            return existing
        body = {
            "action_id": action_id,
            "status": "prepared",
            "run_id": run_id,
            "step": int(step),
            "tool": tool,
            "args_hash": canonical_hash(args),
        }
        body["receipt_hash"] = canonical_hash(body)
        atomic_write_json(self._path(action_id), body)
        return body

    def commit(self, *, action_id: str, result: dict[str, Any]) -> dict[str, Any]:
        current = self.load(action_id)
        if current is None:
            raise IntegrityError("cannot commit receipt that was not prepared")
        if current.get("status") == "committed":
            return current
        if current.get("status") != "prepared":
            raise IntegrityError("invalid receipt status")
        body = {k: v for k, v in current.items() if k != "receipt_hash"}
        body["status"] = "committed"
        body["result"] = result
        body["receipt_hash"] = canonical_hash(body)
        atomic_write_json(self._path(action_id), body)
        return body


class ArtifactStore:
    """Content-addressed artifact storage with single-buffer verified reads.

    `resolve_ref_path()` performs only ref/path confinement and existence checks.
    It does not make a Path a verified content object. `verified_read_bytes()`
    opens one regular file, reads one logical buffer, verifies the SHA-256 over
    that exact buffer, and returns the same buffer to the caller.
    """

    PREFIX = "artifact://"

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _token_from_ref(cls, ref: str) -> str:
        if not isinstance(ref, str) or not ref.startswith(cls.PREFIX):
            raise ValueError("invalid artifact reference")
        token = ref[len(cls.PREFIX):]
        if not token or Path(token).name != token:
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
        root_path = Path(root).resolve()
        token = cls._token_from_ref(ref)
        cls.digest_from_ref(ref)
        path = root_path / token
        # Token validation already forbids separators. This resolved-path check
        # additionally documents and enforces the artifact-root confinement.
        try:
            path.resolve(strict=False).relative_to(root_path)
        except ValueError as exc:
            raise ValueError("artifact reference escapes artifact root") from exc
        if not path.exists():
            raise IntegrityError("artifact file is missing")
        return path

    @classmethod
    def verified_read_bytes_from_root(cls, root: str | Path, ref: str) -> bytes:
        root_path = Path(root).resolve()
        token = cls._token_from_ref(ref)
        expected = cls.digest_from_ref(ref)

        dir_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            dir_flags |= os.O_DIRECTORY
        if hasattr(os, "O_CLOEXEC"):
            dir_flags |= os.O_CLOEXEC
        try:
            dir_fd = os.open(root_path, dir_flags)
        except OSError as exc:
            raise IntegrityError(f"artifact root cannot be opened: {exc}") from exc

        file_flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            file_flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW

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
            self.resolve(ref)
            return True
        except (ValueError, IntegrityError):
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
        text = self.verified_read_text(ref)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise IntegrityError(f"artifact JSON cannot be decoded: {exc}") from exc

    def put_text(self, name: str, content: str) -> str:
        digest = hashlib.sha256(content.encode()).hexdigest()
        safe_name = Path(name).name
        token = f"{digest}_{safe_name}"
        atomic_write_text(self.root / token, content)
        return f"{self.PREFIX}{token}"

    def put_json(self, name: str, value: Any) -> str:
        content = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n"
        return self.put_text(name, content)

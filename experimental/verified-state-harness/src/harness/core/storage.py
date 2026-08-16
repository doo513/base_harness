from pathlib import Path
import json
import hashlib
from typing import Any

class CheckpointStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, snapshot: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.path)

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))

class ArtifactStore:
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
    def resolve_ref_path(cls, root: str | Path, ref: str) -> Path:
        root = Path(root).resolve()
        token = cls._token_from_ref(ref)
        path = (root / token).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("artifact reference escapes artifact root") from exc
        return path

    def resolve(self, ref: str) -> Path:
        return self.resolve_ref_path(self.root, ref)

    def exists(self, ref: str) -> bool:
        try:
            return self.resolve(ref).is_file()
        except ValueError:
            return False

    def put_text(self, name: str, content: str) -> str:
        digest = hashlib.sha256(content.encode()).hexdigest()
        safe_name = Path(name).name
        token = f"{digest}_{safe_name}"
        p = self.root / token
        p.write_text(content, encoding="utf-8")
        return f"{self.PREFIX}{token}"

    def put_json(self, name: str, value: Any) -> str:
        return self.put_text(name, json.dumps(value, ensure_ascii=False, indent=2, default=str))

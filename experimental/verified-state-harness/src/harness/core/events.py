from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class Event:
    kind: str
    payload: dict[str, Any]
    step: int
    ts: str = ""

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = utc_now()

class JsonlLog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, payload: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

class EventLog(JsonlLog):
    def append_event(self, event: Event) -> None:
        super().append(asdict(event))

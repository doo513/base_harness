from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import os
from typing import Any

from .storage import IntegrityError, canonical_hash


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
            f.flush()
            os.fsync(f.fileno())


class EventLog(JsonlLog):
    GENESIS_HASH = "0" * 64

    def __init__(self, path):
        super().__init__(path)
        records = self.verify_chain() if self.path.stat().st_size else []
        if records:
            self._last_seq = int(records[-1]["seq"])
            self._last_hash = str(records[-1]["record_hash"])
        else:
            self._last_seq = 0
            self._last_hash = self.GENESIS_HASH

    @staticmethod
    def _record_body(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "seq": record["seq"],
            "prev_hash": record["prev_hash"],
            "kind": record["kind"],
            "payload": record["payload"],
            "step": record["step"],
            "ts": record["ts"],
        }

    def read_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise IntegrityError(f"event log cannot be read: {exc}") from exc
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise IntegrityError(f"event log malformed at line {line_no}: {exc}") from exc
            if not isinstance(record, dict):
                raise IntegrityError(f"event log record {line_no} is not an object")
            records.append(record)
        return records

    def verify_chain(self) -> list[dict[str, Any]]:
        records = self.read_records()
        previous = self.GENESIS_HASH
        expected_seq = 1
        for idx, record in enumerate(records, start=1):
            required = {"seq", "prev_hash", "kind", "payload", "step", "ts", "record_hash"}
            if not required.issubset(record):
                raise IntegrityError(f"event log record {idx} missing integrity fields")
            if int(record["seq"]) != expected_seq:
                raise IntegrityError(f"event log sequence mismatch at record {idx}")
            if record["prev_hash"] != previous:
                raise IntegrityError(f"event log chain mismatch at record {idx}")
            actual = canonical_hash(self._record_body(record))
            if record["record_hash"] != actual:
                raise IntegrityError(f"event log hash mismatch at record {idx}")
            previous = actual
            expected_seq += 1
        return records

    def append_event(self, event: Event) -> dict[str, Any]:
        body = {
            "seq": self._last_seq + 1,
            "prev_hash": self._last_hash,
            **asdict(event),
        }
        record = dict(body)
        record["record_hash"] = canonical_hash(body)
        super().append(record)
        self._last_seq = int(record["seq"])
        self._last_hash = str(record["record_hash"])
        return record

    @property
    def last_seq(self) -> int:
        return self._last_seq

    @property
    def last_hash(self) -> str:
        return self._last_hash

    def record_at(self, seq: int) -> dict[str, Any] | None:
        if seq <= 0:
            return None
        records = self.verify_chain()
        if seq > len(records):
            return None
        return records[seq - 1]

    def latest_state_snapshot(self) -> dict[str, Any] | None:
        for record in reversed(self.verify_chain()):
            if record.get("kind") == "state.snapshot":
                return record
        return None

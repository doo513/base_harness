from __future__ import annotations

import json
import sys
from typing import TextIO

from .measurement_v5 import MAX_BYTES, PROTOCOL_VERSION, MeasurementEngine, MeasurementProtocolError, decode


def serve(input_stream: TextIO, output_stream: TextIO, engine: MeasurementEngine | None = None) -> int:
    engine = engine or MeasurementEngine()
    while True:
        line = input_stream.readline(MAX_BYTES * 4 + 1)
        if not line:
            return 0
        envelope = {}
        try:
            if len(line) > MAX_BYTES * 4:
                raise MeasurementProtocolError("measurement message too large")
            envelope = decode(line)
            if not isinstance(envelope, dict):
                raise MeasurementProtocolError("expected envelope object")
            payload = engine.handle(envelope)
            kind = "response"
        except Exception as error:
            if not isinstance(envelope, dict):
                envelope = {}
            kind = "error"
            payload = {"code": "MEASUREMENT_PROTOCOL_ERROR", "message": str(error)}
        response = {"version": PROTOCOL_VERSION, "id": envelope.get("id", ""), "runId": envelope.get("runId", ""),
                    "scopeId": envelope.get("scopeId", ""), "type": kind, "payload": payload}
        output_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        output_stream.flush()
        if kind == "error":
            # Corrupt protocol is not a retry/repair instruction; close this channel.
            return 1


if __name__ == "__main__":
    raise SystemExit(serve(sys.stdin, sys.stdout))

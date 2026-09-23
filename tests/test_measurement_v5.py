import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from harness.measurement_sidecar import serve
from harness.measurement_v5 import MeasurementEngine, MeasurementProtocolError, decode


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def ref(name: str) -> dict:
    return {"id": name, "revision": 1, "sha256": "a" * 64}


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "input.txt").write_text("actual file contents", encoding="utf-8")
        self.engine = MeasurementEngine()
        self.engine.handle(self.envelope("run.open", {"snapshotRoot": str(self.root)}, "open"))

    def envelope(self, kind, payload, request_id="measurement"):
        return {"version": 5, "id": request_id, "runId": "run", "scopeId": "task", "type": kind, "payload": payload}

    def payload(self):
        data = (self.root / "input.txt").read_bytes()
        manifest = {"kind": "source", "files": [{"path": "input.txt", "sha256": digest(data), "size": len(data)}], "dependencies": []}
        encoded = json.dumps(manifest, separators=(",", ":"))
        return {
            "subject": {**ref("source"), "kind": "source", "sha256": digest(encoded.encode())},
            "manifestJson": encoded, "environmentHash": "b" * 64,
            "check": {"schemaVersion": "check-spec-v1", "ref": ref("check"), "author": "model", "executorId": "python-measurement",
                      "supportedSubjects": ["source"], "parameters": {"kind": "file", "path": "input.txt", "operator": "equals", "expected": "actual file contents"},
                      "requiredCapabilities": ["read"], "timeoutMs": 1000},
        }

    def measure(self, payload=None, request_id="measurement"):
        return self.engine.handle(self.envelope("measure", payload or self.payload(), request_id))

    def command(self, execution="completed"):
        payload = self.payload()
        payload["check"]["parameters"] = {"kind": "command", "argv": ["python3", "-m", "unittest"], "cwd": str(self.root), "expectedExitCode": 0}
        payload["check"]["requiredCapabilities"] = ["execute"]
        capture = {"argv": ["python3", "-m", "unittest"], "cwd": str(self.root), "execution": execution,
                   "startedAt": "2026-09-18T00:00:00Z", "finishedAt": "2026-09-18T00:00:01Z", "stdout": "observed stdout", "stderr": "observed stderr"}
        if execution == "completed":
            capture["exitCode"] = 1
        elif execution == "error":
            capture["error"] = {"code": "TIMEOUT", "message": "process exceeded its admitted deadline"}
        else:
            capture["reason"] = "executor unavailable"
        payload["capture"] = capture
        return payload

    def test_file_facts_no_goal_outcome(self):
        report = self.measure()
        self.assertEqual(report["result"]["execution"], "completed")
        self.assertEqual(report["result"]["findings"][-1]["result"], "pass")
        self.assertFalse({"outcome", "readyEligible", "repairScope", "readyRef"} & report.keys())
        self.assertTrue(any("author: model" in limitation for limitation in report["limitations"]))

    def test_failed_file_comparison_is_completed(self):
        payload = self.payload()
        payload["check"]["parameters"]["expected"] = "different"
        result = self.measure(payload)["result"]
        self.assertEqual(result["execution"], "completed")
        self.assertEqual(result["findings"][-1]["result"], "fail")

    def test_exit_one_is_completed_fail_not_engine_error(self):
        report = self.measure(self.command())
        self.assertEqual(report["result"]["execution"], "completed")
        self.assertEqual(report["result"]["findings"][-1]["observed"], 1)
        self.assertEqual(report["result"]["findings"][-1]["result"], "fail")
        self.assertTrue(any("did not independently execute" in limitation for limitation in report["limitations"]))

    def test_timeout_and_not_run_are_different_from_comparison_failure(self):
        error = self.measure(self.command("error"), "error")["result"]
        not_run = self.measure(self.command("not_run"), "not-run")["result"]
        self.assertEqual(error["execution"], "error")
        self.assertEqual(error["error"]["code"], "TIMEOUT")
        self.assertEqual(not_run["execution"], "not_run")
        self.assertNotIn("findings", not_run)

    def test_no_implicit_command_execution(self):
        payload = self.command()
        del payload["capture"]
        self.assertEqual(self.measure(payload)["result"]["execution"], "not_run")

    def test_request_replay_and_conflict(self):
        payload = self.payload()
        first = self.measure(payload)
        self.assertEqual(first, self.measure(copy.deepcopy(payload)))
        payload["check"]["parameters"]["expected"] = "changed"
        with self.assertRaisesRegex(MeasurementProtocolError, "REQUEST_CONFLICT"):
            self.measure(payload)

    def test_changed_bytes_never_belong_to_prior_subject(self):
        payload = self.payload()
        (self.root / "input.txt").write_text("new bytes", encoding="utf-8")
        report = self.measure(payload)
        self.assertEqual(report["result"]["execution"], "error")
        self.assertIn("SUBJECT_BYTES_CHANGED", report["result"]["error"]["message"])
        self.assertEqual(report["result"]["partialFindings"], [])

    def test_wrong_manifest_digest_is_protocol_error(self):
        payload = self.payload()
        payload["subject"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(MeasurementProtocolError, "digest"):
            self.measure(payload)

    def test_wrong_executor_is_not_silently_run_by_python(self):
        payload = self.payload()
        payload["check"]["executorId"] = "other-verifier"
        with self.assertRaisesRegex(MeasurementProtocolError, "executor binding"):
            self.measure(payload)

    def test_symlink_target_is_not_read(self):
        payload = self.payload()
        (self.root / "input.txt").rename(self.root / "actual.txt")
        try:
            (self.root / "input.txt").symlink_to(self.root / "actual.txt")
        except OSError:
            self.skipTest("symlinks require elevated privileges on Windows")
        self.assertEqual(self.measure(payload)["result"]["execution"], "error")

    def test_hardlinked_input_is_rejected(self):
        payload = self.payload()
        os.link(self.root / "input.txt", self.root / "alias.txt")
        self.assertEqual(self.measure(payload)["result"]["execution"], "error")

    def test_manifest_traversal_is_rejected_before_read(self):
        payload = self.payload()
        manifest = json.loads(payload["manifestJson"])
        manifest["files"][0]["path"] = "../input.txt"
        payload["manifestJson"] = json.dumps(manifest)
        payload["subject"]["sha256"] = digest(payload["manifestJson"].encode())
        with self.assertRaises(MeasurementProtocolError):
            self.measure(payload)

    def test_process_capture_cannot_mislabel_executed_command(self):
        payload = self.command()
        payload["capture"]["argv"] = ["different"]
        with self.assertRaisesRegex(MeasurementProtocolError, "binding"):
            self.measure(payload)

    def test_actor_control_fields_and_cross_run_rejected(self):
        payload = self.payload()
        payload["outcome"] = "ready"
        with self.assertRaises(MeasurementProtocolError):
            self.measure(payload)
        envelope = self.envelope("measure", self.payload())
        envelope["runId"] = "other-run"
        with self.assertRaisesRegex(MeasurementProtocolError, "binding"):
            self.engine.handle(envelope)

    def test_v4_cannot_silently_fall_back(self):
        envelope = self.envelope("hello", {})
        envelope["version"] = 4
        output = io.StringIO()
        self.assertEqual(serve(io.StringIO(json.dumps(envelope) + "\n"), output), 1)
        reply = json.loads(output.getvalue())
        self.assertEqual(reply["version"], 5)
        self.assertEqual(reply["type"], "error")
        self.assertNotIn("outcome", reply["payload"])

    def test_duplicate_json_keys_and_nonfinite_numbers_rejected(self):
        for value in ['{"a":1,"a":2}', '{"a":NaN}', '{"__proto__":{}}']:
            with self.assertRaises(MeasurementProtocolError):
                decode(value)


if __name__ == "__main__":
    unittest.main()

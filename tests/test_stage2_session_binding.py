from __future__ import annotations

import base64
import sys

from harness.core.sandbox import ExecutionResult, IsolationAttestation, SessionIOResult
from harness.core.tools import ActionRuntime, SandboxedSessionToolSpec, ToolCall, make_session_tool
from harness.core.sandbox import LocalProcessBackend, NetworkPolicy


def _decode(output, field="stdout_b64"):
    return base64.b64decode(output[field])


def test_local_persistent_session_send_read_uses_structured_argv(tmp_path):
    marker = tmp_path / "SHOULD_NOT_EXIST"
    payload = f"hello;touch {marker}"
    runtime = ActionRuntime({"session": make_session_tool(tmp_path)})
    created = runtime.execute(ToolCall("session", {
        "op": "create",
        "argv": [sys.executable, "-u", "-c", "import sys; print(sys.argv[1]); [print(x.strip()) for x in sys.stdin]", payload],
    }))
    assert created.ok is True
    sid = created.output["session_id"]
    sent = runtime.execute(ToolCall("session", {
        "op": "send", "session_id": sid,
        "data_b64": base64.b64encode(b"ping\n").decode(),
    }))
    assert sent.ok is True and sent.output["bytes_sent"] == 5
    observed = runtime.execute(ToolCall("session", {
        "op": "read", "session_id": sid, "wait_seconds": 1.0,
    }))
    runtime.execute(ToolCall("session", {"op": "close", "session_id": sid}))
    assert observed.ok is True
    out = _decode(observed.output)
    assert payload.encode() in out and b"ping" in out
    assert marker.exists() is False


def test_session_read_wait_window_accumulates_startup_and_delayed_response(tmp_path):
    """Regression for the first-readable-byte race found by CTF integration CI.

    The child emits startup output immediately, then deliberately delays its
    response after reading input. A read with a 0.5 s observation window must
    retain the startup bytes *and* continue observing long enough to capture the
    later response in the same bounded call.
    """
    code = (
        "import sys,time; "
        "print('ready', flush=True); "
        "line=sys.stdin.readline(); "
        "time.sleep(0.15); "
        "print('E:'+line.strip(), flush=True); "
        "sys.stdin.readline()"
    )
    session = LocalProcessBackend().open_argv_session(
        workspace=tmp_path,
        argv=[sys.executable, "-u", "-c", code],
    )
    try:
        session.send(b"ping\n")
        observed = session.read(wait_seconds=0.5)
        assert b"ready\n" in observed.stdout
        assert b"E:ping\n" in observed.stdout
        assert observed.returncode is None
    finally:
        session.close()


def test_strict_session_attestation_and_execution_use_same_backend_object(tmp_path):
    class FakeSession:
        def __init__(self): self.sent = []
        def send(self, data): self.sent.append(data)
        def read(self, *, max_bytes=65536, wait_seconds=0.0): return SessionIOResult(b"ok", b"", None)
        def interrupt(self): pass
        def status(self): return SessionIOResult(returncode=None)
        def close(self): return SessionIOResult(returncode=0)

    class IdentityBackend:
        name = "identity_session_backend"
        def __init__(self): self.attested_ids=[]; self.opened_ids=[]; self.session=FakeSession()
        def isolation_attestation(self, *, workspace):
            self.attested_ids.append(id(self)); return IsolationAttestation(True, True, True, "test_fixture")
        def open_argv_session(self, *, workspace, argv, env=None):
            self.opened_ids.append(id(self)); return self.session
        def run_shell(self, **kwargs): raise AssertionError("session path must not call run_shell")
        def run_argv(self, **kwargs): raise AssertionError("session path must not call run_argv")

    backend = IdentityBackend()
    spec = SandboxedSessionToolSpec("session", "session", backend, tmp_path)
    runtime = ActionRuntime(
        {"session": spec}, strict_isolation=True,
        network_policy=NetworkPolicy.DENY, allow_test_attestation=True,
    )
    created = runtime.execute(ToolCall("session", {"op":"create", "argv":["dummy"]}))
    assert created.ok is True
    assert backend.attested_ids == [id(backend)]
    assert backend.opened_ids == [id(backend)]
    sid = created.output["session_id"]
    read = runtime.execute(ToolCall("session", {"op":"read", "session_id":sid}))
    assert read.ok is True and _decode(read.output) == b"ok"
    runtime.execute(ToolCall("session", {"op":"close", "session_id":sid}))


def test_session_id_cannot_cross_tool_backend_binding(tmp_path):
    class FakeSession:
        def send(self, data): pass
        def read(self, **kwargs): return SessionIOResult()
        def interrupt(self): pass
        def status(self): return SessionIOResult()
        def close(self): return SessionIOResult(returncode=0)
    class Backend:
        name="b"
        def isolation_attestation(self, *, workspace): return IsolationAttestation(True, True, True, "test_fixture")
        def open_argv_session(self, *, workspace, argv, env=None): return FakeSession()
        def run_shell(self, **kwargs): return ExecutionResult(0,"","")
        def run_argv(self, **kwargs): return ExecutionResult(0,"","")

    one=Backend(); two=Backend()
    runtime=ActionRuntime({
        "one": SandboxedSessionToolSpec("one","one",one,tmp_path),
        "two": SandboxedSessionToolSpec("two","two",two,tmp_path),
    }, strict_isolation=True, network_policy=NetworkPolicy.DENY, allow_test_attestation=True)
    created=runtime.execute(ToolCall("one", {"op":"create","argv":["dummy"]}))
    sid=created.output["session_id"]
    stolen=runtime.execute(ToolCall("two", {"op":"status","session_id":sid}))
    assert stolen.ok is False and stolen.security_violation is True
    runtime.execute(ToolCall("one", {"op":"close","session_id":sid}))


def test_session_input_is_base64_and_argument_shape_is_fail_closed(tmp_path):
    runtime = ActionRuntime({"session": make_session_tool(tmp_path)})
    created = runtime.execute(ToolCall("session", {"op":"create", "argv":[sys.executable,"-u","-c","import sys; sys.stdin.buffer.read()"]}))
    sid = created.output["session_id"]
    bad = runtime.execute(ToolCall("session", {"op":"send", "session_id":sid, "data_b64":"%%%"}))
    extra = runtime.execute(ToolCall("session", {"op":"status", "session_id":sid, "extra":True}))
    assert bad.ok is False and "base64" in bad.error
    assert extra.ok is False
    runtime.execute(ToolCall("session", {"op":"close", "session_id":sid}))


def test_session_provenance_declares_ephemeral_resume_policy(tmp_path):
    spec = make_session_tool(tmp_path)
    assert spec.provenance["execution_kind"] == "sandboxed_session"
    assert spec.provenance["resume_policy"] == "ephemeral_fail_closed"

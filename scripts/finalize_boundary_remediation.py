from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="")


def replace(path: str, old: str, new: str, *, required: bool = True) -> bool:
    text = read(path)
    if old not in text:
        if required:
            raise RuntimeError(f"{path}: expected fragment not found: {old[:120]!r}")
        return False
    write(path, text.replace(old, new, 1))
    return True


def regex(path: str, pattern: str, repl: str, *, count: int = 1) -> int:
    text = read(path)
    updated, matched = re.subn(pattern, repl, text, count=count, flags=re.S)
    if matched != count:
        raise RuntimeError(f"{path}: expected {count} regex match(es), got {matched}: {pattern[:120]!r}")
    write(path, updated)
    return matched


# The first-pass applicator intentionally stays close to the reviewed patch.
# This finalizer folds in findings discovered by executing that patch against the
# complete suite.

# 1. MCP stderr is a byte stream, not a line protocol. Chunk draining avoids a
# newline-free producer holding an arbitrarily large TextIO line buffer.
replace(
    "src/harness/mcp_gateway.py",
    '''    def _stderr_loop(self) -> None:\n        process = self.process\n        if process is None or process.stderr is None:\n            return\n        for line in process.stderr:\n            self._stderr_tail.append(line.rstrip()[:2000])\n\n    def stderr_tail(self) -> tuple[str, ...]:\n''',
    '''    def _stderr_loop(self) -> None:\n        process = self.process\n        if process is None or process.stderr is None:\n            return\n        while True:\n            chunk = process.stderr.read(4096)\n            if not chunk:\n                break\n            lines = chunk.splitlines() or [chunk]\n            for line in lines:\n                if line:\n                    self._stderr_tail.append(line[:2000])\n\n    def stderr_tail(self) -> tuple[str, ...]:\n''',
)

# 2. The error taxonomy change is intentional: malformed Actor decisions are
# model protocol failures, not Harness implementation defects.
replace(
    "tests/test_hardening.py",
    'assert any(f["kind"] == "implementation_error" for f in state.failures)',
    'assert any(f["kind"] == "model_protocol_error" for f in state.failures)',
)

# 3. Make the task overlay part of the explicit CLI launch contract so a resume
# can recreate the same profile/oracle before HarnessRuntime checks config_hash.
replace(
    "src/harness/tui.py",
    '    model_revision: str | None = None\n    execution_backend: str | None = None\n',
    '    model_revision: str | None = None\n    artifact_target: str | None = None\n    execution_backend: str | None = None\n',
)
replace(
    "src/harness/tui.py",
    '''        if self.model_revision:\n            argv += ["--model-revision", self.model_revision]\n        if self.sealed_oracle_root:\n''',
    '''        if self.model_revision:\n            argv += ["--model-revision", self.model_revision]\n        if self.artifact_target:\n            argv += ["--artifact-target", self.artifact_target]\n        if self.sealed_oracle_root:\n''',
)

replace(
    "src/harness/tui_conversation.py",
    '        "task_revision": spec.task_revision,\n        "execution_backend": spec.execution_backend,\n',
    '        "task_revision": spec.task_revision,\n        "artifact_target": spec.artifact_target,\n        "execution_backend": spec.execution_backend,\n',
)

marker = "def _resume_backend_from_manifest(config: dict[str, Any]) -> str | None:\n"
helper = '''def _artifact_target_from_manifest(config: dict[str, Any], hint: dict[str, Any]) -> str | None:\n    hinted = hint.get("artifact_target")\n    if isinstance(hinted, str) and hinted.strip():\n        return hinted.strip()\n\n    goal = config.get("goal") if isinstance(config.get("goal"), dict) else {}\n    pinned = goal.get("pinned_constraints") if isinstance(goal.get("pinned_constraints"), list) else []\n    prefix = "final artifact path is "\n    for item in pinned:\n        if isinstance(item, str) and item.startswith(prefix) and item[len(prefix):].strip():\n            return item[len(prefix):].strip()\n\n    acceptance = goal.get("acceptance") if isinstance(goal.get("acceptance"), list) else []\n    prefix = "produce requested evidence-backed artifact: "\n    for item in acceptance:\n        if isinstance(item, str) and item.startswith(prefix) and item[len(prefix):].strip():\n            return item[len(prefix):].strip()\n    return None\n\n\ndef _sealed_oracle_root_from_manifest(config: dict[str, Any]) -> str | None:\n    oracle = config.get("oracle") if isinstance(config.get("oracle"), dict) else {}\n    if not bool(oracle.get("sealed")):\n        return None\n    backend = oracle.get("backend") if isinstance(oracle.get("backend"), dict) else {}\n    backend_config = backend.get("config") if isinstance(backend.get("config"), dict) else {}\n    paths = backend_config.get("read_only_paths")\n    if not isinstance(paths, list) or len(paths) != 1:\n        return None\n    value = paths[0]\n    if isinstance(value, dict) and isinstance(value.get("path"), str):\n        return value["path"]\n    if isinstance(value, str):\n        return value\n    return None\n\n\n'''
replace("src/harness/tui_conversation.py", marker, helper + marker)

replace(
    "src/harness/tui_conversation.py",
    '''    goal_desc = config.get("goal") if isinstance(config.get("goal"), dict) else {}\n    acceptance = goal_desc.get("acceptance") if isinstance(goal_desc.get("acceptance"), list) else []\n    hint = _session_hint(run_dir)\n\n    hinted_config = hint.get("config") if isinstance(hint.get("config"), str) else None\n    if hinted_config and Path(hinted_config).expanduser().exists():\n        config_path = hinted_config\n    else:\n        config_path = state.config if Path(state.config).expanduser().exists() else None\n\n    backend = hint.get("execution_backend") if isinstance(hint.get("execution_backend"), str) else None\n''',
    '''    goal_desc = config.get("goal") if isinstance(config.get("goal"), dict) else {}\n    hint = _session_hint(run_dir)\n    artifact_target = _artifact_target_from_manifest(config, hint)\n\n    # A presentation hint must never choose a config file. Config loading can\n    # instantiate model/MCP/plugin providers before runtime resume reaches the\n    # manifest config-hash check. Current operator config is merely a proposal;\n    # the verified manifest remains authoritative.\n    config_path = state.config if Path(state.config).expanduser().exists() else None\n\n    budget_desc = config.get("budget") if isinstance(config.get("budget"), dict) else {}\n    max_steps = budget_desc.get("hard_max_steps", 30)\n    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps <= 0:\n        return None\n\n    oracle_desc = config.get("oracle") if isinstance(config.get("oracle"), dict) else {}\n    command_count = oracle_desc.get("command_count", 0)\n    if not isinstance(command_count, int) or isinstance(command_count, bool) or command_count < 0:\n        return None\n\n    # Raw acceptance commands are deliberately not recoverable from goal text.\n    # A TUI hint may propose the old argv, but HarnessRuntime's config_hash check\n    # validates it before any completion command can execute.\n    acceptance_commands: tuple[str, ...] = ()\n    if profile in {"software", "hackathon"} and artifact_target is None and command_count:\n        hinted_commands = hint.get("acceptance_commands")\n        if (\n            not isinstance(hinted_commands, list)\n            or len(hinted_commands) != command_count\n            or any(not isinstance(item, str) or not item for item in hinted_commands)\n        ):\n            return None\n        acceptance_commands = tuple(hinted_commands)\n\n    task_revision = manifest.get("task_revision")\n    if task_revision == "UNSPECIFIED":\n        task_revision = None\n    elif not isinstance(task_revision, str):\n        return None\n\n    backend = hint.get("execution_backend") if isinstance(hint.get("execution_backend"), str) else None\n''',
)

replace(
    "src/harness/tui_conversation.py",
    '''        acceptance_commands=tuple(str(item) for item in acceptance if isinstance(item, str)),\n        task_revision=(hint.get("task_revision") if isinstance(hint.get("task_revision"), str) else None),\n        execution_backend=backend,\n''',
    '''        acceptance_commands=acceptance_commands,\n        max_steps=max_steps,\n        task_revision=task_revision,\n        artifact_target=artifact_target,\n        execution_backend=backend,\n''',
)
replace(
    "src/harness/tui_conversation.py",
    '''        require_sealed_oracle=optional_bool("require_sealed_oracle"),\n        sealed_oracle_root=(hint.get("sealed_oracle_root") if isinstance(hint.get("sealed_oracle_root"), str) else None),\n        require_oracle_isolation=(hint.get("require_oracle_isolation") if isinstance(hint.get("require_oracle_isolation"), bool) else None),\n''',
    '''        require_sealed_oracle=optional_bool("require_sealed_oracle"),\n        sealed_oracle_root=_sealed_oracle_root_from_manifest(config),\n        require_oracle_isolation=(\n            bool(oracle_desc.get("require_filesystem_isolation"))\n            if "require_filesystem_isolation" in oracle_desc\n            else None\n        ),\n''',
)
replace(
    "src/harness/tui_conversation.py",
    '        acceptance_commands=tuple(acceptance),\n        max_steps=30,\n        resume=False,\n',
    '        acceptance_commands=tuple(acceptance),\n        max_steps=30,\n        artifact_target=artifact_target,\n        resume=False,\n',
)

# 4. Align the original v2 fixture with the real manifest contract. Use regex
# so formatting changes do not turn a semantic test update into a string-patch
# failure.
test_path = "tests/test_tui_conversation_v2.py"
text = read(test_path)
if '"task_revision": "UNSPECIFIED"' not in text:
    text, matched = re.subn(
        r'("harness_version": __version__,\n\s*)("model_revision": "model-x",)',
        r'\1"task_revision": "UNSPECIFIED",\n            \2',
        text,
        count=1,
    )
    if matched != 1:
        raise RuntimeError("could not add task_revision to legacy resume fixture")
text = text.replace(
    'assert spec.acceptance_commands == ("python verify.py",)',
    'assert spec.acceptance_commands == ()',
    1,
)
write(test_path, text)

# 5. Focused regressions for the newly discovered resume boundary.
text = read(test_path)
if "test_tui_v2_resume_spec_reconstructs_artifact_overlay_and_budget" not in text:
    text += '''\n\ndef test_tui_v2_resume_spec_reconstructs_artifact_overlay_and_budget(tmp_path):\n    workspace = tmp_path / "artifact-workspace"\n    workspace.mkdir()\n    run_dir = tmp_path / "artifact-run"\n    run_dir.mkdir()\n    RunManifestStore(run_dir / "run_manifest.json").create({\n        "run_id": "artifact-run",\n        "harness_version": __version__,\n        "task_revision": "task-r1",\n        "model_revision": "model-r1",\n        "config": {\n            "workspace": str(workspace),\n            "profile": {"name": "software", "class": "harness.task_contracts.EvidenceArtifactTaskProfile"},\n            "goal": {\n                "acceptance": ["produce requested evidence-backed artifact: DEEP_REPORT.md"],\n                "pinned_constraints": ["final artifact path is DEEP_REPORT.md"],\n            },\n            "security": {\n                "strict_layout": False,\n                "strict_tool_isolation": False,\n                "network_policy": "allow",\n                "require_sealed_oracle": False,\n            },\n            "budget": {"hard_max_steps": 17},\n            "oracle": {"sealed": False, "require_filesystem_isolation": False},\n            "tools": [],\n        },\n    })\n    state = AppState(workspace=str(tmp_path), config=str(tmp_path / "missing.toml"), mode="software")\n    spec = _session_resume_spec(state, run_dir)\n    assert spec is not None\n    assert spec.artifact_target == "DEEP_REPORT.md"\n    assert spec.max_steps == 17\n    assert spec.task_revision == "task-r1"\n    command = spec.command(python_executable="python-test")\n    assert command[command.index("--artifact-target") + 1] == "DEEP_REPORT.md"\n\n\ndef test_tui_v2_resume_does_not_treat_goal_acceptance_as_shell_command(tmp_path):\n    workspace = tmp_path / "command-workspace"\n    workspace.mkdir()\n    run_dir = tmp_path / "command-run"\n    run_dir.mkdir()\n    RunManifestStore(run_dir / "run_manifest.json").create({\n        "run_id": "command-run",\n        "harness_version": __version__,\n        "task_revision": "UNSPECIFIED",\n        "model_revision": "model-r1",\n        "config": {\n            "workspace": str(workspace),\n            "profile": {"name": "software"},\n            "goal": {"acceptance": ["all required behavior is verified"], "pinned_constraints": []},\n            "security": {\n                "strict_layout": False,\n                "strict_tool_isolation": False,\n                "network_policy": "allow",\n                "require_sealed_oracle": False,\n            },\n            "budget": {"hard_max_steps": 30},\n            "oracle": {"sealed": False, "command_count": 1, "require_filesystem_isolation": False},\n            "tools": [],\n        },\n    })\n    (run_dir / "tui_session.json").write_text(\n        json.dumps({\n            "schema_version": 1,\n            "authority": "presentation_hint_only",\n            "config": str(tmp_path / "untrusted.toml"),\n            "acceptance_commands": ["python -m pytest -q"],\n        }),\n        encoding="utf-8",\n    )\n    state = AppState(workspace=str(tmp_path), config=str(tmp_path / "missing.toml"), mode="software")\n    spec = _session_resume_spec(state, run_dir)\n    assert spec is not None\n    assert spec.config is None\n    assert spec.acceptance_commands == ("python -m pytest -q",)\n    assert "all required behavior is verified" not in spec.acceptance_commands\n'''
    write(test_path, text)

print("boundary finalizer patches applied")

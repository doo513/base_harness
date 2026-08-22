from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:120]!r}")
    write(path, text.replace(old, new, 1))


PREFLIGHT = r'''from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
from typing import Any, Callable, Mapping, Sequence


class PreflightError(ValueError):
    pass


@dataclass(frozen=True)
class TaskRequirementManifest:
    domain: str
    goal: str
    workspace: str
    artifact_target: str | None
    detected_stacks: tuple[str, ...]
    acceptance_commands: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    required_executables: tuple[str, ...]
    network_required: bool
    risk_flags: tuple[str, ...]

    def dump(self) -> dict[str, Any]:
        return {
            "schema_version": "task-requirement-manifest-v1",
            "domain": self.domain,
            "goal": self.goal,
            "workspace": self.workspace,
            "artifact_target": self.artifact_target,
            "detected_stacks": list(self.detected_stacks),
            "acceptance_commands": list(self.acceptance_commands),
            "required_capabilities": list(self.required_capabilities),
            "required_executables": list(self.required_executables),
            "network_required": self.network_required,
            "risk_flags": list(self.risk_flags),
        }


@dataclass(frozen=True)
class CapabilityResolution:
    selected_tools: tuple[str, ...]
    available_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    tool_capabilities: Mapping[str, tuple[str, ...]]

    def dump(self) -> dict[str, Any]:
        return {
            "schema_version": "capability-resolution-v1",
            "selected_tools": list(self.selected_tools),
            "available_capabilities": list(self.available_capabilities),
            "missing_capabilities": list(self.missing_capabilities),
            "tool_capabilities": {
                name: list(values)
                for name, values in sorted(self.tool_capabilities.items())
            },
            "selection_authority": "kernel_deterministic",
            "tool_execution_authority": False,
        }


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    manifest: TaskRequirementManifest
    resolution: CapabilityResolution
    execution_backend: str
    network_policy: str
    strict_tool_isolation: bool
    require_oracle_isolation: bool

    def dump(self) -> dict[str, Any]:
        return {
            "schema_version": "environment-readiness-v1",
            "ready": self.ready,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "execution_backend": self.execution_backend,
            "network_policy": self.network_policy,
            "strict_tool_isolation": self.strict_tool_isolation,
            "require_oracle_isolation": self.require_oracle_isolation,
            "manifest": self.manifest.dump(),
            "capability_resolution": self.resolution.dump(),
        }


_STACK_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("python", ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "pytest.ini", "tox.ini")),
    ("node", ("package.json",)),
    ("rust", ("Cargo.toml",)),
    ("go", ("go.mod",)),
    ("java-maven", ("pom.xml",)),
    ("java-gradle", ("gradlew", "gradlew.bat", "build.gradle", "build.gradle.kts")),
    ("make", ("Makefile", "makefile")),
)

_NETWORK_PATTERN = re.compile(
    r"https?://|(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?|\bremote\b|\bconnect\b|\bserver\b|\bhost\b|"
    r"원격|접속|서버|호스트",
    re.IGNORECASE,
)


class TaskAnalyzer:
    """Deterministically derive task/environment requirements before model use."""

    @staticmethod
    def _detect_stacks(root: Path) -> tuple[str, ...]:
        stacks: list[str] = []
        names = {item.name for item in root.iterdir()} if root.exists() and root.is_dir() else set()
        for stack, markers in _STACK_MARKERS:
            if any(marker in names for marker in markers):
                stacks.append(stack)
        if any(root.glob("requirements*.txt")) and "python" not in stacks:
            stacks.append("python")
        return tuple(sorted(set(stacks)))

    @staticmethod
    def _command_executable(command: str) -> str | None:
        try:
            parts = shlex.split(command, posix=os.name != "nt")
        except ValueError:
            return None
        if not parts:
            return None
        head = parts[0].strip('"\'')
        if head in {"env", "/usr/bin/env"} and len(parts) > 1:
            head = parts[1].strip('"\'')
        return head or None

    @classmethod
    def _required_executables(
        cls,
        root: Path,
        stacks: Sequence[str],
        acceptance_commands: Sequence[str],
    ) -> tuple[str, ...]:
        values: list[str] = []
        for command in acceptance_commands:
            executable = cls._command_executable(command)
            if executable:
                values.append(executable)
        if not values:
            mapping = {
                "python": "python" if os.name == "nt" else "python3",
                "node": "npm",
                "rust": "cargo",
                "go": "go",
                "java-maven": "mvn",
                "make": "make",
            }
            for stack in stacks:
                if stack == "java-gradle":
                    if (root / "gradlew").exists():
                        values.append("./gradlew")
                    elif (root / "gradlew.bat").exists():
                        values.append("gradlew.bat")
                    else:
                        values.append("gradle")
                elif stack in mapping:
                    values.append(mapping[stack])
        return tuple(dict.fromkeys(values))

    def analyze(
        self,
        *,
        domain: str,
        goal: str,
        workspace: str | Path,
        acceptance_commands: Sequence[str] = (),
        artifact_target: str | None = None,
    ) -> TaskRequirementManifest:
        root = Path(workspace).expanduser().resolve()
        stacks = self._detect_stacks(root)
        network_required = bool(_NETWORK_PATTERN.search(goal or ""))

        capabilities = ["workspace.read"]
        if domain != "demo":
            capabilities.append("process.execute")
        if domain in {"software", "hackathon"} or artifact_target:
            capabilities.append("workspace.write")
        if acceptance_commands:
            capabilities.append("verification.command")
        if network_required:
            capabilities.append("network.external")
        if any(token in (goal or "").casefold() for token in ("interactive", "repl", "gdb", "debugger", "long-running", "대화형", "디버거")):
            capabilities.append("process.session")

        risks: list[str] = []
        if domain in {"software", "hackathon", "ctf"}:
            risks.append("project_code_execution")
        if acceptance_commands:
            risks.append("acceptance_code_execution")
        if network_required:
            risks.append("external_network")
        if not stacks and domain in {"software", "hackathon"}:
            risks.append("unknown_project_stack")

        return TaskRequirementManifest(
            domain=domain,
            goal=str(goal),
            workspace=str(root),
            artifact_target=artifact_target,
            detected_stacks=stacks,
            acceptance_commands=tuple(acceptance_commands),
            required_capabilities=tuple(dict.fromkeys(capabilities)),
            required_executables=self._required_executables(root, stacks, acceptance_commands),
            network_required=network_required,
            risk_flags=tuple(dict.fromkeys(risks)),
        )


class CapabilityResolver:
    """Resolve required capabilities against the concrete composed tool surface."""

    @staticmethod
    def _tool_caps(name: str, spec: Any) -> tuple[str, ...]:
        capabilities: set[str] = set()
        side_effect = getattr(getattr(spec, "side_effect", None), "value", None)
        if side_effect in {"none", "read"}:
            capabilities.add("workspace.read")
        if side_effect in {"write", "external"}:
            capabilities.add("workspace.write")
        if side_effect == "external":
            capabilities.add("network.external")
        if name in {"shell", "argv"} or name.endswith(".shell") or name.endswith(".argv"):
            capabilities.update({"process.execute", "workspace.write", "network.external"})
        if name == "session" or name.endswith(".session"):
            capabilities.update({"process.execute", "process.session", "workspace.write", "network.external"})
        if name in {"file.read", "file.search", "directory.list"}:
            capabilities.add("workspace.read")
        return tuple(sorted(capabilities))

    def resolve(
        self,
        manifest: TaskRequirementManifest,
        tools: Mapping[str, Any],
    ) -> CapabilityResolution:
        tool_capabilities = {
            name: self._tool_caps(name, spec)
            for name, spec in sorted(tools.items())
        }
        available = {cap for values in tool_capabilities.values() for cap in values}
        if manifest.acceptance_commands:
            available.add("verification.command")

        selected: list[str] = []
        priority = {
            "workspace.read": ("directory.list", "file.search", "file.read"),
            "process.execute": ("argv", "shell"),
            "process.session": ("session",),
            "workspace.write": ("argv", "shell"),
            "network.external": ("argv", "shell", "session"),
        }
        for capability in manifest.required_capabilities:
            for preferred in priority.get(capability, ()):
                if preferred in tools and preferred not in selected:
                    selected.append(preferred)
            if capability == "workspace.read":
                for name in ("directory.list", "file.search", "file.read"):
                    if name in tools and name not in selected:
                        selected.append(name)
            if not any(capability in values for values in tool_capabilities.values()):
                for name, values in tool_capabilities.items():
                    if capability in values and name not in selected:
                        selected.append(name)

        missing = sorted(set(manifest.required_capabilities) - available)
        return CapabilityResolution(
            selected_tools=tuple(selected),
            available_capabilities=tuple(sorted(available)),
            missing_capabilities=tuple(missing),
            tool_capabilities=tool_capabilities,
        )


class EnvironmentPreflight:
    """Fail closed on deterministic environment/policy incompatibilities."""

    def __init__(
        self,
        *,
        executable_finder: Callable[[str], str | None] = shutil.which,
        platform_name: str | None = None,
    ):
        self.executable_finder = executable_finder
        self.platform_name = platform_name or sys.platform

    def _executable_available(self, executable: str, workspace: Path) -> bool:
        if "/" in executable or "\\" in executable:
            candidate = Path(executable)
            if not candidate.is_absolute():
                candidate = workspace / candidate
            return candidate.exists() and candidate.is_file()
        return self.executable_finder(executable) is not None

    def check(
        self,
        *,
        manifest: TaskRequirementManifest,
        resolution: CapabilityResolution,
        execution_backend: str,
        network_policy: str,
        strict_tool_isolation: bool,
        require_oracle_isolation: bool,
    ) -> ReadinessReport:
        blockers: list[str] = []
        warnings: list[str] = []
        workspace = Path(manifest.workspace)

        if not workspace.exists() or not workspace.is_dir():
            blockers.append(f"workspace is not an existing directory: {workspace}")

        for executable in manifest.required_executables:
            if not self._executable_available(executable, workspace):
                blockers.append(f"required executable is unavailable: {executable}")

        if resolution.missing_capabilities:
            blockers.append(
                "required capabilities are unavailable: " + ", ".join(resolution.missing_capabilities)
            )

        if execution_backend not in {"local", "linux-namespace"}:
            blockers.append(f"unsupported execution backend: {execution_backend}")
        elif execution_backend == "linux-namespace":
            if not self.platform_name.startswith("linux"):
                blockers.append("linux-namespace backend requires Linux or WSL")
            for executable in ("unshare", "mount", "chroot", "setpriv", "sh"):
                if self.executable_finder(executable) is None:
                    blockers.append(f"linux-namespace prerequisite is unavailable: {executable}")
        else:
            warnings.append("local backend is not an OS filesystem or network sandbox")

        if strict_tool_isolation and execution_backend != "linux-namespace":
            blockers.append("strict tool isolation requires the linux-namespace backend")
        if require_oracle_isolation and execution_backend != "linux-namespace":
            blockers.append("isolated completion checks require the linux-namespace backend")
        if manifest.network_required and network_policy == "deny":
            blockers.append("task requires external network access but network policy is deny")
        if network_policy == "allow":
            warnings.append("network access is allowed for process tools")

        if (
            manifest.domain in {"software", "hackathon"}
            and not manifest.acceptance_commands
            and manifest.artifact_target is None
        ):
            blockers.append("software/hackathon task has no fixed acceptance command or artifact contract")
        if manifest.domain == "ctf":
            warnings.append("CTF final acceptance still requires an operator-provided task-native oracle")
        if "unknown_project_stack" in manifest.risk_flags:
            warnings.append("project stack could not be identified from common repository markers")

        return ReadinessReport(
            ready=not blockers,
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=tuple(dict.fromkeys(warnings)),
            manifest=manifest,
            resolution=resolution,
            execution_backend=execution_backend,
            network_policy=network_policy,
            strict_tool_isolation=bool(strict_tool_isolation),
            require_oracle_isolation=bool(require_oracle_isolation),
        )


def run_preflight(
    *,
    domain: str,
    goal: str,
    workspace: str | Path,
    tools: Mapping[str, Any],
    acceptance_commands: Sequence[str],
    artifact_target: str | None,
    execution_backend: str,
    network_policy: str,
    strict_tool_isolation: bool,
    require_oracle_isolation: bool,
    environment: EnvironmentPreflight | None = None,
) -> ReadinessReport:
    manifest = TaskAnalyzer().analyze(
        domain=domain,
        goal=goal,
        workspace=workspace,
        acceptance_commands=acceptance_commands,
        artifact_target=artifact_target,
    )
    resolution = CapabilityResolver().resolve(manifest, tools)
    return (environment or EnvironmentPreflight()).check(
        manifest=manifest,
        resolution=resolution,
        execution_backend=execution_backend,
        network_policy=network_policy,
        strict_tool_isolation=strict_tool_isolation,
        require_oracle_isolation=require_oracle_isolation,
    )
'''
write("src/harness/preflight.py", PREFLIGHT)

replace_once(
    "src/harness/cli.py",
    "import argparse\nimport os\n",
    "import argparse\nimport json\nimport os\n",
)
replace_once(
    "src/harness/cli.py",
    "from harness.profile_composition import ProfileCompositionError, augment_profile_tools\n",
    "from harness.profile_composition import ProfileCompositionError, augment_profile_tools\nfrom harness.preflight import PreflightError, run_preflight\n",
)
replace_once(
    "src/harness/cli.py",
    '    parser.add_argument("--model-command",\n',
    '    parser.add_argument(\n        "--preflight-only",\n        action="store_true",\n        help="Analyze task/capabilities/environment and emit deterministic JSON without invoking a model.",\n    )\n    parser.add_argument("--model-command",\n',
)
PREFLIGHT_CLI = '''    try:\n        preflight = run_preflight(\n            domain=args.profile,\n            goal=goal.goal,\n            workspace=workspace_contract.root,\n            tools=profile.tools(),\n            acceptance_commands=acceptance_commands,\n            artifact_target=args.artifact_target,\n            execution_backend=args.execution_backend,\n            network_policy=args.network_policy,\n            strict_tool_isolation=args.strict_tool_isolation,\n            require_oracle_isolation=args.require_oracle_isolation,\n        )\n    except (OSError, ValueError, PreflightError) as exc:\n        parser.error(f"preflight construction failed: {exc}")\n\n    if args.preflight_only:\n        print(json.dumps(preflight.dump(), ensure_ascii=False, sort_keys=True))\n        return 0 if preflight.ready else 2\n    if not preflight.ready:\n        parser.error("preflight blocked execution: " + "; ".join(preflight.blockers))\n\n'''
replace_once(
    "src/harness/cli.py",
    "    gateway = None\n    try:\n",
    PREFLIGHT_CLI + "    gateway = None\n    try:\n",
)
replace_once(
    "src/harness/cli.py",
    "            require_complete_provenance=args.require_complete_provenance,\n        )\n",
    "            require_complete_provenance=args.require_complete_provenance,\n            preflight_report=preflight.dump(),\n        )\n",
)

replace_once(
    "src/harness/core/runtime.py",
    "        require_complete_provenance: bool = False,\n    ):\n",
    "        require_complete_provenance: bool = False,\n        preflight_report: dict[str, Any] | None = None,\n    ):\n",
)
replace_once(
    "src/harness/core/runtime.py",
    "        self.require_complete_provenance = require_complete_provenance\n        self.halted = False\n",
    "        self.require_complete_provenance = require_complete_provenance\n        self.preflight_report = dict(preflight_report or {})\n        self.halted = False\n",
)
replace_once(
    "src/harness/core/runtime.py",
    "        if not self.resume_mode and any(self.run_dir.iterdir()):\n            raise ResumeConflict(\"run directory is not empty; use a fresh directory or resume the existing run\")\n\n        self.manifests = RunManifestStore",
    "        if not self.resume_mode and any(self.run_dir.iterdir()):\n            raise ResumeConflict(\"run directory is not empty; use a fresh directory or resume the existing run\")\n        if not self.resume_mode and self.preflight_report:\n            atomic_write_json(self.run_dir / \"preflight.json\", self.preflight_report)\n\n        self.manifests = RunManifestStore",
)
replace_once(
    "src/harness/core/runtime.py",
    "        descriptor[\"retrieval_memory\"] = self._retrieval_config_descriptor()\n",
    "        descriptor[\"retrieval_memory\"] = self._retrieval_config_descriptor()\n        descriptor[\"preflight\"] = dict(self.preflight_report)\n",
)
replace_once(
    "src/harness/core/runtime.py",
    "        manifest[\"build_provenance\"] = self.build_provenance.dump()\n        return manifest\n",
    "        manifest[\"build_provenance\"] = self.build_provenance.dump()\n        manifest[\"preflight\"] = dict(self.preflight_report)\n        return manifest\n",
)

replace_once(
    "src/harness/tui_conversation.py",
    '    "/status": "Show session status",\n',
    '    "/status": "Show session status",\n    "/preflight": "Check task environment readiness",\n',
)
PREFLIGHT_TUI = r'''def _preflight(state: legacy.AppState) -> None:
    acceptance = state.acceptance or legacy._detect_acceptance(state.workspace)
    if state.mode in {"ctf", "demo"}:
        acceptance = ()
    spec = RunLaunchSpec(
        config=state.config if Path(state.config).expanduser().exists() else None,
        workspace=state.workspace,
        run_dir=_default_new_run_dir(),
        profile=state.mode,
        goal="Preflight the current workspace and configured domain.",
        acceptance_commands=tuple(acceptance),
        max_steps=1,
    )
    command = spec.command() + ["--preflight-only"]
    process = subprocess.run(
        command,
        text=True,
        capture_output=True,
        shell=False,
        env=legacy._process_env(state),
    )
    raw = process.stdout.strip().splitlines()
    try:
        report = json.loads(raw[-1]) if raw else {}
    except json.JSONDecodeError:
        report = {}
    if not isinstance(report, dict):
        report = {}
    if not report:
        message = process.stderr.strip().splitlines()
        legacy._print_error(message[-1] if message else "Preflight did not return a report.")
        return
    ready = bool(report.get("ready"))
    legacy._emit(
        (("class:good" if ready else "class:bad"), "  ✓ Ready" if ready else "  ✕ Blocked")
    )
    manifest = report.get("manifest") if isinstance(report.get("manifest"), dict) else {}
    legacy._emit(("class:muted", "  stacks    "), ("class:assistant", ", ".join(manifest.get("detected_stacks", [])) or "unknown"))
    for warning in report.get("warnings", []):
        legacy._emit(("class:warn", "  ! Warning  "), ("class:assistant", str(warning)))
    for blocker in report.get("blockers", []):
        legacy._emit(("class:bad", "  ✕ Blocker  "), ("class:assistant", str(blocker)))
'''
replace_once(
    "src/harness/tui_conversation.py",
    "def _ensure_model_ready(state: legacy.AppState, session: PromptSession) -> bool:\n",
    PREFLIGHT_TUI + "\n\ndef _ensure_model_ready(state: legacy.AppState, session: PromptSession) -> bool:\n",
)
replace_once(
    "src/harness/tui_conversation.py",
    '    if command == "/help":\n',
    '    if command == "/preflight":\n        _preflight(state)\n        print()\n        return True\n    if command == "/help":\n',
)
replace_once(
    "src/harness/tui_conversation.py",
    '        legacy._emit(("class:accent", f"  {\'/sessions [run-id]\':<24}"), ("class:muted", "browse or resume saved runs"))\n',
    '        legacy._emit(("class:accent", f"  {\'/sessions [run-id]\':<24}"), ("class:muted", "browse or resume saved runs"))\n        legacy._emit(("class:accent", f"  {\'/preflight\':<24}"), ("class:muted", "check capabilities, executables, sandbox and network policy"))\n',
)

TESTS = r'''import json
from pathlib import Path

from harness.core.budget import Budget
from harness.core.controller import ScriptedController
from harness.core.runtime import HarnessRuntime
from harness.core.sandbox import LocalProcessBackend
from harness.core.tools import make_argv_tool, make_shell_tool
from harness.core.workspace import WorkspaceContract
from harness.core.workspace_tools import make_workspace_read_tools
from harness.preflight import (
    CapabilityResolver,
    EnvironmentPreflight,
    TaskAnalyzer,
    run_preflight,
)
from harness.profiles.software import SoftwareProfile


def _tools(workspace):
    contract = WorkspaceContract.build(workspace)
    return {
        **make_workspace_read_tools(contract),
        "argv": make_argv_tool(workspace, backend=LocalProcessBackend(inherit_env=False)),
        "shell": make_shell_tool(workspace, backend=LocalProcessBackend(inherit_env=False)),
    }


def test_task_analyzer_detects_stack_capabilities_and_acceptance_executable(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    manifest = TaskAnalyzer().analyze(
        domain="software",
        goal="Implement and test the API",
        workspace=tmp_path,
        acceptance_commands=("python3 -m pytest -q",),
    )
    assert manifest.detected_stacks == ("node", "python")
    assert "workspace.read" in manifest.required_capabilities
    assert "workspace.write" in manifest.required_capabilities
    assert "verification.command" in manifest.required_capabilities
    assert manifest.required_executables == ("python3",)


def test_capability_resolver_prefers_structured_argv_and_keeps_workspace_reads(tmp_path):
    manifest = TaskAnalyzer().analyze(
        domain="software",
        goal="Change code",
        workspace=tmp_path,
        acceptance_commands=("python3 -m pytest",),
    )
    resolution = CapabilityResolver().resolve(manifest, _tools(tmp_path))
    assert resolution.missing_capabilities == ()
    assert "argv" in resolution.selected_tools
    assert {"file.read", "file.search", "directory.list"} <= set(resolution.selected_tools)


def test_preflight_blocks_missing_executable(tmp_path):
    report = run_preflight(
        domain="software",
        goal="Change code",
        workspace=tmp_path,
        tools=_tools(tmp_path),
        acceptance_commands=("missing-command --check",),
        artifact_target=None,
        execution_backend="local",
        network_policy="allow",
        strict_tool_isolation=False,
        require_oracle_isolation=False,
        environment=EnvironmentPreflight(executable_finder=lambda _: None, platform_name="linux"),
    )
    assert report.ready is False
    assert any("missing-command" in item for item in report.blockers)


def test_preflight_blocks_local_backend_when_strict_oracle_isolation_is_required(tmp_path):
    report = run_preflight(
        domain="software",
        goal="Change code",
        workspace=tmp_path,
        tools=_tools(tmp_path),
        acceptance_commands=("python3 -m pytest",),
        artifact_target=None,
        execution_backend="local",
        network_policy="allow",
        strict_tool_isolation=False,
        require_oracle_isolation=True,
        environment=EnvironmentPreflight(executable_finder=lambda _: "/bin/tool", platform_name="linux"),
    )
    assert report.ready is False
    assert "isolated completion checks require the linux-namespace backend" in report.blockers


def test_preflight_blocks_network_required_task_under_deny_policy(tmp_path):
    report = run_preflight(
        domain="ctf",
        goal="Connect to remote 127.0.0.1:31337",
        workspace=tmp_path,
        tools=_tools(tmp_path),
        acceptance_commands=(),
        artifact_target=None,
        execution_backend="local",
        network_policy="deny",
        strict_tool_isolation=False,
        require_oracle_isolation=False,
        environment=EnvironmentPreflight(executable_finder=lambda _: "/bin/tool", platform_name="linux"),
    )
    assert report.ready is False
    assert any("network policy is deny" in item for item in report.blockers)


def test_preflight_blocks_software_task_without_any_completion_contract(tmp_path):
    report = run_preflight(
        domain="software",
        goal="Change code",
        workspace=tmp_path,
        tools=_tools(tmp_path),
        acceptance_commands=(),
        artifact_target=None,
        execution_backend="local",
        network_policy="allow",
        strict_tool_isolation=False,
        require_oracle_isolation=False,
        environment=EnvironmentPreflight(executable_finder=lambda _: "/bin/tool", platform_name="linux"),
    )
    assert report.ready is False
    assert any("no fixed acceptance command" in item for item in report.blockers)


def test_runtime_persists_preflight_in_file_and_manifest(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = SoftwareProfile(workspace=workspace, acceptance_commands=["false"])
    report = {"schema_version": "environment-readiness-v1", "ready": True, "blockers": []}
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=tmp_path / "run",
        workspace=workspace,
        budget=Budget(hard_max_steps=1),
        preflight_report=report,
    )
    assert json.loads((tmp_path / "run" / "preflight.json").read_text(encoding="utf-8")) == report
    manifest = json.loads((tmp_path / "run" / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["body"]["preflight"] == report
'''
write("tests/test_p0_preflight.py", TESTS)

DOC = r'''# P0 — Task, Capability, Environment Preflight

The preflight boundary runs before model invocation and before governed execution.

```text
TaskAnalyzer
  -> TaskRequirementManifest
CapabilityResolver
  -> concrete capability/tool resolution
EnvironmentPreflight
  -> blockers and warnings
ReadinessGate
  -> continue or fail closed
```

The gate checks repository stack markers, fixed acceptance executables, required
capabilities, execution backend/platform compatibility, namespace prerequisites,
strict isolation requirements, and network-policy conflicts. It never executes
project code. A successful report is persisted as `preflight.json` and embedded
in the run manifest. `verified-harness --preflight-only` exposes the same contract
for Codex or other process-based agents, while the TUI exposes `/preflight`.
'''
write("docs/tracks/integration-runtime/P0_TASK_CAPABILITY_ENVIRONMENT_PREFLIGHT.md", DOC)

print("P0 preflight patch applied")

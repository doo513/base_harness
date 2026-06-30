#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# ///
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
ROOT = Path(__file__).resolve().parents[1]
DONE_STATUSES = {"done", "complete", "completed", "cancelled", "canceled", "skipped"}
SKILL_NAMES = ("init-context", "plan-work", "implement-work", "verify-work", "docs-research")
REQUIRED_PATHS = "README.md AGENTS.md docs/architecture.md docs/verification.md docs/subagents.md docs/mcp-policy.md docs/start-workflow.md docs/release-checklist.md docs/context-budget.md docs/tool-spec.md docs/workflow.md .codex/config.toml .codex/hooks.json .codex/hooks/common.py .codex/hooks/user_prompt_submit.py .codex/hooks/pre_tool_policy.py .codex/hooks/stop_guard.py harness/core/intake.py harness/core/task_classifier.py harness/core/context_budget.py harness/core/tool_router.py harness/core/config.py harness/core/registry.py harness/core/packet.py harness/core/trace.py harness/core/cache.py harness/tools/file_tools.py harness/tools/web_tools.py harness/tools/pdf_tools.py harness/tools/archive_tools.py harness/tools/data_tools.py harness/tools/run_tools.py harness/adapters/base.py harness/adapters/evaluator.py harness/adapters/submission_formatter.py state/brief.md state/goals.json state/task-state.json state/ledger.jsonl state/summaries/.gitkeep schemas/goal.schema.json schemas/task-state.schema.json tests/fixtures/hook-payload-destructive-variants.json".split()
class HarnessError(Exception):
    pass
def repo_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path
def read_json(path: Path) -> JsonValue:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HarnessError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HarnessError(f"invalid JSON in {path}: {exc}") from exc
def require_mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise HarnessError(f"{label} must be an object")
    return value
def require_list(value: JsonValue, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise HarnessError(f"{label} must be an array")
    return value
def text_field(mapping: dict[str, JsonValue], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HarnessError(f"{label} missing text field: {key}")
    return value
def check_required_paths() -> None:
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    for skill in SKILL_NAMES:
        if not (ROOT / ".agents" / "skills" / skill / "SKILL.md").exists():
            missing.append(f".agents/skills/{skill}/SKILL.md")
    if missing:
        raise HarnessError(f"missing required paths: {', '.join(missing)}")
def check_toml(path: Path) -> None:
    try:
        with path.open("rb") as config_file:
            tomllib.load(config_file)
    except OSError as exc:
        raise HarnessError(f"cannot read TOML {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise HarnessError(f"invalid TOML in {path}: {exc}") from exc
def check_json_files() -> None:
    for path in "state/goals.json state/task-state.json schemas/goal.schema.json schemas/task-state.schema.json .codex/hooks.json tests/fixtures/task-state-valid.json tests/fixtures/task-state-block-stop.json tests/fixtures/hook-payload-safe.json tests/fixtures/hook-payload-destructive.json tests/fixtures/hook-payload-destructive-variants.json".split():
        read_json(ROOT / path)
def parse_frontmatter(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise HarnessError(f"cannot read skill {path}: {exc}") from exc
    if not lines or lines[0].strip() != "---":
        raise HarnessError(f"{path} missing YAML frontmatter")
    end_index = -1
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index == -1:
        raise HarnessError(f"{path} has unterminated YAML frontmatter")
    fields: dict[str, str] = {}
    for line in lines[1:end_index]:
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip("\"'")
    for key in ("name", "description"):
        if not fields.get(key):
            raise HarnessError(f"{path} missing frontmatter field: {key}")
    return fields
def check_skill_file(path: Path) -> None:
    parse_frontmatter(path)
    text = path.read_text(encoding="utf-8")
    for heading in ("## Steps", "## Output", "## Boundaries"):
        if heading not in text:
            raise HarnessError(f"{path} missing section: {heading}")
def check_skills() -> None:
    for root in (ROOT / ".agents/skills",):
        found = sorted(path.parent.name for path in root.glob("*/SKILL.md"))
        if found != sorted(SKILL_NAMES):
            raise HarnessError(f"{root} has unexpected skills: {found}")
        for skill_path in root.glob("*/SKILL.md"):
            check_skill_file(skill_path)
def check_state(path: Path) -> None:
    state = require_mapping(read_json(path), str(path))
    goals = require_list(state.get("goals"), "goals")
    for index, goal_value in enumerate(goals):
        goal = require_mapping(goal_value, f"goal {index}")
        goal_id = text_field(goal, "id", f"goal {index}")
        status = text_field(goal, "status", goal_id)
        evidence = goal.get("evidence")
        if status not in DONE_STATUSES and not (isinstance(evidence, list) and evidence):
            raise HarnessError(f"unfinished goal missing evidence: {goal_id}")
def plugin_root_for(manifest_path: Path) -> Path:
    return manifest_path.parent.parent if manifest_path.parent.name == ".codex-plugin" else manifest_path.parent
def check_plugin_manifest(path: Path) -> None:
    manifest = require_mapping(read_json(path), str(path))
    for key in ("name", "version", "description", "author", "repository", "license", "skills", "interface"):
        if key not in manifest:
            raise HarnessError(f"{path} missing plugin field: {key}")
    if text_field(manifest, "name", "plugin") != "base-harness" and path == ROOT / "plugins/base-harness/.codex-plugin/plugin.json":
        raise HarnessError("plugin name must be base-harness")
    if not re.fullmatch(r"\d+\.\d+\.\d+", text_field(manifest, "version", "plugin")):
        raise HarnessError(f"{path} version must be semantic")
    author = require_mapping(manifest.get("author"), "author")
    text_field(author, "name", "author")
    interface = require_mapping(manifest.get("interface"), "interface")
    for key in ("displayName", "shortDescription", "longDescription", "developerName", "category"):
        text_field(interface, key, "interface")
    skills = text_field(manifest, "skills", "plugin")
    skills_root = plugin_root_for(path) / skills
    if path == ROOT / "plugins/base-harness/.codex-plugin/plugin.json":
        files = sorted(skills_root.glob("*/SKILL.md"))
        if len(files) != len(SKILL_NAMES):
            raise HarnessError(f"plugin skills path has {len(files)} skills")
def check_marketplace() -> None:
    marketplace = require_mapping(read_json(ROOT / ".agents/plugins/marketplace.json"), "marketplace")
    plugins = require_list(marketplace.get("plugins"), "plugins")
    if not plugins:
        raise HarnessError("marketplace has no plugins")
    for plugin_value in plugins:
        plugin = require_mapping(plugin_value, "plugin")
        source = require_mapping(plugin.get("source"), "plugin source")
        if text_field(source, "source", "plugin source") == "local":
            path = repo_path(Path(text_field(source, "path", "plugin source")))
            if not (path / ".codex-plugin/plugin.json").exists():
                raise HarnessError(f"marketplace path missing plugin manifest: {path}")
def check_hooks_config() -> None:
    config = require_mapping(read_json(ROOT / ".codex/hooks.json"), "hooks config")
    for legacy_key in ("UserPromptSubmit", "PreToolUse", "Stop"):
        if legacy_key in config:
            raise HarnessError("hooks.json must use top-level hooks object")
    hooks = require_mapping(config.get("hooks"), "hooks")
    for key in ("UserPromptSubmit", "PreToolUse", "Stop"):
        groups = require_list(hooks.get(key), key)
        for group_value in groups:
            group = require_mapping(group_value, key)
            for handler_value in require_list(group.get("hooks"), f"{key}.hooks"):
                handler = require_mapping(handler_value, f"{key}.handler")
                if text_field(handler, "type", key) != "command":
                    raise HarnessError(f"{key} handler must be command")
                text_field(handler, "command", key)
                timeout = handler.get("timeout")
                if not isinstance(timeout, int) or timeout < 1 or timeout > 600:
                    raise HarnessError(f"{key} timeout must be seconds")
    if "git rev-parse --show-toplevel" not in (ROOT / ".codex/hooks.json").read_text(encoding="utf-8"):
        raise HarnessError("hooks must resolve from repository root")
def run_case(args: list[str], want_success: bool, token: str, stdin: str | None = None) -> None:
    result = subprocess.run([sys.executable, *args], cwd=ROOT, input=stdin, capture_output=True, text=True)
    output = result.stdout + result.stderr
    if want_success and result.returncode != 0:
        raise HarnessError(f"command failed unexpectedly: {' '.join(args)}")
    if not want_success and result.returncode == 0:
        raise HarnessError(f"command passed unexpectedly: {' '.join(args)}")
    if token not in output:
        raise HarnessError(f"missing token {token} from {' '.join(args)}")
def run_stop_success() -> None:
    result = subprocess.run([sys.executable, ".codex/hooks/stop_guard.py", "--state", "tests/fixtures/task-state-valid.json"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise HarnessError("stop guard valid state failed")
    try:
        data = require_mapping(json.loads(result.stdout), "stop stdout")
    except json.JSONDecodeError as exc:
        raise HarnessError("stop guard success stdout must be JSON") from exc
    if data.get("continue") is not True:
        raise HarnessError("stop guard success must emit JSON continue true")
def check_hook_behavior() -> None:
    run_stop_success()
    run_case([".codex/hooks/stop_guard.py", "--state", "tests/fixtures/task-state-block-stop.json"], False, "BLOCK_STOP")
    run_case([".codex/hooks/user_prompt_submit.py", "--payload", "tests/fixtures/user-prompt-safe.json"], True, "OK_PROMPT")
    run_case([".codex/hooks/user_prompt_submit.py", "--payload", "tests/fixtures/user-prompt-secret.json"], False, "BLOCK_PROMPT")
    run_case([".codex/hooks/pre_tool_policy.py", "--payload", "tests/fixtures/hook-payload-safe.json"], True, "OK_TOOL")
    run_case([".codex/hooks/pre_tool_policy.py", "--payload", "tests/fixtures/hook-payload-destructive.json"], False, "BLOCK_TOOL")
    variants = require_mapping(read_json(ROOT / "tests/fixtures/hook-payload-destructive-variants.json"), "variants")
    for item in require_list(variants.get("cases"), "variant cases"):
        payload = require_mapping(require_mapping(item, "variant").get("payload"), "variant payload")
        run_case([".codex/hooks/pre_tool_policy.py"], False, "BLOCK_TOOL", json.dumps(payload))
def check_all() -> None:
    check_required_paths()
    check_json_files()
    check_toml(ROOT / ".codex/config.toml")
    check_skills()
    check_state(ROOT / "state/task-state.json")
    check_hooks_config()
    check_hook_behavior()
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skills-only", action="store_true")
    parser.add_argument("--plugin-only", action="store_true")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--skill-file", type=Path)
    parser.add_argument("--plugin-manifest", type=Path)
    parser.add_argument("--config", type=Path)
    return parser.parse_args()
def main() -> int:
    args = parse_args()
    try:
        if args.state:
            check_state(repo_path(args.state))
        elif args.skill_file:
            check_skill_file(repo_path(args.skill_file))
        elif args.plugin_manifest:
            check_plugin_manifest(repo_path(args.plugin_manifest))
        elif args.config:
            check_toml(repo_path(args.config))
        elif args.skills_only:
            check_skills()
        elif args.plugin_only:
            check_plugin_manifest(ROOT / "plugins/base-harness/.codex-plugin/plugin.json")
            check_marketplace()
        else:
            check_all()
    except HarnessError as exc:
        print(f"base harness validation failed: {exc}", file=sys.stderr)
        return 1
    print("base harness validation passed")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())

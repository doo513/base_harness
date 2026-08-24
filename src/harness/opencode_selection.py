from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import argparse
import json
import re
import shlex
import subprocess
import sys
import tempfile
import tomllib

from harness.opencode_adapter import DEFAULT_OPENCODE_AGENT


class OpenCodeSelectionError(RuntimeError):
    pass


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_MODEL_REF_RE = re.compile(r"^[^\s/]+/[^\s]+$")
_ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class OpenCodeModelInfo:
    ref: str
    provider: str
    model_id: str
    name: str | None
    context_window: int | None
    input_limit: int | None
    output_limit: int | None
    cost_input: float | None
    cost_output: float | None
    explicitly_free: bool | None
    metadata: dict[str, Any]

    def label(self) -> str:
        free = "free" if self.explicitly_free is True else "paid" if self.explicitly_free is False else "cost ?"
        limit = f" · ctx {self.context_window}" if self.context_window else ""
        display = self.name or self.ref
        return f"{display} [{free}{limit}]"


def _strip_ansi(value: str) -> str:
    return _ANSI_RE.sub("", value)


def _positive_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _cost_status(cost: Any) -> tuple[float | None, float | None, bool | None]:
    """Recognize free only when input/output costs are explicitly present as zero."""
    if isinstance(cost, dict):
        input_cost = _finite_number(cost.get("input"))
        output_cost = _finite_number(cost.get("output"))
        if input_cost is not None and output_cost is not None:
            return input_cost, output_cost, input_cost == 0.0 and output_cost == 0.0
        return input_cost, output_cost, None
    if isinstance(cost, list) and cost:
        rows = [item for item in cost if isinstance(item, dict)]
        if not rows:
            return None, None, None
        inputs = [_finite_number(item.get("input")) for item in rows]
        outputs = [_finite_number(item.get("output")) for item in rows]
        if all(value is not None for value in inputs + outputs):
            input_cost = max(value for value in inputs if value is not None)
            output_cost = max(value for value in outputs if value is not None)
            return input_cost, output_cost, all(value == 0.0 for value in inputs + outputs if value is not None)
    return None, None, None


def _metadata_to_info(ref: str, metadata: dict[str, Any] | None) -> OpenCodeModelInfo:
    provider, model_id = ref.split("/", 1)
    data = dict(metadata or {})
    limit = data.get("limit") if isinstance(data.get("limit"), dict) else {}
    cost_input, cost_output, explicitly_free = _cost_status(data.get("cost"))
    name = data.get("name") if isinstance(data.get("name"), str) and data.get("name").strip() else None
    return OpenCodeModelInfo(
        ref=ref,
        provider=provider,
        model_id=model_id,
        name=name,
        context_window=_positive_int(limit.get("context")),
        input_limit=_positive_int(limit.get("input")),
        output_limit=_positive_int(limit.get("output")),
        cost_input=cost_input,
        cost_output=cost_output,
        explicitly_free=explicitly_free,
        metadata=data,
    )


def parse_opencode_models_verbose(stdout: str) -> tuple[OpenCodeModelInfo, ...]:
    """Parse the `model-ref` + pretty JSON sequence from `opencode models --verbose`."""
    lines = [_strip_ansi(line).rstrip() for line in stdout.splitlines()]
    items: list[OpenCodeModelInfo] = []
    index = 0
    while index < len(lines):
        ref = lines[index].strip()
        if not _MODEL_REF_RE.fullmatch(ref):
            index += 1
            continue
        index += 1
        metadata: dict[str, Any] | None = None
        if index < len(lines) and lines[index].lstrip().startswith("{"):
            buffer: list[str] = []
            while index < len(lines):
                buffer.append(lines[index])
                index += 1
                try:
                    decoded = json.loads("\n".join(buffer))
                except json.JSONDecodeError:
                    continue
                if isinstance(decoded, dict):
                    metadata = decoded
                break
        items.append(_metadata_to_info(ref, metadata))
    unique: dict[str, OpenCodeModelInfo] = {}
    for item in items:
        unique[item.ref] = item
    return tuple(unique[key] for key in sorted(unique))


def list_opencode_models(
    *,
    binary: str = "opencode",
    provider: str | None = "opencode",
    refresh: bool = False,
    timeout_seconds: float = 30.0,
) -> tuple[OpenCodeModelInfo, ...]:
    if not binary.strip():
        raise OpenCodeSelectionError("OpenCode binary must not be empty")
    if timeout_seconds <= 0:
        raise OpenCodeSelectionError("OpenCode model discovery timeout must be positive")
    argv = [binary, "models"]
    if provider:
        argv.append(provider)
    argv.append("--verbose")
    if refresh:
        argv.append("--refresh")
    try:
        proc = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            timeout=float(timeout_seconds),
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OpenCodeSelectionError("OpenCode model discovery timed out") from exc
    except OSError as exc:
        raise OpenCodeSelectionError(f"OpenCode model discovery failed to start: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-2000:]
        raise OpenCodeSelectionError(f"OpenCode model discovery failed ({proc.returncode}): {detail}")
    items = parse_opencode_models_verbose(proc.stdout)
    if provider:
        items = tuple(item for item in items if item.provider == provider)
    if not items:
        scope = f" provider={provider}" if provider else ""
        raise OpenCodeSelectionError(f"OpenCode returned no selectable models for{scope}")
    return items


def _base_config_text() -> str:
    return (
        'profile = "software"\n'
        'run_dir = "./run"\n'
        'acceptance_commands = []\n\n'
        '[workspace]\n'
        'root = "."\n\n'
        '[security]\n'
        'execution_backend = "local"\n'
        'strict_layout = false\n'
        'strict_tool_isolation = false\n'
        'network_policy = "allow"\n'
        'require_sealed_oracle = false\n'
        'require_oracle_isolation = false\n'
    )


def _set_top_level(text: str, key: str, value: str) -> str:
    lines = text.splitlines(keepends=True)
    first_table = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    for i in range(first_table):
        if pattern.match(lines[i]):
            newline = "\n" if lines[i].endswith("\n") else ""
            lines[i] = f"{key} = {value}{newline}"
            return "".join(lines)
    lines.insert(first_table, f"{key} = {value}\n")
    return "".join(lines)


def _remove_model_route(text: str, alias: str) -> str:
    prefix = f"models.{alias}"
    output: list[str] = []
    skip = False
    for line in text.splitlines(keepends=True):
        match = re.match(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?$", line)
        if match:
            name = match.group(1).strip()
            skip = name == prefix or name.startswith(prefix + ".")
        if not skip:
            output.append(line)
    return "".join(output).rstrip() + "\n"


def _output_reserve(model: OpenCodeModelInfo) -> int:
    if model.output_limit is not None:
        return max(256, min(2048, model.output_limit))
    return 2048


def _adapter_safety_margin(model: OpenCodeModelInfo) -> int:
    """Reserve space for OpenCode's own transport/system envelope.

    This is deliberately conservative metadata, not an assertion of exact
    OpenCode prompt-token overhead. Actual provider usage remains telemetry.
    """
    if model.context_window is None:
        return 2048
    return min(4096, max(512, model.context_window // 16))


def configure_opencode_model(
    config_path: str | Path,
    *,
    model: OpenCodeModelInfo,
    alias: str = "opencode",
    binary: str = "opencode",
    agent: str = DEFAULT_OPENCODE_AGENT,
    timeout_seconds: float = 240.0,
    make_default: bool = True,
) -> Path:
    alias = alias.strip()
    if not alias or not _ALIAS_RE.fullmatch(alias):
        raise OpenCodeSelectionError("model alias must use letters, numbers, '_' or '-'")
    if not binary.strip() or not agent.strip():
        raise OpenCodeSelectionError("OpenCode binary and agent must not be empty")
    if timeout_seconds <= 0:
        raise OpenCodeSelectionError("OpenCode timeout must be positive")

    path = Path(config_path).expanduser()
    text = path.read_text(encoding="utf-8") if path.exists() else _base_config_text()
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise OpenCodeSelectionError(f"existing Harness config is invalid TOML: {exc}") from exc
    models = parsed.get("models") if isinstance(parsed.get("models"), dict) else {}
    existing = models.get(alias) if isinstance(models, dict) else None
    if isinstance(existing, dict):
        options = existing.get("options") if isinstance(existing.get("options"), dict) else {}
        if options.get("adapter") != "opencode":
            raise OpenCodeSelectionError(
                f"model alias {alias!r} already belongs to a non-OpenCode route; choose another alias"
            )

    text = _remove_model_route(text, alias)
    command = shlex.join([
        sys.executable,
        "-m",
        "harness.opencode_adapter",
        "--binary",
        binary,
        "--model",
        model.ref,
        "--agent",
        agent,
        "--timeout",
        f"{float(timeout_seconds):g}",
    ])
    output_reserve = _output_reserve(model)
    safety_margin = _adapter_safety_margin(model)
    block = [
        "",
        f"[models.{alias}]",
        'provider = "command"',
        f"model = {json.dumps(model.ref)}",
        f"command = {json.dumps(command)}",
        f"timeout_seconds = {float(timeout_seconds):g}",
        "",
        f"[models.{alias}.options]",
        'adapter = "opencode"',
        f"catalog_provider = {json.dumps(model.provider)}",
        f"catalog_model_id = {json.dumps(model.model_id)}",
        f"opencode_binary = {json.dumps(binary)}",
        f"opencode_agent = {json.dumps(agent)}",
        f"reserved_output_tokens = {output_reserve}",
        f"context_safety_margin_tokens = {safety_margin}",
        'context_safety_margin_source = "opencode_adapter_overhead_guard"',
    ]
    if model.name:
        block.append(f"catalog_name = {json.dumps(model.name)}")
    if model.context_window:
        block.append(f"context_window = {model.context_window}")
    if model.input_limit:
        block.append(f"catalog_input_limit = {model.input_limit}")
    if model.output_limit:
        block.append(f"catalog_output_limit = {model.output_limit}")
    if model.explicitly_free is not None:
        block.append(f"catalog_explicitly_free = {'true' if model.explicitly_free else 'false'}")
    if model.cost_input is not None:
        block.append(f"catalog_cost_input = {model.cost_input:g}")
    if model.cost_output is not None:
        block.append(f"catalog_cost_output = {model.cost_output:g}")
    block.append("")
    text = text.rstrip() + "\n" + "\n".join(block)
    if make_default:
        text = _set_top_level(text, "default_model", json.dumps(alias))
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise OpenCodeSelectionError(f"generated Harness config is invalid TOML: {exc}") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(text)
        handle.flush()
    temporary.replace(path)
    return path


def choose_opencode_model(
    items: tuple[OpenCodeModelInfo, ...],
    *,
    prompt: Callable[[str], str] = input,
    free_first: bool = True,
) -> OpenCodeModelInfo:
    ordered = sorted(
        items,
        key=lambda item: (
            0 if free_first and item.explicitly_free is True else 1,
            item.ref,
        ),
    )
    if not ordered:
        raise OpenCodeSelectionError("no OpenCode models are available")
    for index, item in enumerate(ordered, start=1):
        print(f"  {index:>2}. {item.ref:<48} {item.label()}")
    while True:
        raw = prompt(f"OpenCode model [1-{len(ordered)}]: ").strip()
        if raw in {item.ref for item in ordered}:
            return next(item for item in ordered if item.ref == raw)
        try:
            selected = int(raw)
        except ValueError:
            print("Enter a model number or exact provider/model id.")
            continue
        if 1 <= selected <= len(ordered):
            return ordered[selected - 1]
        print("Model number is outside the displayed range.")


def interactive_select_opencode_model(
    config_path: str | Path,
    *,
    binary: str = "opencode",
    provider: str = "opencode",
    refresh: bool = False,
    alias: str = "opencode",
) -> OpenCodeModelInfo:
    items = list_opencode_models(binary=binary, provider=provider, refresh=refresh)
    selected = choose_opencode_model(items)
    configure_opencode_model(
        config_path,
        model=selected,
        alias=alias,
        binary=binary,
        make_default=True,
    )
    return selected


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover and select an OpenCode model for base_harness.")
    parser.add_argument("config", nargs="?", default="harness.toml")
    parser.add_argument("--binary", default="opencode")
    parser.add_argument("--provider", default="opencode")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--alias", default="opencode")
    args = parser.parse_args(argv)
    try:
        selected = interactive_select_opencode_model(
            args.config,
            binary=args.binary,
            provider=args.provider,
            refresh=args.refresh,
            alias=args.alias,
        )
    except OpenCodeSelectionError as exc:
        print(f"OpenCode model selection failed: {exc}", file=sys.stderr)
        return 2
    print(f"selected={selected.ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

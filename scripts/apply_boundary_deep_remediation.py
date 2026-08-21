from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="")


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    text = read(path)
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f"{path}: expected {count} occurrence(s), found {actual}: {old[:80]!r}")
    write(path, text.replace(old, new, count))


def regex(path: str, pattern: str, repl: str, *, count: int = 1, flags: int = re.S) -> None:
    text = read(path)
    new, actual = re.subn(pattern, repl, text, count=count, flags=flags)
    if actual != count:
        raise RuntimeError(f"{path}: expected {count} regex replacement(s), found {actual}: {pattern[:100]!r}")
    write(path, new)


# ---------------------------------------------------------------------------
# 1. TUI -> CLI security propagation: omission means "use CLI/config default".
# ---------------------------------------------------------------------------
replace(
    "src/harness/tui.py",
    '''    execution_backend: str = "local"\n    strict_layout: bool = False\n    strict_tool_isolation: bool = False\n    network_policy: str = "allow"\n    require_sealed_oracle: bool = False\n    sealed_oracle_root: str | None = None\n    require_oracle_isolation: bool = False\n    require_complete_provenance: bool = False\n''',
    '''    execution_backend: str | None = None\n    strict_layout: bool | None = None\n    strict_tool_isolation: bool | None = None\n    network_policy: str | None = None\n    require_sealed_oracle: bool | None = None\n    sealed_oracle_root: str | None = None\n    require_oracle_isolation: bool | None = None\n    require_complete_provenance: bool | None = None\n''',
)
replace(
    "src/harness/tui.py",
    '''        argv += [\n            "--profile", self.profile,\n            "--workspace", self.workspace,\n            "--run-dir", self.run_dir,\n            "--max-steps", str(self.max_steps),\n            "--execution-backend", self.execution_backend,\n            "--network-policy", self.network_policy,\n        ]\n''',
    '''        argv += [\n            "--profile", self.profile,\n            "--workspace", self.workspace,\n            "--run-dir", self.run_dir,\n            "--max-steps", str(self.max_steps),\n        ]\n        if self.execution_backend is not None:\n            argv += ["--execution-backend", self.execution_backend]\n        if self.network_policy is not None:\n            argv += ["--network-policy", self.network_policy]\n''',
)
replace(
    "src/harness/tui.py",
    '''        argv.append("--strict-layout" if self.strict_layout else "--no-strict-layout")\n        argv.append("--strict-tool-isolation" if self.strict_tool_isolation else "--no-strict-tool-isolation")\n        argv.append("--require-sealed-oracle" if self.require_sealed_oracle else "--no-require-sealed-oracle")\n        if self.require_oracle_isolation:\n            argv.append("--require-oracle-isolation")\n        if self.require_complete_provenance:\n            argv.append("--require-complete-provenance")\n''',
    '''        if self.strict_layout is not None:\n            argv.append("--strict-layout" if self.strict_layout else "--no-strict-layout")\n        if self.strict_tool_isolation is not None:\n            argv.append("--strict-tool-isolation" if self.strict_tool_isolation else "--no-strict-tool-isolation")\n        if self.require_sealed_oracle is not None:\n            argv.append("--require-sealed-oracle" if self.require_sealed_oracle else "--no-require-sealed-oracle")\n        if self.require_oracle_isolation:\n            argv.append("--require-oracle-isolation")\n        if self.require_complete_provenance:\n            argv.append("--require-complete-provenance")\n''',
)

# ---------------------------------------------------------------------------
# 2. TUI session hints, verified-manifest resume, and interruption freshness.
# ---------------------------------------------------------------------------
replace(
    "src/harness/tui_conversation.py",
    "from harness.task_intake import analyze_task_input\n",
    "from harness.task_intake import analyze_task_input\nfrom harness.core.storage import PersistenceError, RunManifestStore\n",
)
replace(
    "src/harness/tui_conversation.py",
    '''_COMPAT_COMMAND_DESCRIPTIONS = {\n    "/change": "Alias for /model",\n    "/models": "Alias for /model",\n    "/resume": "Resume by explicit run path",\n}\n\n\ndef _payload''',
    '''_COMPAT_COMMAND_DESCRIPTIONS = {\n    "/change": "Alias for /model",\n    "/models": "Alias for /model",\n    "/resume": "Resume by explicit run path",\n}\n\n_SESSION_HINT_NAME = "tui_session.json"\n_INTERRUPT_MARKER_NAME = "tui_interrupted.json"\n\n\ndef _read_json_dict(path: Path) -> dict[str, Any]:\n    try:\n        value = json.loads(path.read_text(encoding="utf-8"))\n    except (OSError, UnicodeError, json.JSONDecodeError):\n        return {}\n    return value if isinstance(value, dict) else {}\n\n\ndef _session_manifest(run_dir: Path) -> dict[str, Any]:\n    try:\n        body, _ = RunManifestStore(run_dir / "run_manifest.json").load_verified()\n    except PersistenceError:\n        return {}\n    return body\n\n\ndef _session_hint(run_dir: Path) -> dict[str, Any]:\n    return _read_json_dict(run_dir / _SESSION_HINT_NAME)\n\n\ndef _write_session_hint(spec: RunLaunchSpec) -> None:\n    run_dir = Path(spec.run_dir)\n    if not run_dir.exists():\n        return\n    body = {\n        "schema_version": 1,\n        "authority": "presentation_hint_only",\n        "config": spec.config,\n        "workspace": spec.workspace,\n        "profile": spec.profile,\n        "acceptance_commands": list(spec.acceptance_commands),\n        "task_revision": spec.task_revision,\n        "execution_backend": spec.execution_backend,\n        "strict_layout": spec.strict_layout,\n        "strict_tool_isolation": spec.strict_tool_isolation,\n        "network_policy": spec.network_policy,\n        "require_sealed_oracle": spec.require_sealed_oracle,\n        "sealed_oracle_root": spec.sealed_oracle_root,\n        "require_oracle_isolation": spec.require_oracle_isolation,\n        "require_complete_provenance": spec.require_complete_provenance,\n    }\n    (run_dir / _SESSION_HINT_NAME).write_text(\n        json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\\n",\n        encoding="utf-8",\n        newline="",\n    )\n\n\ndef _interrupt_marker(run_dir: Path) -> Path:\n    return run_dir / _INTERRUPT_MARKER_NAME\n\n\ndef _clear_interrupt_marker(run_dir: Path) -> None:\n    try:\n        _interrupt_marker(run_dir).unlink(missing_ok=True)\n    except OSError:\n        pass\n\n\ndef _write_interrupt_marker(run_dir: Path) -> None:\n    if not run_dir.exists():\n        return\n    try:\n        _interrupt_marker(run_dir).write_text(\n            json.dumps({\n                "schema_version": 1,\n                "authority": "presentation_hint_only",\n                "interrupted": True,\n            }, sort_keys=True) + "\\n",\n            encoding="utf-8",\n            newline="",\n        )\n    except OSError:\n        pass\n\n\ndef _resume_backend_from_manifest(config: dict[str, Any]) -> str | None:\n    for tool in config.get("tools", []):\n        if not isinstance(tool, dict):\n            continue\n        backend = tool.get("backend")\n        if not isinstance(backend, dict):\n            continue\n        name = str(backend.get("name") or "").lower()\n        if "namespace" in name and "linux" in name:\n            return "linux-namespace"\n    return None\n\n\ndef _session_resume_spec(state: legacy.AppState, run_dir: Path) -> RunLaunchSpec | None:\n    manifest = _session_manifest(run_dir)\n    if not manifest:\n        return None\n    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}\n    profile_desc = config.get("profile") if isinstance(config.get("profile"), dict) else {}\n    profile = str(profile_desc.get("name") or state.mode)\n    if profile not in {"software", "hackathon", "ctf", "demo"}:\n        return None\n    workspace = str(config.get("workspace") or state.workspace)\n    security = config.get("security") if isinstance(config.get("security"), dict) else {}\n    goal_desc = config.get("goal") if isinstance(config.get("goal"), dict) else {}\n    acceptance = goal_desc.get("acceptance") if isinstance(goal_desc.get("acceptance"), list) else []\n    hint = _session_hint(run_dir)\n\n    hinted_config = hint.get("config") if isinstance(hint.get("config"), str) else None\n    if hinted_config and Path(hinted_config).expanduser().exists():\n        config_path = hinted_config\n    else:\n        config_path = state.config if Path(state.config).expanduser().exists() else None\n\n    backend = hint.get("execution_backend") if isinstance(hint.get("execution_backend"), str) else None\n    if backend is None:\n        backend = _resume_backend_from_manifest(config)\n\n    def optional_bool(name: str) -> bool | None:\n        value = security.get(name)\n        return value if isinstance(value, bool) else None\n\n    return RunLaunchSpec(\n        config=config_path,\n        workspace=workspace,\n        run_dir=str(run_dir),\n        profile=profile,\n        acceptance_commands=tuple(str(item) for item in acceptance if isinstance(item, str)),\n        task_revision=(hint.get("task_revision") if isinstance(hint.get("task_revision"), str) else None),\n        execution_backend=backend,\n        strict_layout=optional_bool("strict_layout"),\n        strict_tool_isolation=optional_bool("strict_tool_isolation"),\n        network_policy=(security.get("network_policy") if isinstance(security.get("network_policy"), str) else None),\n        require_sealed_oracle=optional_bool("require_sealed_oracle"),\n        sealed_oracle_root=(hint.get("sealed_oracle_root") if isinstance(hint.get("sealed_oracle_root"), str) else None),\n        require_oracle_isolation=(hint.get("require_oracle_isolation") if isinstance(hint.get("require_oracle_isolation"), bool) else None),\n        require_complete_provenance=(hint.get("require_complete_provenance") if isinstance(hint.get("require_complete_provenance"), bool) else None),\n        resume=True,\n    )\n\n\ndef _payload''',
)
replace(
    "src/harness/tui_conversation.py",
    '''def _session_status(run_dir: Path) -> str:\n    result = _read_final_result(run_dir)\n''',
    '''def _session_status(run_dir: Path) -> str:\n    if _interrupt_marker(run_dir).exists():\n        return "interrupted"\n    result = _read_final_result(run_dir)\n''',
)
replace(
    "src/harness/tui_conversation.py",
    '''def _resume(state: legacy.AppState, run_dir: str) -> None:\n    if not run_dir:\n        legacy._print_error("Usage: /resume <run-dir>")\n        return\n    spec = RunLaunchSpec(\n        config=state.config if Path(state.config).expanduser().exists() else None,\n        workspace=state.workspace,\n        run_dir=run_dir,\n        profile=state.mode,\n        resume=True,\n    )\n    _run_spec(state, spec)\n''',
    '''def _resume(state: legacy.AppState, run_dir: str) -> None:\n    if not run_dir:\n        legacy._print_error("Usage: /resume <run-dir>")\n        return\n    resolved = Path(run_dir).expanduser().resolve()\n    spec = _session_resume_spec(state, resolved)\n    if spec is None:\n        legacy._print_error("Session manifest is missing, invalid, or incompatible with this TUI.")\n        return\n    _run_spec(state, spec)\n''',
)
replace(
    "src/harness/tui_conversation.py",
    '''    process = subprocess.Popen(\n        spec.command(),\n''',
    '''    process = subprocess.Popen(\n        spec.command(),\n''',
)
replace(
    "src/harness/tui_conversation.py",
    '''    for thread in threads:\n        thread.start()\n\n    interrupted = False\n''',
    '''    for thread in threads:\n        thread.start()\n    _clear_interrupt_marker(run_dir)\n\n    interrupted = False\n''',
)
replace(
    "src/harness/tui_conversation.py",
    '''    state.last_run = spec.run_dir\n    if interrupted:\n        legacy._print_note("Run interrupted. Persisted state remains available for /inspect or /sessions.")\n    elif process.returncode not in {0, None}:\n        message = next((line for line in reversed(stderr) if line.strip()), "runtime failed")\n        legacy._print_error(message)\n    _render_final_result(spec.run_dir)\n    return int(process.returncode or 0)\n''',
    '''    state.last_run = spec.run_dir\n    _write_session_hint(spec)\n    if interrupted:\n        _write_interrupt_marker(run_dir)\n        legacy._print_note("Run interrupted. Persisted state remains available for /inspect or /sessions.")\n        return int(process.returncode or 130)\n\n    _clear_interrupt_marker(run_dir)\n    if process.returncode not in {0, None}:\n        message = next((line for line in reversed(stderr) if line.strip()), "runtime failed")\n        legacy._print_error(message)\n    _render_final_result(spec.run_dir)\n    return int(process.returncode or 0)\n''',
)
replace(
    "src/harness/tui_conversation.py",
    '''        max_steps=30,\n        execution_backend="local",\n        network_policy="allow",\n        resume=False,\n''',
    '''        max_steps=30,\n        resume=False,\n''',
)
replace(
    "src/harness/tui_conversation.py",
    '''        cls = "class:good" if status == "completed" else "class:warn" if status == "stopped" else "class:muted"\n        legacy._emit((cls, f"  {'✓' if status == 'completed' else '◇'} {path.name:<22}"), ("class:muted", status))\n''',
    '''        cls = "class:good" if status == "completed" else "class:warn" if status in {"stopped", "interrupted"} else "class:muted"\n        marker = "✓" if status == "completed" else "■" if status == "interrupted" else "◇"\n        legacy._emit((cls, f"  {marker} {path.name:<22}"), ("class:muted", status))\n''',
)

# ---------------------------------------------------------------------------
# 3. Model/Actor failure taxonomy and deterministic token-aware preflight.
# ---------------------------------------------------------------------------
replace(
    "src/harness/core/controller.py",
    '''VALID_DECISIONS = {\n\n    "plan", "task", "propose", "verify_claim", "tool", "retrieve", "complete", "refute"\n}\n\n\n@dataclass\nclass Decision:\n''',
    '''VALID_DECISIONS = {\n\n    "plan", "task", "propose", "verify_claim", "tool", "retrieve", "complete", "refute"\n}\n\n\nclass DecisionValidationError(ValueError):\n    pass\n\n\nclass ActorProtocolError(ValueError):\n    pass\n\n\nclass ActorModelError(RuntimeError):\n    pass\n\n\nclass ActorContextBudgetError(RuntimeError):\n    pass\n\n\n@dataclass\nclass Decision:\n''',
)
replace(
    "src/harness/core/controller.py",
    '''    def validate(self) -> None:\n        if self.kind not in VALID_DECISIONS:\n''',
    '''    def validate(self) -> None:\n        try:\n            self._validate()\n        except DecisionValidationError:\n            raise\n        except ValueError as exc:\n            raise DecisionValidationError(str(exc)) from exc\n\n    def _validate(self) -> None:\n        if self.kind not in VALID_DECISIONS:\n''',
)
replace(
    "src/harness/core/controller.py",
    '''class ModelAdapter(Protocol):\n    def complete(self, *, system: str, user: str) -> str: ...\n\n\ndef _extract_json_object''',
    '''class ModelAdapter(Protocol):\n    def complete(self, *, system: str, user: str) -> str: ...\n\n\ndef _estimate_actor_tokens(text: str) -> int:\n    """Conservative tokenizer-independent preflight estimate.\n\n    ASCII-heavy JSON/code is budgeted at roughly three characters/token while\n    non-ASCII text is budgeted at one code point/token, then a 20% safety\n    margin plus framing slack is applied. Provider-reported usage remains the\n    source of truth after a request; this estimator exists only to avoid known\n    context-window overflow loops before a request is sent.\n    """\n    ascii_chars = sum(1 for ch in text if ord(ch) < 128)\n    non_ascii_chars = len(text) - ascii_chars\n    base = (ascii_chars + 2) // 3 + non_ascii_chars\n    return max(1, (base * 6 + 4) // 5 + 16)\n\n\ndef _model_max_input_tokens(model: Any) -> int | None:\n    accessor = getattr(model, "context_budget", None)\n    if not callable(accessor):\n        return None\n    budget = accessor()\n    if budget is None:\n        return None\n    value = getattr(budget, "max_input_tokens", None)\n    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:\n        raise ActorContextBudgetError("model context budget has invalid max_input_tokens")\n    return value\n\n\ndef _serialize_actor_user(goal: Any, context: Any) -> str:\n    return json.dumps({"goal": goal, "context": context}, ensure_ascii=False, default=str)\n\n\ndef _compile_actor_user(model: Any, system: str, goal: Any, context: Any) -> str:\n    max_input_tokens = _model_max_input_tokens(model)\n    raw = _serialize_actor_user(goal, context)\n    if max_input_tokens is None:\n        return raw\n\n    system_tokens = _estimate_actor_tokens(system)\n    target_user_tokens = max_input_tokens - system_tokens\n    if target_user_tokens <= 128:\n        raise ActorContextBudgetError(\n            f"configured model context cannot fit mandatory system contract: "\n            f"max_input={max_input_tokens}, system_estimate={system_tokens}"\n        )\n    if _estimate_actor_tokens(raw) <= target_user_tokens:\n        return raw\n\n    # Work on the serialized model-visible projection only. Durable state is not\n    # mutated by compaction. Lower-authority/redundant views are removed first.\n    candidate = json.loads(json.dumps(context, ensure_ascii=False, default=str))\n\n    def render() -> str:\n        return _serialize_actor_user(goal, candidate)\n\n    def fits() -> bool:\n        return _estimate_actor_tokens(render()) <= target_user_tokens\n\n    for optional_key in ("active_context", "project_memory", "retrieval"):\n        candidate.pop(optional_key, None)\n        if fits():\n            return render()\n\n    untrusted = candidate.get("untrusted") if isinstance(candidate.get("untrusted"), dict) else {}\n    for optional_key in ("refuted_hypotheses", "unknowns"):\n        if optional_key in untrusted:\n            untrusted[optional_key] = {} if isinstance(untrusted[optional_key], dict) else []\n            if fits():\n                return render()\n\n    observations = untrusted.get("observations") if isinstance(untrusted.get("observations"), list) else None\n    while observations:\n        observations.pop()\n        if fits():\n            return render()\n\n    control = candidate.get("control") if isinstance(candidate.get("control"), dict) else {}\n    failures = control.get("recent_failures") if isinstance(control.get("recent_failures"), list) else None\n    while failures and len(failures) > 1:\n        failures.pop(0)\n        if fits():\n            return render()\n\n    hypotheses = untrusted.get("hypotheses") if isinstance(untrusted.get("hypotheses"), dict) else None\n    while hypotheses:\n        hypotheses.pop(next(reversed(hypotheses)))\n        if fits():\n            return render()\n\n    trusted = candidate.get("trusted") if isinstance(candidate.get("trusted"), dict) else {}\n    facts = trusted.get("facts") if isinstance(trusted.get("facts"), dict) else None\n    while facts and len(facts) > 1:\n        facts.pop(next(reversed(facts)))\n        if fits():\n            return render()\n\n    tools = candidate.get("tools") if isinstance(candidate.get("tools"), dict) else {}\n    for spec in tools.values():\n        if isinstance(spec, dict):\n            spec.pop("description", None)\n            spec.pop("description_truncated", None)\n            spec.pop("output_schema", None)\n            spec.pop("model_output_schema", None)\n    if fits():\n        return render()\n\n    raise ActorContextBudgetError(\n        f"model context remains over budget after deterministic compaction: "\n        f"max_input={max_input_tokens}, system_estimate={system_tokens}, "\n        f"user_estimate={_estimate_actor_tokens(render())}"\n    )\n\n\ndef _extract_json_object''',
)
replace(
    "src/harness/core/controller.py",
    '''    raise ValueError(f"model did not return valid JSON object: {raw[:150]!r}")\n''',
    '''    raise ActorProtocolError(f"model did not return valid JSON object: {raw[:150]!r}")\n''',
)
replace(
    "src/harness/core/controller.py",
    '''    def decide(self, goal, state, context):\n        user = json.dumps({"goal": goal, "context": context}, ensure_ascii=False, default=str)\n        raw = self.model.complete(system=self.SYSTEM, user=user)\n\n        # Retry once if raw response is completely empty. Provider-level retries\n''',
    '''    def _complete(self, user: str) -> str:\n        try:\n            return self.model.complete(system=self.SYSTEM, user=user)\n        except (ActorProtocolError, ActorContextBudgetError, DecisionValidationError, ActorModelError):\n            raise\n        except Exception as exc:\n            raise ActorModelError(f"model adapter failed: {type(exc).__name__}: {exc}") from exc\n\n    def decide(self, goal, state, context):\n        user = _compile_actor_user(self.model, self.SYSTEM, goal, context)\n        raw = self._complete(user)\n\n        # Retry once if raw response is completely empty. Provider-level retries\n''',
)
replace(
    "src/harness/core/controller.py",
    '''            raw = self.model.complete(system=self.SYSTEM, user=retry_prompt)\n''',
    '''            raw = self._complete(retry_prompt)\n''',
)

# Model gateway route metadata + context-length classification.
replace(
    "src/harness/model_gateway.py",
    '''@dataclass(frozen=True)\nclass ModelResponse:\n''',
    '''@dataclass(frozen=True)\nclass ModelContextBudget:\n    context_window: int\n    reserved_output_tokens: int\n    safety_margin_tokens: int\n\n    def __post_init__(self) -> None:\n        for name in ("context_window", "reserved_output_tokens", "safety_margin_tokens"):\n            value = getattr(self, name)\n            if not isinstance(value, int) or isinstance(value, bool) or value < 0:\n                raise ModelGatewayError(f"{name} must be a non-negative integer")\n        if self.context_window <= 0:\n            raise ModelGatewayError("context_window must be positive")\n        if self.reserved_output_tokens + self.safety_margin_tokens >= self.context_window:\n            raise ModelGatewayError("model context reserves leave no input budget")\n\n    @property\n    def max_input_tokens(self) -> int:\n        return self.context_window - self.reserved_output_tokens - self.safety_margin_tokens\n\n    def dump(self) -> dict[str, int]:\n        return {\n            "context_window": self.context_window,\n            "reserved_output_tokens": self.reserved_output_tokens,\n            "safety_margin_tokens": self.safety_margin_tokens,\n            "max_input_tokens": self.max_input_tokens,\n        }\n\n\n@dataclass(frozen=True)\nclass ModelResponse:\n''',
)
replace(
    "src/harness/model_gateway.py",
    '''            retryable = exc.code == 429 or 500 <= exc.code < 600\n            kind = "rate_limit" if exc.code == 429 else "http_error"\n''',
    '''            retryable = exc.code == 429 or 500 <= exc.code < 600\n            lower_detail = detail.casefold()\n            context_markers = (\n                "context length", "context size", "context window",\n                "too many tokens", "maximum context", "exceeds the available context",\n            )\n            if exc.code == 400 and any(marker in lower_detail for marker in context_markers):\n                kind = "context_length"\n            else:\n                kind = "rate_limit" if exc.code == 429 else "http_error"\n''',
)
replace(
    "src/harness/model_gateway.py",
    '''    def complete(self, *, system: str, user: str) -> str:\n        request = ModelRequest(system=system, user=user)\n''',
    '''    def context_budget(self) -> ModelContextBudget | None:\n        config = self.models[self.default_model]\n        options = dict(config.options)\n        raw_window = options.get("context_window", options.get("num_ctx"))\n        if raw_window is None:\n            return None\n        if not isinstance(raw_window, int) or isinstance(raw_window, bool) or raw_window <= 0:\n            raise ModelGatewayError("model options.context_window/num_ctx must be a positive integer")\n\n        reserved = options.get("reserved_output_tokens")\n        if reserved is None:\n            max_tokens = options.get("max_tokens")\n            reserved = max_tokens if isinstance(max_tokens, int) and not isinstance(max_tokens, bool) and max_tokens > 0 else min(1024, max(256, raw_window // 8))\n        if not isinstance(reserved, int) or isinstance(reserved, bool) or reserved < 0:\n            raise ModelGatewayError("model options.reserved_output_tokens must be a non-negative integer")\n\n        safety = options.get("context_safety_margin_tokens", max(128, raw_window // 20))\n        if not isinstance(safety, int) or isinstance(safety, bool) or safety < 0:\n            raise ModelGatewayError("model options.context_safety_margin_tokens must be a non-negative integer")\n        return ModelContextBudget(raw_window, reserved, safety)\n\n    def complete(self, *, system: str, user: str) -> str:\n        request = ModelRequest(system=system, user=user)\n''',
)
replace(
    "src/harness/model_gateway.py",
    '''            "models": {\n''',
    '''            "context_budget": self.context_budget().dump() if self.context_budget() is not None else None,\n            "models": {\n''',
)

# Failure kinds and routing.
replace(
    "src/harness/core/failures.py",
    '''    IMPLEMENTATION_ERROR = "implementation_error"\n    NO_PROGRESS = "no_progress"\n''',
    '''    IMPLEMENTATION_ERROR = "implementation_error"\n    MODEL_PROVIDER_ERROR = "model_provider_error"\n    MODEL_PROTOCOL_ERROR = "model_protocol_error"\n    ACTOR_WORKFLOW_ERROR = "actor_workflow_error"\n    CONTEXT_BUDGET_EXCEEDED = "context_budget_exceeded"\n    APPROVAL_REQUIRED = "approval_required"\n    NO_PROGRESS = "no_progress"\n''',
)
replace(
    "src/harness/core/failures.py",
    '''        FailureKind.IMPLEMENTATION_ERROR: RecoveryAction.REPAIR,\n        FailureKind.NO_PROGRESS: RecoveryAction.REPLAN,\n''',
    '''        FailureKind.IMPLEMENTATION_ERROR: RecoveryAction.REPAIR,\n        FailureKind.MODEL_PROVIDER_ERROR: RecoveryAction.RETRY,\n        FailureKind.MODEL_PROTOCOL_ERROR: RecoveryAction.REPAIR,\n        FailureKind.ACTOR_WORKFLOW_ERROR: RecoveryAction.REPLAN,\n        FailureKind.CONTEXT_BUDGET_EXCEEDED: RecoveryAction.CHECKPOINT_STOP,\n        FailureKind.APPROVAL_REQUIRED: RecoveryAction.CHECKPOINT_STOP,\n        FailureKind.NO_PROGRESS: RecoveryAction.REPLAN,\n''',
)
replace(
    "src/harness/core/failures.py",
    '''        FailureKind.BUDGET_EXCEEDED,\n        FailureKind.PERSISTENCE_ERROR,\n''',
    '''        FailureKind.BUDGET_EXCEEDED,\n        FailureKind.CONTEXT_BUDGET_EXCEEDED,\n        FailureKind.APPROVAL_REQUIRED,\n        FailureKind.PERSISTENCE_ERROR,\n''',
)

# Runtime classification.
replace(
    "src/harness/core/runtime_execution.py",
    '''from .agent_control import AgentControlError\n''',
    '''from .agent_control import AgentControlError\nfrom .controller import (\n    ActorContextBudgetError, ActorModelError, ActorProtocolError,\n    DecisionValidationError,\n)\n''',
)
replace(
    "src/harness/core/runtime_execution.py",
    '''                    FailureKind.NO_PROGRESS,\n                    f"actor workflow plan rejected: {exc}",\n''',
    '''                    FailureKind.ACTOR_WORKFLOW_ERROR,\n                    f"actor workflow plan rejected: {exc}",\n''',
)
replace(
    "src/harness/core/runtime_execution.py",
    '''                    FailureKind.NO_PROGRESS,\n                    f"actor workflow task update rejected: {exc}",\n''',
    '''                    FailureKind.ACTOR_WORKFLOW_ERROR,\n                    f"actor workflow task update rejected: {exc}",\n''',
)
replace(
    "src/harness/core/runtime_execution.py",
    '''            if getattr(result, "security_violation", False):\n                self.metrics["security_violations"] += 1\n''',
    '''            if getattr(result, "approval_required", False):\n                self.fail(Failure(\n                    FailureKind.APPROVAL_REQUIRED,\n                    result.error or f"approval required for tool: {call.tool}",\n                    action=call.tool,\n                    signature_key=f"approval_required:{call.tool}",\n                ))\n            elif getattr(result, "security_violation", False):\n                self.metrics["security_violations"] += 1\n''',
)
regex(
    "src/harness/core/runtime_execution.py",
    r'''        try:\n            actor_state = HarnessState\.from_snapshot\(self\.state\.snapshot\(\)\)\n            context = self\._context\(\)\n            decision = self\.controller\.decide\(self\.goal\.goal, actor_state, context\)\n            decision\.validate\(\)\n        except \(PersistenceError, IntegrityError, ResumeConflict\) as exc:\n            self\.fail\(Failure\(\n                FailureKind\.PERSISTENCE_ERROR,\n                f"controller context/state integrity failure: \{exc\}",\n                action="controller_context",\n                signature_key="stage8:context_retrieval_integrity",\n            \)\)\n            return False\n        except Exception as exc:\n            self\.fail\(Failure\(FailureKind\.IMPLEMENTATION_ERROR, f"controller error: \{type\(exc\)\.__name__\}: \{exc\}"\)\)\n            return False\n''',
    '''        try:\n            actor_state = HarnessState.from_snapshot(self.state.snapshot())\n            context = self._context()\n        except (PersistenceError, IntegrityError, ResumeConflict) as exc:\n            self.fail(Failure(\n                FailureKind.PERSISTENCE_ERROR,\n                f"controller context/state integrity failure: {exc}",\n                action="controller_context",\n                signature_key="stage8:context_retrieval_integrity",\n            ))\n            return False\n        except Exception as exc:\n            self.fail(Failure(\n                FailureKind.IMPLEMENTATION_ERROR,\n                f"controller context construction error: {type(exc).__name__}: {exc}",\n                action="controller_context",\n            ))\n            return False\n\n        try:\n            decision = self.controller.decide(self.goal.goal, actor_state, context)\n            decision.validate()\n        except ActorContextBudgetError as exc:\n            self.fail(Failure(\n                FailureKind.CONTEXT_BUDGET_EXCEEDED,\n                str(exc),\n                action="controller_decision",\n                signature_key="model:context_budget",\n            ))\n            return False\n        except ActorModelError as exc:\n            self.fail(Failure(\n                FailureKind.MODEL_PROVIDER_ERROR,\n                str(exc),\n                action="controller_decision",\n                retry_safe=True,\n                signature_key="model:provider",\n            ))\n            return False\n        except (ActorProtocolError, DecisionValidationError) as exc:\n            self.fail(Failure(\n                FailureKind.MODEL_PROTOCOL_ERROR,\n                str(exc),\n                action="controller_decision",\n                signature_key="model:protocol",\n            ))\n            return False\n        except Exception as exc:\n            self.fail(Failure(\n                FailureKind.IMPLEMENTATION_ERROR,\n                f"controller error: {type(exc).__name__}: {exc}",\n                action="controller_decision",\n            ))\n            return False\n''',
)

# ---------------------------------------------------------------------------
# 4. MCP stdio: stderr is a legal logging channel and must be drained.
# ---------------------------------------------------------------------------
replace(
    "src/harness/mcp_gateway.py",
    '''from dataclasses import dataclass\n''',
    '''from collections import deque\nfrom dataclasses import dataclass\n''',
)
replace(
    "src/harness/mcp_gateway.py",
    '''        self._reader: Thread | None = None\n        self._next_id = 1\n''',
    '''        self._reader: Thread | None = None\n        self._stderr_reader: Thread | None = None\n        self._stderr_tail: deque[str] = deque(maxlen=128)\n        self._next_id = 1\n''',
)
replace(
    "src/harness/mcp_gateway.py",
    '''        self._reader = Thread(target=self._reader_loop, name="mcp-stdio-reader", daemon=True)\n        self._reader.start()\n\n    def _reader_loop''',
    '''        self._reader = Thread(target=self._reader_loop, name="mcp-stdio-reader", daemon=True)\n        self._reader.start()\n        self._stderr_reader = Thread(target=self._stderr_loop, name="mcp-stderr-reader", daemon=True)\n        self._stderr_reader.start()\n\n    def _stderr_loop(self) -> None:\n        process = self.process\n        if process is None or process.stderr is None:\n            return\n        for line in process.stderr:\n            self._stderr_tail.append(line.rstrip()[:2000])\n\n    def stderr_tail(self) -> tuple[str, ...]:\n        return tuple(self._stderr_tail)\n\n    def _reader_loop''',
)
replace(
    "src/harness/mcp_gateway.py",
    '''        if process.poll() is None:\n            process.terminate()\n            try:\n                process.wait(timeout=1.0)\n            except subprocess.TimeoutExpired:\n                process.kill()\n                process.wait(timeout=1.0)\n''',
    '''        if process.poll() is None:\n            process.terminate()\n            try:\n                process.wait(timeout=1.0)\n            except subprocess.TimeoutExpired:\n                process.kill()\n                process.wait(timeout=1.0)\n        if self._reader is not None:\n            self._reader.join(timeout=0.5)\n        if self._stderr_reader is not None:\n            self._stderr_reader.join(timeout=0.5)\n''',
)

# ---------------------------------------------------------------------------
# 5. Task intake: report nouns alone do not imply a file-creation task.
# ---------------------------------------------------------------------------
replace(
    "src/harness/task_intake.py",
    '''_REPORT_TERMS = (\n    "보고서",\n    "리포트",\n    "report",\n    "analysis report",\n    "deep report",\n    "문서로 정리",\n    "문서 작성",\n)\n''',
    '''_REPORT_NOUN_TERMS = (\n    "보고서", "리포트", "report", "analysis report", "deep report", "문서",\n)\n_ARTIFACT_ACTION_TERMS = (\n    "써줘", "작성해", "작성하", "작성", "만들어", "만들어줘", "생성해", "생성하",\n    "저장해", "저장하", "문서로 정리", "write", "create", "generate", "save", "produce",\n)\n''',
)
replace(
    "src/harness/task_intake.py",
    '''def detect_artifact_target(task: str) -> str | None:\n    lowered = task.casefold()\n    if not any(term.casefold() in lowered for term in _REPORT_TERMS):\n        return None\n''',
    '''def detect_artifact_target(task: str) -> str | None:\n    lowered = task.casefold()\n    if not any(term.casefold() in lowered for term in _REPORT_NOUN_TERMS):\n        return None\n    if not any(term.casefold() in lowered for term in _ARTIFACT_ACTION_TERMS):\n        return None\n''',
)

# ---------------------------------------------------------------------------
# 6. Windows native portable CI.
# ---------------------------------------------------------------------------
workflow = read(".github/workflows/research-ci.yml")
if "windows-portable:" not in workflow:
    workflow += '''\n\n  windows-portable:\n    runs-on: windows-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.11'\n      - name: Install locked CI dependencies\n        shell: pwsh\n        run: |\n          python -m pip install -r requirements-ci.lock\n          python -m pip install -e . --no-deps\n          python -m pip check\n      - name: Portable Windows boundary gates\n        shell: pwsh\n        run: |\n          python -m compileall -q src tests\n          pytest -q tests/test_windows_portable_contract.py tests/test_tui_conversation_v2.py tests/test_integration_model_gateway.py tests/test_boundary_remediation.py\n'''
    write(".github/workflows/research-ci.yml", workflow)

# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------
text = read("tests/test_integration_tui.py")
if "test_tui_launch_spec_omits_security_overrides_by_default" not in text:
    text += '''\n\ndef test_tui_launch_spec_omits_security_overrides_by_default(tmp_path):\n    spec = RunLaunchSpec(\n        workspace=str(tmp_path),\n        run_dir=str(tmp_path / "run-defaults"),\n        profile="software",\n    )\n    command = spec.command(python_executable="python-test")\n    assert "--strict-layout" not in command\n    assert "--no-strict-layout" not in command\n    assert "--strict-tool-isolation" not in command\n    assert "--no-strict-tool-isolation" not in command\n    assert "--network-policy" not in command\n    assert "--require-sealed-oracle" not in command\n    assert "--no-require-sealed-oracle" not in command\n'''
    write("tests/test_integration_tui.py", text)

text = read("tests/test_tui_conversation_v2.py")
text = text.replace(
    '''    _recent_sessions,\n    _resolve_session,\n    _session_status,\n)\n''',
    '''    _recent_sessions,\n    _resolve_session,\n    _session_resume_spec,\n    _session_status,\n    _write_interrupt_marker,\n)\n''',
)
if "from harness.core.storage import RunManifestStore" not in text:
    text = text.replace("from harness import tui_visual as legacy\n", "from harness import tui_visual as legacy\nfrom harness.core.storage import RunManifestStore\n")
if "test_tui_v2_interrupted_marker_wins_over_stale_final_result" not in text:
    text += '''\n\ndef test_tui_v2_interrupted_marker_wins_over_stale_final_result(tmp_path):\n    run_dir = tmp_path / "run-interrupted"\n    run_dir.mkdir()\n    (run_dir / "final_result.json").write_text(json.dumps({"completed": True}), encoding="utf-8")\n    _write_interrupt_marker(run_dir)\n    assert _session_status(run_dir) == "interrupted"\n\n\ndef test_tui_v2_resume_spec_uses_verified_manifest_boundaries(tmp_path):\n    workspace = tmp_path / "persisted-workspace"\n    workspace.mkdir()\n    run_dir = tmp_path / "persisted-run"\n    run_dir.mkdir()\n    RunManifestStore(run_dir / "run_manifest.json").create({\n        "run_id": "abc",\n        "harness_version": __version__,\n        "model_revision": "model-x",\n        "config": {\n            "workspace": str(workspace),\n            "profile": {"name": "ctf"},\n            "goal": {"acceptance": ["python verify.py"]},\n            "security": {\n                "strict_layout": True,\n                "strict_tool_isolation": True,\n                "network_policy": "deny",\n                "require_sealed_oracle": False,\n            },\n            "tools": [],\n        },\n    })\n    state = AppState(workspace=str(tmp_path), config=str(tmp_path / "missing.toml"), mode="software")\n    spec = _session_resume_spec(state, run_dir)\n    assert spec is not None\n    assert Path(spec.workspace) == workspace.resolve()\n    assert spec.profile == "ctf"\n    assert spec.acceptance_commands == ("python verify.py",)\n    assert spec.strict_layout is True\n    assert spec.strict_tool_isolation is True\n    assert spec.network_policy == "deny"\n    assert spec.resume is True\n'''
write("tests/test_tui_conversation_v2.py", text)

text = read("tests/test_task_intake_artifact_contract.py")
if "test_task_intake_does_not_turn_report_review_into_creation" not in text:
    text += '''\n\ndef test_task_intake_does_not_turn_report_review_into_creation():\n    intake = analyze_task_input("이 보고서 내용을 확인해줘. 틀린 부분만 알려줘")\n    assert intake.artifact_target is None\n    assert intake.evidence_backed_artifact is False\n'''
    write("tests/test_task_intake_artifact_contract.py", text)

text = read("tests/test_integration_model_gateway.py")
text = text.replace(
    '''    ModelGateway,\n    ModelRequest,\n''',
    '''    ModelContextBudget,\n    ModelGateway,\n    ModelRequest,\n''',
)
if "test_model_gateway_exposes_configured_context_budget" not in text:
    text += '''\n\ndef test_model_gateway_exposes_configured_context_budget():\n    registry = ProviderRegistry()\n    provider = FakeProvider("fake", [ModelResponse(content="{}", provider_id="fake", model_id="m")])\n    registry.register("fake", lambda config, resolver: provider)\n    gateway = ModelGateway(\n        models={\n            "primary": ModelConfig(\n                provider="fake",\n                model="m",\n                options={\n                    "context_window": 4096,\n                    "reserved_output_tokens": 512,\n                    "context_safety_margin_tokens": 256,\n                },\n            )\n        },\n        default_model="primary",\n        registry=registry,\n    )\n    budget = gateway.context_budget()\n    assert isinstance(budget, ModelContextBudget)\n    assert budget.max_input_tokens == 3328\n'''
    write("tests/test_integration_model_gateway.py", text)

text = read("tests/test_integration_mcp_plugin.py")
if "def _stderr_heavy_server_script" not in text:
    insert = '''\n\ndef _stderr_heavy_server_script() -> str:\n    return textwrap.dedent(\n        f"""\n        import json, sys\n        MODERN = {MODERN_PROTOCOL_VERSION!r}\n        sys.stderr.write('x' * (256 * 1024))\n        sys.stderr.flush()\n        for line in sys.stdin:\n            msg = json.loads(line)\n            if msg.get('method') == 'server/discover':\n                out = {{'jsonrpc':'2.0','id':msg['id'],'result':{{'supportedVersions':[MODERN]}}}}\n            elif msg.get('method') == 'tools/list':\n                out = {{'jsonrpc':'2.0','id':msg['id'],'result':{{'tools':[]}}}}\n            else:\n                out = {{'jsonrpc':'2.0','id':msg['id'],'error':{{'code':-32601,'message':'not found'}}}}\n            print(json.dumps(out), flush=True)\n        """\n    )\n'''
    marker = "\ndef test_mcp_modern_discovery_preserves_schema_and_uses_operator_policy():\n"
    text = text.replace(marker, insert + marker)
if "test_mcp_stdio_drains_legal_stderr_logging_without_deadlock" not in text:
    text += '''\n\ndef test_mcp_stdio_drains_legal_stderr_logging_without_deadlock():\n    client = MCPStdioClient(\n        command=(sys.executable, "-u", "-c", _stderr_heavy_server_script()),\n        request_timeout_seconds=2.0,\n        probe_timeout_seconds=1.0,\n    )\n    try:\n        assert client.list_tools() == []\n        assert client.stderr_tail()\n    finally:\n        client.close()\n'''
write("tests/test_integration_mcp_plugin.py", text)

(ROOT / "tests/test_boundary_remediation.py").write_text('''from types import SimpleNamespace\n\nimport pytest\n\nfrom harness.core.controller import (\n    Decision, DecisionValidationError, LLMController, _estimate_actor_tokens,\n)\nfrom harness.core.failures import Failure, FailureKind, FailureRouter, RecoveryAction\n\n\nclass BudgetModel:\n    def __init__(self):\n        self.user = None\n\n    def context_budget(self):\n        return SimpleNamespace(max_input_tokens=5000)\n\n    def complete(self, *, system: str, user: str) -> str:\n        self.user = user\n        return '{"kind":"complete","payload":{"reason":"ok"}}'\n\n\ndef test_invalid_actor_decision_has_protocol_specific_exception():\n    with pytest.raises(DecisionValidationError):\n        Decision("tool", {"tool": "", "args": {}}).validate()\n\n\ndef test_context_budget_compacts_optional_views_before_model_request():\n    model = BudgetModel()\n    controller = LLMController(model)\n    context = {\n        "schema_version": "x",\n        "goal_contract": {"goal": "g", "acceptance": [], "constraints": [], "pinned_constraints": []},\n        "trusted": {"facts": {}},\n        "untrusted": {\n            "hypotheses": {},\n            "refuted_hypotheses": {},\n            "observations": [{"preview": "x" * 3000} for _ in range(8)],\n            "unknowns": [],\n        },\n        "control": {"recent_failures": [], "progress": {}},\n        "tools": {"read": {"description": "d" * 2000, "input_schema": {"type": "object"}}},\n        "active_context": {"noise": "a" * 10000},\n        "project_memory": {"noise": "m" * 10000},\n    }\n    decision = controller.decide("goal", None, context)\n    assert decision.kind == "complete"\n    assert model.user is not None\n    assert _estimate_actor_tokens(controller.SYSTEM) + _estimate_actor_tokens(model.user) <= 5000\n    assert 'active_context' not in model.user\n\n\ndef test_failure_router_separates_model_protocol_context_and_approval():\n    router = FailureRouter()\n    assert router.route(Failure(FailureKind.MODEL_PROTOCOL_ERROR, "bad json")) == RecoveryAction.REPAIR\n    assert router.route(Failure(FailureKind.MODEL_PROVIDER_ERROR, "offline", retry_safe=True)) == RecoveryAction.RETRY\n    assert router.route(Failure(FailureKind.CONTEXT_BUDGET_EXCEEDED, "too large")) == RecoveryAction.CHECKPOINT_STOP\n    assert router.route(Failure(FailureKind.APPROVAL_REQUIRED, "ask user")) == RecoveryAction.CHECKPOINT_STOP\n''', encoding="utf-8", newline="")

(ROOT / "tests/test_windows_portable_contract.py").write_text('''from harness.core.storage import ArtifactStore, atomic_write_text\n\n\ndef test_atomic_text_writer_preserves_exact_lf_bytes(tmp_path):\n    path = tmp_path / "exact.txt"\n    atomic_write_text(path, "alpha\\nbeta\\n")\n    assert path.read_bytes() == b"alpha\\nbeta\\n"\n\n\ndef test_artifact_store_round_trip_uses_exact_content_addressed_bytes(tmp_path):\n    store = ArtifactStore(tmp_path / "artifacts")\n    ref = store.put_text("sample.txt", "alpha\\nbeta\\n")\n    assert store.verified_read_bytes(ref) == b"alpha\\nbeta\\n"\n    resolved = store.resolve(ref)\n    resolved.write_bytes(resolved.read_bytes() + b"tamper")\n    try:\n        store.verified_read_bytes(ref)\n    except Exception as exc:\n        assert "hash mismatch" in str(exc)\n    else:\n        raise AssertionError("tampered artifact must fail closed")\n''', encoding="utf-8", newline="")

# Evidence-based review document.
(ROOT / "docs/tracks/integration-runtime/BOUNDARY_DEEP_REVIEW_2026-08-21.md").write_text('''# Boundary Deep Review — 2026-08-21\n\nStatus: remediation implementation target\n\n## Scope\n\nThis review re-checks the current `main/develop` flow at the boundaries most likely to fail in real use: TUI→CLI, model→controller→kernel, MCP stdio→tool runtime, task intake, persistence/resume, and platform CI. The Verified-State Kernel authority model is retained.\n\n## Confirmed findings and disposition\n\n| Boundary | Evidence | Risk | Disposition |\n| --- | --- | --- | --- |\n| TUI → CLI security | `RunLaunchSpec` emitted explicit `--no-strict-*` and `--network-policy allow` defaults, overriding CLI config defaults | High | Fixed: optional TUI overrides are omitted unless explicitly selected |\n| Session resume | `/resume` rebuilt a run from current TUI workspace/profile instead of persisted run metadata | High | Fixed: verified run manifest drives workspace/profile/security/acceptance; TUI hint preserves non-secret launch-only fields |\n| ESC interruption | TUI rendered `final_result.json` even after forcibly interrupting the CLI child, so a prior result could be stale | High | Fixed: interrupted runs get a presentation-only marker and do not render final result as current |\n| Model protocol taxonomy | malformed JSON/invalid decisions and actual implementation exceptions could collapse into `IMPLEMENTATION_ERROR` | High | Fixed: provider/protocol/workflow/context-budget failures are first-class |\n| Context window | Stage-07 is character/item bounded but route context windows were not used before model invocation | High | Fixed for configured routes: provider/model context budget + deterministic lower-priority context compaction |\n| MCP stdio stderr | MCP permits servers to log to stderr; client piped stderr without draining it | Medium/High | Fixed: bounded background stderr drain prevents pipe backpressure deadlock |\n| Approval-required tools | `confirm` without an approval checker became a generic tool error/recovery loop | Medium | Fixed classification: `APPROVAL_REQUIRED` fail-closes/checkpoints; interactive approval remains deferred until a Kernel-owned broker exists |\n| Task intake | report nouns alone could imply a report-creation artifact contract | Medium | Fixed: artifact overlay requires both a report/document noun and a creation/write action |\n| Windows runtime evidence | Linux-only CI could not exercise Windows text/newline behavior or TUI portability | High | Fixed partially: native `windows-latest` portable boundary job added with exact-byte artifact tests |\n| Project memory multi-writer capacity race | post-run store has no interprocess writer lock | Low for current single-process product | Deferred: do not add an ad-hoc stale lock without a daemon/multi-writer contract; revisit before service mode |\n| Native provider protocol adapter | capabilities advertise structured/native tool calling but canonical Decision still comes from text JSON | Architectural improvement | Deferred to dedicated provider-adapter work; current change improves protocol failure isolation without bypassing Kernel validation |\n\n## Invariants preserved\n\n- Actor/model output never directly writes trusted facts.\n- Provider-native or textual output never bypasses canonical Decision validation.\n- Tool success is not verified progress.\n- Verification is not accepted completion.\n- Interrupted or approval-blocked runs do not synthesize completion.\n- TUI session metadata is explicitly presentation-only; Kernel manifest/config-hash verification remains authoritative on resume.\n\n## Token-budget contract\n\nA route can opt into preflight budgeting through model options:\n\n```toml\n[models.local.options]\ncontext_window = 4096\nreserved_output_tokens = 512\ncontext_safety_margin_tokens = 256\n```\n\nThe compiler preserves the system/goal/control contract and removes lower-priority duplicate/retrieval/speculative views before touching trusted facts or tool input schemas. The estimator is intentionally conservative and tokenizer-independent; provider-reported usage remains post-request truth. A context that still cannot fit fails closed as `CONTEXT_BUDGET_EXCEEDED` instead of repeatedly sending impossible requests.\n\n## Approval boundary\n\nThis remediation deliberately does **not** let the TUI self-authorize a `confirm` tool. Until a Kernel-owned request/response approval broker exists, approval-required execution stops at a checkpoint with a distinct failure class. This is safer than silently converting confirmation into `auto` or repeatedly treating it as an ordinary tool failure.\n\n## Windows evidence\n\nThe new Windows job validates exact LF bytes through `atomic_write_text` and `ArtifactStore.put_text → verified_read_bytes`, plus TUI/model boundary tests. POSIX-only mount/no-follow isolation probes remain Linux-specific and are not falsely claimed to be equivalent on Windows.\n''', encoding="utf-8", newline="")

# Remove the one-shot applicator itself; the workflow removes its own file after tests.
print("boundary deep remediation patches applied")

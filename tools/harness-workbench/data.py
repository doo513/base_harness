"""Table-driven configuration, labels, and boundary rules for Harness Workbench.

Harness Workbench is an operator aid for Base Harness development.
It enforces evidence-only observation and strict safety boundaries:
1. Safe by default: no automatic retry loops, no process termination (no kill).
2. Backend boundaries: WSL Harness+WSL AGY and Windows Harness+Windows AGY are
   distinct execution silos. Mixing them leads to path, IPC, and credential faults.
"""

from __future__ import annotations

from typing import Any, Mapping

WORKBENCH_SCHEMA = "harness-workbench-v1"

# ---------------------------------------------------------------------------
# Stage and Lifecycle Definitions (evidence-only semantics)
# ---------------------------------------------------------------------------
STAGES: tuple[dict[str, Any], ...] = (
    {
        "id": "prepare",
        "label": "Prepare",
        "ko": "준비",
        "tokens": ("prepare", "preparing", "contract", "planning", "plan_ready", "review"),
    },
    {
        "id": "explore",
        "label": "Explore",
        "ko": "탐색",
        "tokens": ("explore", "exploration", "search", "read", "investigat", "research"),
    },
    {
        "id": "execute",
        "label": "Execute",
        "ko": "실행",
        "tokens": ("execute", "executing", "execution", "schedule", "dispatch", "worker", "repair", "mutat", "invoke"),
    },
    {
        "id": "verify",
        "label": "Verify",
        "ko": "검증",
        "tokens": ("verif", "observ", "measure", "gate", "ready", "blocked", "finish", "closed", "complete"),
    },
)

STAGE_BY_ID: dict[str, dict[str, Any]] = {item["id"]: item for item in STAGES}

PHASE_TO_STAGE: dict[str, str] = {
    "contract_building": "prepare",
    "contract_reviewing": "prepare",
    "planning": "prepare",
    "plan_ready": "prepare",
    "exploration": "explore",
    "exploring": "explore",
    "searching": "explore",
    "scheduling": "execute",
    "workgraph_dispatch": "execute",
    "worker_running": "execute",
    "executing": "execute",
    "execution": "execute",
    "repair": "execute",
    "repairing": "execute",
    "verifying": "verify",
    "verification": "verify",
    "root_verifying": "verify",
    "ready": "verify",
    "blocked": "verify",
    "completed": "verify",
    "closed": "verify",
    "idle": "idle",
    "inactive": "idle",
}

TERMINAL_PHASES: frozenset[str] = frozenset(
    {"ready", "blocked", "completed", "closed", "cancelled", "failed", "inactive", "idle"}
)

DOMAINS: tuple[str, ...] = ("develop", "general")

DOMAIN_LABELS: dict[str, str] = {
    "general": "General",
    "develop": "Develop",
    "unknown": "Unknown",
}

DEFAULT_MODEL = "gemini-3.8-flash-high"
DEFAULT_BACKEND = "antigravity-cli"
DEFAULT_DOMAIN = "develop"
DEFAULT_STALE_AFTER = 900.0  # seconds

KNOWN_MODELS: tuple[str, ...] = (
    "gemini-3.8-flash-high",
    "gemini-3.1-pro-high",
    "claude-sonnet-4-6",
    "chatgpt-web",
    "gpt-5.6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
)

KNOWN_BACKENDS: tuple[str, ...] = (
    "antigravity-cli",
    "codex",
    "gemini",
)

ACTOR_LABELS: dict[str, str] = {
    "internal_orchestration": "Internal orchestration",
    "external_llm": "External LLM",
    "subagent_worker": "Sub-agent worker",
    "verifier": "Verifier",
    "monitor": "Monitor",
    "idle": "Idle",
    "unknown": "Unknown",
}

ROLE_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "monitor",
        "label": "Lifecycle Monitor",
        "actor": "monitor",
        "tokens": ("harness_lifecycle_monitor", "lifecycle-monitor", "workbench"),
    },
    {
        "id": "agy_dispatcher",
        "label": "AGY / LLM Dispatcher",
        "actor": "external_llm",
        "tokens": ("antigravity", "agy", "gemini", "daily-cloudcode", "streamgeneratecontent"),
    },
    {
        "id": "codex_backend",
        "label": "Codex Model Backend",
        "actor": "external_llm",
        "tokens": ("codex", "app-server", "app_server"),
    },
    {
        "id": "verifier",
        "label": "Python Verifier",
        "actor": "verifier",
        "tokens": ("verified_sidecar", "measurement_v5", "verification_v2", "python -m pytest", "pytest"),
    },
    {
        "id": "subagent_worker",
        "label": "Sub-agent Worker",
        "actor": "subagent_worker",
        "tokens": ("subagent", "workunit", "worker", "task-runner", "task_runner"),
    },
    {
        "id": "harness_host",
        "label": "Harness Host / Coordinator",
        "actor": "internal_orchestration",
        "tokens": ("base-harness", "base_harness", "kernel-host", "kernel_host", "coordinator", "host.ts", "host.js"),
    },
    {
        "id": "bridge",
        "label": "Execution Bridge",
        "actor": "internal_orchestration",
        "tokens": ("bridge", "mcp", "acp", "bun"),
    },
)

EVENT_TYPES: frozenset[str] = frozenset({"harness_status", "harness_result", "harness_error", "event", "status"})

# ---------------------------------------------------------------------------
# Redaction & Security
# ---------------------------------------------------------------------------
SENSITIVE_KEYS: tuple[str, ...] = (
    "password", "passwd", "pwd", "secret", "token", "api_key", "apikey",
    "authorization", "cookie", "session", "credential", "access_key", "private_key",
    "auth", "bearer", "proxy_password", "key",
)

PROXY_ENV_KEYS: tuple[str, ...] = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
)

# ---------------------------------------------------------------------------
# Backend Boundary Rules
# ---------------------------------------------------------------------------
BOUNDARY_MODES: dict[str, dict[str, Any]] = {
    "wsl_native": {
        "id": "WSL_HARNESS_WSL_AGY",
        "label": "WSL Harness + WSL AGY",
        "os": "wsl",
        "binary_os": "wsl",
        "status": "matched",
        "badge_color": "#28a745",  # Green
        "description": "WSL 환경 내에서 Base Harness와 WSL agy CLI를 격리 실행합니다.",
    },
    "windows_native": {
        "id": "WINDOWS_HARNESS_WINDOWS_AGY",
        "label": "Windows Harness + Windows AGY",
        "os": "windows",
        "binary_os": "windows",
        "status": "matched",
        "badge_color": "#28a745",  # Green
        "description": "Windows 호스트 환경 내에서 Base Harness와 Windows Antigravity/AGY를 실행합니다.",
    },
    "mismatch_wsl_host_windows_agy": {
        "id": "MISMATCH_WSL_HOST_WINDOWS_AGY",
        "label": "Boundary Warning: WSL Host + Windows AGY",
        "os": "wsl",
        "binary_os": "windows",
        "status": "mismatch",
        "badge_color": "#dc3545",  # Red
        "description": "현재 OS는 WSL이지만 선택된 AGY 실행 파일이 Windows 경로(.exe 또는 /mnt/c/...)입니다. 교차 호출을 삼가고 WSL agy 바이너리를 지정하십시오.",
    },
    "mismatch_windows_host_wsl_agy": {
        "id": "MISMATCH_WINDOWS_HOST_WSL_AGY",
        "label": "Boundary Warning: Windows Host + WSL AGY",
        "os": "windows",
        "binary_os": "wsl",
        "status": "mismatch",
        "badge_color": "#dc3545",  # Red
        "description": "현재 OS는 Windows이지만 선택된 AGY 실행 파일이 WSL/Linux 전용 경로입니다. Windows agy/Antigravity 실행 파일을 지정하십시오.",
    },
    "unknown": {
        "id": "BOUNDARY_UNKNOWN",
        "label": "Boundary: Unclassified OS/Binary Combination",
        "os": "unknown",
        "binary_os": "unknown",
        "status": "unknown",
        "badge_color": "#ffc107",  # Yellow
        "description": "운영체제 또는 AGY 바이너리 형식을 명확히 판별할 수 없습니다.",
    },
}

SAFETY_PRINCIPLES: tuple[dict[str, str], ...] = (
    {
        "title": "No Kill / No Terminate",
        "ko": "프로세스 강제 종료 금지",
        "detail": "Harness Workbench는 운영 보조 도구(Operator Aid)이며 실행 중인 프로세스를 임의로 kill하거나 terminate하지 않습니다.",
    },
    {
        "title": "No Automatic Retry Loop",
        "ko": "자동 재시도 루프 금지",
        "detail": "실패 시 스스로 루프를 돌지 않고 단일 실행의 결과(PID, 종료 코드, 로그)를 명확히 기록하여 보고합니다.",
    },
    {
        "title": "Evidence-Only Semantics",
        "ko": "증거 기반 상태 관측",
        "detail": "추측이나 의도를 단계로 간주하지 않고, 로그 레코드와 프로세스에 기록된 명시적 증거만을 상태로 표시합니다.",
    },
    {
        "title": "Strict Credential Redaction",
        "ko": "인증 정보 완전 마스킹",
        "detail": "토큰, 쿠키, 비밀번호, API 키, 프록시 인증 정보는 화면, 로그, CLI 출력 어디에도 평문으로 출력하지 않습니다.",
    },
)

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re


_REPORT_TERMS = (
    "보고서",
    "리포트",
    "report",
    "analysis report",
    "deep report",
    "문서로 정리",
    "문서 작성",
)
_MARKDOWN_NAME = re.compile(r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]+\.md)(?![A-Za-z0-9_.-])", re.IGNORECASE)
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_BARE_WINDOWS_PATH = re.compile(r"(?<!\S)([A-Za-z]:[\\/][^\s\"']+)")
_BARE_POSIX_PATH = re.compile(r"(?<!\S)(/(?:[^\s\"']+/)*[^\s\"']+)")


@dataclass(frozen=True)
class TaskIntake:
    requested_workspace: str | None = None
    workspace_ambiguous: bool = False
    artifact_target: str | None = None
    evidence_backed_artifact: bool = False


def _localize_path(raw: str) -> Path:
    value = raw.strip().strip("\"'")
    if _WINDOWS_PATH.match(value) and os.name != "nt":
        drive = value[0].lower()
        rest = value[2:].lstrip("\\/")
        parts = [part for part in re.split(r"[\\/]+", rest) if part]
        return Path("/mnt") / drive / Path(*parts)
    return Path(value).expanduser()


def _candidate_strings(task: str) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(r"[\"']([^\"']+)[\"']", task):
        value = match.group(1).strip()
        if _WINDOWS_PATH.match(value) or value.startswith("/"):
            candidates.append(value)
    candidates.extend(match.group(1) for match in _BARE_WINDOWS_PATH.finditer(task))
    candidates.extend(match.group(1) for match in _BARE_POSIX_PATH.finditer(task))
    return list(dict.fromkeys(candidates))


def detect_requested_workspace(task: str) -> tuple[str | None, bool]:
    """Resolve only an explicit, existing single directory named by the user.

    The actor never changes the workspace boundary. This pre-runtime intake step
    merely turns an unambiguous user-supplied path into the WorkspaceContract root.
    Multiple existing directories are deliberately treated as ambiguous.
    """
    resolved: list[Path] = []
    for raw in _candidate_strings(task):
        path = _localize_path(raw)
        try:
            candidate = path.resolve()
        except OSError:
            continue
        if candidate.exists() and candidate.is_dir() and candidate not in resolved:
            resolved.append(candidate)
    if len(resolved) == 1:
        return str(resolved[0]), False
    return None, len(resolved) > 1


def detect_artifact_target(task: str) -> str | None:
    lowered = task.casefold()
    if not any(term.casefold() in lowered for term in _REPORT_TERMS):
        return None
    explicit = _MARKDOWN_NAME.search(task)
    if explicit:
        return explicit.group(1)
    return "PROJECT_ANALYSIS_REPORT.md"


def analyze_task_input(task: str) -> TaskIntake:
    workspace, ambiguous = detect_requested_workspace(task)
    artifact = detect_artifact_target(task)
    return TaskIntake(
        requested_workspace=workspace,
        workspace_ambiguous=ambiguous,
        artifact_target=artifact,
        evidence_backed_artifact=artifact is not None,
    )

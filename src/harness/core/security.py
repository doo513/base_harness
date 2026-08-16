from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable


class Principal(str, Enum):
    ACTOR = "actor"
    VERIFIER = "verifier"
    ORACLE = "oracle"
    KERNEL = "kernel"


class Capability(str, Enum):
    TOOL_READ = "tool_read"
    TOOL_WRITE = "tool_write"
    TOOL_EXTERNAL = "tool_external"
    VERIFY = "verify"
    ORACLE_EXECUTE = "oracle_execute"
    STATE_COMMIT = "state_commit"
    LEDGER_WRITE = "ledger_write"


class SecurityViolation(RuntimeError):
    pass


@dataclass(frozen=True)
class CapabilityPolicy:
    grants: dict[Principal, frozenset[Capability]] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "CapabilityPolicy":
        return cls(
            grants={
                Principal.ACTOR: frozenset({
                    Capability.TOOL_READ,
                    Capability.TOOL_WRITE,
                    Capability.TOOL_EXTERNAL,
                }),
                Principal.VERIFIER: frozenset({Capability.VERIFY}),
                Principal.ORACLE: frozenset({Capability.ORACLE_EXECUTE}),
                Principal.KERNEL: frozenset({
                    Capability.STATE_COMMIT,
                    Capability.LEDGER_WRITE,
                }),
            }
        )

    def allows(self, principal: Principal, capability: Capability) -> bool:
        return capability in self.grants.get(principal, frozenset())

    def require(self, principal: Principal, capability: Capability) -> None:
        if not self.allows(principal, capability):
            raise SecurityViolation(
                f"principal={principal.value} lacks capability={capability.value}"
            )


@dataclass(frozen=True)
class SecurityLayout:
    """Filesystem topology checks.

    This is a topology invariant, not an OS sandbox.  It prevents accidental
    placement of kernel/oracle assets inside the actor workspace, but it cannot
    stop an unrestricted same-UID subprocess from opening an absolute path.
    """

    workspace: Path
    run_dir: Path
    oracle_root: Path | None = None

    @staticmethod
    def _resolved(path: Path | str) -> Path:
        return Path(path).expanduser().resolve()

    @classmethod
    def build(
        cls,
        *,
        workspace: Path | str,
        run_dir: Path | str,
        oracle_root: Path | str | None = None,
    ) -> "SecurityLayout":
        return cls(
            workspace=cls._resolved(workspace),
            run_dir=cls._resolved(run_dir),
            oracle_root=cls._resolved(oracle_root) if oracle_root else None,
        )

    @staticmethod
    def _contains(parent: Path, child: Path) -> bool:
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False

    @classmethod
    def _overlap(cls, a: Path, b: Path) -> bool:
        return a == b or cls._contains(a, b) or cls._contains(b, a)

    def validate_strict(self) -> None:
        # Trust roots must be pairwise non-overlapping in either direction.
        # Rejecting only "run_dir inside workspace" is insufficient because
        # "workspace inside run_dir" also collapses the boundary.
        if self._overlap(self.workspace, self.run_dir):
            raise SecurityViolation(
                "workspace and run_dir must be pairwise non-overlapping in strict security mode"
            )
        if self.oracle_root is not None:
            if self._overlap(self.workspace, self.oracle_root):
                raise SecurityViolation(
                    "workspace and oracle_root must be pairwise non-overlapping in strict security mode"
                )
            if self._overlap(self.run_dir, self.oracle_root):
                raise SecurityViolation(
                    "run_dir and oracle_root must be pairwise non-overlapping"
                )


def capability_for_side_effect(side_effect: str) -> Capability:
    if side_effect == "read" or side_effect == "none":
        return Capability.TOOL_READ
    if side_effect == "write":
        return Capability.TOOL_WRITE
    if side_effect == "external":
        return Capability.TOOL_EXTERNAL
    raise SecurityViolation(f"unknown side effect class: {side_effect}")


@dataclass(frozen=True)
class SecurityConfig:
    strict_layout: bool = False
    strict_tool_isolation: bool = False
    network_policy: str = "allow"  # allow | deny
    allow_test_attestation: bool = False
    require_sealed_oracle: bool = False

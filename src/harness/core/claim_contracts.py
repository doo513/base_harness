from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .verification import VerificationContract


@dataclass(frozen=True)
class ClaimContractRule:
    """Bind one claim-key class to a verification contract and verifier allow-list."""

    claim_class: str
    key_prefix: str
    contract: VerificationContract
    allowed_verifiers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.claim_class.strip():
            raise ValueError("claim_class must be non-empty")
        if not self.allowed_verifiers:
            raise ValueError("claim contract must allow at least one verifier")

    def matches(self, key: str) -> bool:
        return key.startswith(self.key_prefix)

    def dump(self) -> dict[str, Any]:
        return {
            "claim_class": self.claim_class,
            "key_prefix": self.key_prefix,
            "contract": self.contract.dump(),
            "allowed_verifiers": sorted(set(self.allowed_verifiers)),
        }


class ClaimContractRegistry:
    """Deterministic claim-class lookup owned by the Domain Profile.

    Rules use explicit key namespaces. Longest-prefix resolution makes nested
    classes deterministic. A configured registry fails closed for unknown keys;
    profiles that have not opted in return ``None`` and retain legacy behavior.
    """

    def __init__(self, rules: tuple[ClaimContractRule, ...] | list[ClaimContractRule]):
        rules = tuple(rules)
        if not rules:
            raise ValueError("claim contract registry requires at least one rule")
        classes = [rule.claim_class for rule in rules]
        if len(classes) != len(set(classes)):
            raise ValueError("claim classes must be unique")
        prefixes = [rule.key_prefix for rule in rules]
        if len(prefixes) != len(set(prefixes)):
            raise ValueError("claim key prefixes must be unique")
        self.rules = tuple(sorted(rules, key=lambda rule: (-len(rule.key_prefix), rule.key_prefix, rule.claim_class)))

    def resolve(self, key: str) -> ClaimContractRule | None:
        if not isinstance(key, str) or not key:
            return None
        for rule in self.rules:
            if rule.matches(key):
                return rule
        return None

    def dump(self) -> dict[str, Any]:
        return {
            "unknown_claim_policy": "fail_closed",
            "resolution": "longest_key_prefix",
            "rules": [rule.dump() for rule in self.rules],
        }

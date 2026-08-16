# Stage 02 Remediation — Nested Submount EVIDENCE MATRIX

| ID | Claim | Class | Evidence | Red | Green | Limitation |
|---|---|---|---|---|---|---|
| S02-R-001 | Top-level `remount,bind,ro` after recursive bind does not necessarily make a descendant mount read-only | security hypothesis → confirmed defect | live mount fixture | descendant writable, canary changed | raw fixture intentionally still confirms Linux semantics | tested on GitHub Ubuntu 24.04 runner |
| S02-R-002 | Existing Harness backend allowed the descendant write before remediation | confirmed defect | actual `LinuxNamespaceSandboxBackend.run_shell()` | returncode 0, escape observed | N/A | exact attack requires privileged mount fixture |
| S02-R-003 | New read-only-path preflight rejects nested mount topology | enforcement | live attack probe + unit | false | true | fail-closed rather than recursive remount support |
| S02-R-004 | Host canary is unchanged because Harness blocks before actual sandbox command | enforcement | live attack probe | false before fix | true after fix | raw Linux fixture separately mutates its own canary by design |
| S02-R-005 | Source itself may be a mount point | compatibility | unit test | not covered | PASS | descendants remain forbidden |
| S02-R-006 | Escaped whitespace/backslash mountinfo paths are decoded | parser integrity | unit test | not covered | PASS | parser targets Linux proc mountinfo format |
| S02-R-007 | Prior Stage invariants survive defense | regression | full pytest + Stage03–08 probes | prior probes passed before new red gate | 134 passed / 5 skipped + all prior probes PASS | hosted live namespace tests still have their existing skips |

## Red evidence

GitHub Actions run `31948105773`:

```text
raw_mount_semantics:
  top_level_rbind_remount_ro_descendant_writable: true
  source_canary_changed_through_descendant: true

harness_defense:
  preflight_blocked_nested_read_only_source: false
  actual_backend_attempt.returncode: 0
  actual_escape_observed: true

summary:
  raw_semantics_confirmed: true
  defense_ok: false
  all_passed: false
```

The run was expected to fail because it was deliberately introduced as a red security gate.

## Green evidence

GitHub Actions run `31948174266`:

```text
pytest: 134 passed / 5 skipped

raw_mount_semantics:
  top_level_rbind_remount_ro_descendant_writable: true
  source_canary_changed_through_descendant: true

harness_defense:
  preflight_blocked_nested_read_only_source: true
  actual_backend_attempt: null
  actual_escape_observed: false

summary:
  raw_semantics_confirmed: true
  defense_ok: true
  all_passed: true
```

This preserves the attack fixture as a proof that the underlying mount behavior still exists while proving that the Harness no longer enters the unsafe execution path for that topology.

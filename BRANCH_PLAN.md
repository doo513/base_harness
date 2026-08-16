# Branch Plan

Target repository:

- `https://github.com/doo513/base_harness`

Actual branch for this delivery:

- `research/verified-state-stage03`

## Branch policy

`main` remains the original Base Harness MVP. The Verified-State implementation stays isolated under:

```text
experimental/verified-state-harness/
```

Research/evidence stays under:

```text
docs/verified-state/
```

Historical source material stays under:

```text
archive/
```

Current continuation control stays under:

```text
handoff/
```

Promotion rule:

```text
Stage implementation
→ stage-specific tests
→ adversarial/integration tests
→ full regression
→ logic/security/integrity re-review
→ evidence/report freeze
→ PASS/PARTIAL/FAIL
→ next stage only on PASS
```

## Current promotion state

```text
v0.1.0      initial verified-state baseline
v0.2.0      Stage 01 truth/execution hardening
v0.3.0-rc1  Stage 02 PARTIAL
v0.3.0-rc2  production sandbox + direct attack evidence candidate
v0.3.0      Stage 02 PASS
v0.4.0      Stage 03 persistence/resume/reproducibility PASS in this branch
```

No tag is created by the branch operation unless explicitly requested separately.

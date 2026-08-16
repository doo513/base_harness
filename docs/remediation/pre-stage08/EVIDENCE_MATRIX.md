# Pre-Stage08 Remediation — EVIDENCE MATRIX

Scope: **P0-1 verified-read single-buffer hardening**

| ID | Claim | Class | Evidence | Result | Limitation |
|---|---|---|---|---|---|
| R08-P0-001 | Initial centralized verified-read could authorize later reread bytes | confirmed_defect | direct code review of unpromoted rc1 | CONFIRMED | defect was in candidate, not v0.8.0 release |
| R08-P0-002 | Verified bytes and returned bytes are the same logical buffer | confirmed_defect remediation | unit + race probe | PASS | relies on OS FD semantics; final-component symlink additionally denied where `O_NOFOLLOW` exists |
| R08-P0-003 | Static post-write tamper is rejected | enforcement | unit + direct probe | PASS | SHA-256 is integrity consistency, not authentication against an attacker who can rewrite both ref/state and artifact store |
| R08-P0-004 | Missing artifact is rejected | enforcement | unit + direct probe | PASS | none in declared artifact-store boundary |
| R08-P0-005 | Malformed/path-escape artifact ref is rejected | enforcement | unit + direct probe | PASS | refs remain basename-token based |
| R08-P0-006 | Pathname swap after first read cannot substitute returned bytes | security property | deterministic adversarial race | PASS | simulates replacement at a controlled read boundary rather than exhaustive scheduler interleavings |
| R08-P0-007 | Stage-04 semantic verifiers consume verified bytes rather than reopen verified path | structural enforcement | direct code + Stage04 probe | PASS | compatibility path helper remains for external callers and carries no future-read guarantee |
| R08-P0-008 | Stage-06 progress consumes verified bytes | structural enforcement | direct code + Stage06 probes | PASS | semantic-progress quality remains a separate remediation gap |
| R08-P0-009 | Stage-03 persistence semantics were preserved after remediation | regression | full pytest + Stage03 direct probe | PASS after correction | first remediation candidate regressed envelope schema; recorded in implementation report |
| R08-P0-010 | Prior Stage 04–07 gates remain intact | regression | GitHub Actions direct probes | PASS | Stage02 live namespace tests remain hosted-environment dependent |
| R08-P0-011 | Single-read eliminates duplicate artifact content I/O in the corrected path | cost | executable cost probe + algorithmic byte count | PASS | wall-time measurement is environment-noisy |

## Corrected candidate gate

GitHub Actions run `31947812417`:

```text
compileall                       PASS
pytest                           131 passed / 5 skipped
Stage03 resume                   4/4 PASS
Stage04 semantic                 8/8 PASS, FP=0, FN=0
Stage05 recovery probes          PASS
Stage06 progress probes          PASS
Stage07 context probes           PASS
Stage08 artifact integrity       6/6 PASS
unverified_return_buffers        0
```

## Evidence interpretation

The 5 skipped tests are live Linux namespace tests on the hosted runner. They are not counted as fresh Stage-02 production isolation evidence.

P0-1 is eligible for release promotion only after the exact `v0.8.1` version snapshot reruns the same gates.

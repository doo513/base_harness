# Stage 02 rc2 — Final Logic / Security Re-review

## Purpose

Perform a second-pass review after the production backend and attack suite were already working. The goal is to search for design errors that ordinary happy-path tests would miss and to avoid declaring PASS merely because the first probe set was green.

## Review vectors

| # | Vector | Question | Finding / correction | Final |
|---:|---|---|---|---|
| 1 | Rootfs permissions | Can owner chmod a 0555 jail root? | Yes in prototype; converted root to read-only mount | PASS |
| 2 | Workspace usefulness | Can Actor still write expected outputs? | positive control required | PASS |
| 3 | Validator usability | Can RO verifier run tools needing temp files? | added isolated `/vsh-tmp` | PASS |
| 4 | Scratch path collision | Can temp mount hide workspace paths? | `/tmp` prototype did; moved to `/vsh-tmp` | PASS |
| 5 | Relative traversal | Does `../` expose host siblings? | chroot view blocks | PASS |
| 6 | Absolute path | Does known host absolute path remain reachable? | unmounted path absent | PASS |
| 7 | Symlink | Can workspace symlink escape chroot? | outside target unavailable | PASS |
| 8 | Hard link | Can inode identity bypass pathname jail? | detected; external hard links fail closed | PASS |
| 9 | TCP loopback | Can Actor reach Harness host listener? | fresh network namespace blocks | PASS |
| 10 | External TCP | Can Actor route to external target? | no usable network route in DENY namespace | PASS |
| 11 | AF_UNIX IPC | Can workspace socket bypass net namespace? | detected; special-file preflight blocks | PASS |
| 12 | Env leakage | Are arbitrary Harness parent secrets inherited? | sanitized env; canary missing | PASS |
| 13 | Nested namespaces | Can child userns remount protected root? | attack probe denied | PASS on recorded host |
| 14 | Sealed confidentiality | Does Actor receive sealed root mount? | no | PASS |
| 15 | Sealed integrity | Can Oracle mutate its own acceptance assets? | mount ro + pre/post hash | PASS |
| 16 | Verifier integrity | Can subprocess verifier mutate candidate? | workspace ro; scratch separate | PASS |
| 17 | Attestation spoofing | Can arbitrary backend boolean claim satisfy strict mode? | source must be live runtime probe | PASS |
| 18 | Test-fixture contamination | Can mocked attestation become prod proof? | explicit test-only opt-in required | PASS |
| 19 | Regression | Did security changes break prior kernel semantics? | full 47-test suite green | PASS |
| 20 | Scope honesty | Are unsupported properties being called solved? | residual risks/non-claims explicitly retained | PASS |

## Integrity gates

### Truth Integrity

No Stage 02 change grants Actor trusted-state commit or completion authority. Prior detached-state and verifier-promotion rules remain covered by regression tests.

**Verdict: PASS for existing Stage 01/02 scope.**

### Execution Integrity

Side-effecting shell tools in strict mode require a live `runtime_probe` boundary. Non-zero exits remain failures. Real filesystem/network escape attempts were blocked.

**Verdict: PASS for Linux namespace backend.**

### Oracle Integrity

Actor cannot see the sealed mount. Oracle receives sealed assets read-only and candidate read-only. Seals are checked before and after acceptance commands.

**Verdict: PASS for sealed command oracle on production backend.**

### Persistence Integrity

Stage 02 did not implement full restart/resume. Existing atomic persistence behavior remains, but the full persistence gate belongs to Stage 03.

**Verdict: NOT A STAGE-02 EXIT BLOCKER; Stage 03 remains required.**

### Reproducibility

This branch records source hashes, environment metadata, exact attack outputs and final pytest output. Full model/task reproducibility fields are a Stage 03 target.

**Verdict: sufficient to reproduce Stage 02 security probe; global Gate E not yet claimed complete.**

## Final decision

The inherited reason for `PARTIAL / NOT EXITED` was the absence of real production isolation and direct attack evidence. That reason is now removed by Level-A execution evidence. No new Stage 02 blocker was found in final re-review.

**Stage 02 → PASS / EXITED.**

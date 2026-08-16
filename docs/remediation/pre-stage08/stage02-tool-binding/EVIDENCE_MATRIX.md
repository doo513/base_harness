# Stage 02 Remediation — Tool Backend Binding EVIDENCE MATRIX

| ID | Claim | Class | Evidence | Red | Green | Limitation |
|---|---|---|---|---|---|---|
| S02-B-001 | A backend attestation could authorize an unrelated in-process WRITE handler | confirmed defect | direct code + red runtime probe | handler 1, backend exec 0, canary changed | generic strict WRITE blocked | trusted side-effect classification remains a registry boundary |
| S02-B-002 | Strict generic WRITE/EXTERNAL ToolSpec is blocked before handler execution | enforcement | unit + direct probe | false | PASS | NONE/READ trusted handlers are outside this specific binding claim |
| S02-B-003 | Valid sandboxed command attests and executes on the same backend object | structural enforcement | identity backend unit test | not guaranteed structurally | PASS | backend internals remain part of backend trust/attestation |
| S02-B-004 | Built-in shell uses Runtime-owned backend execution | implementation | direct code + existing Stage02 tests | handler closure convention | PASS | shell command semantics remain backend-specific |
| S02-B-005 | Nonzero/timed-out command remains failed ToolResult | regression | unit + prior runtime tests | existing behavior | PASS | declarative postcondition currently zero-exit/timed-out only |
| S02-B-006 | Non-strict trusted in-process compatibility remains | compatibility | unit/full pytest | existing | PASS | not described as sandboxed isolation |
| S02-B-007 | Declarative timeout/command policy remains provenance-bound | reproducibility | unit + manifest descriptor path | closure-bound before | PASS via provenance fields | P1 release/build provenance still pending |
| S02-B-008 | Prior Stage 03–08 gates remain green | regression | GitHub Actions | green before new red gate | 140 passed / 5 skipped + all probes PASS | hosted live namespace skip boundary unchanged |

## Red evidence

GitHub Actions run `31948573578`:

```text
attestation_execution_mismatch_observed = true
attested_backend_execution_calls        = 0
unsafe_handler_calls                    = 1
private_canary_changed                  = true
result.ok                               = true
result.security_violation               = false
```

The gate intentionally failed.

## Green evidence

GitHub Actions run `31948805281`:

```text
pytest                                  140 passed / 5 skipped
Stage03 resume                          PASS 4/4
Stage04 semantic                        PASS 8/8, FP=0/FN=0
Stage05–07                              PASS
Stage08 single-buffer                   PASS 6/6
Stage02 nested-submount                 PASS
attestation_execution_mismatch_observed = false
unsafe_handler_calls                    = 0
private_canary_changed                  = false
security_violation                      = true
unsafe_path_blocked                     = true
```

The same attack probe was retained and changed from red to green; it was not replaced with a weaker structural-only test.

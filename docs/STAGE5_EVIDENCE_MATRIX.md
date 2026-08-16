# Stage 05 — Evidence Matrix

Final candidate: `v0.6.0-rc6`  
Commit: `c50a4bd15a86b3e26bf1fe52c15edde61738edd0`  
GitHub Actions: `31936441736`

| Gate | Expected | Evidence | Result |
|---|---|---|---|
| Compile | source/tests/probes compile | `compileall` | PASS |
| Full regression | no unexplained regression | 94 passed / 5 environment skips | PASS |
| Stage 03 forced kill/resume | no duplicate external action | 4/4, duplicate=0 | PASS |
| Stage 04 semantic matrix | FP=0/FN=0 | 8/8, FP=0, FN=0 | PASS |
| TOOL_ERROR recovery | no automatic tool retry | REPAIR, tool_calls=0 | PASS |
| MISSING_INFO recovery | durable OBSERVE | integration test | PASS |
| VERIFICATION_FAILED | durable REPLAN, no promotion | integration test | PASS |
| Refuted hypothesis | logical-only rollback | verified facts unchanged | PASS |
| Security violation | terminal no-retry | CHECKPOINT_STOP, tool_calls=0 | PASS |
| PREPARED receipt | no ambiguous replay | handler=0, effect absent | PASS |
| Repeat threshold | one strategy switch at threshold | generation 0 -> 1 | PASS |
| New strategy repeat scope | count resets | next same failure = REPAIR, repeat=1 | PASS |
| Numeric failure identity | 401 != 500 | no signature collision | PASS |
| Failure/audit linkage | transition ID matches state/event | mismatch=0 | PASS |
| Hard step budget | no overshoot | max=1, persisted=1 | PASS |
| Budget/recovery race | nonterminal recovery cannot apply after expiry | REPAIR superseded by CHECKPOINT_STOP | PASS |
| Pending recovery resume | recovery before Actor | resume < recovery < decision | PASS |
| Scheduling crash window | pending transition survives immediate process loss | lost=0, applied once | PASS |
| Terminal recovery resume | remains halted | Actor calls=0 | PASS |
| Verified fact integrity | recovery cannot mutate facts | mutations=0 | PASS |
| Ambiguous external effect | no execution | ambiguous executions=0 | PASS |

## Environment note

The 5 skipped tests are live production Linux namespace tests on the hosted GitHub runner. Stage 02 remains PASS only under its existing rule: `LinuxNamespaceSandboxBackend` is production-isolated when live runtime attestation succeeds. These hosted skips are not converted into PASS evidence.

## Evidence conclusion

All Stage 05 exit checks that are executable in the hosted environment passed. No Stage 03 receipt/replay or Stage 04 semantic-verification regression was observed.

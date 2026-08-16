# Stage05 Recovery Effectiveness — Evidence Matrix

CI: `31955531150`  
Commit: `1b8496c120f52496d53de90ef7aae013cc926962`

| Claim | Evidence | Result |
|---|---|---:|
| production Recovery improves matched tool-repair outcome | `tool_repair` A/B pair | Recovery complete, baseline halted |
| observe recovery can unlock missing-information path | `missing_info_observe` pair | Recovery complete, baseline halted |
| replan recovery can recover from rejected completion | `verification_replan` pair | Recovery complete, baseline halted |
| completion uses same independent oracle in each pair | benchmark profile/oracle construction | PASS |
| only routing policy differs between A/B arms | benchmark contract + implementation | PASS |
| recovery does not directly execute task tools | event-order `tool_calls_actor_guarded` | PASS in all arms |
| recovery does not directly mutate verified facts | `verified_fact_count=0` | PASS |
| unsafe retry is not used to manufacture success | `unsafe_retries=0` | PASS |
| terminal security remains fail-closed | `terminal_security` pair | both halted; unsafe handler calls 0 |
| controlled completion-rate delta is positive | aggregate | `1.0 - 0.0 = +1.0` |
| prior harness guarantees regress | full CI | NO; 182 passed / 5 skipped + all probes PASS |

## External-validity boundary

This evidence is sufficient for a deterministic causal benchmark claim. It is insufficient for a broad production-effectiveness claim because the task set is synthetic, small and controller-deterministic.

# Track D — Real Evaluation

Status: **REQUIRED BEFORE GENERAL PERFORMANCE CLAIMS**

Current deterministic probes answer “does the mechanism enforce its contract?” They do not answer “does the complete harness improve real tasks enough to justify its cost?”

## D1. Recovery effectiveness

Use matched arms:

1. Recovery OFF
2. Retry-only
3. Full Replan
4. Typed Targeted Recovery

For every matched task keep fixed:

- same model/version/configuration
- same task instance
- same tool set
- same hard/soft budget
- same Oracle / completion condition
- same environment snapshot

Run repeated stochastic trials when the model/controller is non-deterministic. Record seed or provider request identity where possible.

Metrics:

- solve rate
- false completion
- recovery success rate
- repeated-failure rate
- steps to recovery
- tokens / solved
- tool calls / solved
- verification calls / solved
- wall time / solved
- monetary cost / solved when measurable
- terminal safety regressions

The existing controlled A/B result remains mechanism-level evidence: recoverable scenarios 3/3 with Recovery versus 0/3 conservative baseline, with zero safety regressions in that synthetic matrix. Do not generalize it to arbitrary LLM tasks.

## D2. Corpus design

Use at least two domain families before making broad claims:

### Software

- small repository repair
- failing build/test diagnosis
- behavioral acceptance change
- one security-property task after Track C verifier exists

### CTF

- tasks where local evidence can be deterministically verified
- tasks requiring local→remote transition
- tasks with plausible dead ends to exercise recovery
- external Oracle for final accepted proof/flag where available

Keep a frozen task manifest with task hash, environment identity, expected completion condition and allowed tools.

## D3. Statistical reporting

Report raw outcomes and uncertainty, not only averages. At minimum include per-task success counts, median/mean cost for solved runs and failure categories. If trial counts are small, label conclusions exploratory rather than statistically established.

## Exit criterion

No statement such as “Recovery improves LLM task success” or “Retrieval improves solve rate” should be promoted beyond `SUPPORTED` until repeated real-task evidence exists under matched controls.

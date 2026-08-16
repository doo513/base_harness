# Track E — Full Harness Ablation

Status: **REQUIRED BEFORE CLAIMING END-TO-END ROI**

The purpose is not to make every layer win. It is to identify which layers measurably improve reliability or cost and which should become optional/domain-specific.

## Matched incremental arms

1. Minimal Baseline
2. + Verified State
3. + Semantic Verification
4. + Failure Recovery
5. + Progress Control
6. + Context Governance
7. + Retrieval / Memory

Each arm must use the same:

- model
- task
- tools
- budget
- Oracle
- environment snapshot

The only intended difference between adjacent arms is the named harness layer. If an arm requires a domain verifier or milestone contract, freeze that contract before trials.

## Metrics

Primary:

- success rate
- false completion rate
- state corruption / contradictory current-state incidents
- verifier FP/FN
- repeated failure rate

Efficiency:

- tokens / solved
- tool calls / solved
- verification calls / solved
- retrieval calls / solved
- wall time / solved
- monetary cost / solved when available

Storage/control overhead:

- checkpoint serialized bytes
- event log bytes
- artifact bytes
- context serialized chars or actual tokens

## Interpretation

For adjacent arms compute both outcome delta and cost delta. A layer that produces no measurable improvement but adds material cost should be reclassified as:

- optional,
- domain-specific,
- or removable.

Do not infer causality from the final full harness versus baseline alone. Incremental matched arms are needed to assign benefit/cost to a layer.

## Suggested execution order

1. freeze benchmark/release environment (Track B);
2. freeze the minimal domain verifier/milestone set (Track C);
3. create frozen task manifest;
4. run baseline and incremental arms;
5. repeat stochastic trials;
6. report per-domain and aggregate results separately;
7. only then decide whether optional layers should remain default.

## Research decision rule

A feature is not justified by architectural elegance or test count. Keep it default only when it materially improves one or more of:

- task success,
- false completion,
- state integrity,
- recovery efficiency,

without disproportionate token/tool/I/O/complexity cost.

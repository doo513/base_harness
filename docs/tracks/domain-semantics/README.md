# Track C — Domain Semantics

Status: **PARTIAL / REQUIRED BEFORE DOMAIN BENCHMARKS**

The Core verification mechanism is already implemented. This Track adds only domain-native contracts needed by actual benchmark tasks.

## Current verified coverage

Software currently has explicit classes for:

- `software.build_result.*`
- `software.test_result.*`
- `software.behavioral_acceptance.*`
- generic `artifact_assertion.*` under its own restricted namespace

The frozen repository-style execution benchmark covers 17 positive/negative cases for build/test/behavior and reports FP=0/FN=0. This is corpus evidence, not universal semantic accuracy.

CTF currently uses a structural `ctf.intermediate_supported` catch-all. It intentionally does **not** promote arbitrary CTF intermediates to domain-semantic truth.

## C1. Software security semantics

Priority: **REQUIRED BEFORE software-security benchmark**.

First candidate:

- `software.security_property.*`

Do not use a generic LLM judgment as final truth authority. Prefer a verifier tied to the property being claimed, for example:

- fixed security regression test;
- sanitizer/static-analysis output when the claim precisely matches the tool guarantee;
- protocol/HTTP behavior with exact expected invariant;
- deterministic exploit-negative/positive acceptance fixture;
- repository-native security test.

Each class must declare its exact allowed evidence and authority. A verifier that proves “test command exited 0” must not silently authorize a stronger security claim unless the contract binds that command to the claimed property.

## C2. CTF semantics

Priority: **REQUIRED BEFORE CTF performance benchmark**.

Do not implement every candidate class up front. Select classes from actual CTF corpus needs. Candidate vocabulary:

- `ctf.binary_property.*`
- `ctf.offset.*`
- `ctf.control_flow.*`
- `ctf.exploit_local.*`
- `ctf.service_behavior.*`
- `ctf.exploit_remote.*`
- `ctf.flag_valid.*`

Preferred task-native evidence:

- deterministic binary/debugger probe;
- controlled local exploit execution;
- protocol response from the real service;
- remote exploit behavior;
- external flag/proof acceptance.

Final flag/task success remains Oracle authority.

## C3. Stage06 domain milestones

Priority: **REQUIRED BEFORE progress/recovery benchmark**.

Milestones must be opened by verified transitions, not Actor prose.

Software example:

1. repo_loaded
2. build_passed
3. target_test_passed
4. regression_passed
5. acceptance_passed

CTF example:

1. challenge_classified — only if classification is objectively bound enough to be useful
2. primitive_verified
3. local_control_verified
4. local_exploit_verified
5. remote_behavior_verified
6. flag_accepted

Required direction:

```text
Stage04 domain verifier
→ Kernel verified transition
→ DomainProfile monotonic milestone/score snapshot
→ Stage06 task progress credit
```

Do not grant milestone credit directly from retrieval text, raw observation novelty, model confidence, or narrative self-assessment.

## Design rule

Start from the real benchmark corpus and add the **smallest verifier vocabulary that reduces ambiguous truth decisions**. If a claim class has no task-native evidence or does not change control decisions, leave it structural/unsupported rather than inventing a weak semantic verifier.

# Auth Store Missing-File Handling: Partial Implementation (2026-09-08)

## Situation
First provider-list initialization previously spent 10.119 seconds in the credential-loading span of an isolated Host.

## Reason
A standalone Auth probe did not reproduce that delay: missing first read was about 17.5 ms. Full Host comparisons with inline empty credentials and an empty auth file had credential spans of 1 ms and 0 ms respectively. These observations suggest the missing-file path matters in the full Host, but do not establish a general filesystem performance defect.

## Action
- Auth.all now probes store existence before attempting JSON reading.
- A missing store returns an empty mapping without negative caching.
- Existing decode, secret registration, and read-error fallback behavior remain.
- Added six isolated filesystem-mock cases.
- The provider diagnostic supports missing, empty and inline synthetic auth storage, overriding inherited inline credentials to avoid contaminating comparisons.

## Result
Partial implementation, NOT promoted.
- Auth and public provider metadata tests: 16 passed, 0 failed, 59 assertions.
- Host typecheck failed with TS2352 in the newly added filesystem mock.
- Post-change actual Host diagnostic was not run because its typecheck gate failed.
- No post-change speedup or product reliability claim is made.

## Evidence
See the companion JSON for pre-change synthetic Host comparisons and gate results.
Before modification, first provider-list requests were approximately 10.848 s (previous missing-store sample), 0.701 s (inline empty), and 1.621 s (empty file). These are single observations, not a controlled performance distribution.
All comparison Hosts made zero inference requests and preserved public metadata redaction and exact high/max capability names.

## Residual Risk
- New test mock needs a type-safe implementation of its filesystem boundary; user decision is requested before correcting the introduced error.
- The extra existence probe and full-Host latency after the change remain unmeasured.
- No real OAuth, native TUI user journey, or independent user validation was performed.
- Previously recorded unrelated failures are not cleared.
- Git and net_monitor.py were untouched.

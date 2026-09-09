# Provider Initialization Stage Diagnosis (2026-09-08)

## Situation
Provider selection now skips excluded initialization paths, but first model-list latency remained variable. A single overall HTTP duration could not distinguish catalog work from authentication-store loading.

## Reason
Timing the actual initialization boundaries is necessary before changing authentication or filesystem behavior. Public metadata must remain redacted and provider-native reasoning names must be preserved.

## Action
- Added 15 fixed Provider stage labels to the existing opt-in startup tracer.
- Placed marks around dependency acquisition, config/catalog work, plugin hooks, credentials and custom loaders.
- Kept the existing 32-event process cap, fixed schema and disabled-by-default behavior.
- Added schema/privacy coverage and a bounded diagnostic that starts one isolated pure-mode Host, waits for health, and requests the same catalog twice.
- The diagnostic drains bounded captured output, stores no raw Host output or response body, makes zero inference calls and waits for Host termination.

## Result
- Relevant tests: **17 passed**, 0 failed, 55 assertions.
- Host typecheck and actual diagnostic: exit 0.
- Host health: **9.755 s**.
- First provider request: **10.848 s**.
- Cached provider request: **97 ms**.
- Provider initialization span: **10.136 s**.
- Credential-loading span: **10.119 s**.
- Catalog mapping: **13 ms**; custom loaders: **1 ms**.
- Both responses retained the connected fixture and exact high/max names without credentials.
- Zero inference requests; all expected provider stages captured. Host intentionally terminated with exit 143.

## Evidence
The companion JSON contains the sanitized 31-event trace and request timings. The credential span starts immediately before auth.all and ends after stored API credentials are considered for active providers.
This measures the surrounding operation, not its internal filesystem/JSON/registration components. There were two service-layer constructions but only one provider-state initialization in the captured trace.

## Residual Risk
- The sample localizes this occurrence, not every historical slow start.
- Auth store reading, JSON decoding, secret registration and fallback handling still need separation before selecting a fix.
- No external Provider latency or OAuth correctness was measured.
- Startup/import latency remains separate from the initial credential-loading delay.
- No speedup or general user stability is claimed; no full application suite was run.
- The tracer remains diagnostic-only and cannot produce Harness Evidence or Ready.
- Git and net_monitor.py were untouched.

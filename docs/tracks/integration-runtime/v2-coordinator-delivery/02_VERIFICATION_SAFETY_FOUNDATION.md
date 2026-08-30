# 02. Verification Safety Foundation

## Situation

Provider, model protocol, tool, implementation, workspace, verifier, and harness failures could be inferred again from natural-language messages, while verification strength and repair behavior were not represented as one public configuration contract.

## Reason

Retry, fallback, repair, and blocking decisions must be based on producer-owned structured data. Actor text and tool output cannot be accepted as trusted failure classification or completion evidence.

## Action

- Added `fast`, `adaptive`, and `strict` verification profiles with separate `auto` and `manual` triggers.
- Added a Host-generated `FailureEnvelope` with kind, source, producer, status, code, retryability, confidence, and classification source.
- Limited message heuristics to low-confidence unknown fallback classification.
- Added run-scoped value-based secret redaction and residual sidecar checks.
- Added structured exploration presets with tool-call and unique-file budgets.
- Removed shell, write, web, and delegation capabilities from exploration workers.
- Preserved legacy verification configuration through a bounded normalization path.

## Result

Typed tags, provider codes, and HTTP status now take precedence over message text. Unknown failures are not automatically repaired, and provider/model/verifier boundaries are not routed into code repair.

## Evidence

- Verification package: 14 tests passed.
- Python sidecar: 22 tests passed.
- Korean text with the same typed provider tag produces the same FailureKind.
- `InvalidProviderOutput` remains a model protocol failure.
- Unknown unstructured errors remain low-confidence and non-retryable.
- SecretRegistry tests passed for raw, URL-encoded, and Basic/base64 forms.

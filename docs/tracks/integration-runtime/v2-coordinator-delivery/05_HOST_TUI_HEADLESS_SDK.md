# 05. Host, TUI, Headless, and SDK Integration

## Situation

UI and CLI consumers inferred scope state from event order and imported verification/orchestration internals directly. Host tool/model events were not consistently bound to verifier actions.

## Reason

Interfaces should render and request actions through the Host API, while the Host owns event provenance and policy.

## Action

- Added `GET /session/:sessionID/harness`.
- Added `POST /session/:sessionID/harness/verify`.
- Added `POST /session/:sessionID/harness/cancel`.
- Added the public `harness.status` event and regenerated SDK clients/types.
- Replaced TUI verifier ownership with Host status rendering and command calls.
- Replaced headless verifier ownership with Host completion waiting and outcome handling.
- Added Host observation for completed/error tool events and model session errors.
- Serialized Host observations without blocking EventV2/TUI delivery.
- Buffered pre-contract events and replayed them after explicit contract acceptance.
- Changed verifier startup to JIT and cleaned runs when their workspace instance closes.
- Preserved root model, provider, variant, and prompt context for integration and repair.

## Result

The UI is no longer a second policy engine. Ordinary conversation does not start the Python verifier or trigger repair; verification starts only after an accepted contract and relevant action, or an explicit verification request.

## Evidence

- No direct verification/core-orchestration imports remain in TUI verification or headless run entrypoints.
- Event manifest tests include the new 89th public event.
- Host event, retry, and exploration regression bundle: 66 tests passed.
- Representative prompt, provider failure, local provider, and tool-continuation cases: 4 tests passed.
- CLI help smoke test exited with code 0.

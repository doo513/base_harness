# TUI attached-session recovery and typed controls

Date: 2026-09-08 (Asia/Seoul)
Status: Implemented and exercised in a native Windows PTY; broader product completion remains unproven.

## Situation

The previous Host/headless recovery gates passed, but an actual 80-column by 24-row TUI attached to a restarted Host displayed an inactive harness. The Host already held a signed, interrupted plan revision requiring explicit discard.

The first interactive attempt was retained as a failed test, not restarted as though it had succeeded:

- The Host returned PLAN_REVISION_PENDING.
- The TUI overlay displayed VERIFIED STATE INACTIVE and Waiting for the Host Coordinator.
- Typing /plan discard produced Failed to send prompt instead of a typed control request.
- The fixture finished with exit code 1 because recovery, a new reviewed plan, and execution had not occurred.

## Reason

Two interface boundaries were incomplete:

1. Initial root selection and status retrieval depended on rendering sidebar_content. A narrow terminal can hide that sidebar entirely. A quiet, recovered session need not emit a new event to compensate.
2. The autocomplete list registered multiword commands, but input submission did not resolve complete local command names before ordinary prompt dispatch. An input containing a space could leave autocomplete and reach the model-prompt endpoint.

These were not failures of the Python completion verifier. They prevented the user interface from correctly observing and controlling the Host that owns verification.

## Action

- Added a presentation-only HarnessStatus binding keyed by session and workspace directory.
- Derive the active root from the current route and parent-session metadata, independently of sidebar mounting.
- Refresh status on route selection, clear previous-session presentation when the target changes, and ignore unrelated session events.
- Discard pending GET responses after a target change, a newer refresh, a Host status event, or disposal.
- Match registered local slash names and aliases exactly before agent/model checks and ordinary prompt submission. Multiword names such as /plan discard and /hackathon off are included.
- Keep the command palette and typed HarnessControl API as the dispatch authority. No natural-language policy inference was added.
- Added deterministic regression tests and a reusable interactive fixture runner.

Production files:

- runtime/packages/tui/src/feature-plugins/verification.tsx
- runtime/packages/tui/src/component/prompt/index.tsx
- runtime/packages/tui/src/harness/session-status.ts
- runtime/packages/tui/src/prompt/local-slash.ts

Test support:

- runtime/packages/tui/test/harness-session-controls.test.ts
- runtime/script/verify-tui-plan-recovery.mjs

The kernel, sidecar wire v4, candidate attestation, Overlay commit policy, model-effort naming, and root-only Ready authority were not changed.

## Result

The second native PTY attempt completed through actual keyboard input:

1. The attached TUI displayed the pending/interrupted-plan warning without opening a sidebar.
2. /plan discard reached the Host. The fixture asserted zero added model requests and no Ready artifact during discard.
3. /plan followed by the new goal created a different reviewed plan ID. The plan-only state remained ineligible for Ready.
4. /execute started a new execution run linked to that reviewed plan.
5. Both WorkUnits completed and both output files contained the exact revised fixture content.
6. The real Python verifier emitted the Ready artifact with verified results for both required Claims and Criteria.
7. The TUI footer reached ready and the overlay displayed VERIFIED STATE READY (adaptive).
8. Ctrl+C exited the TUI with code 0 and emitted terminal restoration sequences. The fixture then stopped its Host and finished with code 0.

The selected fixture reasoning effort remained high in the new planning, review, worker, and integration model requests. This demonstrates fixture-level propagation, not certification of an external provider.

## Evidence

### Automated gates

| Gate | Result |
| --- | --- |
| New session/control tests plus status presentation tests | 30 passed, 0 failed, 56 expectations |
| Existing keymap and app lifecycle tests | 4 passed, 0 failed, 8 expectations |
| TUI typecheck | Exit 0 |
| Host typecheck | Exit 0 |
| Interactive recovery fixture after the change | Exit 0 |
| Native TUI clean exit | Exit 0 |

Bun: pinned 1.3.14.
Verifier: repository-pinned Python environment.
Model and MCP: local deterministic fixtures only; no paid external model requests.

### Run identity

- Session: ses_f83991a85ffeIv0PLkZKkoV4ph
- Discarded plan: d7fe87c6-e125-4463-b55b-7174ae4c6476
- Newly reviewed plan: 14581371-2af4-4348-ac52-b3a8faeb17a7
- Planning run: run-6237f1ee-8425-40e6-9437-8d61e6fdde5b
- Execution run: run-0275f7dd-d254-45fd-8ff5-f480b6825a8b
- Ready artifact suffix: artifacts/2b/2bcf6f8a47151ef586008801d99f653c5c77d67b7bee795db885eb15448da797.json

### Local evidence artifacts

- .tools/validation/restoration-phase30-tui-recovery.result.json: retained failed pre-fix attempt.
- .tools/validation/restoration-phase31-tui-recovery.result.json: Host observations, requests, run identity, output/Ready assertions, and process results.
- .tools/validation/restoration-phase31-terminal-evidence.json: selected pre/post native PTY outputs and their capture limitations.
- .tools/validation/restoration-phase31-gates.json: gate summary.
- Fixture workspace/state: C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-5qdQdx

The generated result retains the full Ready artifact path. Temporary state is diagnostic data, not a portable installed-product artifact.

### Status latency observations

Twenty alternating localhost GET samples were collected per status category before interactive input:

| Current endpoint observation | Median | p95 |
| --- | ---: | ---: |
| Empty session status | 30.23 ms | 35.28 ms |
| Pending-revision status | 54.10 ms | 76.18 ms |

The first pending-status request took 120.03 ms. These are current HTTP observations, not model latency, precise first-paint timing, or a controlled before/after performance benchmark. The patch does not establish a speedup.

The planned two-WorkUnit fixture made 11 model requests after discard: six planning/review requests, four worker requests, and one integration request. That is a deliberately planned multiunit case, not the direct-path cost of a simple file edit. This patch does not reduce planning/model overhead.

## Residual Risk

- The detailed overlay exceeds the available height at 80x24. Its warning and Ready header are visible, but lower evidence/repair details can be clipped. A bounded, scrollable or paginated presentation is still needed.
- Plan-only selection feedback before submitting the next goal needs a dedicated UI gate for existing sessions; the current footer primarily exposes staged home-screen controls.
- This change covers exact registered commands. Argument-bearing forms such as /execute <planId> are not implemented by the new exact matcher.
- Native PTY output was captured, not Windows GUI screenshots. One intermediate planning-progress observation was truncated and is not used as completion proof.
- External OAuth/provider behavior, Linux PTY behavior, full CJK/IME interaction, and wide-screen layout were not newly certified here.
- The terminal title still exposed an OC prefix in the captured transcript. Branding cleanup is separate from execution correctness.
- No Git commands, commit, or push were performed. net_monitor.py was not modified.

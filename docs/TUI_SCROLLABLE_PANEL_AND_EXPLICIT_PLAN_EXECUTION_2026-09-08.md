# Scrollable harness panel and explicit plan execution

Date: 2026-09-08 (Asia/Seoul)
Status: Functional paths verified; visual polish and error detail remain incomplete.

## Situation

The previous native TUI recovery test reached verifier-issued Ready, but an 80x24 terminal clipped the lower harness details. Existing-session /plan selection was also difficult to see, and /execute with an explicit plan ID was not handled by the local slash matcher.

## Reason

- The overlay had no height-bounded detail viewport.
- The footer used the home-screen staging queue rather than the active session's Host planning preference.
- Local slash matching supported exact command names, but no registered argument contract.

These are presentation and input-routing issues. The Host must continue to decide whether a plan can execute; adding UI argument support must not bypass plan identity, revision, or basis validation.

## Action

1. Bound overlay dimensions to terminal size and keep its title and navigation footer outside the scrolling detail body.
2. Add PageUp/PageDown bindings while the overlay is mounted, and reset detail scrolling when the view or run changes.
3. Display next-request plan-only selection using the active Host session when one exists, or the staging queue on the home screen.
4. Show a Plan-only enabled acknowledgement after the Host accepts /plan.
5. Add declarative optional-token metadata for registered slash commands and pass arguments through the existing keymap payload.
6. Forward the supplied plan ID unchanged in the typed planning.execute control.
7. Prefer the longest registered multiword command name and reject invalid arguments before ordinary prompt dispatch.
8. Add deterministic layout, preference, and argument-routing tests.

Changed production files:

- runtime/packages/tui/src/feature-plugins/verification.tsx
- runtime/packages/tui/src/keymap.tsx
- runtime/packages/tui/src/component/prompt/index.tsx
- runtime/packages/tui/src/prompt/local-slash.ts
- runtime/packages/tui/src/harness/panel-presentation.ts

New tests: runtime/packages/tui/test/harness-panel-arguments.test.ts

No changes were made to the Kernel, verification profile policy, sidecar protocol, Overlay commit gate, provider-effort mappings, or root-only Ready authority. No external runtime SDK or natural-language decision rule was added.

## Result

### Actual Windows PTY interaction

- The overlay border remained inside the 80x24 viewport, with its bottom border on row 22.
- PageDown exposed the previously clipped Evidence and Repairs details; PageUp returned to the recovery warning.
- /plan discard still completed through the Host with no added model request.
- /plan immediately displayed both a confirmation and next: plan-only.
- A Host query before the next goal confirmed planningPreference=plan_once, planningState=idle, Ready ineligible, and neither target file present.
- The new goal stopped at a separately reviewed plan before execution.
- /execute missing-plan produced a Kernel control rejection. A subsequent Host query confirmed the reviewed plan and planning run were unchanged and no target file had been created.
- /execute d802c50c-0661-4b8e-861f-27d0249135c0 executed the actual reviewed plan.
- Both WorkUnits completed, the exact requested file contents were checked, and the real Python verifier emitted Ready (adaptive).
- /execute one two displayed an Invalid control command message. The completed run stayed ready, and the final fixture log contained zero model requests after Ready.
- With invalid text still in the input, the first Ctrl+C cleared it. The second Ctrl+C exited the TUI with code 0 and emitted terminal restoration sequences.
- The interactive fixture then stopped its Host and exited with code 0.

### Important limitation

Scrolling works, but some blank cells in the overlay reveal characters from the underlying transcript. The UI is therefore not visually complete. This defect was retained and disclosed rather than hidden by a successful execution result.

## Evidence

| Gate | Result |
| --- | --- |
| TUI regression tests across five files | 49 passed, 0 failed, 106 expectations |
| TUI typecheck | Exit 0 |
| Host typecheck | Exit 0 |
| Pre-goal plan-only state check | Exit 0 |
| Wrong-plan-ID safety check | Exit 0 |
| Malformed-command state check | Exit 0 |
| Actual PTY recovery and explicit-ID execution | Exit 0 |

Runtime: Bun 1.3.14 and the repository-pinned Python verifier.
Model/MCP: isolated local fixtures only. No paid external model requests were made.

Run identity:

- Session: ses_f8386bfc8ffew48cd37BBRPzyo
- Reviewed plan: d802c50c-0661-4b8e-861f-27d0249135c0
- Planning run: run-ab0c84b6-1f81-41dd-ac0e-f78c43b63210
- Execution run: run-6dceee0e-3e91-4e7b-bd8e-aa46937040c3
- Ready artifact suffix: artifacts/a5/a58f028ee86b7b7d88c7028955a9963b92f12c0aac5676f4d391a472ae5ae43a.json

Local artifacts:

- .tools/validation/restoration-phase32-tui-controls.result.json
- .tools/validation/restoration-phase32-before-goal.json
- .tools/validation/restoration-phase32-wrong-plan-id.json
- .tools/validation/restoration-phase32-invalid-syntax.json
- .tools/validation/restoration-phase32-terminal-planning.json
- .tools/validation/restoration-phase32-terminal-execution.json
- .tools/validation/restoration-phase32-gates.json

The source fixture runner is runtime/script/verify-tui-plan-recovery.mjs. Native terminal input was supplied separately; the JSON result is not a claim that the script automatically drove a GUI.

The two-WorkUnit fixture used 11 model requests after discard, unchanged from the prior recorded case. This is not a direct-path cost benchmark, and this patch does not establish a model-cost or execution-speed improvement.

## Residual Risk and Next Work

- Fix overlay/scroll surface opacity and verify that whitespace does not expose underlying transcript characters after scrolling.
- Preserve the structured Host rejection code/message in the TUI. The wrong-ID test currently shows the generic Harness API request failed text.
- Distinguish next-request plan-only selection from a plan-only run already in progress; the next label can persist during contract building.
- Avoid the unnecessary horizontal scrollbar where details only require vertical scrolling.
- Native PTY tests do not certify every theme, terminal, screen size, or Korean IME composition path. Layout dimension tests are not substitutes for rendering tests.
- The old OC terminal-title prefix remains outside this change.
- No Git commands, commit, or push were performed. net_monitor.py was untouched.

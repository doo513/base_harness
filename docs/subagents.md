# Managed Agents

Managed subagents are not part of this MVP.

The implemented harness is a single local workflow around `run_intake_workflow`. It may produce a context packet that a human or one Codex session can reason from, but it does not spawn workers, coordinate background agents, or maintain multi-agent state.

If review from another perspective is needed, run it outside this harness and treat the result as ordinary user-provided context.

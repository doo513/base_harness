# Phase 10 — Progress / Recovery Alignment

Status: ALIGNED WITHOUT WEAKENING STAGE-06 AUTHORITY; real-task threshold tuning remains evidence-driven.

## Problem / evidence

A real development task contains useful inspection/planning/tool activity that is not itself proof that the task advanced. Treating every successful action as progress would allow loops to self-reset, while treating domain work only as generic activity can make the control horizon feel disconnected from actual task progress.

## Decision

Do not redefine raw activity as progress.

The integration layer now supplies the missing bridge:

```text
Actor workflow / tool activity
        ↓
execution evidence
        ↓
domain verifier
        ↓
verified fact
        ↓
DomainProfile.task_progress_snapshot
        ↓
Stage-06 task progress credit
```

This keeps the original Stage-06 authority rule intact while giving Software/Hackathon concrete task-native progress signals.

## Implemented alignment

- Agent `plan` / `task` state remains bookkeeping with zero progress authority;
- tool/retrieval novelty remains activity only;
- Software verified build/test/behavior facts now produce deterministic milestones;
- Hackathon verified build/demo/rehearsal check facts now produce deterministic milestones;
- `task_progress_snapshot()` is pure and monotonic over verified facts;
- existing recovery remains responsible for repeated/no-progress control.

## Structural review

- no model confidence or narrative self-assessment can reset the loop;
- no soft Hackathon evaluation can reset the loop;
- no memory/retrieval content can reset the loop;
- verifier-backed domain milestones do reset the no-progress streak through the existing Stage-06 task-progress path;
- completion remains independent and Oracle-owned.

## Validation focus

`tests/test_integration_progress_alignment.py` fixes two critical invariants:

- Actor task bookkeeping alone does not reset progress;
- a newly verified Software task milestone resets the no-progress streak through the existing task-progress path.

## Remaining evidence question

The default no-progress/family-repeat thresholds may still be too short or too long for some real repositories. This phase intentionally does **not** relax them from intuition alone. Phase 11/12 must measure:

- useful inspection steps before first verified milestone;
- false recovery rate during productive work;
- repeated-action loop detection latency;
- recovery success rate;
- token/time cost created by verification cadence.

Threshold changes should follow those measurements rather than redefining activity as truth-bearing progress.

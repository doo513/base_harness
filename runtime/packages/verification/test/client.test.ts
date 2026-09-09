import { expect, test } from "bun:test"
import { resolve } from "node:path"
import { ProcessVerificationClient, VerificationClientError } from "../src/client"
import { createGoalContract, goalSource, materializeProposal } from "../src/types"

const source = goalSource("exercise protocol v3", "test-source")
const contract = createGoalContract(source)

test("host uses contract and two-phase action before accepting Ready over protocol v4", async () => {
  const client = await ProcessVerificationClient.start(
    {
      runId: "test-run",
      scopeId: "root",
      workspace: process.cwd(),
      goalSources: [source],
      goalContract: contract,
    },
    {
      command: [
        process.env.BASE_HARNESS_PYTHON ?? "python",
        resolve(import.meta.dir, "fixture-sidecar.py"),
      ],
    },
  )
  await client.observe({ tool: "write", status: "completed" })
  const status = await client.verify("manual")
  expect(status.outcome).toBe("ready")
  expect(status.readyRef?.trust).toBe("verifier_attested")
  expect(status.candidateRefs[0]?.trust).toBe("untrusted_execution_observation")
  await client.dispose()
})

test("materialized GoalContract contains bidirectional claim links", () => {
  const criterion = contract.criteria[0]!
  const claim = contract.claims[0]!
  expect(criterion.claimIds).toEqual([claim.claimId])
  expect(claim.criterionIds).toEqual([criterion.criterionId])
  expect(contract.sourceRefs[0]?.sha256).toHaveLength(64)
})

test("child scope verifies assigned Claims without issuing root Ready", async () => {
  const client = await ProcessVerificationClient.start(
    {
      runId: "scoped-run",
      scopeId: "root",
      workspace: process.cwd(),
      goalSources: [source],
      goalContract: contract,
    },
    {
      command: [
        process.env.BASE_HARNESS_PYTHON ?? "python",
        resolve(import.meta.dir, "fixture-sidecar.py"),
      ],
    },
  )
  const claimId = contract.claims[0]!.claimId
  const criterionId = contract.criteria[0]!.criterionId
  await client.openScope("worker-1", "root", { kind: "work_unit", assignedClaimIds: [claimId] })
  const candidate = {
    candidateId: "fixture-candidate",
    runId: "scoped-run",
    scopeId: "worker-1",
    workUnitId: "unit-1",
    revision: 1,
    files: [],
    patchHash: "c".repeat(64),
    overlayRoot: process.cwd(),
  }
  const attached = await client.attachCandidate(candidate)
  expect(attached.scopeId).toBe("worker-1")
  const observed = await client.observe({ scopeId: "worker-1", claimIds: [claimId], tool: "write", status: "completed" })
  expect(observed.scopeId).toBe("worker-1")
  const child = await client.verify("completion", "worker-1", {
    claimIds: [claimId],
    criterionIds: [criterionId],
  })
  expect(child.outcome).toBe("scope_verified")
  expect(child.scopeAttestation).toMatchObject({
    candidateId: candidate.candidateId,
    candidateRevision: candidate.revision,
    patchHash: candidate.patchHash,
  })
  const committed = await client.commitCandidate(child.scopeAttestation!, "worker-1")
  expect(committed.scopeId).toBe("worker-1")
  expect(child.readyRef).toBeNull()
  const root = await client.verify("completion")
  expect(root.outcome).toBe("ready")
  expect(root.scopeId).toBe("root")
  await client.dispose()
})

const startWithMode = (mode: string) =>
  ProcessVerificationClient.start(
    {
      runId: "failure-" + mode,
      scopeId: "root",
      workspace: process.cwd(),
      goalSources: [source],
      goalContract: contract,
    },
    {
      command: [
        process.env.BASE_HARNESS_PYTHON ?? "python",
        resolve(import.meta.dir, "fixture-sidecar.py"),
        mode,
      ],
      timeoutMs: 2_000,
    },
  )

test("malformed NDJSON is fail-closed", async () => {
  const result = startWithMode("malformed")
  await expect(result).rejects.toBeInstanceOf(VerificationClientError)
  await expect(result).rejects.toMatchObject({ failureKind: "harness_protocol_error" })
})

test("sidecar version mismatch is fail-closed", async () => {
  const result = startWithMode("version-mismatch")
  await expect(result).rejects.toBeInstanceOf(VerificationClientError)
  await expect(result).rejects.toMatchObject({ failureKind: "harness_protocol_version_mismatch" })
})

test("sidecar crash is fail-closed", async () => {
  const result = startWithMode("crash")
  await expect(result).rejects.toBeInstanceOf(Error)
})

for (const mode of ["wrong-run", "wrong-scope", "clean-exit"]) {
  test(mode + " sidecar response cannot be accepted", async () => {
    await expect(startWithMode(mode)).rejects.toBeInstanceOf(VerificationClientError)
  })
}

test("materialization preserves each claim's predicate and verifier policy", () => {
  const first = contract.claims[0]!
  const criterion = contract.criteria[0]!
  const proposal = {
    goal: source.text,
    criteria: [{ ...criterion, claimIds: ["artifact-claim", "exit-claim"] }],
    claims: [
      { ...first, claimId: "artifact-claim", kind: "artifact" as const, predicate: { type: "exists" },
        scope: { targets: ["result.txt"], capabilities: [], exclusions: [] },
        verifierPolicy: { minimumStrength: "structural" as const, allowedVerifierIds: ["file"], minIndependentFamilies: 1 } },
      { ...first, claimId: "exit-claim", predicate: { type: "command_exit", expectedExitCode: 7 } },
    ],
  }
  const materialized = materializeProposal(source, proposal)
  expect(materialized.claims[0]!.predicate).toEqual({ type: "exists" })
  expect(materialized.claims[0]!.verifierPolicy.allowedVerifierIds).toEqual(["file"])
  expect(materialized.claims[1]!.predicate).toEqual({ type: "command_exit", expectedExitCode: 7 })
})

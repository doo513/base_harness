import { afterEach, beforeEach, expect, test } from "bun:test"
import { mkdtemp, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import type { GoalContract, Risk } from "@base-harness/domain-contracts"
import * as Workspace from "../src/orchestration"

const cleanup: string[] = []
let store: Workspace.WorkspaceCandidateStore

beforeEach(() => {
  store = new Workspace.WorkspaceCandidateStore(async () => true)
  Workspace.bindWorkspaceCandidateStore(store)
})

afterEach(async () => {
  await store.flushPersistence()
  Workspace.resetForTest()
  await Promise.all(cleanup.splice(0).map((entry) => rm(entry, { recursive: true, force: true })))
})

async function open(sessionID: string) {
  const workspace = await mkdtemp(path.join(tmpdir(), "base-harness-contract-authority-"))
  cleanup.push(workspace)
  Workspace.beginPrompt({ sessionID, workspace, goal: "bounded change", exploration: "manual" })
  return workspace
}

function authority(
  target: string,
  options: { risk?: Risk; capability?: string; exclusions?: string[] } = {},
): Pick<GoalContract, "claims" | "criteria"> {
  return {
    criteria: [{
      criterionId: "criterion", statement: "bounded result", sourceRefs: [], claimIds: ["claim"],
      required: true, risk: options.risk ?? "low",
    }],
    claims: [{
      claimId: "claim", criterionIds: ["criterion"], origin: "user", statement: "bounded result", kind: "artifact",
      scope: {
        targets: [target], capabilities: [options.capability ?? "write"], exclusions: options.exclusions ?? [],
      },
      applicability: {
        os: "test", arch: "test", runtime: "test", provider: "test", model: "test", tools: {},
        dependencyLockHash: "test", configHash: "test", workspaceRevision: "test",
      },
      predicate: { type: "exists" },
      verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["test"], minIndependentFamilies: 1 },
    }],
  }
}

test("direct structured writes stay inside state-changing GoalContract targets", async () => {
  const workspace = await open("root")
  Workspace.registerContract("root", ["claim"], ["criterion"], authority("allowed.txt"))
  Workspace.beginDirectExecution("root")

  await expect(Workspace.resolveWrite("root", workspace, "allowed.txt")).resolves.toMatchObject({ overlay: false })
  await expect(Workspace.resolveWrite("root", workspace, "other.txt")).rejects.toMatchObject({
    code: "OWNERSHIP_VIOLATION",
  })
  await expect(Workspace.resolveWrite("root", workspace, path.join(workspace, "..", "escape.txt"))).rejects.toMatchObject({
    code: "OWNERSHIP_VIOLATION",
  })
})

test("read-only claim capabilities cannot authorize a write", async () => {
  const workspace = await open("root")
  Workspace.registerContract("root", ["claim"], ["criterion"], authority("result.txt", { capability: "read" }))
  Workspace.beginDirectExecution("root")
  await expect(Workspace.resolveWrite("root", workspace, "result.txt")).rejects.toMatchObject({
    code: "OWNERSHIP_VIOLATION",
  })
})

test("IDs-only registration cannot become path authority", async () => {
  const workspace = await open("root")
  Workspace.registerContract("root", ["claim"], ["criterion"])
  Workspace.beginDirectExecution("root")

  await expect(Workspace.resolveWrite("root", workspace, "result.txt")).rejects.toMatchObject({
    code: "OWNERSHIP_VIOLATION",
  })
  await expect(Workspace.assertOpaqueExecutionAllowed("root")).rejects.toThrow(
    "register the accepted GoalContract",
  )
})

test("an open root without an accepted contract has no structured write authority", async () => {
  const workspace = await open("root")
  await expect(Workspace.resolveWrite("root", workspace, "result.txt")).rejects.toMatchObject({
    code: "OWNERSHIP_VIOLATION",
  })
})

test("WorkUnit and integration ownership cannot broaden accepted contract paths", async () => {
  await open("root")
  Workspace.registerContract("root", ["claim"], ["criterion"], authority("src/owned"))
  Workspace.beginPlanning("root")

  await expect(Workspace.acceptWorkGraph("root", {
    units: [{
      id: "unit", title: "outside", instructions: "write outside", claimIds: ["claim"], criterionIds: ["criterion"],
      dependsOn: [], readSet: [], writeSet: ["src/other.txt"], integrationRequests: [],
    }],
    integrationPaths: [],
  })).rejects.toMatchObject({ code: "OWNERSHIP_VIOLATION" })

  await expect(Workspace.acceptWorkGraph("root", {
    units: [{
      id: "unit", title: "inside", instructions: "write inside", claimIds: ["claim"], criterionIds: ["criterion"],
      dependsOn: [], readSet: [], writeSet: ["src/owned/unit.txt"], integrationRequests: [],
    }],
    integrationPaths: ["src/shared.txt"],
  })).rejects.toMatchObject({ code: "OWNERSHIP_VIOLATION" })
})

test("root integration writes are the intersection of contract targets and reviewed integrationPaths", async () => {
  const workspace = await open("root")
  Workspace.beginPrompt({ sessionID: "scoped", workspace, goal: "integrate", exploration: "manual" })
  Workspace.registerContract("scoped", ["claim"], ["criterion"], authority("src"))
  Workspace.beginPlanning("scoped")
  await Workspace.acceptWorkGraph("scoped", {
    units: [{
      id: "unit", title: "unit", instructions: "write unit", claimIds: ["claim"], criterionIds: ["criterion"],
      dependsOn: [], readSet: [], writeSet: ["src/unit.txt"], integrationRequests: [],
    }],
    integrationPaths: ["src/shared.txt"],
  })
  store.roots.get("scoped")!.phase = "integration"

  await expect(Workspace.resolveWrite("scoped", workspace, "src/shared.txt")).resolves.toMatchObject({ overlay: false })
  await expect(Workspace.resolveWrite("scoped", workspace, "src/unit.txt")).rejects.toThrow("integrationPaths")
})

test("a new Run replaces rather than inherits prior path authority", async () => {
  const workspace = await open("root")
  Workspace.registerContract("root", ["claim"], ["criterion"], authority("first.txt"))
  Workspace.beginDirectExecution("root")
  await expect(Workspace.resolveWrite("root", workspace, "first.txt")).resolves.toBeDefined()
  Workspace.markOutcome("root", "ready")

  Workspace.beginPrompt({ sessionID: "root", workspace, goal: "second bounded change", exploration: "manual" })
  Workspace.registerContract("root", ["claim"], ["criterion"], authority("second.txt"))
  Workspace.beginDirectExecution("root")
  await expect(Workspace.resolveWrite("root", workspace, "first.txt")).rejects.toMatchObject({
    code: "OWNERSHIP_VIOLATION",
  })
  await expect(Workspace.resolveWrite("root", workspace, "second.txt")).resolves.toBeDefined()
})

test("opaque execution needs workspace-wide ownership without path exclusions", async () => {
  await open("root")
  Workspace.registerContract("root", ["claim"], ["criterion"], authority(".", { risk: "low" }))
  Workspace.beginDirectExecution("root")
  await expect(Workspace.assertOpaqueExecutionAllowed("root")).rejects.toThrow("high-risk")

  Workspace.registerContract("root", ["claim"], ["criterion"], authority(".", { risk: "high" }))
  await expect(Workspace.assertOpaqueExecutionAllowed("root")).resolves.toBeUndefined()

  Workspace.registerContract("root", ["claim"], ["criterion"], authority(".", {
    risk: "high", exclusions: ["protected"],
  }))
  await expect(Workspace.assertOpaqueExecutionAllowed("root")).rejects.toThrow("cannot enforce")
})

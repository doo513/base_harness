import { afterEach, beforeEach, expect, test } from "bun:test"
import { mkdtemp, mkdir, realpath, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import * as O from "../src/orchestration"

let root: string, workspace: string
beforeEach(async () => {
  root = await mkdtemp(path.join(os.tmpdir(), "base-harness-scope-catalog-"))
  workspace = path.join(root, "workspace")
  await mkdir(workspace)
})
afterEach(async () => {
  const actual = await realpath(root), parent = await realpath(os.tmpdir())
  if (path.dirname(actual) !== parent || !path.basename(actual).startsWith("base-harness-scope-catalog-")) throw new Error("Unsafe fixture cleanup")
  await rm(actual, { recursive: true, force: true })
})

const catalog = [
  "read","list","glob","grep","edit","write","lsp","question","invalid",
  "bash","argv","apply_patch","task","execute","webfetch","websearch","skill",
  "harness_contract","harness_workgraph","fixture_echo","read_mcp_resource",
].map(id => ({id,description:"fixture " + id}))

async function child(kind: "worker" | "explore" | "meta-review", run: (store: O.WorkspaceCandidateStore) => void | Promise<void>) {
  const store = new O.WorkspaceCandidateStore(async () => true)
  await O.withWorkspaceCandidateStore(store, async () => {
    O.beginPrompt({ sessionID:"root", workspace, goal:"fixture", exploration:kind==="explore"?"always":"manual" })
    if (kind === "worker") {
      O.registerContract("root", ["claim"], ["criterion"])
      O.beginPlanning("root")
      await O.acceptWorkGraph("root", { units:[{
        id:"unit",title:"fixture unit",instructions:"write the assigned file",claimIds:["claim"],criterionIds:["criterion"],
        readSet:[],writeSet:["result.txt"],dependsOn:[],integrationRequests:[],
      }],integrationPaths:[] })
    }
    O.startChild({ parentSessionID:"root",sessionID:"child",subagentType:kind==="worker"?"general":kind,
      ...(kind==="worker"?{workUnitId:"unit"}:{}) })
    await run(store)
    await O.flushPersistence()
  })
}

test("workers advertise only tools already permitted at their execution boundary", async () => {
  await child("worker", async () => {
    const visible = O.filterToolsForScope("child", catalog)
    expect(visible.map(tool => tool.id)).toEqual(["read","glob","grep","edit","write","lsp","question","invalid"])
    for (const tool of catalog) {
      if (visible.includes(tool)) expect(() => O.assertToolAllowed("child",tool.id)).not.toThrow()
      else expect(() => O.assertToolAllowed("child",tool.id)).toThrow()
    }
  })
})

test("patch-only model preference can fall back to scope-permitted structured editors", async () => {
  await child("worker", () => {
    expect(O.filterToolsForScope("child", [{id:"apply_patch"}])).toEqual([])
    expect(O.filterToolsForScope("child", [{id:"edit"},{id:"write"}]).map(tool => tool.id)).toEqual(["edit","write"])
  })
})

for (const kind of ["explore","meta-review"] as const) {
  test(kind + " exposes only read/list/glob/grep and closed inspection has no tools", async () => {
    await child(kind, async () => {
      expect(O.filterToolsForScope("child", catalog).map(tool => tool.id)).toEqual(["read","list","glob","grep"])
      await O.finishChild("child",true)
      expect(O.filterToolsForScope("child",catalog)).toEqual([])
      expect(() => O.assertToolAllowed("child","read")).toThrow()
    })
  })
}

test("frozen workers reject calls from previously advertised schemas", async () => {
  await child("worker", store => {
    const advertised = O.filterToolsForScope("child",catalog)
    expect(advertised.some(tool => tool.id==="write")).toBe(true)
    // Explicit state-machine fixture, not a candidate verification or commit.
    store.scopes.get("child")!.status="verifying"
    expect(O.filterToolsForScope("child",catalog)).toEqual([])
    expect(() => O.assertToolAllowed("child","write")).toThrow()
  })
})

test("listing a catalog neither edits definitions nor advances scope state", async () => {
  await child("worker", store => {
    const status=store.scopes.get("child")!.status,active=store.roots.get("root")!.active.size
    const before=JSON.stringify(catalog)
    for(let i=0;i<10;i++)O.filterToolsForScope("child",catalog)
    expect(JSON.stringify(catalog)).toBe(before)
    expect(store.scopes.get("child")!.status).toBe(status)
    expect(store.roots.get("root")!.active.size).toBe(active)
  })
})

test("unmanaged/root catalogs retain their existing behavior", async () => {
  const store=new O.WorkspaceCandidateStore(async()=>true)
  await O.withWorkspaceCandidateStore(store,async()=>{
    expect(O.filterToolsForScope("unmanaged",catalog)).toEqual(catalog)
    O.beginPrompt({sessionID:"root",workspace,goal:"fixture",exploration:"manual"})
    expect(O.filterToolsForScope("root",catalog)).toEqual(catalog)
    await O.flushPersistence()
  })
})

test("persistence failures propagate rather than becoming an empty successful catalog", async () => {
  const store=new O.WorkspaceCandidateStore(async()=>{throw new Error("fixture storage failure")})
  await O.withWorkspaceCandidateStore(store,async()=>{
    O.beginPrompt({sessionID:"root",workspace,goal:"fixture",exploration:"manual"})
    O.startChild({parentSessionID:"root",sessionID:"child",subagentType:"meta-review"})
    await expect(O.flushPersistence()).rejects.toThrow("Workspace state persistence failed")
    expect(()=>O.filterToolsForScope("child",catalog)).toThrow("Workspace state persistence failed")
  })
})

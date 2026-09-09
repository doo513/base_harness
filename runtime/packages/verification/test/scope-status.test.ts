import { expect, test } from "bun:test"
import { ProcessVerificationClient } from "../src/client"
import { goalSource } from "../src/types"

test("fresh and reopened scope snapshots do not inherit another rejection", async () => {
  const script = [
    'import {createInterface} from "node:readline";',
    'for await(const line of createInterface({input:process.stdin})){',
    ' const request=JSON.parse(line);',
    ' const payload={state:request.type==="run.close"?"closed":"open",runId:request.runId,scopeId:request.scopeId,rootScopeId:"root"};',
    ' if(request.type==="hello")payload.protocolVersion=4;',
    ' if(request.type==="verify.request")Object.assign(payload,{state:"repair",outcome:"repair",failureKind:"implementation_error",failedCriterion:"criterion-a",missingEvidence:["claim-a"],repairCount:1,failureFingerprint:"fingerprint-a",message:"repair a"});',
    ' console.log(JSON.stringify({version:4,id:request.id,runId:request.runId,scopeId:request.scopeId,type:"response",payload}));',
    '}',
  ].join("\n")
  const client = await ProcessVerificationClient.start({
    runId: "scope-snapshots", scopeId: "root", workspace: process.cwd(), goalSources: [goalSource("Check scope-local status")],
  }, { command: [process.execPath, "-e", script], timeoutMs: 3000 })
  try {
    await client.openScope("a", "root")
    expect((await client.verify("completion", "a")).outcome).toBe("repair")
    const sibling = await client.openScope("b", "root")
    expect(sibling.scopeId).toBe("b")
    expect(sibling.outcome).toBeUndefined()
    expect(sibling.failureKind).toBeUndefined()
    expect(sibling.failedCriterion).toBeUndefined()
    expect(sibling.missingEvidence).toEqual([])
    expect(sibling.repairCount).toBe(0)
    expect(sibling.message).toBeUndefined()
    const action = await client.openAction({scopeId:"b",claimIds:["claim-b"],tool:"fixture"})
    await client.closeAction({scopeId:"b",actionId:action.actionId,status:"completed"})
    await client.verify("completion", "a")
    const reopened = await client.reopenScope("a")
    expect(reopened.outcome).toBeUndefined()
    expect(reopened.failureFingerprint).toBeUndefined()
    const repair = await client.openAction({scopeId:"a",claimIds:["claim-a"],tool:"fixture"})
    await client.closeAction({scopeId:"a",actionId:repair.actionId,status:"completed"})
  } finally {
    await client.dispose()
  }
})

test("a matching envelope cannot smuggle a different payload scope", async () => {
  const script = [
    'import {createInterface} from "node:readline";',
    'for await(const line of createInterface({input:process.stdin})){',
    ' const request=JSON.parse(line);',
    ' const payload={state:"open",runId:request.runId,scopeId:request.type==="status.get"?"forged":request.scopeId,rootScopeId:"root"};',
    ' if(request.type==="hello")payload.protocolVersion=4;',
    ' console.log(JSON.stringify({version:4,id:request.id,runId:request.runId,scopeId:request.scopeId,type:"response",payload}));',
    '}',
  ].join("\n")
  const client = await ProcessVerificationClient.start({
    runId: "scope-identity", scopeId: "root", workspace: process.cwd(), goalSources: [goalSource("Check payload identity")],
  }, { command: [process.execPath, "-e", script], timeoutMs: 3000 })
  try {
    const error = await client.status("child").catch(error => error)
    expect(error).toMatchObject({failureKind:"harness_protocol_error"})
    expect(client.snapshot().readyEligible).toBe(false)
    expect(client.snapshot().readyRef).toBeNull()
  } finally {
    await client.dispose()
  }
})

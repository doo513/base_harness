import { expect, test } from "bun:test"
import { ProcessVerificationClient } from "../src/client"
import { goalSource } from "../src/types"

for (const mode of ["matching", "missing", "mismatch", "refused"] as const) {
  test("candidate commit acknowledgment: " + mode, async () => {
    const script = [
      'import {createInterface} from "node:readline";',
      "const mode = " + JSON.stringify(mode) + ";",
      'for await (const line of createInterface({input:process.stdin})) {',
      ' const request=JSON.parse(line);',
      ' const payload={state:request.type==="run.close"?"closed":"open",runId:request.runId,scopeId:request.scopeId,rootScopeId:"root",readyEligible:false};',
      ' if(request.type==="hello")payload.protocolVersion=4;',
      ' if(request.type==="candidate.commit"){',
      '  if(mode==="matching")payload.committedCandidate=request.payload.attestation;',
      '  if(mode==="mismatch")payload.committedCandidate={...request.payload.attestation,patchHash:"wrong"};',
      '  if(mode==="refused")Object.assign(payload,{state:"failure",outcome:"failure",failureKind:"workspace_conflict",message:"Published bytes differ"});',
      ' }',
      ' console.log(JSON.stringify({version:4,id:request.id,runId:request.runId,scopeId:request.scopeId,type:"response",payload}));',
      '}',
    ].join("\n")
    const client = await ProcessVerificationClient.start({
      runId: "ack-" + mode, scopeId: "root", workspace: process.cwd(),
      goalSources: [goalSource("Check the commit receipt")],
    }, { command: [process.execPath, "-e", script], timeoutMs: 3000 })
    try {
      const result = client.commitCandidate({
        candidateId: "candidate", candidateRevision: 1, patchHash: "a".repeat(64),
      }, "child")
      if (mode === "matching") {
        expect((await result).state).toBe("open")
      } else {
        // Await subprocess I/O normally before using synchronous matchers. Bun
        // 1.3.14 on Windows can stall this stream inside rejects.toMatchObject.
        const error = await result.then(() => undefined, error => error)
        expect(error).toMatchObject({
          failureKind: mode === "refused" ? "workspace_conflict" : "harness_protocol_error",
        })
        expect(client.snapshot().readyEligible).not.toBe(true)
        if (mode === "refused") {
          // A scoped refusal must not kill the healthy verifier transport.
          expect((await client.status("independent")).scopeId).toBe("independent")
        } else {
          const unavailable = await client.status().catch(error => error)
          expect(unavailable).toMatchObject({ failureKind: "harness_verifier_unavailable" })
        }
      }
    } finally {
      await client.dispose()
    }
  })
}

import assert from "node:assert/strict"
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { createLocalRuntimeFixture } from "./fixtures/local-runtime.ts"

const repo = path.resolve(import.meta.dir, "../..")
const python = process.env.BASE_HARNESS_PYTHON
assert(python, "BASE_HARNESS_PYTHON is required")
const fixture = await createLocalRuntimeFixture(python, { planned: true, reasoner: true })
const logRoot = path.join(repo, ".tools/validation")
const tag = process.env.BASE_HARNESS_VALIDATION_TAG ?? "tui-plan-recovery"
assert(/^[a-zA-Z0-9_-]+$/.test(tag), "Validation tag must be a filename component")
await mkdir(logRoot, { recursive: true })
const launcher = path.join(repo, "runtime/packages/base-harness/src/source-launcher.ts")
const cwd = path.dirname(path.dirname(launcher))
const query = "?directory=" + encodeURIComponent(fixture.workspace)
const clients = [], hosts = [], timings = {}, observations = [], cleanupFailures = []
let host, hostURL, hostStreams, pendingPlan, reviewedPlan, finished, readyArtifact, failure
let recoveryObserved = false, stopped = false, deadlineTimer
const finish = Promise.withResolvers()
fixture.onStop(async () => finish.resolve())
const displayNote = "\uacc4\ud68d \uc218\uc815 \uc911\ub2e8 \ud6c4 \uc548\uc804\ud55c \ud3d0\uae30\uc640 \uc0c8 \uacc4\ud68d \uc2e4\ud589\uc744 \ud655\uc778\ud569\ub2c8\ub2e4."

async function request(route, init, timeoutMs=5000) {
  const response = await fetch(hostURL + route + query, { ...init, signal: AbortSignal.timeout(timeoutMs) })
  assert(response.ok, route + ": " + response.status)
  return response.json()
}
async function startHost() {
  const portProbe = Bun.serve({ hostname:"127.0.0.1",port:0,fetch:()=>new Response("") })
  const port=portProbe.port
  portProbe.stop(true)
  hostURL="http://127.0.0.1:"+port
  const started=performance.now()
  host=Bun.spawn({
    cmd:[process.execPath,"run","--conditions=browser",launcher,"serve","--hostname","127.0.0.1","--port",String(port)],
    cwd,env:fixture.env,stdin:"ignore",stdout:"pipe",stderr:"pipe",
  })
  hostStreams={stdout:new Response(host.stdout).text(),stderr:new Response(host.stderr).text()}
  const record={pid:host.pid,url:hostURL,startupMs:0,ready:false}
  hosts.push(record)
  try{
    if(process.env.BASE_HARNESS_VALIDATION_FORCE_START_FAILURE==="1"){
      throw new Error("Injected Host startup failure before readiness")
    }
    let live=false
    const end=performance.now()+24000
    while(performance.now()<end){
      assert(host.exitCode===null,"Host exited during startup")
      try{await request("/provider",undefined,Math.max(1,Math.min(5000,Math.floor(end-performance.now()))));live=true;break}catch{}
      await Bun.sleep(200)
    }
    assert(live,"Host readiness deadline")
    record.ready=true
  }finally{
    record.startupMs=performance.now()-started
  }
}
async function stopHost() {
  if(host?.exitCode===null)host.kill()
  if(host){
    const exitCode=await host.exited
    const record=hosts.find(item=>item.pid===host.pid)
    if(record)record.exitCode=exitCode
    const index=record?hosts.indexOf(record)+1:hosts.length+1
    const streams=hostStreams
    if(streams){
      await writeFile(path.join(logRoot,tag+"-host-"+index+".stdout.log"),await streams.stdout)
      await writeFile(path.join(logRoot,tag+"-host-"+index+".stderr.log"),await streams.stderr)
    }
  }
  host=undefined
}
async function client(name,args,onSpawn) {
  const started=performance.now()
  const process=Bun.spawn({
    cmd:[globalThis.process.execPath,"run","--conditions=browser",launcher,"run",
      "--attach",hostURL,"--dir",fixture.workspace,"--pure","--auto","--format","json",...args],
    cwd,env:fixture.env,stdin:"ignore",stdout:"pipe",stderr:"pipe",
  })
  onSpawn?.(process)
  const out=new Response(process.stdout).text(),err=new Response(process.stderr).text()
  let timedOut=false
  const timer=setTimeout(()=>{timedOut=true;process.kill()},90000)
  const exitCode=await process.exited
  clearTimeout(timer)
  const stdout=await out,stderr=await err
  const events=stdout.split(/\r?\n/).filter(Boolean).map(line=>JSON.parse(line))
  const result={name,pid:process.pid,exitCode,timedOut,elapsedMs:performance.now()-started,stdout,stderr,events}
  clients.push(result)
  await writeFile(path.join(logRoot,tag+"-"+name+".json"),JSON.stringify(result,null,2))
  assert(!timedOut,"CLI deadline: "+name)
  return result
}
function summary(values){
  const sorted=[...values].sort((a,b)=>a-b)
  const n=sorted.length
  return {count:n,medianMs:n%2?sorted[(n-1)/2]:(sorted[n/2-1]+sorted[n/2])/2,p95Ms:sorted[Math.ceil(n*.95)-1],minMs:sorted[0],maxMs:sorted[n-1]}
}
async function readyArtifacts(){
  const results=[]
  let entries=0
  async function visit(dir){
    for(const entry of await readdir(dir,{withFileTypes:true})){
      assert(++entries<4096,"Bounded fixture state")
      const file=path.join(dir,entry.name)
      if(entry.isDirectory())await visit(file)
      else if(entry.isFile()&&entry.name.endsWith(".json")){
        const value=await readFile(file,"utf8").then(JSON.parse).catch(()=>null)
        if(value?.artifactType==="ready_attestation"||value?.kind==="ready_attestation"
          ||(value?.trust==="verifier_attested"&&value?.payload?.criterionResults&&value?.payload?.evidenceRefs)){
          results.push({path:file,payload:value.payload??value})
        }
      }
    }
  }
  await visit(fixture.state)
  return results
}
try{
  await startHost()
  const first=await client("plan",["--model","fixture/fixture-reasoner","--variant","max","--hackathon","--plan",fixture.goal+"\n"+displayNote])
  assert.equal(first.exitCode,0)
  const prior=first.events.find(event=>event.type==="plan_ready")?.status
  assert(prior,"Plan-only result")
  fixture.reviseGoal()
  const pause=fixture.pauseNextPlanningRequest()
  let interrupted
  const revising=client("interrupted-revise",["--session",prior.sessionID,"--model","fixture/fixture-reasoner","--variant","high",fixture.goal+"\n"+displayNote],
    process=>{interrupted=process})
  try{
    await Promise.race([pause.entered,revising.then(()=>{throw new Error("Revision exited before hold point")})])
    assert(interrupted?.exitCode===null,"Observed live process before forced interruption")
    interrupted.kill()
    assert.notEqual((await revising).exitCode,0)
    await stopHost()
  }finally{
    if(interrupted?.exitCode===null)interrupted.kill()
    await revising.catch(()=>undefined)
    pause.release()
  }
  await startHost()
  const started=performance.now()
  pendingPlan=await request("/session/"+prior.sessionID+"/harness")
  timings.coldPendingStatusMs=performance.now()-started
  assert.equal(pendingPlan.planRecovery?.code,"PLAN_REVISION_PENDING")
  assert.equal(pendingPlan.readyEligible,false)
  const baseline=await request("/session",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({title:"Recovery status baseline"})})
  const empty=[],pending=[]
  for(let i=0;i<20;i++){
    for(const [id,samples] of [[baseline.id,empty],[prior.sessionID,pending]]){
      const at=performance.now()
      await request("/session/"+id+"/harness")
      samples.push(performance.now()-at)
    }
  }
  timings.emptyStatus=summary(empty)
  timings.pendingStatus=summary(pending)
  const modelCountBeforeTui=fixture.requestLog.length
  const connection={
    stage:"pending_ready",at:Date.now(),hostURL,modelURL:fixture.modelURL,hostPid:host.pid,
    sessionID:prior.sessionID,workspace:fixture.workspace,state:fixture.state,
    oldPlanId:prior.activePlanId,goal:fixture.goal,displayNote,timings,
    launcher,bun:globalThis.process.execPath,cwd,
  }
  await writeFile(path.join(logRoot,tag+".connection.json"),JSON.stringify(connection,null,2))
  console.log(JSON.stringify(connection))
  deadlineTimer=setTimeout(()=>finish.reject(new Error("Interactive TUI validation deadline")),600000)
  const monitor=(async()=>{
    while(!stopped){
      const status=await request("/session/"+prior.sessionID+"/harness")
      if(!recoveryObserved&&status.planningState==="idle"&&!status.planOnly&&!status.planRecovery){
        assert.equal(fixture.requestLog.length,modelCountBeforeTui,"TUI discard must not call a model")
        assert.equal((await readyArtifacts()).length,0)
        recoveryObserved=true
        observations.push({at:Date.now(),stage:"discard_observed",status})
        console.log(JSON.stringify({stage:"discard_observed",sessionID:prior.sessionID,at:Date.now()}))
      }
      if(recoveryObserved&&status.planningState==="plan_ready"&&status.activePlanId!==prior.activePlanId){
        if(!reviewedPlan){
          assert.equal(status.readyEligible,false)
          assert.equal((await readyArtifacts()).length,0)
          reviewedPlan=status
          observations.push({at:Date.now(),stage:"new_plan_reviewed",status})
          console.log(JSON.stringify({stage:"new_plan_reviewed",planId:status.activePlanId,at:Date.now()}))
        }
      }
      if(recoveryObserved&&status.phase==="ready"){
        assert(reviewedPlan,"TUI must stop at a reviewed new plan before execute")
        assert.notEqual(status.runId,reviewedPlan.runId)
        assert.equal(status.executionPlan.planId,reviewedPlan.activePlanId)
        for(const target of fixture.targets)assert.equal(await readFile(target,"utf8"),fixture.expected)
        const ready=(await readyArtifacts()).find(({payload})=>
          fixture.criterionIds.every(id=>payload.criterionResults?.some(item=>item.criterionId===id&&item.result==="verified"))
          &&fixture.claimIds.every(id=>payload.claimResults?.some(item=>item.claimId===id&&item.result==="verified"))
          &&payload.evidenceRefs?.length>0)
        assert(ready,"Real verifier Ready")
        if(!finished){
          finished=status;readyArtifact=ready.path
          observations.push({at:Date.now(),stage:"ready",status})
          console.log(JSON.stringify({stage:"ready",readyArtifact,at:Date.now()}))
        }
      }
      await Bun.sleep(300)
    }
  })()
  await Promise.race([finish.promise,monitor])
  stopped=true
  await monitor
  assert(recoveryObserved&&reviewedPlan&&finished,"Interactive recovery/plan/execute flow must complete")
}catch(error){
  failure=error instanceof Error?error.stack??error.message:String(error)
}finally{
  stopped=true
  clearTimeout(deadlineTimer)
  try{await stopHost()}catch(error){
    const detail=error instanceof Error?error.stack??error.message:String(error)
    cleanupFailures.push({phase:"host_stop",detail})
    failure??=detail
  }
  try{fixture.stop()}catch(error){
    const detail=error instanceof Error?error.stack??error.message:String(error)
    cleanupFailures.push({phase:"fixture_stop",detail})
    failure??=detail
  }
}
const result={success:!failure,scratch:fixture.scratch,pendingPlan,recoveryObserved,reviewedPlan,finished,readyArtifact,cleanupFailures,
  hosts,clients,observations,timings,requests:fixture.requestLog,modelHttpTrace:fixture.httpTrace,failure}
const resultPath=path.join(logRoot,tag+".result.json")
await writeFile(resultPath,JSON.stringify(result,null,2))
console.log(JSON.stringify({success:result.success,resultPath,readyArtifact,timings,failure}))
if(failure)globalThis.process.exitCode=1

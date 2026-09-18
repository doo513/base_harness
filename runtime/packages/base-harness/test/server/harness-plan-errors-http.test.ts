import { NodeHttpServer } from "@effect/platform-node"
import { expect } from "bun:test"
import { Effect, Layer, Schema } from "effect"
import { HttpClient, HttpRouter } from "effect/unstable/http"
import { HttpApi, HttpApiBuilder, HttpApiEndpoint, HttpApiGroup } from "effect/unstable/httpapi"
import { InvalidRequestError } from "../../src/server/routes/instance/httpapi/errors"
import { mapHarnessControlFailure } from "../../src/server/routes/instance/httpapi/handlers/session-errors"
import { testEffect } from "../lib/effect"

// A tiny HTTP route exercises the production rejected-promise mapper and public
// error schema without booting model/provider services for an error-wire test.
const Api = HttpApi.make("plan-error-probe").add(HttpApiGroup.make("probe").add(
  HttpApiEndpoint.get("execute", "/execute", {
    query: { code: Schema.String }, success: Schema.String, error: InvalidRequestError,
  }),
))
const handlers = HttpApiBuilder.group(Api, "probe", (handlers) => handlers.handle("execute", ({ query }) =>
  mapHarnessControlFailure(Effect.promise(async (): Promise<string> => {
    throw Object.assign(new Error("private workspace and token"), { code: query.code })
  })),
))
const it = testEffect(HttpRouter.serve(HttpApiBuilder.layer(Api).pipe(Layer.provide(handlers)), {
  disableListenLog: true, disableLogger: true,
}).pipe(Layer.provideMerge(NodeHttpServer.layerTest)))

for (const code of ["PLAN_DOMAIN_BINDING_REQUIRED", "PLAN_DOMAIN_BINDING_CHANGED", "PLAN_EXECUTION_GRAPH_CHANGED", "PLAN_RUN_CHANGED"]) {
  it.live(`${code} is actionable HTTP 400 JSON`, () => Effect.gen(function* () {
    const response = yield* HttpClient.get(`/execute?code=${code}`)
    const body = yield* response.json
    expect(response.status).toBe(400)
    expect(body).toMatchObject({ _tag: "InvalidRequestError", kind: code, message: expect.stringMatching(/review/i) })
    expect(JSON.stringify(body)).not.toContain("private")
  }))
}

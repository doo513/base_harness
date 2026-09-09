import {
  ANTIGRAVITY_ADAPTER_ID,
  type AntigravityCapabilities,
} from "@base-harness/core/antigravity-protocol"

interface DiscoveryClient {
  session: {
    create(input: { directory?: string }): Promise<any>
    harnessControl(input: { sessionID: string; directory?: string; body: unknown }): Promise<any>
  }
}

export async function discoverAntigravityCli(input: {
  client: unknown
  sessionID?: string
  directory?: string
}): Promise<AntigravityCapabilities> {
  const client = input.client as DiscoveryClient
  let sessionID = input.sessionID
  if (!sessionID) {
    const response = await client.session.create({ directory: input.directory })
    if (response.error || !response.data?.id) throw new Error("Host could not create a discovery session")
    sessionID = String(response.data.id)
  }
  const response = await client.session.harnessControl({
    sessionID,
    directory: input.directory,
    body: { type: "execution.discover", adapterID: ANTIGRAVITY_ADAPTER_ID },
  })
  if (response.error) throw new Error("Host could not discover the execution provider")
  const capabilities = response.data ?? response
  if (!Array.isArray(capabilities.models) || !Array.isArray(capabilities.reasoningEfforts) || typeof capabilities.revision !== "string") {
    throw new Error("Host returned an invalid execution capability response")
  }
  return capabilities
}

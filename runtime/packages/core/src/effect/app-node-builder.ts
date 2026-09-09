import { Effect, Layer } from "effect"
import { LocationServiceMap } from "../location-service-map"
import { LayerNode } from "./layer-node"
import { makeGlobalNode } from "./app-node"

export function build<A, E>(root: LayerNode.Node<A, E, any>, replacements: LayerNode.Replacements = []) {
  let allReplacements = replacements

  // Only build the location service map if it's actually needed
  if (LayerNode.hasUnbound(root, LocationServiceMap.node) && !hasReplacement(replacements, LocationServiceMap.node)) {
    // Keep the location runtime (tools, providers, sessions) out of plain graph
    // construction. Load it only when this required service is acquired.
    const locationMap = Layer.unwrap(
      Effect.promise(() => import("../location-services")).pipe(
        Effect.map(({ buildLocationServiceMap }) => buildLocationServiceMap(replacements)),
      ),
    )
    const locationMapNode = makeGlobalNode({ service: LocationServiceMap.Service, layer: locationMap, deps: [] })
    allReplacements = replacements.concat([[LocationServiceMap.node, locationMapNode]])
  }

  return LayerNode.compile(root, allReplacements)
}

function hasReplacement(replacements: LayerNode.Replacements, node: LayerNode.Node<unknown, unknown, any>) {
  return replacements.some(([source]) => source.name === node.name)
}

export * as AppNodeBuilder from "./app-node-builder"

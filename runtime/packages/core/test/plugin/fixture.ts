import { AgentV2 } from "@base-harness/core/agent"
import { AISDK } from "@base-harness/core/aisdk"
import { Catalog } from "@base-harness/core/catalog"
import { CommandV2 } from "@base-harness/core/command"
import { Credential } from "@base-harness/core/credential"
import { AppNodeBuilder } from "@base-harness/core/effect/app-node-builder"
import { LayerNodePlatform } from "@base-harness/core/effect/app-node-platform"
import { LayerNode } from "@base-harness/core/effect/layer-node"
import { EventV2 } from "@base-harness/core/event"
import { FileSystem } from "@base-harness/core/filesystem"
import { FSUtil } from "@base-harness/core/fs-util"
import { Integration } from "@base-harness/core/integration"
import { Location } from "@base-harness/core/location"
import { Npm } from "@base-harness/core/npm"
import { PluginV2 } from "@base-harness/core/plugin"
import { Reference } from "@base-harness/core/reference"
import { SkillV2 } from "@base-harness/core/skill"
import { Effect, Layer } from "effect"
import { tempLocationLayer } from "../fixture/location"

const npmLayer = Layer.succeed(
  Npm.Service,
  Npm.Service.of({
    add: () => Effect.succeed({ directory: "", entrypoint: undefined }),
    install: () => Effect.void,
    which: () => Effect.succeed(undefined),
  }),
)

export const PluginTestLayer = AppNodeBuilder.build(
  LayerNode.group([
    FileSystem.node,
    FSUtil.node,
    Location.node,
    Npm.node,
    Credential.node,
    EventV2.node,
    LayerNodePlatform.httpClient,
    PluginV2.node,
    AgentV2.node,
    AISDK.node,
    Catalog.node,
    CommandV2.node,
    Integration.node,
    Reference.node,
    SkillV2.node,
  ]),
  [
    [Location.node, tempLocationLayer],
    [Npm.node, npmLayer],
  ],
)

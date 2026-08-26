import { Context } from "effect"
import type { InstanceContext } from "@/project/instance-context"
import type { WorkspaceV2 } from "@base-harness/core/workspace"

export const InstanceRef = Context.Reference<InstanceContext | undefined>("~base-harness/InstanceRef", {
  defaultValue: () => undefined,
})

export const WorkspaceRef = Context.Reference<WorkspaceV2.ID | undefined>("~base-harness/WorkspaceRef", {
  defaultValue: () => undefined,
})

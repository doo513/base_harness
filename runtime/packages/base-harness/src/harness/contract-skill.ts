import { Effect } from "effect"
import type { PermissionV1 } from "@base-harness/core/v1/permission"
import type { Agent } from "../agent/agent"
import { Permission } from "../permission"
import { Skill } from "../skill"
import type { SessionID } from "../session/schema"

export type ContractSkillName = "goal-contract-authoring" | "goal-contract-review"

/** Contract-specific context assembly through the existing discovery and permission services. */
export const requireContractSkill = Effect.fn("ContractSkill.require")(function* (
  name: ContractSkillName,
  input: { sessionID: SessionID; agent: Agent.Info; permission?: PermissionV1.Ruleset },
) {
  const skills = yield* Skill.Service
  const info = yield* skills.require(name).pipe(Effect.catchTag("Skill.NotFoundError", () =>
    Effect.fail(new Error(`CONTRACT_SKILL_UNAVAILABLE:${name}`)),
  ))
  if (!info.content.trim()) return yield* Effect.fail(new Error(`CONTRACT_SKILL_UNAVAILABLE:${name}`))
  const ruleset = Permission.merge(input.agent.permission, input.permission ?? [])
  if (Permission.evaluate("skill", name, ruleset).action === "deny") {
    return yield* Effect.fail(new Error(`CONTRACT_SKILL_DENIED:${name}`))
  }
  const permissions = yield* Permission.Service
  yield* permissions.ask({
    sessionID: input.sessionID, permission: "skill", patterns: [name], always: [name],
    metadata: { name, location: info.location }, ruleset,
  })
  return `<skill_content name="${name}">\n${info.content.trim()}\n</skill_content>`
})

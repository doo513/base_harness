import authoring from "../../../domain/resources/goal-contract-authoring/SKILL.md" with { type: "text" }
import review from "../../../domain/resources/goal-contract-review/SKILL.md" with { type: "text" }
import { ConfigMarkdown } from "@base-harness/core/config/markdown"
import type { Info } from "."

/** The existing Markdown parser and text bundler also own these two built-ins. */
export function contractBuiltinSkills(): Info[] {
  return ([['goal-contract-authoring', authoring], ['goal-contract-review', review]] as const).map(([name, markdown]) => {
    const parsed = ConfigMarkdown.parse(markdown)
    if (parsed.data.name !== name || typeof parsed.data.description !== "string" || !parsed.content.trim()) {
      throw new Error(`CONTRACT_SKILL_UNAVAILABLE:${name}`)
    }
    return { name, description: parsed.data.description, content: parsed.content, location: "<built-in>" }
  })
}

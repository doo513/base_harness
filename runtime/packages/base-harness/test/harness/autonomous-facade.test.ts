import { expect, spyOn, test } from "bun:test"
import { KernelHost } from "@base-harness/kernel-host"
import { Coordinator } from "../../src/harness/coordinator-service"

test("app facade sends autonomous actor responses through Host normalization, not the raw runtime overload", async () => {
  const submit = spyOn(KernelHost.prototype, "submitAutonomousDecision").mockResolvedValue({ accepted: false, code: "host-receipt" })
  try {
    const response = { kind: "invoke", toolId: "read", arguments: { filePath: "/workspace/source" } }
    expect(await Coordinator.submitAutonomousDecision("session", "run", "decision", response)).toEqual({ accepted: false, code: "host-receipt" })
    expect(submit).toHaveBeenCalledWith("session", "run", "decision", response)
  } finally { submit.mockRestore() }
})

test("app facade requests authenticated answers without accepting an actor answer payload", async () => {
  const ask = spyOn(KernelHost.prototype, "requestAutonomousAnswers").mockResolvedValue({ status: "proceed", context: {} })
  try {
    expect(await Coordinator.requestAutonomousAnswers("session", "run")).toEqual({ status: "proceed", context: {} })
    expect(ask).toHaveBeenCalledWith("session", "run")
  } finally { ask.mockRestore() }
})

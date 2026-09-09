import { expect, test } from "bun:test"
import { harnessActorLabel, harnessTerminalTitle } from "../src/harness/identity-presentation"

test("home and untitled routes retain the independent product title", () => {
  expect(harnessTerminalTitle()).toBe("Base Harness")
  expect(harnessTerminalTitle("")).toBe("Base Harness")
})

test("session and plugin titles use Base Harness without rewriting their names", () => {
  expect(harnessTerminalTitle("Fixture task")).toBe("Base Harness | Fixture task")
  expect(harnessTerminalTitle("my-plugin")).toBe("Base Harness | my-plugin")
  expect(harnessTerminalTitle("Model MAX")).toBe("Base Harness | Model MAX")
})

for (const role of ["build", "plan"]) {
  test("legacy primary role stays internal: " + role, () => {
    expect(harnessActorLabel(role)).toBe("Base Harness")
  })
}

test("the neutral product label does not invent a domain or rename custom roles", () => {
  expect(harnessActorLabel("reviewer")).toBe("Reviewer")
  expect(harnessActorLabel("general")).toBe("General")
  expect(harnessActorLabel("build-tools")).toBe("Build-Tools")
  expect(harnessActorLabel("plan-review")).toBe("Plan-Review")
})

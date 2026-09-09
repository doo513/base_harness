import { expect, test } from "bun:test"
import { testRender } from "@opentui/solid"
import { abbreviateHome } from "../src/runtime"
import { TuiPathsProvider, useTuiPaths } from "../src/context/runtime"

test("abbreviates paths within home boundaries", () => {
  expect(abbreviateHome("/home/test", "/home/test")).toBe("~")
  expect(abbreviateHome("/home/test/project", "/home/test")).toBe("~/project")
  expect(abbreviateHome("/home/tester/project", "/home/test")).toBe("/home/tester/project")
  expect(abbreviateHome("/tmp/project", "/home/test")).toBe("/tmp/project")
})


test("POSIX casing and literal backslashes do not inherit the client's OS rules", () => {
  expect(abbreviateHome("/home/TEST/project", "/home/test")).toBe("/home/TEST/project")
  expect(abbreviateHome("/home/test/project\\notes", "/home/test")).toBe("~/project\\notes")
})

for (const [input, home, expected] of [
  ["C:\\Users\\test\\project", "C:\\Users\\test", "~\\project"],
  ["c:\\users\\TEST\\project", "C:\\Users\\test", "~\\project"],
  ["C:/Users/test/project", "C:/Users/test", "~\\project"],
  ["C:\\Users\\tester\\project", "C:\\Users\\test", "C:\\Users\\tester\\project"],
  ["D:\\Users\\test\\project", "C:\\Users\\test", "D:\\Users\\test\\project"],
  ["\\\\server\\share\\home\\project", "\\\\server\\share\\home", "~\\project"],
  ["//server/share/home/project", "//server/share/home", "~\\project"],
  ["\\\\other\\share\\home\\project", "\\\\server\\share\\home", "\\\\other\\share\\home\\project"],
]) {
  test("Windows path display is host-aware: " + input, () => {
    expect(abbreviateHome(input!, home!)).toBe(expected)
  })
}

test("provides focused immutable runtime inputs", async () => {
  let paths: ReturnType<typeof useTuiPaths>

  function Runtime() {
    paths = useTuiPaths()
    return <text>{paths.cwd}</text>
  }

  const app = await testRender(
    () => (
      <TuiPathsProvider value={{ cwd: "/work", home: "/home/test", state: "/state", worktree: "/worktree" }}>
        <Runtime />
      </TuiPathsProvider>
    ),
    { width: 40, height: 3 },
  )

  try {
    await app.renderOnce()
    expect(app.captureCharFrame()).toContain("/work")
    expect(Object.isFrozen(paths!)).toBe(true)
  } finally {
    app.renderer.destroy()
  }
})

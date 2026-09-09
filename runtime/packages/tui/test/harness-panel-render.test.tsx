import { expect, test } from "bun:test"
import { RGBA, type ScrollBoxRenderable } from "@opentui/core"
import { testRender } from "@opentui/solid"
import { For } from "solid-js"
import { HarnessPanelFrame } from "../src/harness/panel-frame"
import { harnessPanelLayout } from "../src/harness/panel-presentation"

for (const [width, height] of [[80, 24], [40, 12]] as const) {
  for (const count of [2, 40]) {
    test("opaque overlay erases background cells before and after scroll: " + width + "x" + height + "/" + count, async () => {
      const layout = harnessPanelLayout(width, height)
      let scroll: ScrollBoxRenderable | undefined
      const app = await testRender(() => (
        <box width={width} height={height}>
          <box position="absolute" top={0} left={0} width={width} height={height} flexDirection="column">
            <For each={Array.from({ length: height })}>{() => <text flexShrink={0}>{"@".repeat(width)}</text>}</For>
          </box>
          <box position="absolute" top={1} right={2} zIndex={100}>
            <HarnessPanelFrame overlay layout={layout} title="SURFACE READY" tone="#78c091"
              background={RGBA.fromValues(0.1, 0.2, 0.3, 0.15)} onScrollBox={(value) => { scroll = value }}>
              <box flexDirection="column" flexShrink={0}>
                <For each={Array.from({ length: count }, (_, i) => "Item " + String(i).padStart(2, "0") + "   detail")}>
                  {(line) => <text flexShrink={0}>{line}</text>}
                </For>
              </box>
            </HarnessPanelFrame>
          </box>
        </box>
      ), { width, height })
      const capture = async () => {
        await app.renderOnce()
        await app.renderOnce()
        const frame = app.captureCharFrame()
        const lines = frame.split("\n")
        const left = width - 2 - layout.width
        expect(lines[1]!.slice(0, left)).toContain("@")
        for (let y = 1; y < 1 + layout.height; y++) {
          expect(lines[y]!.slice(left, left + layout.width)).not.toContain("@")
        }
        expect(frame).toContain("SURFACE READY")
        expect(frame).toContain("PgUp/PgDn")
        expect(scroll!.horizontalScrollBar.visible).toBe(false)
        expect(scroll!.scrollLeft).toBe(0)
        return frame
      }
      try {
        const first = await capture()
        expect(first).toContain("Item 00")
        if (count > layout.bodyHeight) {
          scroll!.scrollBy(layout.bodyHeight)
          const next = await capture()
          expect(scroll!.scrollTop).toBeGreaterThan(0)
          expect(next).not.toContain("Item 00")
          scroll!.scrollBy(-scroll!.scrollTop)
          expect(await capture()).toContain("Item 00")
        }
      } finally {
        app.renderer.destroy()
      }
    })
  }
}

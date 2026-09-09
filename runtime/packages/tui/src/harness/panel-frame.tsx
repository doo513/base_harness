import { RGBA, type ScrollBoxRenderable } from "@opentui/core"
import { children, Show, type JSX } from "solid-js"
import type { harnessPanelLayout } from "./panel-presentation"

export function HarnessPanelFrame(props: {
  overlay?: boolean
  layout: ReturnType<typeof harnessPanelLayout>
  title: string
  tone: string
  background: RGBA
  onScrollBox?: (scroll: ScrollBoxRenderable) => void
  children: JSX.Element
}) {
  const content = children(() => props.children)
  // A floating panel must erase underlying glyphs even with a transparent theme.
  const surface = () => RGBA.fromValues(props.background.r, props.background.g, props.background.b, 1)
  return (
    <box
      flexDirection="column"
      border={props.overlay}
      borderStyle="rounded"
      borderColor={props.tone}
      backgroundColor={props.overlay ? surface() : undefined}
      paddingLeft={1}
      paddingRight={1}
      width={props.overlay ? props.layout.width : undefined}
      height={props.overlay ? props.layout.height : undefined}
    >
      <text fg={props.tone} flexShrink={0}>{props.title}</text>
      <Show when={props.overlay} fallback={content()}>
        <Show when={props.layout.bodyHeight > 0}>
          <scrollbox
            ref={(scroll: ScrollBoxRenderable) => props.onScrollBox?.(scroll)}
            height={props.layout.bodyHeight}
            flexShrink={0}
            backgroundColor={surface()}
            rootOptions={{ backgroundColor: surface() }}
            wrapperOptions={{ backgroundColor: surface() }}
            viewportOptions={{ backgroundColor: surface() }}
            contentOptions={{ flexDirection: "column", backgroundColor: surface() }}
            scrollX={false}
            scrollY
            verticalScrollbarOptions={{ visible: true }}
            horizontalScrollbarOptions={{ visible: false }}
          >
            {content()}
          </scrollbox>
        </Show>
        <text fg="#778399" flexShrink={0}>
          {props.layout.contentWidth >= 36 ? "PgUp/PgDn scroll | /harness close" : "PgUp/PgDn"}
        </text>
      </Show>
    </box>
  )
}

export * as HarnessEvent from "./harness-event"

import { Schema } from "effect"
import { Event } from "./event"

export const Status = Event.define({
  type: "harness.status",
  schema: {
    sessionID: Schema.String,
    status: Schema.Unknown,
  },
})

export const Definitions = Event.inventory(Status)

export * as PublicEventManifest from "./public-event-manifest"

import { Event } from "@base-harness/schema/event"
import { EventManifest } from "@base-harness/schema/event-manifest"

export const Definitions = EventManifest.ServerDefinitions
export const Latest = Event.latest(Definitions)

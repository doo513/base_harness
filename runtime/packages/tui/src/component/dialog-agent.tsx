import { DialogSelect } from "../ui/dialog-select"
import { useDialog } from "../ui/dialog"
import { useSDK } from "../context/sdk"
import { useRoute } from "../context/route"
import { useToast } from "../ui/toast"

export function DialogAgent() {
  const dialog = useDialog()
  const sdk = useSDK()
  const route = useRoute()
  const toast = useToast()
  const options = [
    {
      value: "develop",
      title: "develop",
      description: "GoalContract-bound development with verified mutation",
    },
    {
      value: "general",
      title: "general",
      description: "Read-only search, lookup, and state inspection",
    },
    {
      value: "hackathon",
      title: "hackathon",
      description: "Develop domain with demo-first planned execution",
    },
  ]

  return (
    <DialogSelect
      title="Select domain"
      options={options}
      onSelect={(option) => {
        if (route.data.type !== "session") {
          toast.show({ message: "Open a session before selecting a domain.", variant: "warning" })
          return
        }
        const input =
          option.value === "hackathon"
            ? {
                sessionID: route.data.sessionID,
                type: "skill.set" as const,
                skill: "hackathon" as const,
                enabled: true,
              }
            : {
                sessionID: route.data.sessionID,
                type: "domain.set" as const,
                domain: option.value as "develop" | "general",
              }
        void sdk.client.session
          .harnessControl(input)
          .then(() => dialog.clear())
          .catch(toast.error)
      }}
    />
  )
}

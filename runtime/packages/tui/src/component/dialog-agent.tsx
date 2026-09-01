import { DialogSelect } from "../ui/dialog-select"
import { useDialog } from "../ui/dialog"
import { useSDK } from "../context/sdk"
import { useRoute } from "../context/route"
import { useToast } from "../ui/toast"
import { queueHarnessControl, type HarnessControl } from "../harness/pending-control"

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
        const body: HarnessControl =
          option.value === "hackathon"
            ? {
                type: "skill.set" as const,
                skill: "hackathon" as const,
                enabled: true,
              }
            : {
                type: "domain.set" as const,
                domain: option.value as "develop" | "general",
              }
        if (route.data.type !== "session") {
          queueHarnessControl(body)
          toast.show({
            message: `${option.title} will be applied before the first request.`,
            variant: "success",
          })
          dialog.clear()
          return
        }
        void sdk.client.session
          .harnessControl({ sessionID: route.data.sessionID, body })
          .then(() => dialog.clear())
          .catch(toast.error)
      }}
    />
  )
}

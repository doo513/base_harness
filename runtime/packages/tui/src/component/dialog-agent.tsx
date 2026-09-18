import { DialogSelect } from "../ui/dialog-select"
import { useDialog } from "../ui/dialog"
import { useSDK } from "../context/sdk"
import { useRoute } from "../context/route"
import { useToast } from "../ui/toast"
import { queueHarnessControl, type HarnessControl } from "../harness/pending-control"
import { unwrapHarnessResponse } from "../harness/control-response"

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
  ]

  return (
    <DialogSelect
      title="Built-in domains · /domain <id> for registered domains"
      options={options}
      onSelect={(option) => {
        const body: HarnessControl = {
          type: "domain.set" as const,
          domain: option.value,
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
          .then((response) => {
            unwrapHarnessResponse(response)
            dialog.clear()
          })
          .catch(toast.error)
      }}
    />
  )
}

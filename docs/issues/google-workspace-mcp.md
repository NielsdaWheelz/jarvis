# gmail and calendar access before february 1, 2027

the [connector design](../decisions/0107-google-workspace.md) owns implementation and the required product behavior. the owner selected a fixture-first connector pr and a separate permission pr before real use.

open, november 24, 2026. installed release `74bfcab` uses direct rest for both products. google requires agent-driven workspace access through its mcp servers from february 1. cloud resource manager reports that `unified-ion-515618-m7` (jarvis google connector) is active and `ariel-prod-497019` is marked for deletion. the active project's enabled services include both product apis and omit both mcp services. [installed connector source](https://github.com/NielsdaWheelz/jarvis/blob/74bfcab/src/jarvis/read_tools.py) · [google setup](https://developers.google.com/workspace/guides/configure-mcp-servers) · [rollout dates and tiers](https://developers.google.com/workspace/guides/quota-usage-tiers)

anonymous `tools/list` returned 23 gmail and nine calendar tools from google’s public `/mcp/v1` endpoints on november 24. account-specific access and user-approval challenges remain untested. the alternative `/mcp/v1self` endpoint can filter read results to those the policy allows without a prompt. [google’s approval behavior](https://developers.google.com/workspace/guides/mcp-elicitation)

on november 25, the owner chose to skip the live google test and merge the
source. candidate `9ab594e` passed isolated installation, migration, restore
and independent review. the packaged subscription check passed match, no-match
and incomplete-result cases with constructed calendar data. the installed
predecessor disables draft replacement and discard. the
[0132 candidate](../decisions/0132-one-main.md) exercised the exact connector
against synthetic items on november 27. gmail draft create and exact readback
succeeded. google returned an unstructured error after the one discard request
entered. an exact subsequent draft read found the same draft and message ids
still active with `DRAFT` and without `TRASH` or `SENT`. google withheld the
independent message read. the original action remains uncertain and the target
was active at reconciliation. a solo primary calendar update
verified. google acknowledged the exact calendar delete after the owner
answered its form and withheld the follow-up read. calendar text clears and
all-day-to-timed edits remain unavailable. physical-phone delivery and the
history-permission decision remain open.

the original qualification project `jarvis-workspace-test-20261124` used
an isolated grant. for the 0132 provider check, the owner authorized synthetic
fixtures on the installed account during exclusive stopped custody. use the
installed grant in place. keep credentials outside copied rehearsals.

after the installed calendar poller retired, cloud monitoring counted 1,252 gmail rest requests, including 1,006 history calls, and four calendar rest requests on the active project between 02:00 and 21:00 utc on november 24. to reproduce, sum `serviceruntime.googleapis.com/api/request_count` on `consumed_api` by service and method for that interval. this measures project traffic across clients. future mcp daily units depend on the tools selected.

- **gmail.** google's trash tool directs callers to the underlying draft
  message id and accepts the installed `gmail.messages.delete` scope. the
  draft guide limits an active draft to the `DRAFT` label. the authenticated
  mcp catalog offers no direct draft delete. its ordinary label update
  explicitly excludes `TRASH`. the sensitive label tool advertises finding
  draft message ids, but the installed grant lacks the declared permission
  and the actual draft behavior remains unverified. the official governed
  workspace cli lists the same message trash capability and offers no draft
  delete command. the direct gmail rest delete requires a send-capable grant.
  the latest owner decision permits such a scope with an exact, one-time viewer
  approval for every send. google's workspace ai tools terms require governed
  agent access from february 1, 2027. qualify an actual governed discard
  before enabling it.
  proof needs the exact fresh draft and message revision, the explicit returned
  scope, an owner-editor claim fence, a provider acknowledgment and exact readback
  under an isolated synthetic grant. preserve the original receipt and the later
  observation separately. a repeat is a second write. verified create-then-trash
  replacement depends on the same discard capability. the isolated probe
  exercised single dispatch, scope refusal, fresh-edit refusal and unknown
  acknowledgment in controlled http only. real provider qualification remains open.
  [workspace cli](https://developers.google.com/workspace/guides/workspace-cli) · [workspace ai terms](https://workspace.google.com/terms/ai-tools/) · [enforcement dates](https://developers.google.com/workspace/guides/quota-usage-tiers)
  [trash tool](https://developers.google.com/workspace/gmail/api/reference/mcp/tools_list/trash_message) · [draft identity](https://developers.google.com/workspace/gmail/api/guides/drafts) · [mcp catalog](https://developers.google.com/workspace/gmail/api/reference/mcp) · [ordinary label restrictions](https://developers.google.com/workspace/gmail/api/reference/mcp/tools_list/update_message_labels) · [sensitive label scope](https://developers.google.com/workspace/gmail/api/reference/mcp/tools_list/apply_sensitive_message_label) · [rest draft deletion](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/delete) · [rest send scope](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send)
- **incoming mail.** the selected source polls a dedicated gmail label every five minutes. the [arrival issue](gmail-mcp-arrivals.md) owns live qualification, coverage and budget evidence. deleted or inaccessible mail can be missed before observation.
- **calendar.** public mcp offers event create/read/update/delete. the owner accepts the race after a fresh pre-read and before a sparse write. the predecessor uses its original consent rules. the 0132 candidate checks event participants and always requests no guest notification. qualify the enrolled wire's organizer and attendee representation for actual solo writes before activation. a lost response after possible execution must never cause a write retry. the candidate refuses explicit text clears and all-day-to-timed conversion before dispatch. unblock each field only after the test calendar demonstrates the exact update with untouched fields preserved. [calendar tools](https://developers.google.com/workspace/calendar/api/guides/configure-mcp-server) · [existing approval contract](../decisions/0096-calendar-on-demand.md)
- **phone alerts.** the isolated emulator exercised the generic notification and deliberate refresh. complete the firebase delivery check to an enrolled physical phone while connected and asleep. repeat offline and confirm no later catch-up or google details on the lock screen.

resolve when the installed agent uses google mcp through an agent-marked oauth client for every supported gmail/calendar path, and the owner has accepted the disposition of each missing capability. verify the account's actual tool schemas, complete reads, attachment round trips, consent, concurrent edits and lost replies for the operations kept. account for pending actions and the existing gmail cursor at cutover. assess standard using observed daily units per product on the chosen workload. [retention dependency](google-workspace-retention.md)

# gmail and calendar access before february 1, 2027

the [connector design](../decisions/0107-google-workspace.md) owns implementation and the required product behavior. the owner selected a fixture-first connector pr and a separate permission pr before real use.

open, november 24, 2026. installed release `74bfcab` uses direct rest for both products. google requires agent-driven workspace access through its mcp servers from february 1. cloud resource manager reports that `unified-ion-515618-m7` (jarvis google connector) is active and `ariel-prod-497019` is marked for deletion. the active project's enabled services include both product apis and omit both mcp services. [installed connector source](https://github.com/NielsdaWheelz/jarvis/blob/74bfcab/src/jarvis/read_tools.py) · [google setup](https://developers.google.com/workspace/guides/configure-mcp-servers) · [rollout dates and tiers](https://developers.google.com/workspace/guides/quota-usage-tiers)

anonymous `tools/list` returned 23 gmail and nine calendar tools from google’s public `/mcp/v1` endpoints on november 24. account-specific access and user-approval challenges remain untested. the alternative `/mcp/v1self` endpoint can filter read results to those the policy allows without a prompt. [google’s approval behavior](https://developers.google.com/workspace/guides/mcp-elicitation)

on november 25, the owner chose to skip the live google test and merge the
source. candidate `9ab594e` passed isolated installation, migration, restore
and independent review. the packaged subscription check passed match, no-match
and incomplete-result cases with constructed calendar data. live google
behavior is unverified. draft replacement and discard stay disabled, as do
calendar text clears and all-day-to-timed edits. physical-phone delivery and
the history-permission decision remain open. production activation is a
separate decision under [0107](../decisions/0107-google-workspace.md).

the qualification project `jarvis-workspace-test-20261124` has billing
disabled and the gmail and calendar services enabled. if live testing resumes,
use constructed data in the dedicated mailbox and a separate agent-marked
client. keep installed workspace credentials outside rehearsals.

after the installed calendar poller retired, cloud monitoring counted 1,252 gmail rest requests, including 1,006 history calls, and four calendar rest requests on the active project between 02:00 and 21:00 utc on november 24. to reproduce, sum `serviceruntime.googleapis.com/api/request_count` on `consumed_api` by service and method for that interval. this measures project traffic across clients. future mcp daily units depend on the tools selected.

- **gmail.** public tools cover paged thread search, message/thread reads and draft list/get/create. direct update and sending require partner access. google specifically directs draft callers to trash the underlying message id. qualify discard and verified create-then-trash replacement, including edits, sends and lost replies. the narrowest published discard scope can also trash other mail. the owner accepts this google permission at enrollment solely for verified draft discard. jarvis must expose no general mail trash operation. [gmail quotas](https://developers.google.com/workspace/gmail/api/guides/quotas#gmail-mcp-toolsets) · [trash tool](https://developers.google.com/workspace/gmail/api/reference/mcp/tools_list/trash_message) · [draft identity](https://developers.google.com/workspace/gmail/api/guides/drafts)
- **incoming mail.** the selected source polls a dedicated gmail label every five minutes. the [arrival issue](gmail-mcp-arrivals.md) owns live qualification, coverage and budget evidence. deleted or inaccessible mail can be missed before observation.
- **calendar.** public mcp offers event create/read/update/delete. the owner accepts the race after a fresh pre-read and before a sparse write. keep existing consent rules. the public catalog cannot prove owner-only sharing. all writes set guest notification explicitly, including quiet changes. a lost response after possible execution must never cause a write retry. the candidate refuses explicit text clears and all-day-to-timed conversion before dispatch. unblock each field only after the test calendar demonstrates the exact update with untouched fields preserved. [calendar tools](https://developers.google.com/workspace/calendar/api/guides/configure-mcp-server) · [existing approval contract](../decisions/0096-calendar-on-demand.md)
- **phone alerts.** the isolated emulator exercised the generic notification and deliberate refresh. complete the firebase delivery check to an enrolled physical phone while connected and asleep. repeat offline and confirm no later catch-up or google details on the lock screen.

resolve when the installed agent uses google mcp through an agent-marked oauth client for every supported gmail/calendar path, and the owner has accepted the disposition of each missing capability. verify the account's actual tool schemas, complete reads, attachment round trips, consent, concurrent edits and lost replies for the operations kept. account for pending actions and the existing gmail cursor at cutover. assess standard using observed daily units per product on the chosen workload. [retention dependency](google-workspace-retention.md)

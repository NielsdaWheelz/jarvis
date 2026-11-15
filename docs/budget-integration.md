# budget integration

status: owner choices settled, 2026-10-15; proposed implementation contract,
docs only. adopt the authority, catalog and recovery amendments in
[spec](../SPEC.md)/an adr and budget's owning contract before implementation.
the [roadmap](implementation-plan.md#budget-integration) owns delivery order.

## target and scope

jarvis reads the budget, records expenses/refunds, interprets receipts, corrects
records and manages plans through the budget app. both clients see the same facts.
main chooses useful work from any event under [o6](one-main-events.md); uploads
do not force imports. direct owner statements can create manual entries without
fabricated receipts. ordinary bookkeeping is automatic, including changes to
owner-entered records, voiding, reopening and evidence relinking.

budget owns accepted financial facts, arithmetic, revisions, originals and command
receipts. jarvis owns interpretation, acquisition, its action journal and notices.
no jarvis financial table, duplicate ledger, extraction agent, import controller,
new scheduler or financial ui. use existing native readers and ordinary work/wakes.

retain budget's existing usd-only, paid-expense/refund scope. no payments, purchases,
bank access, transfers, currency conversion, tax-rule updates, account administration,
new categories or source deletion. record corrections/voids retain history.
attachments supply originals; notes' native access supplies agent reading. basic
manual bookkeeping/reporting does not require file acquisition.

## audited foundation and required changes

pulled both repositories from origin on 2026-10-15: jarvis `3bbf8c0` was current;
budget-app advanced to `7b7a9c2`. budget already implements history, imports,
reports, revisions, scoped tokens and durable command receipts. its
[contract](https://github.com/NielsdaWheelz/budget-app/blob/7b7a9c2/docs/budget-history.md),
[schemas](https://github.com/NielsdaWheelz/budget-app/blob/7b7a9c2/src/shared/history-schemas.ts)
and [store](https://github.com/NielsdaWheelz/budget-app/blob/7b7a9c2/src/server/history-store.ts)
are the starting point, not a missing ingestion service. source presence does not
prove deployed availability.

the owner selected two expansions: full bookkeeping powers for jarvis, and the
attachment feature's formats/100-mib maximum instead of budget's current 2-mib
pdf/image/text upload. these require the bounded budget handoff below.

## authority and financial contract

- broaden the existing budget `write` bearer to all bookkeeping mutations;
  retain authenticated `client=jarvis`, separate read-only credentials, owner
  scoping and browser origin checks. no browser cookie borrowing or third role.
  remove `owner_protected` and its current checks/ui. revisions and reasons still
  apply to every correction. jarvis may now change an owner-entered record.
- automatic means the ordinary admitted main action path. operational pause,
  immutable arguments, serial dispatch and effect recovery remain. no extra model
  gate or per-expense confirmation. connector payments/communication retain their
  separate authority and receive no tools in this slice.
- reuse `TransactionInput`: `date`, `kind=expense|refund`, positive safe-integer
  `amount_cents`, `currency=USD`, `payee`, nullable `note`, `payment_reference`,
  `original_expense_id`, and nonempty distinct-category `allocations` summing
  exactly to the amount. dates are financial calendar dates, never upload times.
  category keys come from budget's catalog; null means uncategorized.
- reuse `PlannerState`, `PlannerSave`, `MonthPlanSave`, `TransactionCreate`,
  `TransactionUpdate`, `ImportCommand` and their existing validation. planner
  money is MONTHLY cents even when `period=Yearly` selects display. calculations
  stay in budget. adopted months remain independent of later template edits.
- one evidence item identifies one financial event; line items/splits do not
  also create a second total expense. paid portions and refunds use their actual
  financial dates. an unpaid invoice remains pending. a card repayment is not
  another purchase. matching merchant/date/amount is never a uniqueness rule.
- imports retain explicit `record`, `link`, `hold`, `ignore`, `reopen`, `relink`.
  preserve stable item keys, current revisions and settled-item conflict rules.
  corrections change facts; refunds add facts; voiding removes a contribution;
  relinking changes evidence only. expanded authority does not erase these distinctions.

## budget api handoff

keep the existing authenticated `/api` routes and owner/client command namespace.
publish `integration_contract=jarvis-budget-v1`, supported media and limits in
`GET /catalog`; jarvis accepts this contract explicitly. two app-only credentials
map to the configured owner, verified through existing `GET /auth/me` during setup.
freeze the origin/owner/contract identity in binding
policy; rotate secrets without changing command identity.

| surface | required change |
| --- | --- |
| existing bookkeeping mutations | allow `write` as well as browser owner: planner/plan save, manual create, correction/void, reopen/relink, correction-target changes and adding a missed item after extraction completion |
| `POST /planner/preview` | read scope; `PlannerState` input → `PlannerPreview` below. extract one shared budget-owned calculation from `use-budget.ts`; browser and api use it. no persistence/idempotency key |
| `POST /sources` | replace base64 bytes with metadata reservation: `expected_revision:null`, `namespace`, `external_key`, `label`, `media_type`, `byte_length`, `sha256`, nullable `external_reference`. existing command key required; return `SourceRecord` |
| `GET /sources/:id/upload` | write scope; return `{url, headers, expires_at}` for the exact reserved object. fresh, short-lived capability; no sql mutation or durable command receipt |
| `POST /sources/:id/ready` | write scope, command key, empty closed body; verify original bytes, then atomically publish readiness, source audit and command receipt. already-ready produces an acknowledgement without another source revision |
| `GET /sources/:id/content` | authenticate/read scope, require ready, redirect once to a short-lived signed download; no 100-mib response through the app |
| `POST /sources/:id/complete` | retain revisioned EXTRACTION completion, distinct from upload readiness; imports and completion require ready originals |
| records/reports/inbox | source records add nullable `content_ready_at`; report/inbox add `awaiting_upload_source_count`, separate from ready-but-unextracted sources and pending items |

`PlannerPreview` is closed: `currency=USD`, `period=Monthly|Yearly`, existing
`scenarioName`, `basis={tax_year:2025,payroll_year:2025,state:California,
filing_status:Single,bracket_period:Yearly}`, and `displayed`. reuse the current
displayed shape: `grossIncome`, `takeHomePay`, `savings`; `deductions` with
`socialSecurity`, `medicare`, `federalIncomeTax`, `stateIncomeTax`,
`healthInsurance`, `rentersInsurance`, `total`; `federalTaxResult` and
`stateTaxResult` with existing `TaxResult` fields; `categories[]` with
`group`, `heading`, `items[{key,label,amount,editable}]`, `subtotal`.
money values are safe-integer usd cents for the selected display period,
EXCEPT bracket `min/max`, which remain annual thresholds; rates are decimal
fractions. reuse existing enum/null shapes. basis describes the checked-in data,
not current-year tax advice; no data upgrade is implicit.
extract to `src/domain/planner-preview.ts`, reusing the existing services and
checked money helpers. reject overflow; do not retain raw multiplication/casts
from the browser hook as an alternate unchecked calculation.

reuse existing `sources`; add stored byte length, immutable r2 account/bucket/key
and nullable readiness time, remove `original bytea`. no upload/jobs table. the
single object key is `sources/<source-id>/original`; supplied filenames never
select paths. identity `(owner, namespace, external_key)` remains unique. matching
bytes/size under an existing identity return its original metadata; changed bytes
conflict. never overwrite an original or replace its first provenance.

accept nonempty exact originals up to 104,857,600 bytes: `application/pdf`,
`image/jpeg`, `image/png`, `image/webp`, `text/plain`, `text/csv`,
`application/vnd.openxmlformats-officedocument.wordprocessingml.document`.
plain text/csv must be valid utf-8; unsupported encodings remain explicit.
retain existing field bounds: labels/keys 200 utf-16 units, other prose 2000,
proposals 16 kib. size is per file, not a total-history ceiling. no transcoding.

use a dedicated private budget r2 bucket and the standard javascript s3 sdk;
reuse its public signing/streaming methods. browser and jarvis transfer directly.
this bypasses the [hosting body limit](https://vercel.com/docs/functions/limitations)
without moving the application or adding a proxy/worker.

- sign one 15-minute `PUT` with `If-None-Match:*`, the fixed media type,
  attachment disposition and `Cache-Control:no-store`; allow only the budget
  browser origin in cors. no public bucket endpoint or automatic expiry.
  [presigned urls](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)
  are bearer capabilities; keep them out of model context, receipts and logs.
- readiness checks for the original command receipt/already-ready source first;
  otherwise streams the actual object outside sql, counts bytes, verifies sha256
  and applicable utf-8, then rechecks the command receipt and frozen identity and commits readiness,
  audit and receipt in one existing serializable transaction. metadata
  and etag are not a sha256 proof. `If-None-Match` prevents a still-valid upload
  url from changing the ready object. use the documented atomic
  [conditional put](https://developers.cloudflare.com/r2/api/s3/api/).
- absent/incomplete bytes leave the source pending; mismatch is an explicit
  integrity failure, never ready or an automatic overwrite. resumable same-object
  transfer uses a fresh ticket. no multipart controller, background verifier,
  automatic cleanup or deletion pipeline; inspect failed pending uploads through
  the existing inbox and repair explicitly.
- ready originals remain independently available through budget after jarvis
  outages or attachment deletion. retain them indefinitely. a database restore
  also requires the referenced bucket originals; revise the old db-only recovery
  claim. this feature adds no global erasure/backup service.

## jarvis tools and composition

declare one `budget` family through existing llm-tools, main's o6 catalog and
native callbacks. no grant to compactor/dreamer. closed python schemas project
the owning budget schemas; no copied financial calculations or runtime openapi
tool discovery. all writes use the normal `ActionRequest` envelope.

| tools | operation arguments / result |
| --- | --- |
| `budget.catalog` | no arguments → category keys, currency, limits and contract identity |
| `budget.get_planner`, `budget.preview_planner`, `budget.save_planner` | none / `PlannerState` / `PlannerSave` → saved state or budget-computed preview |
| `budget.get_plan`, `budget.save_plan` | month / month plus `MonthPlanSave` → current adopted month |
| `budget.report` | period, optional through-month → canonical `HistoryReport`; explicit owner-local cutoff when needed |
| `budget.list_transactions`, `budget.get_transaction` | existing `TransactionListQuery` / id → page with category contribution / current record |
| `budget.create_transaction`, `budget.update_transaction` | `TransactionCreate` / id plus `TransactionUpdate` → committed record/revision; update includes explicit voided flag and reason |
| `budget.list_sources`, `budget.get_source` | existing `SourceListQuery` / id plus item cursor/limit → metadata/page; no original bytes |
| `budget.open_source` | source id → source identity/digest, verified local original path; pending/unavailable is explicit |
| `budget.add_source` | ready jarvis attachment id, explicit bounded display label → budget source id/digest and original ready acknowledgement |
| `budget.import_item`, `budget.complete_source` | existing `ImportCommand` / source id plus expected revision → committed outcome / extraction-completion receipt |
| `budget.changes` | existing `ChangesQuery` → paged attributed historical snapshots |

reads use the read credential and `ReDispatchable` recorder; original callback
receipts still replay without i/o. writes use the write credential.
preview is a read despite its http method. `open_source` uses budget's authenticated
download and the attachment module's verified-cache primitive; it adds no jarvis
attachment row or second durable original. native tools read that path. fresh
turns reopen; an old path receipt is historical, not guaranteed live image context.

reuse [search continuation](complete-and-continuable-searches.md#result-and-continuation-rules):
default 20/max 100 rows, normalized scope, observation time, opaque scope-bound
cursor, `more|exhausted` and explicit errors. return a whole provider page within
64 kib or `OutputTooLarge` with its input cursor unchanged. no discarded suffix,
total traversal limit or snapshot claim. all json reads in the tool table accept
`projection=snapshot|text` (default snapshot); `open_source` is the file exception.
text starts at `offset=0`, with `max_bytes=8192` by default (range 1–32768);
later offsets supply the returned digest as `expected_digest`. it losslessly chunks canonical json
of that same requested result/page using the search contract's utf-8 offsets,
digest, total/end/next offsets and observation time. snapshot rejects chunk
arguments. reuse its disposable projection cache and `SourceChanged` behavior;
never restart or skip a page silently. use budget's consistent report result,
not sums of an incomplete list.

one bounded http client/composition, fixed configured origin, no automatic
redirects/retries. follow only the protocol's exact r2 upload/download target
without forwarding budget authorization. app secrets and signed urls never
reach native commands. responses preserve ids/revisions and typed errors:
validation, forbidden, not found, conflict, too large, not ready, integrity,
unavailable or uncertain; failure is never empty financial data.

## source identity and effect recovery

`add_source` freezes attachment id, exact original source tuple, sha256, size,
media type, label and budget target before entry. namespace is `jarvis/discord`
or `jarvis/gmail`; external key is sha256 of canonical json of that full source
tuple, including account/channel identity. external reference is `attachment:<id>`.
recapturing the same provider original reuses the budget source; a different upload
is a distinct source even with identical bytes. matching purchases remains main's
judgment. use source item keys tied to document entries, not model attempts.

ordinary budget mutations use `canonical_text(action.id)` as command key.
`add_source` alone has two fixed provider keys: `<action.id>:source` for metadata
reservation and `<action.id>` for readiness. these are connector protocol
constants, not a new operation journal or general sub-action facility:

1. recover the final ready receipt first; otherwise an admitted executor may
   reserve/recover metadata with the first key and frozen payload. failed receipt
   lookup proves neither absence nor success; observe-only recovery stops there.
2. obtain a fresh ticket and upload the verified original to its one create-only
   key when needed. a 412 means inspect/finalize existing bytes, never overwrite.
3. publish readiness using the final key. only that receipt completes this tool;
   reservation or uploaded bytes alone are partial progress. imports happen in
   later ordinary calls and retain their own action identities.

remote receipts/source identity reconstruct progress. missing native cache does
not defeat final-receipt recovery or verification of already-uploaded bytes.
otherwise reopen the canonical attachment; lost bytes yield explicit incomplete
progress with the source id. never switch to model-generated text as the original.

adopt a narrow additional safe-repeat basis in existing `ActionStore`/dispatch:
the same budget key, method, target and normalized body may repeat under budget's
atomic receipt contract even while the first request is unresolved. a missing
receipt is NOT absence proof. conditional r2 upload similarly keeps the same
object and bytes. [negative reads](https://developers.cloudflare.com/r2/reference/consistency/)
cannot prove an in-flight write will not commit. all other connectors keep their
existing repeat rules.

use `ReDispatchable`, two lifetime executor entries, staged actual external-attempt
accounting and original action/native receipts. no hidden http/sdk mutation retries.
default metadata request deadline 15 seconds; object transfer 300; readiness
verification 120 server/150 client. `add_source` permits at most eight external
requests per entry and sixteen cumulatively; ordinary writes one per entry/two
cumulatively. stage counts before dispatch and never reset them on re-entry.
reconciliation observations have their separate bounded read allowance; no outer write timeout.
after an ambiguous entry, observe its final command at 0, 2 and 8 seconds with
10-second read deadlines. matching receipt settles; malformed/conflicting or
unavailable evidence cannot prove success. a repeat needs current eligibility
and remaining entry capacity; exhaustion with unresolved evidence is terminal
uncertain. a later rejected attempt cannot disprove an earlier unresolved commit.
do not invent a new key to evade it.

paused/stopped recovery may observe and settle original receipts. reservation,
upload and readiness publication are effects and require admitted executor entry;
no recovery GET may secretly finalize them. retain partial source ids in safe
outcomes. ordinary source work after an uncertain action does not bypass its
existing request/action barrier.

revision conflict is a rejected proposal: read current state and make a deliberate
new correction, never silently refresh the revision. immutable acknowledgements
may describe older values. fetch current records before claiming current state.
historical audits/command bodies remain bounded opaque json, not executable
legacy schemas; preserve their stored values when retiring `owner_protected`. semantic
`record` reuse under a NEW key returns the current source item and transaction
in the same serializable transaction, without reapplying the old input; that
observation becomes the new command receipt. a different proposal or relinked
item conflicts. retain `accepted_input`; remove redundant `accepted_outcome`
after verifying original acknowledgements survive in command receipts. SAME-key
replay returns its exact stored status/body without today's record encoder.

## content designer contract

the designer supplies instructions/examples to the definition-file owner; no
runtime critic. good content distinguishes evidence, accepted facts and estimates:

- infer useful handling without compulsory import, extraction sequence or plan
  adoption. retain source/page/entry references; unread pages forbid a claim of
  complete extraction. completion means entries were considered, including holds,
  not that every entry was paid/recorded. missed entries can be added explicitly.
- clear amount/date/payment/currency supports recording; uncertain category can
  be uncategorized. otherwise use the existing partial proposal and concrete hold
  reason or ask the smallest useful question. do not invent tax, tip or currency.
- report `recorded`, `linked`, `pending`, `ignored`, `voided` or uncertainty
  accurately. “linked to the existing purchase; spending is unchanged.” direct
  owner statements need no manufactured document.
- null `content_ready_at` means “awaiting upload,” with download/import/complete
  unavailable; ready plus incomplete means “awaiting extraction.” pending items
  are independent. these counts are global; a reserved file is not yet uploaded.
- use canonical report period/totals; disclose missing plans and relevant pending
  evidence. pending counts are global. net zero differs from no transactions.
  say recorded spending, never all spending or actual savings. planner output is
  an estimate using budget's configured rules.
- explain material corrections and month-plan changes with their reason. never
  adjust a plan merely to hide an overrun or manufacture complete coverage.
  conflicting revisions require fresh judgment, not another blind write.
- link existing `/history?period=<month>&transaction=<id>` and
  `/inbox?source=<id>` under the configured budget origin; no public original urls.
  example: “recorded $42.80 usd at grocer on october 12 under groceries. [receipt].”
  uncertainty: “the invoice shows $180 due; payment is unconfirmed. saved for review.”

## nonoverlapping delivery and hard cutover

| owner/unit | files and exact responsibility |
| --- | --- |
| budget api/domain | existing `src/shared/history-{schemas,errors}.ts`, `src/server/{api,auth,history-handlers,history-store}.ts`, new `src/domain/planner-preview.ts` and one migration: expanded bookkeeping, historical evidence, preview, source metadata/readiness, atomic receipts |
| budget storage/content | new `src/server/source-storage.ts`; existing `src/web/api-client.ts`, `evidence-inbox.tsx`, `transaction-editor.tsx`, `hooks/use-budget.ts`, package/config and budget docs: sdk transfer/signing/hash verification, current upload ui, truthful readiness/content; api owner alone edits shared routes/schema |
| jarvis declarations | new `src/jarvis/budget_tools.py`: closed tool inputs/results, instructions and one family; no financial arithmetic |
| jarvis connector | new `src/jarvis/budget_connector.py`: fixed-origin client, source copying, receipt recovery; extract/reuse attachment cache access with its owner |
| jarvis integration | existing `settings.py`, `cli.py`, `tool_composition.py`, `definitions.py`, `read_dispatch.py`, `write_policy.py`, `write_dispatch.py`, `actions.py`, compatibility manifest and spec/adr: one shared writer owns wiring and narrow retry amendment |
| deployment | budget owner provisions private bucket/cors/app credentials; dev-server provisions jarvis origin/owner/read/write secrets and native cache access. no kernel/provider/skid/llm-tools api change beyond the existing notes prerequisite |
| verification | temporary synthetic boundary/live journeys below; each proof owned once, with content review |

external handoff is prepared here, not assigned or implemented. agree the public
schema first; budget api/storage units precede jarvis integration. use existing
sdk primitives; no local shared-library fork or general http-tool proxy.

hard-cut budget's bytea/base64 transport, owner-only bookkeeping restrictions and
protection ui. stop writes, drain unresolved old commands, copy existing originals
to their fixed keys and verify count/hash before dropping bytea. preserve source
ids, revisions, item links, audit and original command bodies. no runtime dual
storage, old upload route or compatibility decoder. deployment drains incompatible
jarvis actions normally. retained originals are evidence, not a legacy code path.

## acceptance and costs

three temporary red → green → refactor journeys, adversarially reviewed at the
contract, failing oracle, working integration and final cleanup stages:

1. real budget api/postgres + jarvis action/callback path: manual entry, plan
   preview/adoption/amendment, expense/refund, correction/void/reopen/relink and
   owner-entered record edits. read token cannot write; two clients conflicting
   on revision cannot silently overwrite. lost responses, two simultaneous
   same-key requests, restart and pause preserve one effect and original receipts.
2. real private test r2 + browser/jarvis: each supported format, >2-mib and
   100-mib boundary, mismatched hash and duplicate/in-flight conditional upload.
   reserve/upload/ready crashes never claim an unavailable original. budget copy
   opens after jarvis-original deletion; no signed url/token reaches model/logs.
   migration preserves old bytea originals; metadata plus object restoration works.
3. real native main + synthetic receipts/statements/reports: repeated delivery
   reuses the same source/item; a corroborating second document can link the
   existing purchase. equal-valued distinct purchases survive, unpaid and
   unread entries remain honest, a >100-row history stays traversable. independent
   oracle: september plan 50000, expense 51595 → +1595; october refund 2000 →
   −2000 recorded. missing plans, monthly planner units, historical receipts and
   uncertainty cannot produce false current totals or false success.

use isolated data/resources and existing test tools; no production finance data
or service operations. delete the new temporary tests after reviewed evidence
and refactoring; run normal static/build checks. do not delete budget's existing
tests or restore jarvis's retired suite. no behavioral/live checks run for this doc.

costs: automatic bookkeeping can revise owner-entered facts; audit/revisions aid
repair. independent originals duplicate storage and survive jarvis deletion.
100-mib support requires direct uploads and a verification read; interrupted
transfers may repeat. usd/format/size limits remain explicit. bounded recovery
can still need live repair. deleting temporary tests loses lasting regression
coverage. no payment, historical completeness or exactly-once semantic matching
guarantee is implied.

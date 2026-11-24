# adr 0106 · interrupted answers and parked work

**accepted for source implementation.** baseline jarvis `74bfcaba`, provider `1faa4912`, kernel `a3b37282`, stock `0.171.0`, schema `0023`. one turn produced a final answer and two confirmed calendar writes, then parked four inputs because an earlier assistant draft remained open. the original turn has no accepted seal. [incident, ids and reproduction](../issues/native-steer-interrupted-message.md)

**target.** tolerate a proved superseded draft. retain strict effect, input and answer evidence. park each affected request under its own authority. tell the owner once what happened and what remains. an operator inspects and releases named inputs. this decision amends [0086 §b](0086-native-recovery-and-memory-availability.md#b-native-admission-rejection-and-one-fresh-retry) for notice cardinality, and adopts the existing [batch notice intent](../one-main-events.md#selection-continuation-and-recovery). it grants no production cut or authority to replay a write.

## a · provider terminal acceptance

**owner and files.** provider-runtime in llm-calling owns the codex dialect, event ordering and evidence. edit `src/provider_runtime/agent_runtime/codex_sdk.py` and `docs/provider-native-turns.md`. jarvis's existing `native_diagnostics.py` owns log rendering. kernel continues to propagate the original cause. the public terminal, submission, steer, tool and seal schemas stay unchanged.

**decision rule.** at the existing `_turn_terminal` unfinished-item guard, admit precisely one additional case. validate before changing live state.

1. the controlled turn has a genuine successful stock completion for this exact thread, turn and submitted attempt, with no error, contradiction, raw loss or fabricated seal. provider evidence and jarvis authority to publish are checked separately; fencing never reauthorizes effects. all existing identity, accounting, submission, containment and later product checks still apply.
2. every outstanding normalized start is an `agentMessage`. there are no unresolved tools, calls, reply tokens, server requests, possible unpublished calls or submitted inputs awaiting native recording. check the owning turn handle as well as the adapter state. a queued steer ack proves nothing. conservatively reject this exception if a definitively refused steer still occupies a pending slot.
3. stock's `itemsView=summary` contains exactly one eligible assistant `final_answer`. require a distinct, fresh normalized start and completion for it on this turn. match the selected completed item's id, phase and exact text to the summary. each discarded draft's **last** observed activity precedes that final's **start**. use ordered decoder events, never timestamps. any intervening draft delta, reuse, incomplete identity history, missing summary or disagreement defeats this exception. never read an answer from logs or from the summary alone.
4. use the existing bounded per-turn identity state, including retired ids and retry resets. record just the ordering needed for the predicate. after all native checks succeed, retire only those open display ids before close. emit the ordinary terminal once. never invent completion events. the ordinary balanced path, genuine stock disconnect path, isolated turns, owner-stop and seal-before-product validation keep their established contracts.

**content designer.** the provider designer owns the evidence vocabulary and counterexamples. on a rejected terminal with unfinished starts, expose a typed content-free cause under `ProtocolDefect` to the existing bounded jarvis diagnostic. report the first failed check in order `open_authority`, `pending_input`, `incomplete_identity`, `unproved_order`, `summary_mismatch`, with counts of open display/other items, pending calls/inputs/server requests and a summary match value `match | mismatch | absent | unchecked`. a matching summary passes the last check, so it produces no rejection diagnostic. reuse the enclosing attempt id and 8 kib limit. never log text, arguments, raw type names or provider ids. no extra success log or durable diagnostics schema.

## b · one notice per parking operation

**owner and files.** jarvis `native_journal._fail_inputs` is the shared entry for protocol faults, sealed failures, retry exhaustion and pre-submission oversize. keep the current receipt/eligibility selection and locks. partition the inputs into retry and park first, including mixed contact/context histories. update every newly parked row with its own reason, timestamp and configuration wait. zero newly parked produces zero notices. for the rest, replace the per-row message/notification insertion with one canonical `message(source=native_failure)` and one existing `enqueue_notice(kind=reply)`. both commit with those transitions and the attempt's existing settlement. retain a fresh notice for every actual no-attempt singleton repark. crash/re-entry must neither omit nor duplicate the logical notice. firebase receives only the existing ids and kind. android keeps its generic lock-screen title “jarvis replied”. quotes and receipt details appear only in private chat.

**schema and owner content.** use existing message text, scope, trace and `home.proposal_ids`. union distinct pending proposal ids for the newly parked origins under the same scope. a failure card is never evidence that an approval was presented. keep chat, web, android and push payloads as they are. historical notices and acknowledgments remain original.

the notice designer supplies deterministic examples for a mixed group, a background-only group, a partial/uncertain action and a singleton. render in this order:

- what failed, in ordinary language. for this fault, “i couldn't deliver the final answer.” distinguish size, exhausted retry and malformed product when the stored cause establishes them.
- operations recorded for exactly the newly parked requests. use distinct action ids, same scope and original `origin_message_id`; use actual status and supported typed receipts. read existing result codecs in `actions.py` and calendar success types in `write_tools.py`; approval previews describe proposals, so cannot supply this evidence. a confirmed calendar receipt may name its event title. say “created and updated” about one event only with matching known account, calendar and event identity. unsupported/opaque tools get their recorded operation name and status. a failed or uncertain operation conveys only the recorded outcome. queued, executing or awaiting approval never becomes a success. counts of reads, proposed arguments and session text cannot establish an effect.
- what remains open. identify owner requests with short quoted excerpts of their canonical text; count host facts by source. pending proposals need repair before a decision. keep quotes and receipt titles plain, one line, up to 80 unicode characters each; show up to three labels per category plus the omitted count, ordered by source time and id (actions by creation and id). treat excerpts as quoted data; escape renderer metacharacters and suppress control characters. surface uncertain effects even if ordinary examples are omitted. use only trusted labels and bounded status counts. no generated interpretation of a request, ids, private mail body, shell command or second model call in the notice.

example for an isolated matching receipt and owner text: “i couldn't deliver the final answer. calendar event ‘boutique visit’ was created and updated. still open: ‘research sizing options’. two mail notices also await processing.” a reproduced notice may describe an action as of parking; it cannot certify later external state.

## c · operator inspection and receipt-led recovery

**owner and files.** jarvis `cli.py`, `messages.py`, `docs/operations.md`. add `jarvis list-parked`, read-only online or stopped, runtime database login, one read-only consistent snapshot, no writer lock or connector calls. use `PausedSettings` for database and owner scope. select owner/host rows with a nonnull park stamp; flag inconsistent states for inspection without a command. for new and old rows use the same grouping rule: require matching scope, park timestamp, a real attempt linked to this input, the attempt named by the input’s `trace.native_attempt_id` has `attempt_seq > trace.released_through_native_attempt` (absent watermark means zero), and a native failure notice names that same attempt. its `processed_at` must equal the input’s exact `processing_parked_at`; use the same transaction timestamp value when writing both. group only these corroborated rows by scope, attempt and park stamp. otherwise display the row alone with unverified provenance. a no-attempt park can retain an earlier trace id. never group by time or reason alone. order groups by park time, members by id. print time, attempt if known, full member ids, role/source, original reason and one literal `jarvis release-parked ID [ID ...]` command per group. empty inventory prints “no parked requests” and succeeds; query failure exits nonzero without partial commands. add no execute flag, api endpoint, app button, table or grant. both commands use the same eligibility predicate. grouping is descriptive; only `clear_parked` checks and mutates live state.

**recovery designer.** good output makes the effect boundary and next action clear. the runbook requires a fresh stopped inventory under operator custody immediately before release; stale printed ids can name requests that reparked. keep multi-id release atomic, the existing watermark and named operator lock. an original valid seal settles locally when its existing fences permit. an unsealed attempt requires fresh reasoning from exact inputs and original `accepted_action`/`receipt.read` evidence. `existing_action_ref` reopens its compatible receipt; a null ref expressly proposes a new operation. retain billed-once and uncertain-effect barriers. the report is owed here; the calendar already contains both writes. a prompt or matching arguments cannot guarantee semantic deduplication. reuse existing recovery instructions if the red journey confirms them.

## delivery and acceptance

a and b can proceed independently. c owns cli/recovery and runbook. the integrator alone owns the dependency chain, lockfiles, jarvis role manifest and `definitions.EXPECTED_GIT_PINS`. land provider, then a dependency-only kernel repin, then jarvis. use one executable path per case. replace the old per-request writer at its source. retain historical receipts under their actual contracts. no schema migration, feature switch, provider fork, upstream wait, notification service, raw transcript archive, automatic unpark or changes to steering priority.

each unit has a content designer and an engineer. before implementation the designer supplies good/bad examples within its contract. independent claude opus challenges each design and reviews each refactored proof plus the integrated cut. scoped exception to [0046](0046-reset-testing.md): first run a temporary normal-entry integration/live probe against the predecessor and record the specific red; implement, go green, simplify, rerun on the final bytes. established behavior supplies positive controls, not manufactured reds. use actual pinned stock, provider, kernel, jarvis, postgres and outbox on macbook. intercept external writes. the existing http fixture demonstrates the adapter symptom. production's 21:47:42 interruption logs carry `transport="responses_websocket"`. for the decisive red, drive stock through a loopback responses websocket: start a draft, send a native steer, **wait for stock’s correlated outbound** `response.interrupt`, then ack it, emit the matching interrupted item and incomplete response, and finish sampling with a fresh final. capture normalized order and assert the terminal view, id, phase and text on red. a missing witness or unavailable websocket fixture blocks qualification. a no-steer upstream interruption is a separate control. [stock websocket fixture](https://github.com/openai/codex/blob/rust-v0.171.0/codex-rs/core/tests/suite/pending_input.rs#L1590-L1653)

| unit | decisive observations |
| --- | --- |
| a | after one externally counted write, interrupt a draft with a real steer. original input is recorded, fresh final exactly matches the terminal summary, final settles once. repeat with upstream interruption alone. a balanced control passes. mismatched summary, later draft activity, pending steer or unresolved callback fences the corresponding dirty case; original action and read evidence survives. also steer during reasoning and partial tool arguments. no stale write may dispatch. record actual native closures; an open non-display item still fences. if stock strands reasoning, open a separate record in `docs/issues/` before the cut and surface its measured impact. test exhausted identity evidence and content-free diagnostics. |
| b | four waking inputs, two successful writes on one event, one owner notice and one push outbox target. all four ids park. mixed retry/park reports only newly parked members, per-input causes and pending proposals. an uncertain effect stays explicit. retry-only stays silent. interrupted transaction and restart publish once. release and repark a pre-submission singleton: two distinct transitions. both clients render existing text/cards. |
| c | inventory before/after partial named release, no-attempt park, empty inventory and a stale mixed list. a refused release changes zero rows. crash after a valid seal settles locally without a model call. for an unsealed parked group, stop, release reviewed ids, restart; obtain the sourced research answer, correct input dispositions and the same event with both original action receipts. count actual connector entries. preserve unrelated parks. |

**cut and closure.** use dev-server's `scripts/rehearse-worktree` on macbook for the detached rehearsal. retain named red/green/refactor and opus evidence outside scratch, reopen/hash it, then delete only this cut's temporary probes. report proof and fixture/resource cleanup separately. at a separately authorized [0104 cut](0104-maintenance-without-owner-pause.md), qualify the recovery reader for the changed lock and finish named activation. verify the selected release and services. then stop the assistant for independent maintenance, refresh `list-parked`, inspect and release under `deploy/with-independent-maintenance`, then restart and verify service. never nest independent maintenance inside an activation hold. release the [original four ids](../issues/native-steer-interrupted-message.md) only if still eligible and consistent with owner controls. the owner chose to keep all four parked for the cut. if the november 25, 2026 visit at 11 am pacific has passed, first inspect the original receipts and obtain the owner’s disposition before releasing any of the four. do the same if state or effects have changed. for deferral or owner-directed retirement, close only the isolated qualification and record the owner disposition; installed delivery of the old answer remains unproved. leave unrelated parks alone. following an actual release, verify the same event and original create/update receipts, zero new calendar writes for this repair, delivered research answer and per-input settlement. report installed evidence separately. historical alerts stay visible.

**trade-offs.** strict corroboration can still park a genuine answer. deterministic copy exposes less nuance than a generated explanation. a grouped notice reduces interruptions while full diagnosis requires the cli. named release costs downtime and human inspection. production-matched loopback traffic costs more than an http stub and makes the rare timing repeatable. the owner accepts possible delay past the visit; installed recovery then needs a new disposition. deleting the temporary tests reduces ongoing regression coverage; retain the cases and evidence here for dependency changes.

## source qualification · 2026-11-24

the macbook rehearsed jarvis `9e19e4f8`, kernel `a6e06de4`, provider
`cbd64ee3`, stock `0.171.0` and postgres 16 at `0023`. git resolved the
two dependency commits from local worktrees under the normal immutable urls.
the lock check, wheel install and runtime provenance check passed. candidate
publication still requires publishing those commits.

- **provider.** under default responses websocket settings the predecessor
  recorded the steer, one intercepted calendar create and one paid read, then
  rejected the exact final summary with one abandoned assistant draft. four
  parks produced four failure replies. the candidate settled one final and
  all four inputs. balanced and upstream-only turns settled too. partial tool
  arguments yielded zero stale callbacks. a fully published calendar update
  entered and closed before the steer, and its output reached the next sample.
  summary disagreement, late draft activity, unrecorded input, unresolved
  callback, exhausted identity history and identity reuse fenced the terminal.
  [interrupted reasoning](../issues/native-steer-interrupted-reasoning.md)
  also fenced the terminal in stock's observed item sequence.
- **notices and inspection.** postgres verified four parks with one failure
  message and one matching push row, mixed retry/park, uncertain effects,
  rollback and restart, and two notices for two singleton transitions.
  intercepted firebase delivery contained kind and ids. chromium and android
  displayed the exact literal excerpts and pending proposal card. inventory
  verified exact group corroboration and showed a valid unverified trace
  claim for inspection. partial named release, stale and mixed-set refusal,
  writer-lock independence, query failure and an empty list all passed.
- **recovery.** a stock turn parked after the steer stranded one reasoning
  item, reported as `open_authority`. stopped named release reopened two
  action receipts and the original paid read, replayed both original action
  refs, and delivered one sourced fixture answer. all four inputs settled.
  the same event and original receipts survived with zero additional calendar
  calls, and an unrelated park remained. after process death following a valid
  seal, startup published that final once with zero model calls. the scripted
  model proof establishes the receipt and dispatch contracts. production
  behavior also depends on the live model's choice to reuse receipts.

existing provider (192) and kernel (176) checks passed. claude opus reviewed
the predecessor evidence, each unit and the integrated candidate. the
reopened manifest at
`~/.local/state/jarvis/qualification/adr0106/qualified-evidence.sha256`
has sha-256 `01916aef942ddc3e56770b6f2428d98bbbe42107a8249eee8173758636918dd2`.
the detached receipts separately record checks and successful teardown.
the temporary probes were deleted after evidence verification. installed
verification of the four original requests remains open under the cut and
owner disposition rule above.

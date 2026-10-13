# V1 acceptance specification

the owner-approved [testing reset](decisions/0046-reset-testing.md) removes the
previous suite, fixtures, evaluation corpus, and qualification runners. execution
of the old test/qualification criteria is suspended pending the subsequent
[testing redesign](issues/testing-redesign.md), including the five-run and
four-of-five quality scoring requirements.

the criteria below retain the intended product behavior. descriptions of removed
test procedures are historical requirements to reconsider in the redesign, not
commands or gates available today. no static/build result proves these behaviors. native cutover proof is the
explicit adr 0065 exception described below.
dated reports in git remain evidence only for their recorded revisions and environments.

Every result appears in a dated acceptance report. Any owner-approved waiver is
named explicitly; no criterion disappears or is weakened silently.

the accepted [universal-memory contract](universal-memory.md)
owns its [focused acceptance](universal-memory.md#11-acceptance-and-verification),
as simplified by [adr 0063](decisions/0063-simplify-memory-policy-and-retrieval.md).
retain two small regression groups: capture/retry and memory completion. verify
atomic complete-event capture, bounded retries, atomic memory progress and
direct-note idempotency; interrupted background inference may repeat paid work.
main's recorder, paid-search uncertainty barriers and effect recovery retain their
checks. no frozen background-batch replay tests or recurring fleet matrix are
required. focused checks also cover automatic atomic activation, native-field
validation, deterministic fusion, the shared search gate and valid seed-only
dreaming. targeted review and live provider checks supplement these regressions;
there is no learned-reranker selection or mandated search choreography.
the source implementation adds six tables after the native nine and replaces
A5's old role/evaluation criteria with the consolidated focused acceptance.
source, live provider, fleet installation and production results remain distinct;
none establishes the seven-day personal acceptance by implication.

## native cutover acceptance

[adr 0065](decisions/0065-native-agent-supervision.md) replaces retired main
step/session/CAS/capacity tests with shared
[N001–N020](https://github.com/NielsdaWheelz/llm-agent-kernel/blob/9d57e8945be5b26397c5a3942612f81a190f8db4/docs/native-agent-spec.md#9-delivery-and-acceptance).
the [shared evidence](https://github.com/NielsdaWheelz/llm-agent-kernel/blob/main/docs/native-agent-evidence.md)
and [jarvis integration handoff](native-agent-integration.md) distinguish exact
installed artifacts, genuine native/model/tool proof, controlled fault fixtures,
local host topology and unrun deployment/domain behavior. follow their recorded
revisions; a newer mutable source tree is not the tested artifact.

these native criteria are the authorized implementation gate. the whole-product
checkboxes below remain separate acceptance records; an unchecked domain,
physical deployment or seven-day owner criterion does not create another kernel
feature gate. historical A1.9 is its dated baseline receipt, not current readiness.
temporary feature probes are deleted only after final integrated green proof;
existing shared conformance remains. this restores no retired standing suite.

## A1. Repository and deployment

- [ ] **A1.1** The existing Hetzner `dev-server` runs Jarvis from an immutable
      host-native release under a dedicated `jarvis` account using Python 3.12
      and a reproducible lockfile. Jarvis opens no public listener, is not owned
      by rootless Docker, and the Nexus production host and application state
      remain untouched.
- [ ] **A1.2** `llm-agent-kernel`, `provider-runtime`, `llm-tools` and `universal-memory` use
      qualified pinned git revisions, not the user's mutable local worktrees.
- [ ] **A1.3** A clean checkout can be configured without modifying Ariel,
      `llm-agent-kernel`, `llm-calling`, or `llm-tools`.
- [ ] **A1.4** migrations produce the fifteen application tables: the native nine
      and six library-owned memory tables, with exact columns from spec and the
      memory contract.
- [ ] **A1.5** `scripts/verify` runs the frozen-environment, formatting, lint, type,
      documentation-link, dependency-audit and package build/install checks.
      native integration/live acceptance follows the explicit adr 0065 exception;
      the wider testing redesign remains separate.
- [ ] **A1.6** Secrets are absent from the repository, fixtures, PostgreSQL, model
      context, and ordinary logs.
- [ ] **A1.7** A second Jarvis instance against the same deployment refuses to
      start while the first holds the ownership lock.
- [ ] **A1.8** startup refuses mismatched exact library pins, schema-4 personal host
      mapping, kernel base instruction or stock native `0.160.0` startup policy.
      public initialize/config-origin qualification precedes thread creation.
- [x] **A1.9 — historical.** a dated Slice 0 qualification report records the exact tool
      manifest and schemas, live authority classification, credential
      ownership/handoff, Discord nonce/history behavior, Calendar ACL/client-ID
      behavior, Gmail send reconciliation, Web canaries, kernel port/conformance
      qualification against the real AgentRuntime API, the upgraded public
      `llm-tools` validation/plan/HostTable/async-recorder seams, and
      credential-containment results. It also records the provider
      failure/cold-bootstrap matrix, finite per-tool lifetime attempt ceilings,
      intended action-backed schedule-recorder mapping, and empty-plan isolated
      one-shot. For Jarvis adapters that do not exist yet, it records the exact
      owning slice and acceptance evidence rather than a fictional pass. The
      owner signs it before Slice 1.

## A2. Discord and conversation history

- [ ] **A2.1 — live.** The owner can speak naturally to Jarvis without slash
      commands and receive useful text/Markdown replies.
- [ ] **A2.2 — live.** The effective bot permissions include `VIEW_CHANNEL`,
      `SEND_MESSAGES`, `ATTACH_FILES`, and `READ_MESSAGE_HISTORY`.
      `ADMINISTRATOR`, guild/channel/message/thread/role/webhook management,
      moderation, kick, and ban permissions are absent; broader inherited
      non-management permissions are an accepted v1 deployment trade-off.
      Every create sets `SUPPRESS_EMBEDS` and empty mention parsing, and every
      content edit preserves those controls. Gateway intents are exactly
      `GUILDS`, `GUILD_MESSAGES`, and `MESSAGE_CONTENT`.
- [ ] **A2.3** A non-owner cannot start controlled tool work or approve an action.
- [ ] **A2.4** Owner messages and interactions in direct messages, threads, or
      any channel other than the configured channel are ignored. No Jarvis
      capability can create, rename, reorder, archive, or delete a channel or
      thread, manage another message, or add a reaction.
- [ ] **A2.5** Approve and Deny are the only custom action components.
- [ ] **A2.6** canonical stop/pause fences callback authority, cancels unentered
      approvals/queued work and persists the notice without model I/O. approval,
      stop and actual effect entry share lock order. entered effects still settle
      truthfully. resume restores eligible requests with fresh approval identities.
      no file-backed pause or implicit restart after owner stop. shared N015–N018.
- [ ] **A2.7** Every inbound owner message is stored before processing and one
      redelivered Discord event starts no second turn.
- [ ] **A2.8** Every assistant response is inserted before Discord delivery and
      receives a `source_message_id` after a successful create response; a
      null ID is the only outbound retry watermark. Its 20-character Discord
      nonce is derived exactly from `message.id` as specified and is not stored.
- [ ] **A2.9 — live.** Every Discord create and retry uses the same nonce with
      `enforce_nonce=true`. Injecting a lost accepted response inside the nonce
      window leaves exactly one visible message. A simulated delayed retry uses
      the same nonce, obeys the finite Slice 1 retry/backoff bound, and may
      produce the explicitly accepted rare repeated conversational message
      because Discord history can omit nonce. Create uses the qualified direct
      REST binding, not a private `discord.py` API; duplicate presentation never
      duplicates an action effect.
- [ ] **A2.10** each top-level turn acquires a fresh native lease from the fixed
      admitted memory view, exact unfinished requests and original tool receipts.
      compatible steering stays in its active tool loop. connection, process or
      owner loss fences old callbacks; effects already entered retain their
      dispatchers until settlement. no saved
      session-reference cache, restart resume or CAS exists. sealed original
      terminals settle locally before current model/tool construction; stale
      stop/resume refuses publication. unknown action/read outcomes block
      redispatch. exact manifest/role/provider fingerprints remain. shared N017.
- [ ] **A2.11** public commentary and useful partial answers commit before delivery
      without completing owner requests. strict `JarvisTerminal` contains a
      response and explicit input dispositions; omitted requests retain state.
      only validated complete dispositions close requests. actual blockers/action
      references are host-validated. complete rendered output fits 2,000
      characters without cropping; incomplete Calendar evidence stays visibly
      partial. commentary, native seal and product acceptance are distinct.
      shared N013/N019.
- [ ] **A2.12** native input delivery records prepared/sent/queued/recorded/rejected
      facts; RPC acceptance never proves native recording. new topics arrive
      promptly while unfinished requests remain. scheduled wakes use a separate
      read-only plan. ambiguous steering fences the old turn before fresh
      reconstruction. explicit current request state governs completion, and
      configuration quarantine remains operator-owned. shared N013/N017.
- [ ] **A2.13** canonical product context uses shared typed prompt sections, source
      timestamps, original receipts and host timezone/`as_of`. provider-private
      types stay inside provider-runtime. fresh reconstruction requires no
      native transcript and restores unfinished work, not fresh effect authority.
      shared N013/N017.
- [ ] **A2.14** native attempt/invocation/input-delivery records preserve exact original
      lineage and immutable results/replies. product dispositions/response/trace
      commit atomically; `origin_message_id` alone is not effect recovery authority.
      changed callback arguments fail closed and repeated delivery replays the
      original receipt. shared N011/N013/N018.

## A3. Existing integrations

These criteria are **live** and use the registrations and credentials qualified
in Slice 0.

- [ ] **A3.1** Jarvis searches and reads a Gmail conversation.
- [ ] **A3.2** Jarvis creates an email draft automatically.
- [ ] **A3.3** Jarvis reads every live reader-or-better calendar, including
      hidden CalendarList entries, under a 50-calendar bound. A final-code probe
      observes at least three normal events with `end.type=unspecified` and
      returns each payload-free rather than rejecting it or exposing Google's
      compatibility end; output reports only counts and no event content or ID.
      The model-visible `calendar.list_events` input contains no `calendar_id`;
      it also contains no result bound. The host performs bounded CalendarList
      discovery and deterministic event pagination with at most ten concurrent
      requests, 100 event-page requests, 202 external attempts, and the stated
      deadline/count/byte bounds. A deterministic 35-calendar, multi-page,
      1,170-event case returns chronological complete coverage; a
      table-driven case proves every partial reason, exact attempts, whole-event
      clipping, and cancellation propagation.
      The list returns at most 1,500 compact overview items in a 524,288-byte
      canonical success envelope. It preserves exact IDs, status, summary,
      start, observed end, and location; full details require
      `calendar.get_event` with the returned IDs.
      `calendar.list_calendars` returns exact IDs and human display names for
      targeted work. An ordinary owner request naming no calendar receives a
      grounded answer without an ID clarification. The typed coverage value is
      complete only after discovery and every selected page are exhausted with
      no failure or clipping. Partial failures and bounds are explicit and must
      be disclosed. A live two-week production read spanning all 35 current
      calendars and at least 1,000 events must be complete; its sanitized result
      records the observed count without content or provider IDs.
- [ ] **A3.4** Jarvis creates, edits, and removes a no-attendee event on a
      verified owner-only calendar without approval. Create uses the exact
      action-derived Google event ID from SPEC section 7.3; an injected lost
      create response followed by reconciliation leaves exactly one matching
      event.
- [ ] **A3.5** A shared or unknown-ACL calendar write requires approval.
- [ ] **A3.6** Adding or notifying another attendee requires approval.
- [ ] **A3.7** A naive calendar datetime is rejected, and owner-local relative
      time resolves correctly around midnight.
- [ ] **A3.8** Jarvis performs live Maps place lookup and directions calls.
- [ ] **A3.9** Jarvis uses `web.search` to search Brave and `web.read` to read a
      returned public page as bounded inert text.
- [ ] **A3.10** The public-Web reader sends no cookies or connector credentials,
      executes no JavaScript, loads no subresources, and rejects a
      credential-bearing URL, loopback/private/link-local target, unsafe
      redirect, unsupported media type, and oversized response. Unmistakable
      credential material in a Web argument is rejected before dispatch.
- [ ] **A3.11** No new Google or Discord registration is created. The one
      unavoidable replacement Google offline consent requests exactly the seven
      scopes in SPEC section 8; it requests no Drive, `gmail.modify`,
      `gmail.send`, `calendar.readonly`, or `calendar.freebusy` scope.
- [ ] **A3.12** Every credential has one owning process, and no bot token or
      autonomous mailbox/calendar authority is concurrently shared with Ariel.

## A4. Model and tool boundary

- [ ] **A4.1** every role uses the shared kernel through personal subscription-backed
      Codex, without provider/model/API-key fallback. main is a
      `NativeDefinition`/`run_native`; compactor, dreamer and gate use
      actual fresh isolated `AgentDefinition`/`run_one_shot` roles. closed schemas
      and exact frozen-plan consistency/tightening validate before I/O; isolated
      plans contain no Write and scheduled wakes are read-only. fresh budgets
      exactly match their plan. shared N001/N010/N015.
- [ ] **A4.2 — live.** The embedding key succeeds on the configured embedding
      endpoint and is denied on a generative endpoint.
- [ ] **A4.3** native cognition receives no application/connector credentials.
      the separate personal host retains its original host-only Codex account;
      jarvis receives no copied authentication. the client group crosses only
      the qualified socket/empty cwd boundary. root-owned application environment
      files and the non-dumpable parent remain protected. shared N014/N019.
- [ ] **A4.4** the actual provider request has a closed structured output schema,
      private empty mode-0750 read-only cwd, disabled native shell/files/Web/network,
      denied unsolicited approval, no MCP/subagents or copied app environment,
      and only declared host callbacks. exact stock `0.160.0` startup catalogue
      and public qualification enforce the whole-host boundary. shared N001/N014.
- [ ] **A4.5** main uses declared native callbacks and strict terminal output, with no
      main step decoder. isolated roles retain strict serial `call_tool | finish`;
      the shared kernel owns their wire envelope and JSON-string decoder.
      whole-step/pure input validation precedes dispatch. unsupported contracts
      fail before submission; unknown/changed native authority fails closed.
      shared N001/N009/N011.
- [ ] **A4.6** main consumes the public prepared native turn/events; isolated roles
      consume `stream_turn` directly. no production `run_turn` projection drops
      authority evidence. callbacks, commentary, input recording, controls and
      native seals remain typed distinct facts. native tools/permissions, unknown
      active items or malformed identities fail-stop. actual adversarial native
      probes are distinct from controlled provider peers. shared N004/N014.
- [ ] **A4.7** main has no cumulative call/token/byte or arbitrary elapsed cutoff.
      finite tool-operation, in-flight/message/frame/queue and control timeouts
      remain; isolated roles retain their actual bounded invocation protocol.
      reader/control stay live during serial dispatch/gate waits. llm-tools
      accounts executor replay and settlement once; usage never grants authority
      or gates work. shared N010/N012/N015.
- [ ] **A4.8** Quota exhaustion produces a fixed host-authored notice and changes
      no provider, model, or credential.
- [ ] **A4.9** reads create no action rows; every external `Write` creates one action
      before executor entry with immutable arguments/execution contract and uses
      `action.id` as both `InvocationPosition` and `EffectId`.
- [ ] **A4.10** Canonical message, raw-memory, and summary transactions create no
      action rows.
- [ ] **A4.11** each exact published catalog/binding matches its declaration, schema,
      implementation revision, effect/replay and frozen plan. cross-catalog or
      handler substitutions fail before I/O. full and scheduled plans retain
      their current grants; isolated roles remain narrow. Calendar discovery v1,
      list v6 and get v2 keep their exact contracts and finite per-operation
      bounds. portable web reader binding is v3; extraction identifiers stay v2.
      no main aggregate output/context quota remains. shared N001/N010.
- [ ] **A4.12** pure input validation touches no executor budget or effect recorder.
      a known invalid native proposal preserves raw evidence and its rejected
      reply without executor entry. completed callbacks retain original
      `ToolResult` and exact model-visible reply before wire delivery; pending
      approval returns its durable receipt without completing the owner request.
      later resolution supplies original action/arguments/evidence. shared N011/N016.
- [ ] **A4.13** one dispatch lane serializes callbacks and approved effects. gate uses a
      current-owner permit naming the active parent invocation; no reserved
      child-turn/token allowance exists. native observation/control, ingress,
      consent and outbox stay live while dispatch waits. shared N012/N015/N016.
- [ ] **A4.14 — live.** The compatibility manifest records the exact qualified
      ChatGPT-local-account model IDs without fixing their count. Configuration
      accepts `gpt-5.6-terra` and rejects retired `gpt-5.4` before ingress,
      admission, provider I/O, or tool I/O. Every recorded route runs the paid
      consumer probes against the exact release code and lock, and at least one
      route currently supported by the provider passes.
- [ ] **A4.15** every role fingerprints the exact kernel-owned base instruction and
      complete native containment policy. application prompts cannot replace
      either. unsupported native versions/startup policy fail before thread
      creation; actual forbidden native authority produces zero host effect.
      source review and controlled peers never substitute for that native proof.
      shared N001/N014.
- [ ] **A4.16** main exposes current `agent.list/info/start/read/send/text/keys/stop/close`
      under SPEC 7.3 and adr 0052. exact captured refs, stop modes and close scopes
      survive admission/recovery; terminal and conversation identity stay distinct.
      every mutation is BilledOnce with one executor entry and truthful partial/
      uncertain receipts. no herdr gate, retired ref codec or silent terminal-input
      fallback remains. unfinished retired work blocks activation; finalized old
      rows remain opaque history. actual worker-fleet journeys require their own
      receipt and are not native-kernel acceptance.

## a5. memory

the [universal-memory acceptance](universal-memory.md#11-acceptance-and-verification)
is authoritative for policy, activation, capture, compression, orientation,
dreaming, echo suppression, retrieval and cutover/repair. retain only the two small
capture/retry and memory-completion regression categories. wider temporary
integration/live checks qualify exact artifacts and are removed after proof;
the retired recaller/rememberer suite and scoring corpus are not restored.

prove the package boundary through actual jarvis composition, including canonical
receipt survival under projection failure, admitted post-cutover eligibility,
fresh top-level views and active steering, exact main-save replay under revocation,
quiet atomic dreaming, shared search accounting and unchanged paid-read/effect
barriers. dev-server's loaded collectors/native clients and nexus's chats-only
consumer require separate concrete receipts. no automated nexus helper inherits
the owner's corpus.

## A6. Automatic actions and approval

These criteria are **live** where they call Gmail or Discord.

- [ ] **A6.1** Catalogued reads and ordinary responses or requested wake notices
      in the configured Discord channel execute automatically. Email drafts,
      verified owner-only no-attendee calendar work, and `schedule.wake` execute
      automatically after the required owner-grounding gate. Discord transport
      operations create no action rows.
- [ ] **A6.2** An email send becomes `awaiting_approval` and does not send before
      the owner clicks Approve.
- [ ] **A6.3** native callback/action schemas have no model-authored approval preview.
- [ ] **A6.4** Host rendering displays the real stored recipients, subject, and
      complete body for email, and the real calendar, attendees, title,
      description, location, start/end/timezone, recurrence, reminders, and
      notification choice for calendar changes, even when model commentary
      describes something else. Safety behavior, five of five.
- [ ] **A6.5** Every supported approval has one bounded host-generated UTF-8 text
      attachment containing the action ID, canonical tool name, and exact
      validated operation payload from the immutable action envelope. a long body remains complete and approvable as
      one action; arbitrary payload text cannot become component-message Markdown.
- [ ] **A6.6** An approval-bearing tool without a host renderer fails closed.
- [ ] **A6.7** The opaque component binds the action and internal approval-message
      IDs. The configured owner, guild, channel, live Discord message ID, stored
      relationship, and current `awaiting_approval` state all validate before an
      atomic decision. The interaction is then acknowledged by disabling both
      components before slow external work begins.
- [ ] **A6.8** Free-form “yes,” “send it,” or relayed approval never approves an
      action. Safety behavior, five of five.
- [ ] **A6.9** Deny moves the action to `cancelled` and prevents send; Approve by
      the owner sends the exact stored draft; a non-owner or mismatched
      guild/channel/message cannot decide it.
- [ ] **A6.10** Duplicate Approve interactions claim one action execution.
      A provider retry occurs only after reconciliation proves the effect absent;
      two deliberately created actions with identical arguments are not
      collapsed by a semantic intent key.
- [ ] **A6.11** A process killed around dispatch leaves `executing`; startup runs
      the complete tool-specific reconciliation procedure before any repeat and
      no action lease is used. `attempts` increments before each actual executor
      entry only while below immutable finite `max_attempts`, but authorizes
      nothing. A repeat also requires proof of absence and safety. At the
      lifetime ceiling, proved absence becomes failed and unresolved evidence
      becomes uncertain. A timeout alone authorizes neither retry nor
      `uncertain`.
- [ ] **A6.12** Only an outcome still unknowable after bounded automatic
      reconciliation becomes terminal `uncertain`. Jarvis presents its evidence
      and asks the owner to inspect provider state; it never automatically
      re-executes and does not block a distinct action authorized by fresh owner intent.
- [ ] **A6.13 — live.** An approved email produces exactly one recipient copy,
      including an injected ambiguous-timeout test reconciled through the Gmail
      draft/known-thread behavior. The draft and immutable action snapshot
      contain the exact stable `jarvis_effect_id` derived from the original
      draft-creation action ID; the MIME `X-Jarvis-Effect-ID` header survives
      updates and send,
      and the send action copies it. Send reconciliation makes three fixed
      observations, fetches the known thread as minimal metadata, and fetches at
      most one hundred enumerated messages individually as raw without mailbox
      search or ordering assumptions. Excluding only the live draft message ID,
      one unique observed exact header-and-content match proves success after
      every selected bounded message is processed, even if a larger thread has
      an unprocessed tail; no Gmail label is required. Multiple, conflicting,
      malformed, or partially processed evidence cannot; repeat requires three
      complete unchanged-draft/no-matching-non-draft-message observations.
- [ ] **A6.14** External success is reported only from provider or reconciliation
      evidence, never a model assertion. An action outcome that cannot return to
      its still-live originating loop creates exactly one host-authored waking
      message keyed by action ID plus resolved state; startup repairs a missing
      row, a later evidence-based resolution of `uncertain` appends rather than
      rewrites, and the new run contains the action ID, tool, original validated
      arguments, state, and safe evidence rather than a model call ID. a silent
      final response or model failure instead persists a
      deterministic visible fallback; asynchronous action results are never
      consumed without an owner notice.
- [ ] **A6.15** The action table has exactly the columns in SPEC section 9 and the
      seven statuses in section 5.4; canonical `tool_name`, `arguments`,
      `execution_contract`, and `origin_message_id` cannot change after
      insertion. The closed contract records the exact tool-contract,
      implementation, policy, and plan revisions, effect/replay declarations,
      input digest, finite attempt ceiling, native attempt/checkpoint/callback
      lineage, ordered admitted input IDs, and gate-supporting owner
      IDs for the occupied position. Stored arguments and contract are
      revalidated before rendering, execution, replay, or reconciliation. original
      `ActionRequest` envelope/receipts remain exact; fresh consent links a successor
      through `supersedes_action_id` without modifying the original;
      unsupported or invalid non-executing work is cancelled and reported.
- [ ] **A6.16** `schedule.wake` creates an exact due wake and cancels a named
      queued wake. A requested wake becomes eligible at its stored instant and
      after restart when overdue. Claiming it creates exactly one host input from
      the immutable stored instruction and requested instant. The visible model result or deterministic
      fallback marks the wake succeeded atomically. Schedule creation stores an
      immutable creation receipt while status remains queued; recorder replay
      returns that receipt at every later lifecycle status, and due processing
      writes only a separate closed concluded/cancelled/failed wake outcome; the
      lifecycle status agrees with that variant and never becomes uncertain.
      The host input retains exact `message.source = schedule_wake`; that
      protocol value is distinct from the canonical tool ID. A
      queued schedule without a valid receipt never fires. Cancellation is a
      separate gated action with its own ID/position/receipt and can cancel only
      a queued original. No generic
      quiet-hours transform, periodic connector turn, or autonomous
      inbox/calendar monitor is configured.
- [ ] **A6.17** Immediately before an approved Gmail send, the live draft must
      match the stored recipient, subject, and complete-body snapshot. A
      mismatch sends nothing, fails the action, and requires a new proposal.
- [ ] **A6.18** Every validated model-proposed `Write`, including an
      approval-bearing one, runs AutomaticWriteGate before action creation. The
      gate has an empty tool plan and receives only current owner input IDs/text,
      canonical tool ID, and the allowlisted scalar effect descriptor, with
      timezone/`as_of` only where relative-time validation needs them; recall,
      connector/Web/tool observations, model rationale/history, credentials, and
      free-form payload text are absent. Deny, ambiguity, invalid output,
      admission/quota failure, or non-current supporting IDs create no action or
      approval. Prompt-injection fixtures from memory, email, Web, and calendar
      are denied five of five; direct owner write requests remain usable.

## A7. Recovery and operations

- [ ] **A7.1** V1 deploys with no application backup, restore command, Restic/R2
      credential, backup database role, or backup timer. The owner explicitly
      accepts that loss of the devbox, disk, or database can permanently lose
      jarvis state; backup remains addable later without changing the application
      application schema.
- [ ] **A7.2** The acceptance report records the production host, release commit,
      Python, PostgreSQL, pgvector, and running-kernel identities; UTC state;
      loopback database binding; root-only environment files; non-dumpable
      parent and systemd `/proc`/resource controls; process restart recovery;
      and the deferred newer-kernel reboot. Deployment does
      not interrupt the owner's tmux sessions or live Codex processes.
- [ ] **A7.3** derived tree nodes, frontiers, embeddings and indexes can be rebuilt
      from preserved originals. original positions and dream progress survive;
      legacy flat summaries remain preserved rather than newly regenerated.
- [ ] **A7.4** After process restart, `succeeded`, `failed`, `uncertain`, and
      `cancelled` actions do not become executable; `executing` actions reconcile
      before any evidence-proven repeat.
- [ ] **A7.5** after restart, Discord catch-up/outbox retries retain the original
      nonce and bounded delayed ambiguity. main fences the old native owner,
      settles original sealed evidence locally, then cold-starts reasoning for
      unfinished requests with original action/read recovery barriers. shared N017.
- [ ] **A7.6** PostgreSQL contains no usable Google, Discord, Codex, Brave, Maps,
      embedding, PostgreSQL, or connector-encryption credential and no
      disposable provider state.
- [ ] **A7.7** Ordinary logs and checked-in transcripts contain no real private
      message, email body, memory text, or secret.
- [ ] **A7.8** known invalid callback repetition stops no-progress without executor
      entry. protocol defects retain original evidence and require repair; local
      stop never becomes a seal. computation may restart only after old callback
      authority is fenced, and owner stop prevents replacement reasoning.
      no retired main claim-counter/cumulative-capacity gate remains. shared N008/N015/N017.
- [ ] **A7.9** every provider/tool entry requires the current deployment owner and
      canonical authority; a gate additionally names its parent invocation.
      missing usage and exhausted historical reservation fields grant no
      authority. no rolling capacity file, refund or reset timer exists.
      stale permits perform no dispatch. shared N015.
- [ ] **A7.10** composed races prove steering/delivery ambiguity, new-topic retention,
      stop/approval/effect entry in both orders, entered-result settlement,
      sealed-terminal local recovery and stale product refusal. single-run or
      controlled provider fixtures alone do not prove real consumer research.
      shared N013/N016/N017.
- [ ] **A7.11** actual process/connection loss fences old callbacks. new-owner reasoning
      preserves original accepted actions and complete read receipts; unknown
      entered work cannot redispatch. original sealed terminal and usage recover
      with zero provider/catalog calls before product publication. shared N017.
- [ ] **A7.12** parked input remains excluded until explicit operator repair under the
      deployment lock or stopped service. release names exact message IDs and
      preserves historical attempt/effect evidence; it is unavailable to Discord
      and model roles. native configuration blockers are canonical request state.
- [ ] **A7.13** An isolated first-SIGINT test during startup and an in-flight
      worker query exits with the existing operator-stop status 130, without
      invalidating the ownership connection, and a successor acquires its lock.
      Idle shutdown starts no delivery query. Admission closes for ready,
      message, and approval callbacks; admitted callbacks drain before client
      closure. An already-dispatched approved write records its durable result
      before exit, while an approval waiting for execution remains recoverable
      without entering its executor. Genuine owner loss still blocks publication.
      Forced termination at the existing systemd deadline is a recovery case,
      not a pass for this graceful-shutdown criterion.

## A8. End-to-end memory scenario

required scenario:

1. The owner states a durable preference and discusses a matter linked to Gmail
   and Calendar.
2. jarvis responds; canonical originals project into the admitted archive/tree.
3. the top-level provider lease is discarded.
4. compression builds the historical view; dreaming may append attributed notes.
5. in a fresh turn, the owner refers to the matter indirectly.
6. main receives the fixed historical view and can retrieve/open original evidence.
7. Jarvis reads live Gmail or Calendar state where current truth matters.
8. Jarvis produces a useful response or draft without requiring repeated context.

## A9. Personal acceptance

After at least seven days, the owner affirms:

- [ ] **A9.1** Natural conversation is preferable to command-oriented use.
- [ ] **A9.2** Memory saved repeated explanation on multiple occasions.
- [ ] **A9.3** Irrelevant recall was not routinely distracting.
- [ ] **A9.4** Automatic calendar and draft work did not feel like babysitting.
- [ ] **A9.5** Email approval was accurate and not burdensome.
- [ ] **A9.6** The single Discord channel remained usable and Jarvis did not
      create notification noise sufficient to justify multiple channels or
      threads.
- [ ] **A9.7** At least one interaction connected remembered context and live
      service state into meaningful cognitive offloading.

## Acceptance report

The report records:

- Git revision and dependency-lock digest.
- Kernel revision/conformance result plus Codex server/TUI/runtime/model and prompt
  digests.
- in-process native reuse, input delivery/control, fresh reasoning recovery and
  zero-provider sealed-terminal local settlement.
- exact native/isolated requests, separate contained host/startup qualification,
  kernel base-instruction identity, native-authority/unknown-event fail-stop, upgraded
  `llm-tools` public-seam qualification, action/schedule-recorder mapping,
  AutomaticWriteGate isolation/adversarial results, and multi-run
  owner/control/recovery results.
- Embedding model, dimension, key restriction test, and disclosed processor.
- Results by criterion ID and behavioral trial counts.
- Integration operations and credential ownership.
- Signed Slice 0 qualification report revision.
- Recall scores before and after rebuild.
- Explicit no-backup risk acceptance and absence of backup authority.
- Known limitations, explicit waivers, and owner sign-off.

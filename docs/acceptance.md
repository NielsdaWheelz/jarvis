# V1 acceptance specification

V1 is accepted only when the mandatory criteria below pass on the intended Linux
deployment. Tests use synthetic or redacted fixtures unless marked **live**.

Behavioral tests run five times. Safety behaviors must pass five of five; quality
behaviors pass at least four of five. The test implementation, not this document,
owns exact prompts and fixtures so they can evolve without expanding the product
specification.

Every result appears in a dated acceptance report. Any owner-approved waiver is
named explicitly; no criterion disappears or is weakened silently.

## A1. Repository and deployment

- [ ] **A1.1** The existing Hetzner `dev-server` runs Jarvis from an immutable
      host-native release under a dedicated `jarvis` account using Python 3.12
      and a reproducible lockfile. Jarvis opens no public listener, is not owned
      by rootless Docker, and the Nexus production host and application state
      remain untouched.
- [ ] **A1.2** `llm-agent-kernel`, `provider-runtime`, and `llm-tools` use
      qualified pinned git revisions, not the user's mutable local worktrees.
- [ ] **A1.3** A clean checkout can be configured without modifying Ariel,
      `llm-agent-kernel`, `llm-calling`, or `llm-tools`.
- [ ] **A1.4** Migrations from an empty PostgreSQL database produce exactly the
      six Jarvis application tables and exact application-column rosters in the
      specification.
- [ ] **A1.5** Unit, integration, and pinned `llm-agent-kernel` conformance tests
      run through one documented command.
- [ ] **A1.6** Secrets are absent from the repository, fixtures, PostgreSQL, model
      context, and ordinary logs.
- [ ] **A1.7** A second Jarvis instance against the same deployment refuses to
      start while the first holds the ownership lock.
- [ ] **A1.8** Startup refuses mismatched pinned kernel, provider-runtime,
      `llm-tools`, Codex host mapping/version, or kernel base-instruction identity.
- [x] **A1.9** A dated Slice 0 qualification report records the exact tool
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
- [ ] **A2.6** `stop` or `pause` immediately signals the active cancellation
      token, settles the interrupted/control inputs with a host-authored stopped
      conclusion at the next safe boundary, and pauses tools, actions,
      proactivity, and dreaming without a model call. `resume` restores
      operation; the flag survives restart. A committed external effect is
      reconciled rather than falsely undone.
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
- [ ] **A2.10** Consecutive owner turns reuse one native main Codex session; an
      ordinary restart or compatible deployment resumes it; a changed
      agent-definition fingerprint, deleted reference, invalid reference, or
      resume failure starts a fresh session through the kernel ports and
      reconstructs useful context from centralized messages and recalled memory.
      A stale session-reference generation cannot overwrite a newer one or
      proceed to dispatch/settlement. A successful store advances the expected
      generation. A crash
      after reference advancement but before canonical settlement leaves the
      input unprocessed and forces that speculative reference to be discarded
      before replay. Every definition has a non-empty manifest-derived
      `session_compatibility_revision`; changing its application contract,
      selected role contract, or a pinned dependency rotates the fingerprint,
      except that ADR 0027's exact atomic kernel/provider usage-fix pair and ADR
      0035's containment pair retain their certified predecessor application
      identity. The latter still rotates every definition fingerprint through
      the kernel base-instruction identity. Qualified-model membership is not a
      revision input because the selected model independently participates in
      the agent-definition fingerprint.
- [ ] **A2.11** The host promptly shows typing state; no partial structured model
      output is streamed into Discord. Active Main has no `say` terminal and
      returns one closed structured `answered | partial | needs_input | failed |
      silent` result. The host renders it deterministically. There is no
      in-progress variant, and an incomplete Calendar observation promotes
      `answered` or `silent` to a visible partial response. A deterministic
      threaded tool-loop, action-suspension, host-input fallback, settlement,
      restart, and cold-bootstrap proof passes. One paid production prompt
      produces useful final content with no unsupported continuation or later
      phantom message.
- [ ] **A2.12** `processed_at` is set only with a durable turn conclusion. Claims
      are non-empty and contain a host-selected plan. Compatible owner input
      arriving mid-loop is polled and appears exactly once before the next
      provider/tool boundary; scheduled-wake input remains unclaimed under an
      interactive plan. Stop preempts. Ordinary input arriving after the final
      poll retains the current valid answer and runs next. Startup scans null
      `processed_at` rows only when `processing_parked_at` is null. Cleanup
      release never arms a successor. Configuration parking atomically stamps
      the claimed batch, opens the cognitive circuit, and survives restart until
      explicit operator repair clears it.
- [ ] **A2.13** Jarvis product context selection supplies plain canonical data to
      the kernel bootstrap and continuation ports. A fake stateless adapter
      consumes the bootstrap without provider-private transport types; `llm-tools` typed prompt
      sections preserve the current owner message exactly once and one
      host-supplied `as_of` per admitted batch; stable material includes the
      owner timezone before dynamic time; tool/protocol continuation does not
      repeat the current batch;
      continuation does not resend completed history or the stable timezone.
- [ ] **A2.14** Settlement writes the same run ID, through-checkpoint, nullable
      conclusion-message ID, and conclusion kind/outcome into bounded trace on
      every consumed waking row. A write proposed after mid-loop input stores
      immutable claim/checkpoint/ordered-input/model-step lineage, and recovery
      closes exactly those admitted inputs rather than relying on
      `origin_message_id` alone.

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

- [ ] **A4.1** Every cognitive role runs through `llm-agent-kernel` and
      authenticates through subscription-backed Codex with no generative API-key
      or provider fallback. The main definition is `continuing`; recaller,
      rememberer, dreamer, and AutomaticWriteGate definitions are isolated
      one-shot runs, always open fresh, and never touch an input-checkpoint or
      saved-session port. Active Main and every internal role have closed
      structured result schemas. Recall/remember/dream roles have memory-read
      maximum envelopes; AutomaticWriteGate has an empty envelope. Every run
      plan is publicly proven internally consistent with its exact catalog view
      and to tighten its definition envelope in full; internal plans contain no
      `ToolEffect.Write` and the scheduled-wake main plan is read-only. A
      plan-aware factory creates a fresh `BudgetState` only after plan
      validation, with limits exactly equal to the selected plan's
      `profile.run_limits`; mismatch reaches no rendering, admission, provider,
      or tool I/O.
- [ ] **A4.2 — live.** The embedding key succeeds on the configured embedding
      endpoint and is denied on a generative endpoint.
- [ ] **A4.3** Codex cognition receives no connector, Brave, Discord, Maps,
      embedding, database, Google OAuth, or connector-encryption credential.
      Production root-owned mode-0600 environment files remain unreadable to
      `jarvis`; its non-dumpable parent environment remains protected. The
      host-owned Personal App Server retains only its development-account Codex
      state. A dedicated local group grants socket access and traversal of empty
      cognition directories, not Jarvis application state.
- [ ] **A4.4** The real `AgentRuntime` request uses `JsonSchemaAgentOutput`, an
      empty non-secret mode-0750 group-readable/traversable read-only cwd containing no repository source, no additional
      directories, disabled network, denied approval, empty copied environment,
      no MCP, disabled native built-ins/Web, and only the SDK-required
      `allowed_tools=("*",)` sentinel.
- [ ] **A4.5** The kernel accepts exactly `say | call_tool | finish`. It rejects
      unknown fields and validates the whole step, output contract, frozen
      binding, and pure arguments before output or dispatch. `call_tool` has one
      tool, executes serially, and accepts no prose, model call/effect ID,
      preview, authority, approval, or delivery field. A conversational kernel
      consumer may use `say` only after observing an outcome; Jarvis Main instead
      accepts only a schema-valid structured `finish.result` and rejects `say`.
      Its Codex wire schema has one closed object root, four required envelope
      fields, nullable unselected branches, and only closed nested objects.
      JSON-string tool arguments reject duplicate keys, non-JSON numeric
      constants, and non-object roots before independent logical and
      `llm-tools` validation.
      Unsupported structured-result schemas fail before provider I/O. No
      parallel or multi-call path exists.
- [ ] **A4.6** The production adapter consumes `AgentRuntime.stream_turn` over
      a declared WebSocket dependency and the profile-selected host-owned App
      Server Unix socket, and never calls its
      event-discarding `run_turn` convenience projection. The retained custom
      `exec` incident, every audited native authority class, and denied server
      requests normalize to `AgentToolUse` or `AgentPermissionRequest`; either
      fails and discards the session with no accepted terminal or host dispatch.
      Unknown requests/items/notifications, malformed identity, or a terminal
      after authority activity is a fatal `ProtocolDefect`. Only the explicit
      bounded/redacted inert `AgentNative` whitelist survives. Streaming
      `AgentText` is never executable or delivered.
- [ ] **A4.7** `KernelLimits` bound provider turns, repairs, cooperative time at
      safe boundaries, reported usage, and cumulative newly rendered kernel
      context bytes. Provider turns receive the remaining cooperative deadline;
      a slow host port may exceed it, and no blunt outer timeout interrupts a
      `Write`. Tests separately bound provider system/developer material,
      output-schema overhead, retained native history, and compaction because
      `max_new_context_bytes` does not. `llm_tools.RunLimits` alone bound tool
      calls, attempts, bytes, `max_in_flight=1`, and tool elapsed time. An
      intentional loop stops without double-charging a tool replay, and
      cancellation leaves its product checkpoint recoverable.
- [ ] **A4.8** Quota exhaustion produces a fixed host-authored notice and changes
      no provider, model, or credential.
- [ ] **A4.9** Reads create no action rows; every `Write` creates one action
      before executor entry with immutable arguments/execution contract and uses
      `action.id` as both `InvocationPosition` and `EffectId`.
- [ ] **A4.10** Canonical message, raw-memory, and summary transactions create no
      action rows.
- [ ] **A4.11** Definition maximum envelopes equal the SPEC section 7.3 catalog
      by role, and every frozen run plan is proven internally consistent with
      its exact published catalog view and to tighten its envelope in full.
      Cross-catalog effect, schema, handler-implementation, replay-policy, and
      revision substitutions fail before rendering or I/O. Every binding has
      the non-empty owner-controlled implementation revision required by SPEC
      section 7.3, and HostTable/action evidence carries it. Owner-input and
      action-resolution main runs receive the full Main plan; scheduled-wake
      runs receive only the
      catalogued external reads; internal one-shots receive exactly the two
      memory reads. No plan grants `tool.search`, `tool.read`,
      local-filesystem, Gmail organization, Discord, general delegation, program
      execution, or another unlisted tool. The kernel neither discovers tools
      nor classifies product authority.
      Calendar discovery v1, aggregate list v6, and get v2 publish their exact
      output contracts and binding implementations: every compact normal list
      item has a required direct timed/all-day/unspecified tagged end. The
      affected catalogs, maximum and selected profiles, plans, HostTables, Main
      definition fingerprint, and terminal contract are newly frozen; an older
      continuing session cold-bootstraps without a second compatibility bump for
      the v6 binding alone. Read/scheduled, Slice 5, and active Main selected
      aggregate output limits are respectively 786,432, 1,249,280, and
      1,708,032 bytes; Slice 2 and active Main maximum output limits are
      1,638,400 and 2,166,784 bytes, and the Slice 2 new-context limit is
      706,144 bytes.
- [ ] **A4.12** Pure `llm-tools` input validation touches no recorder, position,
      executor, or tool budget. A completed dispatch returns one bounded
      `ToolResult`; approval or reconciliation returns one durable suspension.
      Later resolution includes the action reference, tool, original validated
      arguments, resolved state, and safe evidence without provider history.
- [ ] **A4.13** Active Jarvis cognition turns and Jarvis host-tool dispatches are serialized.
      AutomaticWriteGate can run only while its main parent is paused at the
      dispatch boundary, uses a child allowance included in the root admission
      reservation, and never overlaps another provider call.
- [ ] **A4.14 — live.** The compatibility manifest records the exact qualified
      ChatGPT-local-account model IDs without fixing their count. Configuration
      accepts `gpt-5.6-terra` and rejects retired `gpt-5.4` before ingress,
      admission, provider I/O, or tool I/O. Every recorded route runs the paid
      consumer probes against the exact release code and lock, and at least one
      route currently supported by the provider passes.
- [ ] **A4.15** Every definition fingerprints the exact qualified kernel base
      instruction and every provider request contains it before separate Jarvis
      role material. Its bytes count toward the provider-system ceiling. The
      containment dependency upgrade cold-bootstraps old fingerprints while
      preserving the application `session_compatibility_revision`. A live
      adversarial shell/exec probe causes zero host effect; any observed
      authority event yields only the truthful host-authored runtime-failure
      response.
- [ ] **A4.16** Main exposes exactly `codex.list`, `codex.read`, `codex.start`,
      `codex.prompt`, and `codex.interrupt` in addition to the existing catalog;
      scheduled and internal roles expose none. Inputs reject unknown fields,
      invalid profiles, malformed handles, generic cognition targets, and
      oversize content before host I/O. The host rejects out-of-root cwd before
      native creation; native exact-Steer rejects stale turns before steering.
      Start first resolves an existing canonical permitted cwd through the
      closed host helper, then creates one prompt-free native thread,
      unsubscribes Jarvis, creates and observes one exact ordinary tmux session,
      and performs native Submit. Launch revalidates the exact cwd.
      `Started` does not claim asynchronous TUI attachment or worker completion.
      Submit truthfully means start-or-steer. Interrupt reports the observed
      Interrupted, natural Finished, Stale, or Unknown outcome without retry.
      Worker approvals receive no Jarvis response. Every mutation is BilledOnce
      with one executor entry; Partial/Unknown retain the exact surviving prefix,
      and cancellation/restart/original-input reconsideration never redispatches
      an ambiguous effect. Workers run independently without entering the
      cognition decoder or adding a fifth table.

## A5. Memory

- [ ] **A5.1** Recall runs before every owner-authored human input and begins with
      exactly one kernel-dispatched deterministic `memory.search` typed
      observation before adaptive recaller search/open. The isolated recaller may
      correctly return an empty schema-valid bundle through its one-shot terminal
      result.
- [ ] **A5.2** Full-text search finds an exact or rare-keyword memory.
- [ ] **A5.3** Semantic search finds relevant memory with no important shared
      query keyword.
- [ ] **A5.4** Search covers raw memories and summaries, deduplicates only exact
      row identities, and permits a summary and its raw source to coexist.
- [ ] **A5.5** The recaller may issue multiple searches and open a summary's raw
      sources.
- [ ] **A5.6** The rememberer runs once per settled input group containing owner
      messages after an `answered`, `partial`, `needs_input`, `failed`, or
      `silent` terminal, or an approval proposal. It receives every
      consumed owner message plus persisted response/tool context and returns a
      schema-valid isolated one-shot result even when it chooses no memory.
- [ ] **A5.7** A successful zero-memory result sets `remembered_at` on every
      consumed owner row; a cancelled run leaves all targets null. A bounded
      sweep retries only completed `role = owner` rows, normally grouping by
      shared settlement trace and falling back to individual rows when grouping
      metadata is absent. Host inputs are never targets.
- [ ] **A5.8** Raw memories and every target `remembered_at` commit atomically and
      create no action row or duplicate storage elsewhere.
- [ ] **A5.9** Under the application role, raw text/time updates, deletes, and
      truncation fail while embedding updates succeed.
- [ ] **A5.10** A useful preference is recalled in a fresh provider session and a
      linked external resource can be reopened.
- [ ] **A5.11** An unmistakable private-key or known API-token fixture is rejected
      before memory insertion without leaking the value in diagnostics.
- [ ] **A5.12** Memory text asserting permission or standing approval cannot alter
      host action classification. Safety behavior, five of five.
- [ ] **A5.13** Every summary has non-empty valid raw lineage; summary-of-summary
      lineage is flattened.
- [ ] **A5.14** The dreamer changes summaries but cannot change raw memory or use
      external tools; its mutation batch is a schema-valid isolated one-shot
      result applied only by host code.
- [ ] **A5.15** Wiping summaries and embeddings leaves lexical raw recall working;
      complete rebuild restores a recall-evaluation result no worse than before.
- [ ] **A5.16** The checked-in recall set has at least fifteen cases with the lane
      coverage required by the memory specification.

## A6. Automatic actions and approval

These criteria are **live** where they call Gmail or Discord.

- [ ] **A6.1** Catalogued reads and ordinary responses or requested wake notices
      in the configured Discord channel execute automatically. Email drafts,
      verified owner-only no-attendee calendar work, and `schedule.wake` execute
      automatically after the required owner-grounding gate. Discord transport
      operations create no action rows.
- [ ] **A6.2** An email send becomes `awaiting_approval` and does not send before
      the owner clicks Approve.
- [ ] **A6.3** The model step and action schema have no approval preview field.
- [ ] **A6.4** Host rendering displays the real stored recipients, subject, and
      complete body for email, and the real calendar, attendees, title,
      description, location, start/end/timezone, recurrence, reminders, and
      notification choice for calendar changes, even when model commentary
      describes something else. Safety behavior, five of five.
- [ ] **A6.5** Every supported approval has one bounded host-generated UTF-8 text
      attachment containing the action ID, canonical tool name, and exact
      validated stored arguments. A long body remains complete and approvable as
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
      re-executes and does not block a later identical new action.
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
      arguments, state, and safe evidence rather than a model call ID. A silent
      `finish` or model failure instead persists a
      deterministic visible fallback; asynchronous action results are never
      consumed without an owner notice.
- [ ] **A6.15** The action table has exactly the columns in SPEC section 9 and the
      seven statuses in section 5.4; canonical `tool_name`, `arguments`,
      `execution_contract`, and `origin_message_id` cannot change after
      insertion. The closed contract records the exact tool-contract,
      implementation, policy, and plan revisions, effect/replay declarations,
      input digest, finite attempt ceiling, claim ID, through-checkpoint,
      model-step ordinal, ordered admitted input IDs, and gate-supporting owner
      IDs for the occupied position. Stored arguments and contract are
      revalidated before rendering, execution, replay, or reconciliation;
      unsupported or invalid non-executing work is cancelled and reported.
- [ ] **A6.16** `schedule.wake` creates an exact due wake and cancels a named
      queued wake. A requested wake becomes eligible at its stored instant and
      after restart when overdue. Claiming it creates exactly one host input from
      the immutable stored instruction and requested instant; it does not invoke
      the owner-input recaller. The visible model result or deterministic
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
      Jarvis state; backup remains addable later without changing the six-table
      application schema.
- [ ] **A7.2** The acceptance report records the production host, release commit,
      Python, PostgreSQL, pgvector, and running-kernel identities; UTC state;
      loopback database binding; root-only environment files; non-dumpable
      parent and systemd `/proc`/resource controls; process restart recovery;
      and the deferred newer-kernel reboot. Deployment does
      not interrupt the owner's tmux sessions or live Codex processes.
- [ ] **A7.3** Derived summaries and embeddings can be completely regenerated
      from the preserved local raw memory log.
- [ ] **A7.4** After process restart, `succeeded`, `failed`, `uncertain`, and
      `cancelled` actions do not become executable; `executing` actions reconcile
      before any evidence-proven repeat.
- [ ] **A7.5** Jarvis resumes Discord operation, boundedly catches up owner input,
      and retries pending assistant rows with null `source_message_id` after
      restart using the deterministic enforced nonce and the finite delivery
      retry/backoff policy, with the accepted possibility of a rare repeated
      ordinary response after delayed ambiguous acknowledgement. It resumes a
      configuration-compatible main session when possible and cold bootstraps
      from canonical context when not.
- [ ] **A7.6** PostgreSQL contains no usable Google, Discord, Codex, Brave, Maps,
      embedding, PostgreSQL, or connector-encryption credential and no
      disposable provider state.
- [ ] **A7.7** Ordinary logs and checked-in transcripts contain no real private
      message, email body, memory text, or secret.
- [ ] **A7.8** Protocol, run-budget, quota, explicit-stop, and repeated-provider
      exhaustion persist a host-authored stopped conclusion, consume the poison
      input, and cause zero automatic successor runs. Simulated process crashes
      increment `processing_attempts`; the configured ceiling stops the row
      before another provider call rather than silently renewing work.
- [ ] **A7.9** A host-issued rolling admission check occurs before every
      cognitive provider invocation. Before I/O, the content-free journal
      durably reserves one root slot plus finite maximum root/serial-child turns
      and configured normalized tokens. Clean exits settle actual usage and
      refund unused capacity; quota and ordinary failures do likewise. The
      six-hour ceiling contains two complete worst-case foreground envelopes
      plus one Rememberer allowance, and a normally settled production turn
      does not prevent the next full reservation. A corrupt journal fails
      closed. A configuration or plan-budget defect calls the
      checkpoint park transaction, stamps `processing_parked_at` on the claimed
      unprocessed batch, and starts no new cognitive work.
- [ ] **A7.10** Multi-run race fixtures cover mid-loop compatible input, stop
      preemption, ordinary follow-up during finalization, suspension/resolution,
      startup recovery, session-ref CAS, poison input, and admission. Passing
      single-run kernel tests alone is insufficient.
- [ ] **A7.11** Killing the process after admission reservation leaves the full
      turn/token reservation charged. Startup under the exclusive deployment
      lock marks it interrupted and releases only its concurrency slot. Admission
      preflight denial performs no provider I/O and does not claim or increment
      an input. After successful preflight, claim atomically increments
      `processing_attempts`; a later inconsistent capacity result raises
      `AdmissionStateDefect` and parks the claim. Owner/action-resolution work
      becomes eligible at reset, with one deterministic assistant notice for
      delays of at least 60 seconds, while background memory work defers
      silently.
- [ ] **A7.12** A process killed after durable parking cannot reclaim the row on
      restart. Any parked row opens the single cognitive circuit while delivery
      and operator repair remain available. Only the documented operator repair
      path clears `processing_parked_at`, after which the corrected input becomes
      claimable without resetting its attempt history. Release is unavailable
      to Discord and every model role, names explicit message IDs, and runs only
      with the service stopped or under the deployment ownership lock.

## A8. End-to-end memory scenario

The following scenario passes:

1. The owner states a durable preference and discusses a matter linked to Gmail
   and Calendar.
2. Jarvis responds and the rememberer appends useful raw memory.
3. The provider session is discarded.
4. The dreamer creates a grounded summary.
5. In a new conversation, the owner refers to the matter indirectly.
6. The recaller locates relevant summary/raw memory and can open its raw basis.
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
- Main-session continuation, compatible resume, and lost-session bootstrap
  results.
- Exact AgentRuntime request, shared App Server transport classification,
  kernel base-instruction identity, native-authority/unknown-event fail-stop, upgraded
  `llm-tools` public-seam qualification, action/schedule-recorder mapping,
  AutomaticWriteGate isolation/adversarial results, and multi-run
  admission/crash/poison results.
- Embedding model, dimension, key restriction test, and disclosed processor.
- Results by criterion ID and behavioral trial counts.
- Integration operations and credential ownership.
- Signed Slice 0 qualification report revision.
- Recall scores before and after rebuild.
- Explicit no-backup risk acceptance and absence of backup authority.
- Known limitations, explicit waivers, and owner sign-off.

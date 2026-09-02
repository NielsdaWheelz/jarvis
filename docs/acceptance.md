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

- [ ] **A1.1** The server uses Python 3.12 with a reproducible lockfile.
- [ ] **A1.2** `llm-agent-kernel`, `provider-runtime`, and `llm-tools` use
      qualified pinned git revisions, not the user's mutable local worktrees.
- [ ] **A1.3** A clean checkout can be configured without modifying Ariel,
      `llm-agent-kernel`, `llm-calling`, or `llm-tools`.
- [ ] **A1.4** Migrations from an empty PostgreSQL database produce exactly the
      four Jarvis application tables and exact application-column rosters in the
      specification.
- [ ] **A1.5** Unit, integration, and pinned `llm-agent-kernel` conformance tests
      run through one documented command.
- [ ] **A1.6** Secrets are absent from the repository, fixtures, PostgreSQL, model
      context, and ordinary logs.
- [ ] **A1.7** A second Jarvis instance against the same deployment refuses to
      start while the first holds the ownership lock.
- [ ] **A1.8** Startup refuses mismatched pinned kernel, Codex SDK, or runtime
      versions.
- [ ] **A1.9** A dated Slice 0 qualification report records the exact tool
      manifest and schemas, live authority classification, credential
      ownership/handoff, Discord nonce/history behavior, Calendar ACL/client-ID
      behavior, Gmail send reconciliation, Web canaries, kernel port/conformance
      qualification against the real AgentRuntime API, the upgraded public
      `llm-tools` validation/plan/HostTable/async-recorder seams, and
      credential-containment results; the owner signs it before Slice 1.

## A2. Discord and conversation history

- [ ] **A2.1 — live.** The owner can speak naturally to Jarvis without slash
      commands and receive useful text/Markdown replies.
- [ ] **A2.2 — live.** The effective bot permissions are exactly
      `VIEW_CHANNEL`, `SEND_MESSAGES`, `ATTACH_FILES`, and
      `READ_MESSAGE_HISTORY` in the configured channel. `ADMINISTRATOR`, thread,
      channel-management, message-management, reaction, membership, webhook,
      role, invite, moderation, and `EMBED_LINKS` permissions are absent. Gateway
      intents are exactly `GUILDS`, `GUILD_MESSAGES`, and `MESSAGE_CONTENT`.
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
      receives a `source_message_id` after success or history reconciliation; a
      null ID is the only outbound retry watermark. Its 20-character Discord
      nonce is derived exactly from `message.id` as specified and is not stored.
- [ ] **A2.9 — live.** Every Discord create and retry uses the same nonce with
      `enforce_nonce=true`. Injecting a lost accepted response inside the nonce
      window leaves exactly one visible message. A simulated delayed restart
      outside that window finds the nonce in bounded history and performs no
      second create; an incomplete history check leaves the row pending. Create
      uses the qualified direct REST binding, not a private `discord.py` API.
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
      before replay.
- [ ] **A2.11** The host promptly shows typing state; no partial structured model
      output is streamed into Discord.
- [ ] **A2.12** `processed_at` is set only with a durable turn conclusion. Claims
      are non-empty and contain a host-selected plan. Compatible owner input
      arriving mid-loop is polled and appears exactly once before the next
      provider/tool boundary; scheduled-wake input remains unclaimed under an
      interactive plan. Stop preempts. Ordinary input arriving after the final
      poll retains the current valid answer and runs next. Startup scans null
      `processed_at` rows. Cleanup release never arms a successor.
- [ ] **A2.13** Jarvis product context selection supplies plain canonical data to
      the kernel bootstrap and continuation ports. A fake stateless adapter
      consumes the bootstrap without Codex SDK types; `llm-tools` typed prompt
      sections preserve the current owner message exactly once and one
      host-supplied `as_of` per admitted batch; stable material includes the
      owner timezone before dynamic time; tool/protocol continuation does not
      repeat the current batch;
      continuation does not resend completed history or the stable timezone.

## A3. Existing integrations

These criteria are **live** and use the registrations and credentials qualified
in Slice 0.

- [ ] **A3.1** Jarvis searches and reads a Gmail conversation.
- [ ] **A3.2** Jarvis creates an email draft automatically.
- [ ] **A3.3** Jarvis reads the live calendar.
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
- [ ] **A3.11** No avoidable new Google or Discord registration or authorization
      was required.
- [ ] **A3.12** Every credential has one owning process, and no bot token or
      autonomous mailbox/calendar authority is concurrently shared with Ariel.

## A4. Model and tool boundary

- [ ] **A4.1** Every cognitive role runs through `llm-agent-kernel` and
      authenticates through subscription-backed Codex with no generative API-key
      or provider fallback. The main definition is `continuing`; recaller,
      rememberer, and dreamer definitions are isolated one-shot runs, always
      open fresh, and never touch an input-checkpoint or saved-session port. The
      main output contract is conversational; each internal role has a closed
      structured result schema and a memory-read maximum envelope. Every run plan
      is publicly proven to tighten its definition envelope;
      internal plans contain no `ToolEffect.Write` and the scheduled-wake main
      plan is read-only.
- [ ] **A4.2 — live.** The embedding key succeeds on the configured embedding
      endpoint and is denied on a generative endpoint.
- [ ] **A4.3** Codex receives no connector, Brave, or embedding credential and
      its child environment contains none.
- [ ] **A4.4** The real `AgentRuntime` request uses `JsonSchemaAgentOutput`, a
      private empty read-only cwd containing no repository source, no additional
      directories, disabled network, denied approval, empty copied environment,
      no MCP, disabled native built-ins/Web, and only the SDK-required
      `allowed_tools=("*",)` sentinel.
- [ ] **A4.5** The kernel accepts exactly `say | call_tool | finish`. It rejects
      unknown fields and validates the whole step, output contract, frozen
      binding, and pure arguments before output or dispatch. `call_tool` has one
      tool, executes serially, and accepts no prose, model call/effect ID,
      preview, authority, approval, or delivery field. A separate `say` may
      describe only an observed outcome. Structured roles accept only a
      schema-valid `finish.result`; the main role rejects terminal result
      payloads. No parallel or multi-call path exists.
- [ ] **A4.6** A scripted `AgentToolUse` or `AgentPermissionRequest` event fails
      and discards the confined session with no host dispatch or conclusion,
      while a scripted native reasoning passthrough event does not. Streaming
      `AgentText` is never delivered.
- [ ] **A4.7** `KernelLimits` bound provider turns, repairs, wall time, reported
      usage, and cumulative visible context; `llm_tools.RunLimits` alone bound
      tool calls, attempts, bytes, `max_in_flight=1`, and tool elapsed time. An
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
      by role, and every frozen run plan tightens its envelope. Owner-input and
      action-resolution main runs receive the full Main plan; scheduled-wake
      runs receive only the catalogued external reads; internal one-shots receive
      exactly the two memory reads. No plan grants `tool.search`, `tool.read`,
      local-filesystem, Gmail organization, Discord, delegation, program
      execution, or another unlisted tool. The kernel neither discovers tools
      nor classifies product authority.
- [ ] **A4.12** Pure `llm-tools` input validation touches no recorder, position,
      executor, or tool budget. A completed dispatch returns one bounded
      `ToolResult`; approval or reconciliation returns one durable suspension.
      Later resolution includes the action reference, tool, original validated
      arguments, resolved state, and safe evidence without provider history.

## A5. Memory

- [ ] **A5.1** The recaller runs before every owner-authored human input and may
      correctly return an empty schema-valid bundle through its isolated
      one-shot terminal result.
- [ ] **A5.2** Full-text search finds an exact or rare-keyword memory.
- [ ] **A5.3** Semantic search finds relevant memory with no important shared
      query keyword.
- [ ] **A5.4** Search covers raw memories and summaries, deduplicates only exact
      row identities, and permits a summary and its raw source to coexist.
- [ ] **A5.5** The recaller may issue multiple searches and open a summary's raw
      sources.
- [ ] **A5.6** The rememberer runs after `say`, `finish`, and approval-proposal
      turns, returning a schema-valid isolated one-shot result even when it
      chooses to write no memory.
- [ ] **A5.7** A successful zero-memory result sets `remembered_at`; a cancelled
      run leaves it null, and a bounded sweep retries only `role = owner` rows
      with non-null `processed_at` and null `remembered_at`; host inputs are never
      selected.
- [ ] **A5.8** Raw memories and `remembered_at` commit atomically and create no
      action row or duplicate storage elsewhere.
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

- [ ] **A6.1** Catalogued reads, email drafts, verified owner-only no-attendee
      calendar work, `schedule_wake`, and ordinary responses or requested wake
      notices in the configured Discord channel execute automatically. Discord
      transport operations create no action rows.
- [ ] **A6.2** An email send becomes `awaiting_approval` and does not send before
      the owner clicks Approve.
- [ ] **A6.3** The model step and action schema have no approval preview field.
- [ ] **A6.4** Host rendering displays the real stored recipients, subject, and
      complete body for email, and the real calendar, attendees, time, title,
      and recurrence for calendar changes, even when model commentary describes
      something else. Safety behavior, five of five.
- [ ] **A6.5** A long body is shown through host-owned split messages or an
      attachment and remains approvable as one exact action.
- [ ] **A6.6** An approval-bearing tool without a host renderer fails closed.
- [ ] **A6.7** The component interaction is acknowledged and disabled before slow
      external work begins.
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
      entry but authorizes nothing. A timeout alone authorizes neither retry nor
      `uncertain`.
- [ ] **A6.12** Only an outcome still unknowable after bounded automatic
      reconciliation becomes terminal `uncertain`. Jarvis presents its evidence
      and asks the owner to inspect provider state; it never automatically
      re-executes and does not block a later identical new action.
- [ ] **A6.13 — live.** An approved email produces exactly one recipient copy,
      including an injected ambiguous-timeout test reconciled through the Gmail
      draft/Sent behavior.
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
      insertion. The closed contract records the exact tool/policy/plan
      revisions, effect/replay declarations, and input digest for the occupied
      position. Stored arguments and contract are revalidated before rendering,
      execution, replay, or reconciliation; unsupported or invalid non-executing
      work is cancelled and reported.
- [ ] **A6.16** `schedule_wake` creates an exact due wake and cancels a named
      queued wake. A requested wake becomes eligible at its stored instant and
      after restart when overdue. Claiming it creates exactly one host input from
      the immutable stored instruction and requested instant; it does not invoke
      the owner-input recaller. The visible model result or deterministic
      fallback marks the wake succeeded atomically. No generic quiet-hours
      transform, periodic connector turn, or autonomous inbox/calendar monitor
      is configured.
- [ ] **A6.17** Immediately before an approved Gmail send, the live draft must
      match the stored recipient, subject, and complete-body snapshot. A
      mismatch sends nothing, fails the action, and requires a new proposal.

## A7. Recovery and operations

- [ ] **A7.1** A daily encrypted backup includes all four application tables and
      required connector state; at least one copy is off-host.
- [ ] **A7.2** Restore into a clean PostgreSQL instance preserves message IDs,
      raw memory IDs/text/timestamps, and action effects/status/results.
- [ ] **A7.3** Derived summaries and embeddings can be completely regenerated
      after restore.
- [ ] **A7.4** Restored `succeeded`, `failed`, `uncertain`, and `cancelled` actions
      do not become executable; restored `executing` actions reconcile first.
- [ ] **A7.5** Jarvis resumes Discord operation, boundedly catches up owner input,
      and retries pending assistant rows with null `source_message_id` after
      restart using deterministic nonce/history reconciliation. It resumes a
      configuration-compatible main session when possible and cold bootstraps
      from canonical context when not.
- [ ] **A7.6** A database backup contains no usable Google, Discord, Codex,
      Brave, or embedding credential.
- [ ] **A7.7** Ordinary logs and checked-in transcripts contain no real private
      message, email body, memory text, or secret.
- [ ] **A7.8** Protocol, run-budget, quota, explicit-stop, and repeated-provider
      exhaustion persist a host-authored stopped conclusion, consume the poison
      input, and cause zero automatic successor runs. Simulated process crashes
      increment `processing_attempts`; the configured ceiling stops or parks the
      row before another provider call.
- [ ] **A7.9** A host-issued rolling admission check occurs before every
      cognitive provider invocation and bounds turns, available normalized
      tokens, no-progress attempts, and cognitive concurrency at one. Usage settles on success,
      failure, cancellation, and quota exhaustion. A corrupt private admission
      journal fails closed, and a configuration defect parks work rather than
      looping.
- [ ] **A7.10** Multi-run race fixtures cover mid-loop compatible input, stop
      preemption, ordinary follow-up during finalization, suspension/resolution,
      startup recovery, session-ref CAS, poison input, and admission. Passing
      single-run kernel tests alone is insufficient.

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
- Kernel revision/conformance result plus Codex SDK/runtime/model and prompt
  digests.
- Main-session continuation, compatible resume, and lost-session bootstrap
  results.
- Exact AgentRuntime containment request, native-event fail-stop, upgraded
  `llm-tools` public-seam qualification, and multi-run admission/poison results.
- Embedding model, dimension, key restriction test, and disclosed processor.
- Results by criterion ID and behavioral trial counts.
- Integration operations and credential ownership.
- Signed Slice 0 qualification report revision.
- Recall scores before and after rebuild.
- Backup/restore result.
- Known limitations, explicit waivers, and owner sign-off.

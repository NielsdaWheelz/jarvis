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
- [ ] **A1.2** `provider-runtime` and `llm-tools` use qualified pinned git
      revisions, not the user's mutable local worktrees.
- [ ] **A1.3** A clean checkout can be configured without modifying Ariel,
      `llm-calling`, or `llm-tools`.
- [ ] **A1.4** Migrations from an empty PostgreSQL database produce exactly the
      four Jarvis application tables in the specification.
- [ ] **A1.5** Unit and integration tests run through one documented command.
- [ ] **A1.6** Secrets are absent from the repository, fixtures, PostgreSQL, model
      context, and ordinary logs.
- [ ] **A1.7** A second Jarvis instance against the same deployment refuses to
      start while the first holds the ownership lock.
- [ ] **A1.8** Startup refuses mismatched pinned Codex SDK/runtime versions.

## A2. Discord and conversation history

- [ ] **A2.1 — live.** The owner can speak naturally to Jarvis without slash
      commands and receive useful text/Markdown replies.
- [ ] **A2.2 — live.** The effective bot permissions are exactly the eleven
      permissions listed in SPEC section 4.1; `ADMINISTRATOR`, membership,
      webhook, role, invite, and `EMBED_LINKS` permissions are absent.
- [ ] **A2.3** A non-owner cannot start controlled tool work or approve an action.
- [ ] **A2.4** Jarvis can create, rename, and archive a test channel without
      approval but cannot delete it.
- [ ] **A2.5** Approve and Deny are the only custom action components.
- [ ] **A2.6** `stop` pauses tools, actions, proactivity, and dreaming without a
      model call; `resume` restores operation; the flag survives restart.
- [ ] **A2.7** Every inbound owner message is stored before processing and one
      redelivered Discord event starts no second turn.
- [ ] **A2.8** Every assistant response is inserted before Discord delivery and
      receives a source message ID plus `delivered_at` after success.
- [ ] **A2.9** An undelivered assistant row is retried after restart. A duplicate
      conversational message is tolerated, but no tool effect is duplicated.
- [ ] **A2.10** A fresh provider session reconstructs recent context from
      centralized messages and recalled memory.
- [ ] **A2.11** The host acknowledges input and shows typing state; no partial
      structured model output is streamed into Discord.

## A3. Existing integrations

These criteria are **live** and use existing registrations and credentials.

- [ ] **A3.1** Jarvis searches and reads a Gmail conversation.
- [ ] **A3.2** Jarvis creates an email draft automatically.
- [ ] **A3.3** Jarvis reads the live calendar.
- [ ] **A3.4** Jarvis creates, edits, and removes a no-attendee event on a
      verified owner-only calendar without approval.
- [ ] **A3.5** A shared or unknown-ACL calendar write requires approval.
- [ ] **A3.6** Adding or notifying another attendee requires approval.
- [ ] **A3.7** A naive calendar datetime is rejected, and owner-local relative
      time resolves correctly around midnight.
- [ ] **A3.8** Jarvis performs a live Maps/place lookup.
- [ ] **A3.9** No avoidable new Google or Discord registration or authorization
      was required.
- [ ] **A3.10** Every credential has one owning process, and no bot token or
      autonomous mailbox/calendar authority is concurrently shared with Ariel.

## A4. Model and tool boundary

- [ ] **A4.1** Every cognitive role authenticates through subscription-backed
      Codex with no generative API-key or provider fallback.
- [ ] **A4.2 — live.** The embedding key succeeds on the configured embedding
      endpoint and is denied on a generative endpoint.
- [ ] **A4.3** Codex receives no connector or embedding credential and its child
      environment contains none.
- [ ] **A4.4** Codex runs from an empty read-only directory containing no Jarvis,
      Ariel, or sibling repository source, with network disabled and no MCP.
- [ ] **A4.5** Unknown, malformed, or ungranted tool calls fail before integration
      code.
- [ ] **A4.6** A scripted `AgentToolUse` event fails the confined turn while a
      scripted native reasoning passthrough event does not.
- [ ] **A4.7** Tool and turn bounds stop an intentional infinite-loop fixture.
- [ ] **A4.8** Quota exhaustion produces a fixed host-authored notice and changes
      no provider, model, or credential.
- [ ] **A4.9** Reads create no action rows; effectful tool calls create one action
      before execution with a durable effect identity.
- [ ] **A4.10** Canonical message, raw-memory, and summary transactions create no
      action rows.

## A5. Memory

- [ ] **A5.1** The recaller runs before every owner-authored human input and may
      correctly return an empty bundle.
- [ ] **A5.2** Full-text search finds an exact or rare-keyword memory.
- [ ] **A5.3** Semantic search finds relevant memory with no important shared
      query keyword.
- [ ] **A5.4** Search covers raw memories and summaries, deduplicates only exact
      row identities, and permits a summary and its raw source to coexist.
- [ ] **A5.5** The recaller may issue multiple searches and open a summary's raw
      sources.
- [ ] **A5.6** The rememberer runs after `say`, `finish`, and approval-proposal
      turns, including when it chooses to write no memory.
- [ ] **A5.7** A successful zero-memory result sets `remembered_at`; a cancelled
      run leaves it null and a bounded sweep retries it.
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
      external tools.
- [ ] **A5.15** Wiping summaries and embeddings leaves lexical raw recall working;
      complete rebuild restores a recall-evaluation result no worse than before.
- [ ] **A5.16** The checked-in recall set has at least fifteen cases with the lane
      coverage required by the memory specification.

## A6. Automatic actions and approval

These criteria are **live** where they call Gmail or Discord.

- [ ] **A6.1** Reads, local writes, personal calendar work, drafts, and permitted
      Discord organization execute automatically.
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
- [ ] **A6.9** Deny prevents send; Approve by the owner sends the exact stored
      draft; a non-owner or mismatched guild/channel cannot decide it.
- [ ] **A6.10** Duplicate Approve interactions and repeated active intents produce
      no duplicate external effect.
- [ ] **A6.11** A process killed around dispatch is reconciled before retry and
      leaves no permanently executing row.
- [ ] **A6.12** A genuinely unknowable outcome becomes terminal `uncertain`, is
      reported, and does not block a later identical new action.
- [ ] **A6.13 — live.** An approved email produces exactly one recipient copy,
      including an injected ambiguous-timeout test reconciled through the Gmail
      draft/Sent behavior.
- [ ] **A6.14** External success is reported only from provider or reconciliation
      evidence, never a model assertion.

## A7. Recovery and operations

- [ ] **A7.1** A daily encrypted backup includes all four application tables and
      required connector state; at least one copy is off-host.
- [ ] **A7.2** Restore into a clean PostgreSQL instance preserves message IDs,
      raw memory IDs/text/timestamps, and action effects/status/results.
- [ ] **A7.3** Derived summaries and embeddings can be completely regenerated
      after restore.
- [ ] **A7.4** Restored completed, denied, expired, superseded, and uncertain
      actions do not become executable.
- [ ] **A7.5** Jarvis resumes Discord operation and retries pending assistant
      delivery after restart.
- [ ] **A7.6** A database backup contains no usable Google, Discord, Codex, or
      embedding credential.
- [ ] **A7.7** Ordinary logs and checked-in transcripts contain no real private
      message, email body, memory text, or secret.

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
- [ ] **A9.4** Automatic calendar and local work did not feel like babysitting.
- [ ] **A9.5** Email approval was accurate and not burdensome.
- [ ] **A9.6** Jarvis did not create gratuitous Discord structure or notification
      noise.
- [ ] **A9.7** At least one interaction connected remembered context and live
      service state into meaningful cognitive offloading.

## Acceptance report

The report records:

- Git revision and dependency-lock digest.
- Codex SDK/runtime/model and prompt digests.
- Embedding model, dimension, key restriction test, and disclosed processor.
- Results by criterion ID and behavioral trial counts.
- Integration operations and credential ownership.
- Recall scores before and after rebuild.
- Backup/restore result.
- Known limitations, explicit waivers, and owner sign-off.

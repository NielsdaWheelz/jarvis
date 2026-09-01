# V1 acceptance specification

V1 is accepted only when all mandatory criteria below pass on the intended Linux
deployment. Tests may use recorded connector fixtures unless a criterion
explicitly requires a live personal integration.

## 1. Repository and build

- [ ] The server is Python 3.12 and has a reproducible locked environment.
- [ ] `provider-runtime` and `llm-tools` are pinned to qualified revisions.
- [ ] A clean checkout can be configured without modifying Ariel,
      `llm-calling`, or the user's existing `llm-tools` checkout.
- [ ] Unit and integration tests run through one documented command.
- [ ] No rejected v1 workflow, agent, queue, graph, search, or vector framework
      is present as a transitive architectural dependency without an ADR.
- [ ] Secrets can be supplied without appearing in the repository or ordinary
      logs.

## 2. Discord experience

- [ ] The owner can talk to Jarvis naturally in the dedicated Discord server.
- [ ] Jarvis responds with normal Discord text/Markdown without requiring slash
      commands.
- [ ] Jarvis ignores or safely refuses control from a non-owner Discord user.
- [ ] Jarvis can create and organize a test channel without approval.
- [ ] Jarvis can proactively send one useful test message without a preceding
      slash command.
- [ ] Approve and Deny are the only custom action components exposed.
- [ ] Restarting Jarvis does not require recreating the Discord server or bot.

## 3. Existing integrations

These criteria use the user's existing integration registrations and credentials.

- [ ] Jarvis can search/read a live Gmail conversation.
- [ ] Jarvis can create a Gmail draft automatically.
- [ ] Jarvis can read the user's live calendar.
- [ ] Jarvis can create, modify, and remove a personal no-attendee test event
      automatically.
- [ ] Jarvis requires approval before adding or notifying another attendee.
- [ ] Jarvis can perform a live Maps/place lookup.
- [ ] No avoidable new Google or Discord application registration or OAuth grant
      was required.
- [ ] Every exposed integration operation has a closed `llm-tools` declaration
      and validated binding.

## 4. Main agent and tools

- [ ] The main model authenticates through the subscription-backed Codex lane.
- [ ] No provider API-key fallback exists.
- [ ] The main model cannot read connector credentials.
- [ ] The main model cannot write to the Jarvis or Ariel source checkout.
- [ ] Unknown or malformed tool requests are rejected before integration code.
- [ ] A tool result is returned as a typed observation to the model.
- [ ] Turn limits stop an intentional infinite tool-loop fixture.
- [ ] A relevant current-state question uses a live tool rather than memory alone.
- [ ] An unexpected native Codex file/command/tool event fails the confined turn.

## 5. Raw memory

- [ ] The recaller runs before every owner-authored human input.
- [ ] The rememberer runs after every completed meaningful interaction.
- [ ] The rememberer can correctly emit zero memories.
- [ ] A useful explicit preference is appended to `memory_log` and recalled in a
      later fresh provider session.
- [ ] Raw rows remain unchanged after dream and summary rebuild operations.
- [ ] Raw memory may contain and preserve a Gmail, Calendar, Maps, or Discord
      reference in its text.
- [ ] A malformed reference does not prevent search or recall of the memory.
- [ ] A secret-bearing fixture is not persisted as ordinary memory.

## 6. Retrieval

- [ ] Full-text search finds an exact or rare-keyword memory.
- [ ] Semantic search finds a relevant memory that shares no important query
      keyword.
- [ ] The recaller can issue multiple memory searches for one human input.
- [ ] The recaller returns an empty bundle for an unrelated input.
- [ ] The context bundle is bounded and preserves memory IDs and timestamps.
- [ ] Search covers both raw memories and summaries.
- [ ] Recaller failure does not prevent a normal memory-free response.

## 7. Summaries and dreaming

- [ ] Every summary has at least one valid raw source ID.
- [ ] Summary lineage contains raw IDs, never only summary IDs.
- [ ] The recaller can open all raw memories behind a selected summary.
- [ ] A contradiction fixture yields a summary that retains the disagreement.
- [ ] The dreamer cannot mutate or delete `memory_log`.
- [ ] The dreamer has no external-action tools.
- [ ] Deleting all summaries still leaves raw-memory recall functional.
- [ ] Deleting all summaries and embeddings, then rebuilding, restores passing
      recall behavior on the fixed evaluation set.

## 8. Autonomy and approval

- [ ] Reads execute automatically.
- [ ] Local writes execute automatically within the configured Jarvis workspace.
- [ ] Memory append and summary rebuild execute automatically.
- [ ] Personal no-attendee calendar changes execute automatically.
- [ ] Discord server organization executes automatically.
- [ ] An email send is stored and previewed rather than executed immediately.
- [ ] Deny prevents the stored email from being sent.
- [ ] Approve by the owner executes the exact stored email once.
- [ ] Clicking Approve twice does not send a duplicate.
- [ ] Approval by a non-owner does not execute the action.
- [ ] A crash during an ambiguous send does not cause a blind duplicate retry.
- [ ] Success or uncertainty is based on integration evidence, not a model claim.

## 9. Memory-supported interaction scenario

The following live or realistic fixture scenario MUST pass end to end:

1. The owner tells Jarvis a durable preference and discusses an upcoming matter
   linked to an email and calendar event.
2. Jarvis answers naturally and the rememberer appends useful raw memories.
3. The provider session is discarded.
4. Summaries are generated.
5. In a new conversation, the owner refers to the matter indirectly.
6. The recaller finds the relevant summary or raw memories and can open the raw
   basis.
7. Jarvis reads live Gmail or Calendar state as needed.
8. Jarvis produces a useful grounded response or draft without asking the owner
   to repeat the remembered context.

## 10. Rebuild and recovery

- [ ] PostgreSQL backup and restore has been exercised once on a clean instance.
- [ ] Restored raw memory has identical IDs, text, and creation timestamps.
- [ ] Summaries and embeddings can be regenerated after restore.
- [ ] Jarvis resumes Discord operation after a process restart.
- [ ] Pending denied and completed actions do not become pending again.
- [ ] Credentials and private content are absent from ordinary application logs.

## 11. Personal acceptance

Automated tests are necessary but insufficient. The owner must use the deployed
system for at least seven days and affirm:

- [ ] Natural conversation is preferable to the old command-oriented behavior.
- [ ] Recalled memory has saved repeated explanation on multiple occasions.
- [ ] Irrelevant recall is not routinely distracting.
- [ ] Automatic calendar and local actions do not feel like babysitting.
- [ ] Email approval is clear and not burdensome.
- [ ] Jarvis has not created gratuitous Discord structure or notification noise.
- [ ] At least one interaction produced the intended cognitive-offloading effect:
      Jarvis connected remembered context and live service state into useful work.

## 12. Acceptance report

The release candidate MUST include a dated acceptance report containing:

- Git revision and dependency lock digest.
- Codex SDK/runtime/model configuration.
- Test results.
- Integration operations exercised.
- Memory evaluation results before and after rebuild.
- Known limitations.
- Owner sign-off or explicit waived criteria.

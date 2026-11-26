# can jarvis keep ordinary google history?

[citation inspection 0124](../decisions/0124-citations-and-viewer-delivery.md)
adds owner-only replay of retained observations and a bounded passage selector.
include pages, pinned editions and reports derived from workspace reads,
their notes git history, exported drive files and downstream copies. these can
survive grant fences and withdrawal. cover their destinations, backups and
retention before using real workspace material or synthetic fixtures on the
owner's real account.

open. follow-up pr for [connector design 0107](../decisions/0107-google-workspace.md). on november 24 the owner explicitly selected ordinary recording of google reads and answers, for past and future jarvis history. the connector pr may use synthetic examples. real-account use of the replacement waits for an evidenced answer. there is no authorization to change history, backups, model, subscription or cost.

the [revision candidate](../decisions/0121-exact-chat-draft-revisions.md) adds
the verified draft body and envelope to its private action receipt. an
observed provider-added quote can contain third-party text. include that copy
and its backup generations in the retention determination. the receipt
copy stays outside model-facing results.

**what google actually says.** the addendum does not impose a 30-day mailbox limit. §2(a) restricts storage under the existing api policies and processing to active user-authorized tasks. §2(b–c) caps covered technical information at 30 days and limits its processing. the definition expressly excludes user data but names service-derived embeddings, memory indexes, profiles and findings. §2(d) bars retaining either class after the tool is disconnected or access revoked. §2(f) prohibits training, fine-tuning, evaluation-dataset building and distillation with either. the underlying api terms condition permanent copies and certain caching on express content-owner permission or applicable law. mailbox control alone cannot establish that permission for all incoming mail. google's published terms give us no clear authorization for this entire design. they do not establish a blanket retroactive purge either. [addendum](https://workspace.google.com/terms/ai-tools/) · [api terms §5(e)](https://developers.google.com/terms#e_prohibitions_on_content) · [workspace user data policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy) · [effective date](https://developers.google.com/workspace/guides/quota-usage-tiers)

**what needs an answer.** map each actual transfer and use to the governing clause, authorized task, purpose, retention and disconnect behavior: tool results and retry receipts; chat and quoted answers; shared search, stored embeddings, summaries, unrelated later recall, nightly synthesis and recall evaluations; owner-requested saved gmail files in private storage, cache and the existing artifact viewer; transfers to the subscribed inference/embedding providers and their training, telemetry, cache, support and deletion terms. distinguish independently supplied owner content, fetched originals, provider-derived information and mixed records. include the stopped copies, native captures, third-party sessions and all recoverable backups where the observations actually travel. do not copy live mail into evidence. identify the actual consumer account/plan and applicable agreements; use written provider clarification or qualified legal interpretation wherever official text leaves a material gap. [capture and memory](../../SPEC.md#shared-memory-freshness-after-the-private-web-home) · [attachment custody](../attachments-and-durable-originals.md)

the [drive files cut](../decisions/0120-drive-files.md) also needs a determination for drive/docs observations, excerpts, answers, processed copies, developer storage, disconnect and recoverable backups. account separately for the standard human read-only preview and the disposable stopped import. synthetic qualification on the authorized test account keeps real owner content outside this work.

**why it blocks.** ordinary receipts and history are durable. database dumps have a 30-day remote object lock with asynchronous expiry. the verified mac generation may survive longer. no current check proves that disconnection removes these copies. a dashboard setting, no-training selection, local ephemeral thread, alternate google client, encrypted backup with a usable key or an empty search cannot establish the full claim. disabling agent traffic only limits further collection. the effect on previously acquired material remains an independent question. report any conflict with existing applicable policies immediately. [backup custody](../decisions/0088-storage-and-memory-recovery.md)

**exit.** produce a dated, checkable determination for each use and processor, including whether earlier records are covered; give any written permissions their exact scope and term. prove the applicable retention and revocation behavior with synthetic records through actual capture, provider configuration and an isolated restore. record permitted, incompatible or unresolved with owner impact. permission for every necessary use and demonstrated behavior can clear rollout. a negative answer resolves the question and keeps rollout blocked until the owner chooses a different product contract. no answer by february 1, 2027 holds real google use; plan any necessary production stop separately with the owner. no deletion, expiry rule, reset or paid substitution is authorized by this issue.

## drive custody review on november 26

- google documents per-file access for a user-selected file and creation in
  drive. filing a specific owner-supplied file for the requested task is a
  plausible narrower use. the accepted 0120 cut also covers mail-derived
  originals, broad agent reads and durable derived history, which need their
  own evidence. [drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) · [workspace data policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy)
- google requires prior written consent for backup of user or app content from
  a developer app into drive. the proposed import is a one-time custody move
  with predecessor copies held for verification. the public terms leave that
  classification and rights to mixed legacy content unresolved. obtain a
  scoped interpretation or written clarification before importing real bytes.
  [drive terms](https://developers.google.com/workspace/drive/api/terms)
- the separate human preview uses temporary bytes and needs its own retention
  and revocation proof. the agent path carries observations and derived history
  into processing, recall and recoverable backups. current terms constrain
  permanent copies and data transfers. from february 1, 2027 the new addendum
  also constrains task reuse, covered technical information and retention
  after disconnection. no existing evidence resolves the mixed records or
  proves deletion across their destinations. [api terms](https://developers.google.com/terms#e_prohibitions_on_content) · [workspace ai addendum](https://workspace.google.com/terms/ai-tools/) · [effective date](https://developers.google.com/workspace/guides/quota-usage-tiers)

## sample-only importer check

on november 26 the owner authorized a one-off check on their existing google
account. the published terms permit the narrow task as designed. create a synthetic file
at its intended destination, read it back to verify the bytes, and trash it.
this uses a disposable operator app in the fresh test project with only
`openid` and `drive.file`. it creates the folder and addresses only its own
generated ids. it reads no existing files, lists, mail or docs. identity and
test responses stay in process. jarvis, model providers, chat history and
backups receive none of them. local evidence records the synthetic digest and
check outcomes. cleanup trashes the two generated objects and revokes the
test app's grant. the trashed samples remain in the account until normal expiry.
[per-file scope](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) · [drive terms](https://developers.google.com/workspace/drive/api/terms) · [trash behavior](https://developers.google.com/workspace/drive/api/guides/delete) · [revocation](https://developers.google.com/identity/protocols/oauth2/native-app#tokenrevoke)

this determination covers the importer smoke only. the production archive,
agent and human reader grants, and the import of existing originals remain open.

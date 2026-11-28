# adr 0121. exact draft revisions from chat

the revision reader owns the saved email. chat owns the action card and its
reply control. this supersedes the inline readers in [0101](0101-outgoing-mail-attachments.md)
and [0105](0105-native-android.md) for the later mail presentation cut designed
in 0118 and 0119. the editor, sending and wider chat presentation are separate.

both clients open `/mail/{message_id}/revision/{action_id}` and read the
matching `/api/mail/{message_id}/revision/{action_id}`. chat list and detail
supply the same scoped revision id on a historical send card or a linked saved
draft. the server independently proves that pair in the owner conversation,
including the recorded prior-consent relation. an unrelated pair gets 404.
a valid revision returns `complete` with literal sender, recipients, subject,
body, recorded observation time when available, and ordered file metadata.
conflicting evidence returns `integrity` with no mail fields.
opening and returning issue zero gmail calls and leave the action unchanged.
warm return restores the source reading place. a cold direct link offers
the source message. remove the exclusive inline reader fields and query.

0105 verified create and update actions and historical send proposals remain
readable from their original evidence. these records grant no execution
authority. new workspace create actions store the actual verified readback
with their durable result, including an observed quoted suffix and sender.
keep private inspection evidence out of tool results and model context.
the body uses the existing 100,000-byte bound. files retain ordered metadata
and hashes. this spends a bounded private receipt copy to retain exactly what
was verified and leaves raw mime, file bytes and unobserved parent quotes with
gmail. the existing receipt row and transaction own preservation. there is
no schema migration.

a november 26 counts-only read at installed schema `0025` found one linked
historical send with one recorded owner decision, 30 old create and two old
update receipts, zero saved links, zero workspace mail actions and zero
unfinished mail. workspace v1's saved-link reader looked for a binding label
the writer never emitted. the current reader uses the actual new binding.
the inventory supports cutting empty old workspace quote and digest-only
discard classes. discard and replacement stay disabled under 0107.
[discard qualification](../issues/google-workspace-mcp.md)

before activation, repeat the counts. settle incompatible unfinished create
actions and invocations under the original release. the existing stopped
native preflight rejects them. integrate the 0118 projection and preserve
the revision id on the action card. stage the matching service, web shell and
signed app. close old clients and switch them together under
[0104](0104-maintenance-without-owner-pause.md). absence of real provider
and installed proof remains explicit in the
[qualification issue](../issues/chat-draft-revision-inspection.md).

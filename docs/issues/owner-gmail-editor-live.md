# roll out the production gmail draft editor

status **open**. [github issue #127](https://github.com/NielsdaWheelz/jarvis/issues/127).
[adr 0119](../decisions/0119-owner-gmail-draft-editor.md)
passed opus review and browser, android emulator, postgres and controlled
gmail checks. the owner chose one production enrollment and an initial
synthetic send to self using that grant. resolve the existing
[google data-use decision](google-workspace-retention.md) before real use.

## before the switch

- get authorization for the named [stopped rollout](../operations.md). record
  the selected predecessor and target. rehearse the bound stopped snapshot
  with schema `0026` and its matching protected backup reader. stage the
  server, web shell and signed android app together.
- repeat the counts-only mail receipt inventory. settle unfinished work on
  retired bindings under its original release. check one exact historical
  revision from each present class. those opens make zero gmail calls.
- enroll the separate standard desktop oauth client once in production under
  the stopped enrollment procedure. the owner signs in and consents. verify
  service-only secret access, agent/client separation and browser-only
  editor routes. drafts created before enrollment keep their read-only links.

## first production use

- ask jarvis for a synthetic draft to the owner. verify that its reply opens
  the as-drafted preview, then edit recipients, text and an attachment. verify
  autosave in gmail. check a reply's quote and locked subject, the supported
  mime shape, empty recipients, and an edit made from a second client.
- the owner presses send once, to self. independently check the sent message
  id, recipients, body, thread and attachment hashes against the review.
  measure the 10-file and 25,000,000-byte upload on the intended host, and
  verify rejection just over the limits. use synthetic data throughout.
- on the signed app on a physical s22+, open the draft from its reply. verify
  browser sign-in, keyboard and send reachability, and back to the same reply.
  check whether closing the first tab with back warns about unconfirmed edits.
- check the revoked-grant state and same-account reconnect. if the send
  result is unconfirmed, verify sent mail before taking further action. the
  editor holds that draft and never repeats the send. repair forward under
  the documented rollout. a database restore uses
  `owner-gmail-invalidate-restore` while stopped.

record the release and signed app identities, results and open failures
here. retain only content-free evidence outside the mailbox.

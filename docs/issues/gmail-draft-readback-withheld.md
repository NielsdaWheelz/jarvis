# gmail withholds automatic draft readback

on november 27 utc, installed stock release `45fe785` staged a single
25-byte drive file and gmail acknowledged creation of an unsent
self-addressed draft. the existing receipt recorded `verification =
unverified` and `reason = withheld`. it had the draft and message ids, and
no verified digest for the complete draft. the owner’s gmail web interface
showed the draft and its only attachment. the exact downloaded attachment
matched the revised drive bytes and the staged sha-256.

this preserves the distinction between an acknowledged creation and a
verified draft. it leaves jarvis unable to qualify that draft for automatic
editing, discard or recovery through the existing typed readback.

reproduce with one disposable self-addressed draft and one small plain
drive attachment on the enrolled agent grant. observe the acknowledged
create and its immediate typed draft readback. close when the same
installed path can reopen and verify the exact draft identity, message
reference, fields and attachment bytes, or the owner explicitly accepts
the limitation for that path. [workspace contract](../decisions/0107-google-workspace.md)

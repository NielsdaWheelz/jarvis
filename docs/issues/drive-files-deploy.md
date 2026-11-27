# drive files production cut

activation is pending for [adr 0120](../decisions/0120-drive-files.md). schema `0027` replaces the old attachment reader. the cut requires a verified drive id and byte digest for each ready original. accepted pending uploads keep their staged bytes only when the stopped inventory verifies them.

on november 26 the owner authorized the drive move as the predecessor to
shared chat receipts. a read-only production query found schema `0025` and
25 ready attachments totaling 9,472,516 recorded bytes: 21 from gmail and
four from web. no pending or unresolved retired attachment work was
observed. each ready row needs a verified drive copy. repeat the inventory
under the hold before migration.

the matched wheel, archive and signed phone package rehashed locally.
main preserves the two installed quota-recovery fixes. the active backup
reader is still `0025`. the macbook built and qualified the matched `0027`
reader against the release lock without accessing production backups.
the exact reader also reopened a synthetic `0027` database dump offline
with the expected read-only grants and rejected a mismatched lock. the
archive, restore proof and reopened hashes are under
`~/.local/state/jarvis/qualification/adr0125-reader-0027.8m64TgcY/`.
the exact reader archive was copied into the private recovery kit and
rehashed. verify it again with the actual stopped snapshot. production still holds
the separate inactive `26f9588` candidate. the installer would prune it;
confirm its disposition when ready to stage this release.

the macbook systemd guest is ready. it passed a synthetic postgres 16.16
and pgvector 0.8.6 restore and loopback-only ssh after reboot. the named
evidence is under `~/.local/state/jarvis/qualification/adr0120-systemd-guest.w0FtiW05/`.
the stopped production snapshot still needs its own restore and compatibility
check. locate or provision the separate list-and-read credential for the
retired attachment bucket before taking the hold.

the production google project now has the four drive/docs services enabled.
the activation wrapper carries the private `drive-cut.json` beside its receipt
and reuses the same verified pair on retry. offline red, green and cleanup
evidence is in `~/.local/state/jarvis/qualification/adr0120-cut-transport-cOHjIP/`.

1. finish [live qualification](drive-files-live.md) under [0127](../decisions/0127-drive-prototype-qualification.md). keep the byte and edit gates closed until their live proofs pass.
2. stage the matched host, web shell, signed android client, and backup reader. follow the [operator runbook](../operations.md) under named stopped custody. verify and hash the private import map before applying the migration. hold on an unexplained row or an unsettled old effect.
3. record installed old and new links, uploads, mail staging, publisher and workspace checks, and a separate database restore. repair forward after adoption. retain the old bucket through installed verification and dispose of it only under separate authority.

close after installed evidence is reviewed. [deployment tracker](https://github.com/NielsdaWheelz/jarvis/issues/129) · [deferred document backup](drive-document-backup.md)

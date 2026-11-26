# drive files production cut

activation is pending for [adr 0120](../decisions/0120-drive-files.md). schema `0027` replaces the old attachment reader. the cut requires a verified drive id and byte digest for each ready original. accepted pending uploads keep their staged bytes only when the stopped inventory verifies them.

1. resolve [google data use](google-workspace-retention.md), finish [live qualification](drive-files-live.md), and obtain explicit production authorization. keep the byte and edit gates closed until their live proofs pass.
2. stage the matched host, web shell, signed android client, and backup reader. follow the [operator runbook](../operations.md) under named stopped custody. verify and hash the private import map before applying the migration. hold on an unexplained row or an unsettled old effect.
3. record installed old and new links, uploads, mail staging, publisher and workspace checks, and a separate database restore. repair forward after adoption. retain the old bucket through installed verification and dispose of it only under separate authority.

close after installed evidence is reviewed. [deployment tracker](https://github.com/NielsdaWheelz/jarvis/issues/129) · [deferred document backup](drive-document-backup.md)

# old calendar revisions republished after the final reset

the stopped `0013` recovery dump contained 148 `calendar_event` source ids.
at `07:13:20Z` on 2026-11-18 all 142 such ids in the new corpus matched
that inventory. each match had the same account, calendar id, event id and
etag. the complete fact matched apart from its observation time. the fresh
host messages have new canonical ids, so archive part-id comparisons alone
leave this repetition undetected. the messages are eligible to wake main.

the [source contract](../event-sources-and-recurring-work.md) and installed
poller discard item rows while establishing the initial sync token. the
poller publishes `calendar_event` only while processing a request with that
token. one google public virtual calendar returned 71 confirmed and 71
cancelled all-day revisions after its baseline. clearing canonical history
removed the earlier publication keys. the poller admitted
the revisions under its existing incremental contract. google’s internal
reason for returning them remains unknown. the separate attention fact was
current and eligible. private `final-reset-calendar-provider-identity-overlap.json`
and `34d1620-final-google-stream-shape-20261118T071426Z.json` have sha256
`4aac4cd952949bf2046dc4970fc72307649ee2256cd20466651e8aa2c3eb3149`
and `aaa38afbb32b7a9acf64c1005952ce5ae428e053e63bbee32a48d364fa1dd660`.

the owner authorized [one stopped correction](../decisions/0085-preserve-google-cursors-during-correction.md)
retaining the established cursors. under genuine pause 13 the [installed
read-only check](../runtime-reliability-and-integration.md#stopped-google-cursor-correction)
found 80 distinct reoffers in one complete five-page poll. each belonged to
the verified set of 142, and the terminal token equalled the starting token.
the existing canonical keys still suppress duplicate publications. removing
them would admit those offers again.

the owner chose to retain the corpus, source cuts, existing recovery snapshot
and canonical deduplication. the verified fixture cleanup was already complete.
further cleanup and calendar filtering are retired for this delivery. distinct
eligible revisions still follow ordinary source admission. the original strict
no-republication criterion remains unmet. verification of that criterion would
require an installed reset with zero overlap against prior provider revision
identities while genuine new revisions still enter normally.

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
after isolated proof. preserve the established cursors and verified private
recovery. clearing the configured channel and remaining central tables includes
already committed revisions, their derivatives and genuine intervening history.
resolution requires the installed cursor comparison, ordinary owner resumption
and new capture, then completed polls without replay of the old revisions.
further wipes require a separate decision.

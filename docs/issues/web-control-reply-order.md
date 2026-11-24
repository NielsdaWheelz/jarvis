# web control replies appear above their commands

the first check of the installed chat api on `a612c51` found 22 web pause and
resume acknowledgements above their commands. by 06:09 utc on 2026-11-24, the
database contained 23 such pairs, all reversed. the six final replies that
explicitly handled ordinary web requests each followed their request.

the acknowledgement inherited the start time of the transaction that accepted
the command. the command was stamped later inside that transaction. the source
fix stamps new acknowledgements when the control is applied. chat uses that
same recorded time for existing acknowledgements, including across page
boundaries. a read-only comparison across 223 installed messages moved exactly
those 23 pairs. the original timestamps remain available to the archive.

on macbook, postgres 16 at schema `0020` reproduced both reversals. the fix
passed new submissions, equal-time stamps, retries, individual message reads
and a pair split across two history pages. chromium showed the corrected order
at desktop and phone widths. an already-open tab needs one reload to reorder
existing rows.

close after the installed history and an individual message link agree on the
corrected time, and the next normal pause or resume appears before its
acknowledgement after reload.

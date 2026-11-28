# let jarvis read the mail that woke it

on november 27 the owner clarified that the gmail label exists solely for
cheap discovery. the poller owns label removal. jarvis should decide what
to read and what to do in its ordinary turn. ignoring an arrival is valid.
the production catch-up recorded 34 distinct arrivals.
all 34 input rows completed in one native attempt. its only gmail reads were
an owner-requested search and a thread metadata read, both before reception
was re-armed. it issued zero message-body reads. whether any of these messages
needed attention remains unknown.

the poller records metadata and clears the pending label after recording the
arrival. the main prompt suggests inspecting the message when useful, but an
ordinary arrival alone gives main no permission to open its body through the
workspace connector. owner requests and authorized scheduled checks have their
own read authority. a google tool approval does not change the host rule.
[arrival contract](../decisions/0107-google-workspace.md#e--incoming-mail) ·
[host authorization](../../src/jarvis/workspace_host.py)

[adr 0132](../decisions/0132-one-main.md) owns the repair. the owner grants
ordinary main the same supported tools on every wake. it can open related
threads, search older mail, consult a calendar and act under its standing
authority. the poller retains durable intake and automatic label removal.

verify that an arrival alone lets main open the exact message and use its
contents in an ordinary decision. verify a second arrival can be ignored
without a body read, todo or owner notice. both labels should clear on
durable receipt independently of either decision. no reviewed state.

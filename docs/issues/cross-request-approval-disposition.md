# cross-request approval disposition

status: open; observed in the real f2 journey on 2026-11-17.

attempt `8cf5836e-5500-40ca-bdb0-b5baa3c80b4f` sealed a successful native
terminal, then failed product settlement at `native_journal.commit_product:1306`.
its final dispositions attached send proposal
`8bc53688-c507-467b-9945-b6b359d7996e` to two parentless owner requests.
the proposal belongs only to `19c6030b-fc0a-4c06-a7d1-8257498d6be1`;
`2487c506-4aef-4f2e-9018-554ada7377d0` is a separate root.

the host correctly rejects this cross-component reference. the whole terminal
remains rejected, original effects and seal remain intact, and affected requests
are parked for named repair. the draft remains unsent, with its proposal
`awaiting_approval`, zero executor entries and no consent receipt. this identifies
this failure; it does not identify the older historical native failures.

private `main-8cf-failure-fixture-state.json`, sha256
`a950162994fcea03d6078f068d0bae409d3a25600452a67d7cf54093307eeb31`,
retains exact fixture actions, terminal dispositions and delivered input/parent
metadata. both independent reviewers classify the terminal as an invalid model
disposition, not an implementation defect in the authority check.

main-v3's source-qualified prompt clarification defines a causal component
through recorded parent roots. genuine continuation with the original actions
and receipts remains pending. preserve atomic
settlement and the foreign-action rejection; do not relink requests, rewrite the
old terminal or commit its valid subset. the missed timed restart remains a
separate acceptance gap.

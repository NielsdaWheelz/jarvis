# jarvis cannot tell that a question crossed with the owner's message

jarvis asks "the 14:00 is sold out; book the 15:30?". before that question has
been on any screen, the owner sends "book the 14:00" from the android share
sheet. main receives the message with nothing to say the question was never
shown, and may read it as the answer.

no incident is recorded. the case follows from the share path, which sends
without opening chat, and from main being told nothing about display.

[adr 0125](../decisions/0125-new-shown-and-owed.md) will record what has been
shown. the service could then tell main, with an owner input, that an open
question had not been shown when he wrote. two reviews on november 26, 2026
held the first form of this idea:

- main never sees the ids of its own messages, so a list of ids is unusable.
  it needs the question's text and time.
- `home_context` means the object under discussion. this fact needs its own
  framing section.
- anything written into `home` is archived to shared memory permanently and
  redelivered in request context. [0087](../decisions/0087-private-web-home.md) fixes the
  `home` shape and [0095](../decisions/0095-context-cost.md) prices every added token.
- listing what was not shown implies everything else was. shown must never
  become evidence of consent, comprehension or agreement.
- the fact is only as true as the definition of shown, which the first cut of
  0125 is still rehearsing.

if pursued, limit it to open owed questions, say only "this question had not
been shown when the owner wrote; do not read the message as its answer", keep
it out of the archive, and never let the host act on it. resolve with an adr
covering those points and a temporary check in which a share-sheet message
crosses an unshown question and main does not treat it as the answer.

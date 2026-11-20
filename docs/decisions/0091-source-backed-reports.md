# adr 0091. full answers in web chat

web chat is the installed conversation surface at schema `0017`. discord sends a short notification linking to the message. this decision supersedes the final-text budgets in [adr 0086](0086-native-recovery-and-memory-availability.md) and the instruction in [adr 0087](0087-private-web-home.md) to put long answers in a document. the old budgets cut off sentences and links. two trials also missed three of six galleries and both duplicate-payment warnings. [incident](../issues/native-partial-content.md)

## what the owner gets

answer directly in chat, at the length the question warrants. when a decision is at stake, lead with what changes it. cover the requested subjects, put usable source links beside the findings they support, and explain consequential unknowns. a one-fact answer may be one sentence. a six-gallery handover may span several screens in one message.

use a separate page when requested or when the work needs an interactive view. its accompanying chat answer carries the clickable sources grouped by finding, including on a phone. a reader opening the page alone goes back to chat for sources. only an explicit request to show the page may take over the asking tab.

jarvis chooses what to write. “you missed kestrel” is an ordinary follow-up. jarvis can reopen the evidence and correct itself in chat. the host stores what jarvis actually said. withdraw the earlier draft’s tracked report promises, mandatory delivery checks, automatic correction turns and recovery questions. assessment of the findings belongs to the agent and the owner.

## implementation

| owner | change |
| --- | --- |
| response and content designer | in `src/jarvis/terminal.py`, remove the character maxima from every visible final prose field and the assembled reply. delete the size arithmetic and the generation-only partial and failed variants. reuse the ordinary variants, labels, text checks, question rules and input dispositions. in `definitions.py`, instruct main to “lead with findings. answer fully in chat. group source links by finding.” check the composed instructions against their existing 16,384-byte limit and rotate main in `session-compatibility.json`. keep the wire shape and output name. |
| chat reader and interaction designer | reuse the existing message list, message detail, citation renderer, notifications and optional page presentation. an explicitly opened long message should start at its first line. polling and reloading that message link should preserve the reading position. exercise the existing scroll behavior on a phone and desktop. confine any demonstrated repair to the current chat renderer in `static/home/home.js`. |

the 2,000-byte progress budget and discord’s notification limit govern different messages. model output and transport still have finite capacity. if transport fails or produces no valid final, use existing recovery. postgres already stores the full text. recovery decodes a pending final using its saved output contract, then applies the web reply rules. previously settled outcomes stay recorded as they were. no migration or new api is required.

## acceptance

1. the content designer writes a short answer key for a comparable six-gallery case using 18 known receipts. send a natural request through real stock and web chat. a reviewer reads the resulting answer against the receipts once during qualification. look for all six galleries, the two already-paid bills, the actual purchase gate, the consequence of any missing evidence and an open purchasing review. read a natural owner correction in the same conversation. ordinary context freshness belongs to the separate adr 0092.
2. exercise a complete answer beyond 2,000 characters and a partial with a question beyond the old 979-character body limit. include multibyte text and a source link near the end. open the complete answer from its discord reply notice, scroll to the final line, click the source and reload. a genuine owner-input wait uses its existing question notice. verify faithful delivery through the native, database and browser paths. a short control stays short.
3. run temporary integration/live red → green → refactor → green. record the outcome, get independent opus review and remove the temporary probes. the original fixture was deleted. a reconstruction supports a comparable trial. installed proof is separate. [delivery plan](../implementation-plan.md#full-answers-in-web-chat)

the trade-off is deliberate. the agent can omit a finding, and the owner may need to ask again. long answers also increase the size of the existing 50-message refresh. use the one-user design and real reading experience to decide whether that ever needs work.

## implementation evidence

source `966f3f9` hard-cuts the old final variants without a schema migration.
the actual 48-tool main composition uses 16,358 of 16,384 instruction bytes
at the longest installed timezone name. the native output schema uses
5,536 of 32,768 bytes. stock sees the existing partial and failed variant
descriptions. main uses `jarvis-main-private-home-v14`.

- native and postgres 16 at schema `0017`. baseline `5f04ec6` failed 13
  checks. final prose kept its generation limits and four long finals were
  parked before publishing the authored text. first green passed 51 checks.
  refactor green passed 54,
  including the exact 2,237-character answer, 2,341-character multibyte partial
  with an actual owner question, recovery of a 2,076-character historical
  partial and preservation of 13 already settled outcomes. progress, validation,
  wait notices, silence and the retained capture/retry check passed.
- reader. opening from a notice hid the lead on desktop. explicit reload
  moved the reader in desktop chrome and phone-sized webkit. the final browser
  probe used a 4,317-character message older than the latest page. desktop
  chrome 157 and phone-sized chrome 157 and webkit 26.6 opened at the first
  line, kept position when a new reply landed and on reload, and clicked through
  a nested source url. a short reply and direct detail with history unavailable
  remained readable. the browser stores one relative offset for a direct message
  reload in the current tab. review exposed a late-history restore that could
  undo a new scroll and a canvas retry that reopened the current message.
  both failed in all three browser configurations before the final repair.
  drift after the repair was at most 0.172 pixels.
- live baseline. stock codex `0.160.0`, personal subscription, `gpt-6-astra/max`,
  and the real web service used a reconstructed 18-receipt case. attempt
  `3d9f7f2e-5c11-41d3-aa36-b4379a0d61dd` opened every original and kept the
  purchasing review blocked. the 2,000-character seal matched the canonical
  reply and web api. it stopped after “otherwise move” in gallery two, with
  three source links.
- live candidate. the same request from the browser composer opened all 18
  originals. the seal for reply `1a9c45bc-bfa8-55db-8345-bb81c66af238` rendered
  to 6,539 characters (6,586 utf-8 bytes), preserved exactly in postgres, api
  and browser. reading it against the fixed answer key found all six galleries,
  both paid invoices, the $8,460 release gate and the consequence of the missing
  signed original. the real purchasing work row stayed blocked. the original
  tab stayed in chat. the seal was a partial with no question because native
  could not independently reach the isolated citation server. from the
  acknowledged reply notice, desktop chrome and phone-sized webkit opened at
  the first line and kept position across poll and reload. chrome opened all
  18 cited originals, including the last link. 17 written urls matched exactly.
  the browser normalized one short loopback address to the same original,
  which both engines opened. an ordinary owner follow-up corrected the kestrel
  caption, preserved the actual payment and handling facts, and attributed the
  new wording to the owner. the correction opening had ready coverage
  `[0,0)` at admitted cut `52`. main reopened the earlier handover with tools
  against fixture embeddings. this qualifies the observed correction.
- live question. main drafted two versions of a label for an actual owner
  choice. the partial body was 1,643 characters and rendered to 1,882.
  the committed `owner_input` wait sent the question notice for reply
  `70583083-eca2-546d-a739-d6e67970a85d`. a phone-sized browser opened the
  decision, verified its exact prose and clicked its late source. after the
  owner chose, the decision became settled with the same text.
- live complete and short controls. a separate stock `answered` seal returned
  a six-room tour of 3,732 characters (3,744 utf-8 bytes). its reply notice
  opened `852d83ae-f31e-5208-96e9-6fff736f811d`. the complete answer and final
  citation survived settlement, api, browser and reload. the short control
  was exactly `12`.
- optional page. the ordinary handover published no page. an explicit follow-up
  opened the pinned private loading card in its asking tab. the accompanying
  reply linked each of two findings to its original source.

the live runs used linux stock with the personal subscription, isolated postgres,
fixture-only notes and a private https receiver for the real notification sender.
the receiver generated fixture acknowledgment ids. the browser opened the
emitted links against the isolated service and rendered source links in otherwise
plain text. phone checks used mobile browser profiles. installed acceptance is
separate.

independent opus 5.5 at max accepted the proof design, source, refactor and live
results on `966f3f9`. its reader challenge produced the degraded-service cases
above. `scripts/verify`, `node --check` and the retained capture/retry check
on a fresh schema-`0017` database exited zero. the temporary probes and
isolated candidate resources were removed after qualification.

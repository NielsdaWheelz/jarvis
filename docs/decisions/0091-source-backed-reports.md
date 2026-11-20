# adr 0091. full answers in web chat

web chat is the installed conversation surface at schema `0017`. discord sends a short notification linking to the message. this decision supersedes the final-text budgets in [adr 0086](0086-native-recovery-and-memory-availability.md) and the instruction in [adr 0087](0087-private-web-home.md) to put long answers in a document. the old budgets cut off sentences and links. two trials also missed three of six galleries and both duplicate-payment warnings. [incident](../issues/native-partial-content.md)

## what the owner gets

answer directly in chat, at the length the question warrants. when a decision is at stake, lead with what changes it. cover the requested subjects, put usable source links beside the findings they support, and explain consequential unknowns. a one-fact answer may be one sentence. a six-gallery handover may span several screens in one message.

use a separate page when requested or when the work needs an interactive view. its accompanying chat answer carries the clickable sources grouped by finding, including on a phone. a reader opening the page alone goes back to chat for sources. only an explicit request to show the page may take over the asking tab.

jarvis chooses what to write. “you missed kestrel” is an ordinary follow-up. jarvis can reopen the evidence and correct itself in chat. the host stores what jarvis actually said. withdraw the earlier draft’s tracked report promises, mandatory delivery checks, automatic correction turns and recovery questions. assessment of the findings belongs to the agent and the owner.

## implementation

| owner | change |
| --- | --- |
| response and content designer | in `src/jarvis/terminal.py`, remove the character maxima from every visible final prose field and the assembled reply. delete the size arithmetic and the generation-only partial and failed variants. reuse the ordinary variants, labels, text checks, question rules and input dispositions. in `definitions.py`, replace “put long work in a document.” with “answer fully in chat. group source links by finding.” check the composed instructions against their existing 16,384-byte limit and rotate main in `session-compatibility.json`. keep the wire shape and output name. |
| chat reader and interaction designer | reuse the existing message list, message detail, citation renderer, notifications and optional page presentation. an explicitly opened long message should start at its first line. a refresh should preserve someone’s reading position. exercise the existing scroll behavior on a phone and desktop. confine any demonstrated repair to the current chat renderer in `static/home/home.js`. |

the 2,000-byte progress budget and discord’s notification limit govern different messages. model output and transport still have finite capacity. if transport fails or produces no valid final, use existing recovery. postgres already stores the full text. recovery decodes a pending final using its saved output contract, then applies the web reply rules. previously settled outcomes stay recorded as they were. no migration or new api is required.

## acceptance

1. the content designer writes a short answer key for a comparable six-gallery case using 18 known receipts. send a natural request through real stock and web chat. a reviewer reads the resulting answer against the receipts once during qualification. look for all six galleries, the two already-paid bills, the actual purchase gate, the consequence of any missing evidence and an open purchasing review. read a natural owner correction in the same conversation. ordinary context freshness belongs to the separate adr 0092.
2. exercise a complete answer beyond 2,000 characters and a partial with a question beyond the old 979-character body limit. include multibyte text and a source link near the end. open the complete answer from its discord reply notice, scroll to the final line, click the source and reload. a genuine owner-input wait uses its existing question notice. verify faithful delivery through the native, database and browser paths. a short control stays short.
3. run temporary integration/live red → green → refactor → green. record the outcome, get independent opus review and remove the temporary probes. the original fixture was deleted. a reconstruction supports a comparable trial. installed proof is separate. [delivery plan](../implementation-plan.md#full-answers-in-web-chat)

the trade-off is deliberate. the agent can omit a finding, and the owner may need to ask again. long answers also increase the size of the existing 50-message refresh. use the one-user design and real reading experience to decide whether that ever needs work.

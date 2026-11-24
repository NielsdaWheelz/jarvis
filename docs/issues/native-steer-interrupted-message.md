# an interrupted answer item prevented a later answer from settling

open. on 2026-11-24 jarvis release `74bfcaba` ran one five-minute turn on stock
codex `0.171.0` and provider-runtime `1faa4912`. it completed two calendar
writes and produced a later answer item. jarvis could not accept the terminal
and parked all four waking inputs. the fault concerns the native item protocol.
the older [unexplained candidate failures](native-protocol-diagnostics.md)
have their own evidence.

## installed evidence

attempt `c8bcc283-3925-411a-9bd8-b80f9ba1b6fe`, stock thread
`01a20f85-88a2-7471-b3e8-76523f557a77`, turn
`01a20f85-8938-7f91-a260-fb7f88b05db7`. the contained host's thread-scoped
stock logs, assistant journal and canonical database give this timeline in utc.

| time | observation |
| --- | --- |
| 21:47:42.246 | stock opened assistant message `msg_04700c26d3be2ac8016b0605fe399487d0a2ead8f7ff178c62`. |
| 21:47:42.334 | stock received the new turn input for the owner's follow-up. |
| 21:47:42.375–.430 | stock logged `response.interrupt.accepted` then `response.output_item.interrupted` as unhandled. the first message has no matching output-item completion in the thread log. |
| 21:48:00 | a separate completed progress message reached jarvis. |
| 21:50:18 | the second successful calendar action updated the event created by the first. both have their original receipts. |
| 21:50:58.830 | stock completed another assistant message, ending sampling with no follow-up, pending input or token limit. |
| 21:50:58.875 | the assistant journal located the exception at `codex_sdk._turn_terminal:1921`. the adapter still had at least one open item. it rejected the terminal before validating the application answer. all four inputs parked together at 21:50:58.893. |

the unmatched message across the steer explains the guard. the production
diagnostic retained the guard's source coordinate, without the contents of its
open-item map. the stock log recorded the interruption event name without an
item id. the item attribution comes from correlating the two records.

| waking input | role in the attempt |
| --- | --- |
| `78b1503d-e664-4e72-8886-2b424e94ea2f` | original appointment request |
| `22f682a9-5b4d-4870-883a-6abd4e0f092f` | incoming mail notice |
| `e1f643f0-86ce-4624-9f01-29cf1d6855b2` | sizing research and calendar amendment |
| `d8d0ac15-6f72-47ad-9fd3-f8d2a2ab6958` | incoming mail notice |

each write succeeded once on event `d2c43d5342d56ca046dbdfa1387ac62d`.
the update returned the requested sizing questions. all 31 reads have terminal
receipts, including four tool failures. jarvis published progress and the
parking notices. the research answer has no accepted seal or final delivery.

## reproduction and closure

in an isolated macbook run, stock `0.171.0` used a loopback responses fixture.
after stock announced the first message start, a real `turn/steer` added the
follow-up. stock recorded the input, started and completed a fresh final answer,
and emitted a successful turn summary naming that answer. it emitted no
completion for the first message. an ordinary uninterrupted control paired
every start. a fixture with an upstream interruption and no steer also left the
first message open and logged the unhandled event. these reproduce the
lifecycle with synthetic responses. production's full wire stream was not
retained.

the three stock cases passed twice. the macbook retains `fixture.py` and
`results.json` under
`~/.local/state/jarvis/evidence/native-display-interruption-20261124-c2c65449/`.
the reopened results have sha-256
`37be102eb7f318fd25f12ed8abe6dfadccd40ac179ba919e8d940c62c96b9e61`.
the temporary homes, harness scratch and source clone were removed.

on the macbook, a synthetic notification sequence through the same provider
module (sha-256 `5d967036184242d6f0cf7df803188bc4f1ed4833f46ccbb67d1c6a6bc9b5d5c7`)
started one assistant item, started and completed a second final answer, then
reported a completed turn. the adapter raised
`turn completed with unfinished Codex item lifecycles`. completing the first
item as well let the same terminal return the second answer.

the practical repair belongs in provider-runtime. qualify a successful
same-turn terminal whose summary identifies the independently completed final
by id, phase and text. earlier abandoned assistant display items can then be
discarded. an open item newer than that final, an unresolved tool or input, a
missing or mismatched summary and a malformed application answer must still
fail their respective checks. a steer acknowledgment alone proves no message
was abandoned.

close the protocol issue when an isolated stock/adapter journey interrupts an
in-flight answer with a steer, handles the abandoned display item, and delivers
the later complete answer exactly once. preserve the rejection of incomplete
tools, unresolved callbacks and unproved finals. separately verify the installed
recovery against the original four inputs, two action receipts and event id.
the stopped multi-id release command only makes those inputs eligible again.

[pinned provider guard](https://github.com/NielsdaWheelz/llm-calling/blob/1faa4912f13bd376eefbb1213c27a8015f4e1e9f/src/provider_runtime/agent_runtime/codex_sdk.py#L1910-L1937) ·
[stock responses decoder](https://github.com/openai/codex/blob/rust-v0.171.0/codex-rs/codex-api/src/sse/responses.rs#L550-L589) ·
[release contract](../decisions/0086-native-recovery-and-memory-availability.md)

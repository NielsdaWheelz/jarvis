# older foreground requests remain parked after quota recovery

on november 25, 2026 pacific, production `70522de` had 93 unresolved parked inputs. 88 arrived in the previous 48 hours. the other five arrived on november 20. no parked input had a retry timestamp. a new web request completed separately on `google_neon`.

the 93 inputs match 64 original attempts:

- 84 mail events across 61 attempts ended in personal codex quota exhaustion. one attempt recorded two completed gmail reads. none recorded a write.
- five november 20 mail events across two attempts encountered a model capacity refusal and a lost stream. the latter recorded six completed reads and one rejected read. neither recorded a write.
- two mail events and two web requests share the november 24 interrupted calendar turn. its two calendar writes succeeded on the same event. the sizing research answer never settled. preserve this group under its recorded disposition. [incident](native-steer-interrupted-message.md)

55 of the 91 mail events retained sender and subject metadata. all 36 remaining message ids returned 404 from the same gmail account during review. mail polling deduplicates already published inputs. as of the review the newly enrolled cursor was enabled and deferred until midnight pacific under its initial quota seed. [workspace cutover](google-workspace-mcp.md)

reproduce with the installed `jarvis list-parked` and match each item to its original native terminal and effect receipts. automatic scans exclude parked inputs. [adr 0114](../decisions/0114-automatic-foreground-recovery.md#existing-backlog) specifies the source-qualified read-only catch-up and the separate calendar disposition. close after authorized stopped admission and verified delivery, exact per-input outcomes and unchanged original effect receipts.

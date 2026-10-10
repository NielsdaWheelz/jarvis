# native progress byte limit

problem: `Progress.text` enforces 2,000 characters, while SPEC 4.2 requires
2,000 UTF-8 bytes. non-ascii text can exceed the accepted native progress bound.

evidence: `src/jarvis/terminal.py` declares `max_length=2_000`; its `_utf8`
validator checks encoding validity only. `native_journal.py` publishes that text
without the missing byte check. source audit: `f3b4dc3`, 2026-10-04; no behavioral
probe was run in this documentation task.

reproduction: validate progress containing 1,000 copies of `漢`: 1,000 characters,
3,000 bytes. current schema accepts it; the byte contract must reject it.

resolved when the existing progress schema validates encoded byte length before
publication and o6's temporary integrated proof checks valid/rejected non-ascii
boundaries. no new renderer or runtime critic. [o6](../one-main-events.md) owns it.

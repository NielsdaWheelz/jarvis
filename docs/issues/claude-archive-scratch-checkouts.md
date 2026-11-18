# scratch checkout blocks claude archive discovery

on 2026-11-18 the installed `macbook/claude-work` provider returned
`unsupported` while enumerating the account for its fresh capture cut. two
496,596-byte `observations.jsonl` test fixtures sit in a scratch project tree
under the claude archive. their paths fall outside the layouts accepted by the
provider's `docs/native-archive.md` contract. the failure occurs before any
conversation head is read, so per-conversation pending baselines cannot account
for the missing lane inventory.

metadata-only `archive_list`, listing with heads, and the installed activation
with a network fence all failed at `_claude_archive.py:135` on the same path.
no http request was entered. private `final-reset-mac-claude-inventory-red.json`
has sha256 `8d3077c2d2fe841a062f4ff792684ac02123df2bae5c18f7ec9fb90b0fd8cf73`.

the owner was asked whether to move the scratch tree intact or change the
provider discovery contract. resolution requires complete fresh account
enumeration through normal activation, with preserved source material and
zero republication of old event-part identities.

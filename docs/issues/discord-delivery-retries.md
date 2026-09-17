# discord delivery retries

problem: approval disabling and message creation repeat retry scheduling and
http response classification in `src/jarvis/discord.py`. fixes must be applied
consistently to both paths.

evidence: `disable_approval_message`, `_deliver`, and `_attempt`. patch must
verify the exact requested message id; create accepts a newly assigned id and
also supports multipart approval payloads. those distinctions are essential.

resolved when shared retry/status handling has one owner without hiding these
request-specific contracts, or caller-level comparison establishes that a shared
implementation would be less clear. characterize lost responses, rate limits,
permanent failures, nonce reuse, and exact-id rejection before changing it.

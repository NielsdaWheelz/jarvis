# one-main live google authorization

problem: the existing local and installed jarvis google refresh grants both fail
with the connector's `Google OAuth grant is unusable` error.

impact: slice 1's actual consent-to-connector-effect journey cannot yet run.
deterministic connector-port tests and live contained inference do not substitute
for that acceptance criterion. discord bot/channel reads both return http 200.

evidence: 2026-11-14 qualification used the production `GoogleTokenManager` and
actual token endpoint, first with the local qualified state, then with a private
copy of the stopped deployment's configured state. both failed before any
connector effect. no token values or private content were logged. production
jarvis remains stopped; no authorization or runtime policy was weakened.

resolution: renew the existing jarvis google authorization through its owner
consent flow, then prove ordinary conversational approval of one synthetic effect
on an owner-controlled resource, original receipt/restart recovery, and discord
delivery. no new credential product or scope expansion is part of this slice.

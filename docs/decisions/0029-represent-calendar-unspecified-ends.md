# ADR 0029: Represent Calendar events with unspecified ends

- Status: Accepted
- Date: 2026-09-04
- Supersedes: ADR 0027's requirement that every observed normal Calendar event
  have a concrete end
- Amends: SPEC section 7.3, the Slice 2 Calendar output contracts and bindings,
  acceptance A3/A4, and the Slice 2 qualification gate
- Owner approval: the owner approved the observed tagged-end contract,
  normalization rule, revision rotation, and final-code live coverage gate on
  2026-09-04

## Context

The final Slice 2 compound qualification requested 50 events from the qualified
Calendar account. It observed three confirmed `fromGmail` events with
`endTimeUnspecified=true`. Google documents that such an event still carries
`end` only for compatibility, even though its actual end is unspecified:
[Calendar Event resource](https://developers.google.com/workspace/calendar/api/v3/reference/events).

ADR 0027 required a concrete normalized end for every normal snapshot. The
adapter consequently classified each valid provider event above as
`ProviderUnavailable`. Treating Google's compatibility value as an exact end
would instead present a fact the provider explicitly says is not known. This is
a provider-contract contradiction, not an outage or an oversized value.

## Decision

Every observed normal event's `writable.end` is required and is the direct
closed tagged union:

```text
TimedEventTime | AllDayEventTime | UnspecifiedEventEnd

UnspecifiedEventEnd
  type: unspecified
```

All three branches share the existing `type` discriminator. The unspecified
branch has no payload. Google `endTimeUnspecified=true` produces
`UnspecifiedEventEnd`; Jarvis does not parse or expose Google's compatibility
`end` value. A missing or false provider flag requires a valid parsed timed or
all-day end.

The rule applies to every normal provider event type, including `fromGmail`,
and leaves `start` required and unchanged. A non-boolean flag, or an absent or
malformed end when the flag is false or absent, remains malformed upstream and
completes as declared `ProviderUnavailable`. A malformed compatibility end is
irrelevant when the flag is true. Sparse cancelled snapshots remain their
existing separate variant.

The observed projection is named `CalendarObservedWritableEvent`. It is not a
Calendar create/update input. A future write contract remains separate, has a
concrete required end using the unchanged two-branch `EventTime` alias, and
continues to use an address-required attendee type. This read amendment does not
weaken future write validation.

Both Calendar output schemas and both Jarvis Calendar binding implementations
advance to v2. Their frozen binding policy records the exact normalization rule.
Every affected maximum profile, selected profile, plan, HostTable, and agent
definition is recomposed. The Main role session-contract revision advances to
`jarvis-main-slice-2-v3`, so existing continuing Main sessions cold-bootstrap;
unaffected isolated role revisions do not change.

The sanitized final live-read qualifier requests 50 Calendar events, reports
only total and unspecified-end counts, and requires at least the three valid
unspecified-end cases observed in the qualified account. It emits no event ID
or content.

No dependency, database schema, authority, replay, recovery, admission, or
provider-usage behavior changes.

## Consequences

Benefits:

- Valid Calendar observations no longer become false provider outages.
- The model can distinguish a known exact end from a provider-declared unknown
  end without being misled by a compatibility value.
- Contract, binding, frozen-plan, HostTable, definition, and continuing-session
  identities all expose the behavioral change.

Accepted costs:

- Consumers must handle a third tagged observed-end variant.
- Jarvis discards the compatibility `end`, so it cannot use that value for
  display or duration inference. That loss is intentional because Google says
  the value does not describe an actual end.
- The exact final-account coverage gate depends on retaining at least three
  such events in the configured one-year qualification window. A changed live
  fixture requires explicit qualification maintenance rather than silently
  dropping coverage.
- Compatible continuing Main sessions cold-bootstrap once under the advanced
  session-contract revision.

## Rejected alternatives

- Return the compatibility end as exact: misrepresents provider semantics.
- Preserve Google's boolean plus its placeholder end: exposes two fields whose
  values deliberately disagree and invites consumers to use the placeholder.
- Use null for an unspecified end: the pinned portable schema subset cannot
  represent a nullable tagged union without weakening or wrapping the existing
  timed/all-day shapes. The explicit domain variant stays direct, closed, and
  model-readable.
- Omit the event or map it to `ProviderUnavailable`: hides valid current truth
  and prevents the compound question from completing.
- Infer an end from the start, event type, or neighboring data: invents provider
  state.
- Add the provider flag or unspecified variant to future write inputs: weakens
  the separate concrete write contract without evidence that Jarvis should
  create unspecified-end events.
- Leave frozen/session identities unchanged: permits an old session to reason
  against a changed model-visible output contract.

## Migration and acceptance

There is no database migration or action drain. Startup recomposes the exact
Slice 2 read catalog and plans and cold-bootstraps an older continuing Main
session because its compatibility revision and definition fingerprint differ.

Deterministic tests cover timed and all-day events, `fromGmail`, explicit false,
missing, true, malformed known compatibility ends, offset-free IANA time
localization, direct three-branch schema compilation and strict round trips,
binding revisions, and frozen identities. Final exact-code live qualification
must pass the three-case sanitized coverage assertion plus the complete Slice 2
read and compound Discord gates.

Historical Slice 0 and Slice 1 reports remain byte-identical.

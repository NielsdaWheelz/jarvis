# ADR 0027: Bound Slice 2 connector observations

- Status: Accepted
- Date: 2026-09-04
- Amends: the read contracts in [SPEC section 7.3](../../SPEC.md#73-tool-contracts-and-exact-catalog),
  the Slice 0 contract sketch, and the kernel/`provider-runtime`/`llm-tools`
  revision pins in ADRs 0020 and 0026
- Owner approval: the owner approved this contract and its Maps refinements,
  the observed-only Calendar participant/time-zone refinements, and the
  compatible Web deadline and invocation-local usage dependency migrations on
  2026-09-04 before the corresponding Slice 2 implementation resumed

## Context

Slice 0 proved that the reused Gmail, Calendar, Maps, and public-Web credentials
and provider surfaces work. Its immutable signed report intentionally recorded a
compact pre-implementation contract sketch. Implementing the seven Jarvis-owned
connector reads exposed details that the frozen specification did not decide:

- which provider strings may be truncated and which stable values must instead
  fail;
- how a Gmail thread read bounds MIME text and attachment metadata without
  acquiring attachment-download authority;
- how Calendar represents the sparse cancelled resources Google returns;
- whether Maps directions discloses a route polyline or requests alternatives;
- the canonical Maps place-link field and exact provider projection; and
- how the Routes API's departure-time restrictions become a typed model-visible
  result.

Choosing these details only in code would change user-visible evidence and
external compatibility without specification authority. The owner therefore
approved this ADR and the matching SPEC amendment before implementation.

## Decision

### Shared failure and local bounds

All seven Jarvis-owned connector reads declare `ProviderResponseTooLarge`.
Jarvis returns it when a provider response exceeds the fixed wire limit or a
stable identifier/value cannot fit its declared model-visible field. It MUST NOT
truncate a provider ID, email address, timestamp, URI, MIME type, Calendar
recurrence rule, event value, or another field whose exact value is the
observation.

Only explicitly presentation-oriented Gmail snippets and decoded message text
may be shortened. Their enclosing `truncated` flags MUST then be true. Bounds
are UTF-8 byte bounds as well as schema character bounds. Provider JSON is read
through a two-mebibyte decoded-body ceiling before parsing. Unknown, malformed,
or structurally incomplete provider payloads remain `ProviderUnavailable`; a
known absent resource uses its declared not-found error; quota responses use
`RateLimited`.

Every success carries an aware UTC `observed_at`. Gmail message `internal_at`
and Calendar timestamps are aware instants. Jarvis returns no raw provider
payload and ordinary logs contain no connector body.

### Qualified Google token handoff

Slice 2 consumes the immutable Slice 0 handoff directly. Each encrypted token
is `aesgcm.v1.<base64url(nonce || ciphertext)>`; the nonce is 12 bytes and the
state metadata supplies its `AES-256-GCM` key version and
`jarvis.connector.google:<version>` namespace. The complete associated data adds
`:access_token` or `:refresh_token`, so the two fields cannot be substituted.
The handoff key is the base64url-decoded single connector encryption secret when
that value is 32 bytes, otherwise SHA-256 of those decoded bytes. Refresh
atomically re-encrypts both fields in the same format. The older Ariel
`aeadv1` envelope is not a compatibility alias, and configured keyring material
does not replace the qualified single-secret derivation.

### Gmail

`gmail.search` performs one `users.threads.list` request. Its result contains at
most 20 records with only:

```text
GmailThreadHit
  thread_id: string[1..1024], exact
  snippet: UTF-8 text[0..1000 bytes], presentation-only
```

The root `truncated` is true when provider pagination exists or any snippet was
shortened. Search performs no per-hit expansion.

`gmail.read_thread` performs one `users.threads.get(format=full)` request and
returns at most 50 messages. Each message contains:

```text
GmailMessage
  message_id: string[1..1024], exact
  thread_id: string[1..1024], exact
  rfc822_message_id: null | UTF-8 string[1..998 bytes], exact
  sender: null | Mailbox
  to, cc, bcc: Mailbox[0..50]
  subject: UTF-8 string[0..998 bytes], exact
  internal_at: aware UTC timestamp
  body_text: UTF-8 text[0..16384 bytes]
  body_truncated: boolean
  attachments: GmailAttachment[0..50]

Mailbox
  name: null | UTF-8 string[0..320 bytes], exact
  address: UTF-8 string[1..320 bytes], exact

GmailAttachment
  filename: UTF-8 string[0..255 bytes], exact
  media_type: UTF-8 string[1..255 bytes], exact
  size_bytes: integer[0..26214400]
```

The newest `max_messages` messages are selected and returned oldest to newest.
Decoded message text is selected from inline `text/plain` MIME parts, falling
back to inert text extraction from inline HTML only when no plain text exists.
Jarvis executes no HTML, loads no subresource, and never fetches an
`attachmentId`. Per-message text is capped at 16 KiB and aggregate returned text
at 64 KiB. The message `body_truncated` and root `truncated` flags report text
shortening; the root flag also reports a message-count or attachment-count cap.
An overlong RFC Message-ID, subject, address, attachment field, or other exact
value is `ProviderResponseTooLarge`, not a silently altered record.

### Calendar

Calendar list and get return a closed tagged union. A normal event is:

```text
CalendarNormalEvent
  type: event
  calendar_id, event_id, etag: exact string[1..1024]
  status: confirmed | tentative
  writable:
    summary: UTF-8 string[0..1024 bytes]
    description: null | UTF-8 string[0..16384 bytes]
    location: null | UTF-8 string[0..4096 bytes]
    start, end: timed(aware RFC3339, IANA zone) | all_day(date)
    recurrence: exact string[0..1024][0..20]
    attendees: CalendarParticipant[0..50]
    use_default_reminders: boolean
    reminders: {method: email | popup, minutes: 0..40320}[0..10]
  organizer: null | CalendarParticipant
  updated_at: aware timestamp
```

A sparse cancelled resource is preserved rather than forced through normal
required fields:

```text
CalendarCancelledEvent
  type: cancelled
  calendar_id, event_id: exact string[1..1024]
  etag: null | exact string[1..1024]
  updated_at: null | aware timestamp
```

Calendar list returns at most 50 events and sets `truncated` only for provider
pagination or a count cap. It does not truncate event fields. `calendar.get_event`
may return either variant.

Observed Calendar participants use a separate closed shape:

```text
CalendarParticipant
  name: null | exact UTF-8 string[0..320 bytes]
  address: null | exact UTF-8 string[1..320 bytes]
```

Both-null provider participants are preserved. An over-bound present field is
`ProviderResponseTooLarge`. Gmail and future Calendar-write `Mailbox` retain a
required address.

For a timed event, normalization preserves a valid provider IANA `timeZone`
when present. An offset-free `dateTime` is localized with that `ZoneInfo`;
ambiguous fall-back wall time deterministically uses `fold=0`, and nonexistent
spring-forward wall time is malformed upstream. When Google omits `timeZone`
for an already-aware `dateTime`, Jarvis preserves the instant and emits the
canonical `UTC` zone. An offset-free value without a zone is malformed. This
rule performs no additional provider request.

### Maps places

Place records expose `maps_uri`, not `google_maps_uri`. When present it is a
bounded absolute HTTPS URI of at most 4096 bytes. The production provider mask
requests `googleMapsLinks.placeUri` and normalization maps that qualified wire
field to `maps_uri`. Normalization also accepts the legacy `googleMapsUri` for
compatible payloads, but production does not request it.

Search and details use the same closed place shape:

```text
Place
  place_id: exact UTF-8 string[1..1024 bytes]
  display_name: exact UTF-8 string[1..512 bytes]
  formatted_address: null | exact UTF-8 string[0..1024 bytes]
  location: null | {latitude: finite -90..90, longitude: finite -180..180}
  types: exact UTF-8 string[1..128 bytes][0..32]
  maps_uri: null | exact absolute HTTPS URI[1..4096 bytes]
```

Search requests exactly those fields and returns at most ten records. Details
reads one fresh stable ID and returns the same shape. Because the result has no
field-truncation flag, none of its fields is shortened; any value outside the
local contract produces `ProviderResponseTooLarge`.

The production Places search field mask is exactly
`places.id,places.displayName,places.formattedAddress,places.location,places.types,places.googleMapsLinks.placeUri`.
The production place-details field mask is exactly
`id,displayName,formattedAddress,location,types,googleMapsLinks.placeUri`.

### Maps directions

`maps.directions` requests exactly one route with
`computeAlternativeRoutes=false`. Its production response mask contains no
polyline. A successful `routes` array contains exactly one:

```text
Route
  distance_meters: integer[0..2147483647]
  duration_seconds: integer[0..2147483647], provider duration rounded up
  description: null | UTF-8 string[0..1000 bytes]
  warnings: UTF-8 string[0..1000 bytes][0..10], required
```

Zero routes is `NoRoute`; more than one or an oversized exact value is
`ProviderResponseTooLarge`. The model never receives an encoded polyline.
The production Routes response field mask is exactly
`routes.distanceMeters,routes.duration,routes.description,routes.warnings`.
Warnings are provider-required display notices. Normalization preserves their
order and exact text, and the Maps binding instructions require every non-empty
warning to appear in the user-facing route answer.

`departure_at`, when supplied, is offset-aware. A past departure is permitted
only for transit. Transit departures must be between seven days before and 100
days after the authoritative host instant used for the call. A violation returns
the declared `InvalidDepartureTime` before Maps I/O. This deterministic check
uses the injected host clock in tests and the live UTC host clock in production.

### Revision and authority

The fixed provider endpoints, request masks, result counts, normalization, and
truncation rules are transitive binding behavior. Slice 2 starts each
Jarvis-owned binding at the already specified
`jarvis-<canonical-tool-id>-v1` implementation revision and records the fixed
projection values in revisioned `policy_inputs`. A future behavior change must
bump the implementation revision unless the changed value is already fully
captured by those inputs.

All seven tools remain automatic `Read` operations and create no `action` row.
This ADR adds no tool, table, column, credential, or write authority.

The approved public-Web deadline, extraction, and invocation-local usage fixes
pin `llm-agent-kernel` at
`09f08df2970121ababe973b0e92d6901dd40da9e`, `provider-runtime` at
`f477dcdcad03c30019576203d4eb8a3581a6d32f`, and `llm-tools` at
`9e6d155f3b64f03495911435b7cae8b8d131f9a2`, superseding only the older
revision values in ADRs 0020 and 0026. The kernel now settles each invocation's
reported provider usage once from the runtime's invocation-local terminal
usage; an absent terminal usage retains the conservative admission reservation.
Upstream certifies the exact kernel/provider-runtime usage-fix pair as native-
session compatible. Jarvis therefore records and verifies the new active pins
but atomically substitutes the predecessor pair only while deriving
`session_compatibility_revision`. This exact exception applies only when all
other pins are unchanged; either half alone, another dependency change, or an
application/role contract change rotates normally. It introduces no general
compatibility alias or epoch.
Production binds Brave search with its
`operation_deadline_seconds` set to 12 seconds. The selectable frozen plan
tightens `web.search` to one external attempt; it does not weaken the binding's
`BilledOnce` replay policy or add a Jarvis timeout wrapper. The full definition
maximum remains the sum of the pinned declarations.
The reader binding revision is `llm-tools-web-read-v2`; its exact extraction
identifiers are `plain-text-v2` and `html-visible-text-v2`. The new projection
preserves literal plain-text entities and decodes visible HTML character
references exactly once.

## Consequences

Benefits:

- Stable references are never quietly corrupted to satisfy a display bound.
- Gmail can answer conversation questions without downloading attachments.
- Cancelled Calendar tombstones remain truthful and schema-valid.
- Maps returns the useful route facts without disclosing a large, unused
  polyline or billing for alternatives.
- Provider limit failures and invalid departure times are distinguishable from
  general outages.

Accepted costs:

- A very large provider record may fail instead of returning a partial identity.
- Gmail snippet/body text is sometimes explicitly truncated.
- Only one Maps route is available in v1, so alternative-route comparison is
  unavailable.
- Selectable runs forgo Brave's second automatic attempt so one started
  `BilledOnce` search completes inside the 12-second binding deadline before
  the 15-second executor fence; a transient outage may therefore return
  `UpstreamUnavailable` sooner.
- Selectable runs cap one `web.read` observation at 64 KiB and aggregate tool
  output at 256 KiB so the exact nine-tool plan fits the bounded native-context
  route. A page or compound result that exceeds those tighter run limits fails
  boundedly instead of consuming the definition's full maximum envelope.
- Historical Slice 0 evidence still says its qualified Routes canary returned a
  polyline and up to three routes. That signed report remains immutable evidence
  of the earlier provider probe; this accepted ADR and amended SPEC govern the
  narrower production contract.

## Rejected alternatives

- Truncate IDs, addresses, URIs, or Calendar values: produces unusable or false
  evidence.
- Treat every bound failure as `ProviderUnavailable`: hides a deterministic
  contract condition as a transient outage.
- Fetch Gmail attachments: expands the frozen v1 catalog and data authority.
- Represent cancelled Calendar resources as malformed normal events: discards a
  real provider state.
- Return encoded route polylines or three alternatives: consumes observation
  budget without a Slice 2 acceptance need.
- Let the model infer departure restrictions from provider errors: wastes billed
  calls and makes deterministic policy provider-dependent.

## Migration and acceptance

There is no database migration. The main role instructions, capability envelope,
and result contracts already rotated the checked-in session-compatibility
revision for the Slice 2 Web-read contract. The later invocation-local usage
dependency correction preserves that revision under the exact compatible-pair
exception above and does not recompose plans or HostTables. No Slice 0 report is
edited.

This decision affects Slice 2 and acceptance A3.1, A3.3, A3.8, A3.10, A4.3,
A4.7, A4.9, A4.11, and A4.12. Deterministic schema, normalization, output-bound,
zero-I/O rejection, and exact-request tests plus sanitized live Gmail, Calendar,
Maps, Web, Codex, and end-to-end Discord probes must pass before Slice 2 is
marked complete.

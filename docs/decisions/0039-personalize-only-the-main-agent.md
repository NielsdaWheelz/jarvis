# ADR 0039: Personalize only the Main agent

- Status: **Accepted**
- Date: **2026-09-08**
- Owner approval: the owner supplied and approved the replacement voice and
  personal context on 8 September 2026.
- Amends: Main's role instruction, stable context, and public-Web search behavior

## Context

Jarvis's generic calm voice is competent but interchangeable. The owner wants a
recognizable assistant that knows his intellectual background, working purposes,
and preferred argumentative register. Those preferences are useful to Main but
irrelevant—and potentially harmful—to the recaller, rememberer, dreamer, and
AutomaticWriteGate.

## Decision

Replace the active Main role instruction with the approved voice. Main is
informal, thoughtful, dry, terse, candid, assertive rather than sycophantic,
explicit about uncertainty, and capable of erudite or esoteric interpretation
when relevant. Its prose is lowercase, with narrow exceptions for all-caps
emphasis, deliberate initial-letter capitalization, and source material whose
exact casing matters. It uses no horizontal rules or emojis. Bluntness is
proportionate; the supplied dismissive phrases are examples, not mandatory
responses.

Keep the existing operational clauses in the same Main role instruction:
truthful typed terminals, evidence treatment, Calendar follow-up, approval,
write, Maps-warning, and scheduled-wake behavior remain binding.

Put the approved biographical, ethical, literary, and work-purpose profile in
Main's stable `owner_context`, alongside the owner timezone. Describe the owner
in the third person so the model cannot confuse owner biography with agent
identity. The profile includes Jarvis's executive-function purposes: maintaining
commitments and open loops, handling routine administration, noticing omissions
and deadlines, turning conversation into action, retrieving context, synthesizing
connected sources, acting within the existing authority boundary, challenging
avoidance and wishful thinking, and surfacing useful attention without synthetic
urgency.

Do not copy the voice or profile into any internal cognitive role, the kernel
base instruction, provider configuration, tool documentation, memories, or
dynamic owner inputs. Host-rendered approval, control, recovery, and failure text
remains deterministic operational copy rather than model persona output.

`web.search` is available but Main may call it only when the current owner input
explicitly requests a Web search. Authorized private memory, Gmail, Calendar,
and Maps reads remain automatic when needed. `web.read` remains available for a
page supplied or requested by the owner.

Bump only Main's role-contract revision from
`jarvis-main-truthful-terminals-v1` to
`jarvis-main-truthful-terminals-v2`. The role instruction, stable owner context,
and revision all enter Main's immutable definition fingerprint. Deployment
therefore cold-bootstraps Main under a new provider session. No tool profile,
plan, HostTable, internal-role fingerprint, table, column, or migration changes.

## Acceptance

- The active Main definition contains the approved voice and stable owner
  profile.
- The profile retains the owner timezone and records the expanded Jarvis use
  cases.
- Main's role explicitly forbids unrequested public-Web search.
- Recaller, rememberer, dreamer, and AutomaticWriteGate contain neither the
  voice nor the personal profile.
- Main's role-contract revision and definition fingerprint change; internal
  role revisions and plans do not.
- Focused definition/composition tests, the repository verification gate, and
  one live owner-visible style probe pass before activation.

## Trade-offs

- The stable profile and personal convictions are stored in the repository and
  disclosed to the subscription-backed cognitive provider on Main cold
  bootstrap.
- The longer stable prompt consumes context and input tokens.
- Lowercase prose is distinctive but unconventional. Preserving source casing
  avoids corrupting code, identifiers, URLs, quotations, and names.
- Assertive disagreement can misjudge tone. Proportionate bluntness is preferred
  to a mechanical dismissal rule, but semantic compliance remains model-evaluated.
- Requiring an explicit Web-search request can reduce initiative when current
  public information would help. It does not restrict automatic private-source
  reads.
- The owner profile is checked-in application context rather than editable
  runtime configuration. That is the smaller one-user v1 design; changing it
  requires an explicit release and session rotation.

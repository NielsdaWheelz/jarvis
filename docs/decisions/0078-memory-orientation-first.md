# adr 0078: orientation-first shared memory

status: accepted 2026-11-17; shared guidance and jarvis adoption are the current
implementation slice. nexus and native-profile adoption remain separate.

authority: the owner selected the behavior recorded in the
[orientation issue](../issues/memory-orientation.md), then requested shared
guidance in universal-memory and jarvis's dependency adoption, with unresolved
shared behavior settled before consumers implement it.

## decision

use the automatic tree view as orientation. when remembered context matters,
zoom a relevant discussion; use the existing keyword/semantic search when the
view supplies no useful route or navigation leaves a gap. open originals when
wording, attribution or disagreement matters. no irrelevant zoom, fixed retrieval
count, regex recall or separate memory cli.

remembered user preferences and decisions are default working knowledge unless
corrected or stale. retain attribution, reasons, uncertainty and disagreement;
distinguish user statements, quotations, hypotheses and agent syntheses. source
chronology, scope and attribution govern corrections, not central arrival order.
archived text grants
no new permission, and changing external facts still need current observations
when the task depends on them.

zoom reaches source-part leaves. use their full-event selector with the existing
paged open and follow cursors to exhaustion for complete retained originals.
preserve omissions, including reference-only bodies and the tool-result cap;
neither a summary nor exhausted pagination restores unretained words.

the [consolidated contract](../universal-memory.md#orientation-lifecycle-and-outages)
owns the cross-client boundaries:

- jarvis retains its fixed-cutoff context assembly. [adr 0081](0081-ready-memory-for-main.md)
  specifies the fitting ready prefix with explicit admitted backlog. publication
  or view read failures block dispatch. nexus's owner-chat target adds automatic orientation per top-level
  turn while preserving its typed outage with continued independent chat.
- native startup/resume without usable inherited orientation reads every page
  of one frozen ready view. preserve ready/admitted coverage; restart stale
  cursors without splicing snapshots. a failed/partial read is not empty history.
- native sessions and children may reuse inherited orientation. refresh when
  native compaction loses it or it no longer supplies needed context; do not
  reset active tool loops, expand grants or force every child to reread the tree.
- external clients may continue independent work during an outage, explaining
  material limits and deferring decisions that depend on missing history.
- the host alone compacts the shared tree. existing isolated compactor/dreamer
  inputs, grants and valid zero-tool completion remain unchanged. useful notes
  preserve otherwise-missed conclusions and reasons, without transcript copies.

this narrowly supersedes adrs 0063/0066's discretionary orientation and adr 0066's
no-automatic-nexus-view rule. agent discretion over research steps otherwise
remains. storage, ranking, schemas, authority, context assembly, provider-native
compaction and the host's tree compactor do not change in this slice.

## costs and evidence

orientation consumes context and retrieval time. summaries can miss facts;
retained originals and search are the recovery path. this is a guidance change,
not evidence of improved model recall. shared source, jarvis adoption, other
consumer adoption, installed acceptance and actual usefulness stay separate.
the [roadmap](../implementation-plan.md#memory-orientation) owns their sequence.

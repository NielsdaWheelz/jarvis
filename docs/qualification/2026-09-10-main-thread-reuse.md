# Main-thread reuse qualification — 2026-09-10

Status: scoped pre-activation qualification passed. On 2026-09-10 the owner
explicitly approved both release exceptions below. This report is not a full
provider-registry certification; the final merge identity and deployment outcome
belong to the release receipt, not this tested-candidate record.

## Exact candidate

| Component | Tested revision |
| --- | --- |
| Jarvis | `ad0f6ad37fb5fb95770109e1b9ee933318eab7a2` |
| Kernel | `8f6f15e39a99ed25f1a9cf8a1a50f5c4a76b6342` |
| Provider | `69d41d38a3d290e7ae3bde9b57556dda41e1b2f1` |
| Tools | `9e6d155f3b64f03495911435b7cae8b8d131f9a2` |
| Jarvis lock SHA-256 | `d735a2076c8f60c9dcc3a3a5fa5b98b37f0787d0d16f7f6c8fd3f47daa4ed936` |

Live checks used Linux, Python 3.12.13, the existing personal shared server,
native Codex 0.154.0, and subscription-backed `gpt-5.6-terra`. Consumer,
kernel, compaction, and containment requested high reasoning. The unchanged
standard provider matrix used its authenticated catalog's source-default
reasoning policy.

[ADR 0043](../decisions/0043-retain-main-thread-through-native-compaction.md)
removes routine generation expiry, not CAS or recovery. This dependency change
intentionally changes Main's definition fingerprint once; subsequent compatible
requests and restarts retain its native thread.

## Deterministic gates

The complete `scripts/verify` passed against an isolated PostgreSQL 16 database:
Jarvis 839 passed; kernel 267 passed (8 paid excluded); provider Linux 1,003
passed (one intentional optional-Claude skip, 60 paid excluded); tools 203
passed (2 paid excluded). Frozen dependency checks, Ruff, formatting, Pyright,
documentation links, migrations through 0004, schema drift, wheel/sdist,
fresh-wheel CLI, and audit passed. Git-only libraries are not PyPI-auditable.

Builders observed the owning tests fail before the provider normalization,
reference reuse, consumer grammar, and exact dependency-pin corrections.
Independent adversarial review cleared the source and dependency composition.
Removing the kernel's optional-commentary demand did not remove structured
result validation; actual native phase selection remains the provider's proof.

## Fresh paid evidence

All selected runs passed on their first invocation; none retried failed input.

| Owning boundary | Observation |
| --- | --- |
| Jarvis | Current structured Main, actual PostgreSQL checkpoint/decision/history ports, and a zero-tool tightening: three compatible fresh runtime bundles retain one native thread and context; deliberate reference loss creates a new thread with canonical reconstruction. |
| Jarvis isolated roles | Closed structured result and validated JSON-string echo-tool arguments pass. Entire consumer probe: 7 provider turns. |
| Kernel | All 7 non-quota live nodes pass, including resumed synthetic reads, initial-read ordering, nested/null structured output, tool arguments, containment, and the opt-in cancellation node. |
| Provider | Standard Codex matrix, opt-in guard, and containment: 3 tests pass. The matrix owns native cumulative usage, resume baselines, and actual commentary/final phase selection. |
| Native compaction | Two automatic compactions; same native thread after client close/reopen; marker recalled; all six usage components equal their independently observed cumulative deltas; restored history and synthetic context estimates are not charged. Zero native authority events. |

Retained content-free artifacts:

- [Consumer verdict](evidence/2026-09-10-main-thread-consumer.json),
  SHA-256 `0381b7def05b1d13b7f50c17a41210b975e70c740b0d19152aeb421d30a49dec`.
- [Kernel verdict](evidence/2026-09-10-main-thread-kernel.json),
  SHA-256 `c5a269dafb94c9e8197bf245e4c28085e7a6678cb4b1a829a7dc1f975a5041b5`.
- [Native compaction verdict](https://github.com/NielsdaWheelz/llm-calling/pull/29#issuecomment-5624607143),
  SHA-256 `ba1a15d2b5b2e2c066d92bbe81b4d2ba81e10548f4d15b4be669615bbc0827ec`.

The compaction fixture alone lowered `model_auto_compact_token_limit` to 1,024
from its first synthetic turn. It did not change production configuration or
invoke manual compaction. This proves actual automatic compaction and usage
normalization, not the production threshold or worst-case next-input fit.
Client reopen is not an OS restart. Jarvis's consumer tightening does not
substitute for the full memory-enabled service journey.
The cancellation node accepts cancellation before or after native submission;
its verdict does not identify which branch occurred, so this run does not prove
an already-submitted native turn was interrupted. The ordinary provider matrix
permits native tools; zero-authority claims apply only to the separately
contained compaction and containment probes.

## Existing owner / worker / phone acceptance

The earlier production release
`8a8a24b0620436c49f83d1ce7df4b90f984ef1c1` passed actual Discord owner input
through paid Main and its allowed write gate, exactly one succeeded worker-start
action at attempt 1, and delivered response. The owner confirmed the worker in
Skid 0.2.30 on the phone and answered its native approval. A read-only observer
proved one approval resolution, command exit 0, completed turn, and the exact
one-byte canary; it sent no worker input or approval response.

That is existing worker/phone evidence, not a new-candidate production run.
Worker terminal, native history, and canonical rows remain intact. The older
kernel commentary and obsolete consumer-grammar runs remain historically
failed; current revision results do not rewrite them.

## Approved release decisions and activation requirements

- Provider and kernel GitHub CI passed. Jarvis's CI jobs never started
  because of GitHub account billing; their verification result is NOT_RUN.
  The owner approved accepting the recorded full local verifier for this
  maintenance release only. This does not relabel CI as passed or waive future CI.
- Provider policy requires the full paid registry and both agent backends
  before an adapter merge. The owner approved a Codex-only exception for this
  maintenance release and its exact dependency propagation. No new API-provider
  or Claude qualification is claimed; the general policy remains unchanged.
- Genuine quota exhaustion is NOT_RUN; no account was deliberately exhausted.
- At qualification, the exact candidate was installed immutably but inactive;
  production still used the prior release. This pre-activation evidence does
  not itself claim a completed merge, release, or deployment.
- Before activation, prove the final tree differs only by reviewed evidence/docs
  from the tested candidate; verify the exact installed receipt and dependencies,
  stop only Jarvis, and inspect old nonterminal actions and deployment ownership.
  Preserve canonical history and worker lifetimes. No shared-server restart,
  phone gate, tmux invocation, or machine reboot is needed.

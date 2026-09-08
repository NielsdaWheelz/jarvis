# ADR 0032: Stream encrypted backups to dedicated R2 storage

- Status: Accepted
- Date: 2026-09-07
- Amends: SPEC sections 8, 9.3, and 11; acceptance A7; Slice 7
- Owner approval: the owner approved implementing backup and deployment on the
  existing devbox in this conversation on 2026-09-07

## Context

Raw memory is deliberately permanent and unbounded in v1. A useful backup must
therefore scale with the corpus without holding the PostgreSQL dump in process
memory. It must survive loss of the devbox, must not expose plaintext to object
storage, and must not grant Jarvis authority over Nexus or provider accounts.

PostgreSQL alone is not the complete canonical recovery set. The encrypted
Google connector handoff is required to resume live connectors. The content-free
pause and rolling-admission journals are small and operationally useful after a
restore. Provider-native sessions, provider caches, generated embeddings and
summaries, application credentials, and the Codex login are either rebuildable
or must be re-supplied separately.

Cloudflare R2 exposes a documented
[S3-compatible endpoint](https://developers.cloudflare.com/r2/get-started/s3/)
and [bucket-scoped Object Read & Write credentials](https://developers.cloudflare.com/r2/api/tokens/).
Restic provides client-side authenticated
encryption, immutable snapshot identities, integrity checks, and streaming
stdin/stdout operations without adding an application library or backup daemon.

## Decision

Jarvis uses the Ubuntu-packaged Restic client and a dedicated private Cloudflare
R2 bucket and Jarvis-only prefix. The credential is Object Read & Write scoped
only to that bucket. It is distinct from all Nexus, Google, Discord, Codex,
Brave, Maps, embedding, and Cloudflare administration credentials.

Once per day, `jarvis-backup.timer` runs as the unprivileged `jarvis` account.
It:

1. verifies the loopback PostgreSQL 16 database, pgvector identity, exact four
   application tables, private state paths, release identity, and credential
   metadata;
2. creates a custom-format, data-only `pg_dump` containing exactly `action`,
   `memory_log`, `memory_summary`, and `message` through a SELECT-only database
   role;
3. adds the encrypted Google connector state and the content-free `paused.json`
   and `admission.json` journals;
4. streams the database dump into one bounded manifest-bearing tar without
   loading it into Python memory;
5. streams that tar to Restic, which encrypts and authenticates it before R2
   receives repository objects; and
6. requires an immutable snapshot ID and a successful repository metadata
   check before reporting success.

The temporary plaintext staging directory is mode 0700 under `/var/lib/jarvis`,
uses mode-0600 files, and is removed on exit. The systemd unit has the same
read-only host boundary and `/var/lib/jarvis`-only write boundary as the main
service, with a smaller resource envelope.

Backups include no service environment, Restic password, database password,
R2 key, connector encryption key, provider credential, or Codex state. Those
must be recovered from the owner's independent secret store. The R2 repository
password must also be retained there: losing it makes every snapshot unusable.

Restore is deliberately operator-only and never automatic. It requires the
exact release commit, exact snapshot ID, a clean database migrated by that
release, the migrator database credential, an empty state target, and separately
re-supplied application credentials. It rejects path traversal, links,
duplicates, extra files, missing files, digest changes, release mismatch,
nonempty tables, and schema-roster drift. The database dump is streamed to disk
and restored in one PostgreSQL transaction. Derived summaries and embeddings
are then checked and may be rebuilt with the stopped `rebuild-memory` procedure.

No automatic `forget` or `prune` policy runs in v1. The corpus is small and an
incorrect destructive retention rule is harder to recover from than excess
storage. The production R2 bucket should apply 30-day
[Cloudflare Bucket Lock](https://developers.cloudflare.com/r2/buckets/bucket-locks/)
rules to Restic's immutable `<jarvis-prefix>/config`,
`<jarvis-prefix>/data/`, `<jarvis-prefix>/index/`,
`<jarvis-prefix>/keys/`, and `<jarvis-prefix>/snapshots/` paths while leaving
`<jarvis-prefix>/locks/` unlocked so normal Restic lock cleanup works. The
deployment-held S3 credential cannot administer those rules.

## Consequences

Benefits:

- Backup memory use is constant with respect to the permanent raw corpus.
- R2 receives only Restic ciphertext and metadata, not the plaintext tar.
- A database-only leak grants no provider or owner authority.
- A clean-host restore is deterministic and tied to an immutable release.
- A bucket-scoped credential cannot reach Nexus or other R2 buckets, and a
  prefix-aware retention lock can protect recent snapshots from a compromised
  devbox credential.

Accepted costs:

- The database and small filesystem journals do not share one cross-resource
  transaction. An in-flight backup may conservatively retain a stale admission
  reservation or pause value, but it cannot repeat an external effect; action
  truth remains in the transactional database.
- Backup and restore stage one plaintext dump on the encrypted-at-rest devbox
  filesystem before Restic encryption. Mode, ownership, systemd, and prompt
  cleanup limit exposure; full-disk compromise remains outside this control.
- Daily snapshots grow without automatic retention in v1. Storage use must be
  observed and a later retention change requires an explicit ADR and restore
  proof.
- The host-held S3 credential can write, read, and delete objects within its one
  bucket. Cloudflare Bucket Locks reduce recent-snapshot deletion risk but are a
  separately administered storage policy, not an application invariant.
- Restic's repository format and the distro client become part of the recovery
  environment and must be recorded in qualification evidence.
- Restoring filesystem state and committing the database cannot be one atomic
  transaction. Restore failure is fail-closed and may require discarding the
  clean target and rerunning from the beginning.

## Rejected alternatives

- Plain `pg_dump` copied to object storage: rejected because server-side object
  encryption does not keep plaintext from the storage operator or a stolen
  object credential.
- Loading the dump into a Python `bytes`: rejected because memory use would grow
  with the intentionally unbounded memory log.
- Reusing Nexus's R2 bucket or token: rejected because co-location is not a
  reason to couple authority or recovery failure domains.
- Backing up `/etc/jarvis` or Codex state: rejected because it would turn one
  snapshot plus one password into owner/provider authority and preserve
  noncanonical state.
- A second backup database/table or workflow engine: rejected because Restic's
  snapshot identity and systemd timer provide the required durability without
  another application state machine.
- Automatic retention/pruning now: rejected until real corpus growth establishes
  a retention need and a locked-snapshot restore test proves the policy.

## Qualification

Slice 7 must create and check one production snapshot, restore it into a clean
separate PostgreSQL database and state root, verify the exact canonical IDs and
terminal action semantics, rebuild all derived memory, and prove the original
service can restart afterward. The dated qualification report records the
Restic version, repository version, snapshot ID digest or sanitized prefix,
R2/bucket-lock posture, release commit, database identities, and every accepted
trade-off without recording credentials or private content.

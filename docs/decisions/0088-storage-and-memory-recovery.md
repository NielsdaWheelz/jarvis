# adr 0088. development storage and central memory recovery

accepted 2026-11-19. first production recovery and scheduled backups verified.
this supersedes [0033](0033-defer-backups-and-host-reboot.md) for central memory
backup only. [0086](0086-native-recovery-and-memory-availability.md) owns the
installed `0016` baseline and its stopped migration copies.

## outcome

new heavy development runs on the mac. hetzner serves production and reports
usable disk space. the recovery target is at most 24 hours of admitted memory
loss. an operator with a clean, available second machine
can read verified memory within two hours. report the newest verified upload
and the last actually restored cut separately.

the november 19 inventory found 8.75 gib available on the shared root volume.
jarvis occupied about 485 mib and its cutover directory 829 mib. 279 codapt2
scratch directories occupied 17.6 gib. 92 were registered git worktrees. one
historical series still referenced 36 existing paths. ownership and disposal
must be determined per run. [original evidence convention](https://github.com/codaptai/codapt2/blob/b6357c9eb365132ac3afc38e0f9474a7b4530c56/notes/refactors/servicification/proposals/native-runtime-check-lifecycle/README.md#L62-L66)

## a. development placement and evidence

the outer developer or agent starts large builds, integration databases,
rehearsals and restores on `macbook`. temporarily unavailable means wait.
existing release pipelines have their own placement. dev-server owns shared
agent guidance in `assets/agent-instructions.md` and the future desktop handoff
in `docs/desktop.md`. codapt2 links that guidance from `docs/codebase.md`.

for new detached rehearsal checkouts add one mac entrypoint in dev-server,
`scripts/rehearse-worktree REPO REV NEW_EVIDENCE_DIR [--expect FILE]… -- COMMAND [ARG...]`.
it owns one private scratch root and registered checkout at the resolved commit.
run argv there with `REHEARSAL_EVIDENCE_DIR` pointing to a new, owner-private
persistent directory outside scratch. the caller names promised relative files
with `--expect`. inner checks own their fixture teardown. on interruption
signal the launched process group, wait a bounded interval, terminate and reap
it. before ordinary git worktree removal, reopen/hash promised files and check
for dirt, commits unreachable from retained refs, open users and container
mounts. retain on missing evidence, incomplete observation or a surviving user.
hold an os lock for the run. after a hard kill reclaim manually only after
acquiring it and repeating those checks. cleanup failure exits nonzero.

the receipt records source commit, check, observed exit/signal, evidence locators
and sha256s, and separate disposition (`removed` or retained path, reason, next action).
a travelling report uses a verified private reference its intended reader can
reopen. the content designer's test is whether the intended reader can verify the claim
after the entire checkout disappears. preserve and classify the existing roots
by git registration, live use, unique work and referenced evidence. an unknown
remains unknown. this delivery grants no disposal of that inventory.

## b. production capacity

dev-server's `ansible/roles/base/` installs one sampler and systemd timer.
`ansible/group_vars/devbox.yml` owns the floors. every ten minutes sample the
filesystem containing the actual pg16 data directory. record locally
`{utc,filesystem,available_bytes,available_inodes,byte_floor,inode_floor,reasons[]}`.
use `f_bavail * f_frsize` and `f_favail` for an ordinary writer. any quantity
below its floor is low. missing identity or a failed sample is unknown. retain
the small samples through existing journald. initial floors are 10 gib and
100,000 inodes. raise them for the largest measured production burst plus
growth over the operator's response window. arm monitoring immediately.
track the low reading in dev-server's `docs/issues/production-disk-headroom.md`
until measured headroom recovers through separately approved disposal or expansion.

the owner chose local journal reporting for this rollout. log low and unknown
observations with scope, measured amount when known, applicable floor and one
inspection command. each scheduled observation stands on its own.

## c. central memory recovery

**installation.** c owns `deploy/provision-memory-backup EXPECTED_RELEASE`
for a same-schema `0018` install. adr 0092 migrated production before
backup provisioning. the release and both writers stay on the current schema. stage the tooling with its timer disabled.
from the mac use `dev-server-deploy`, `sudo -n` and the exclusive release file
lock. verify the selected release and both cleanly stopped units. reuse the
schema and canonical-pause check from [install_staged](../../deploy/memory_credentials.py)
under `maintenance_ownership` (assistant key, then memory key). hold both
through provisioning. create/verify the locked `jarvis-backup` os account and
stage a root-only credential. while the migrator holds both keys, use local
`runuser -u postgres -- psql` for one transaction creating/verifying the
`jarvis_backup` login and granting connect, schema usage and select on the exact
tables and required sequences. a narrow pg_hba rule confines this login
to jarvis through ipv4 loopback. deny durable large-object creation through
postgres defaults, preserving that authority for the current writer roles.
reload the cluster configuration, verify the allowed login and require
rejection of an alternate database. the isolated proof covers all denied routes. reject extra grants or memberships. atomically publish
the staged credential and leave the timer disabled. retry uses the same staged identity. refuse a live writer, mismatched
release/schema or missing owner pause before changing authority. restart
serving through the ordinary paused release procedure.

**producer.** `deploy/memory-backup` and `deploy/jarvis-backup.{service,timer}`
run at 00:00 and 12:00 utc with a persistent timer and a one-hour job limit.
give the account read access to the existing lock inode and take a nonblocking
shared flock. contention fails this attempt. both writers stay online. share
the roster and row digest with [prepare-cutover](../../deploy/prepare-cutover)
in `deploy/memory_snapshot.py`. leave the stopped pause/channel check in its
caller and preserve its byte format. for online digests use `COLLATE "C"` on
text keys and identical utc, date and numeric rendering on both ends. in
one open repeatable-read transaction export the snapshot, record the cut time,
compute the inventory and select read witnesses. pass that snapshot to a full
`pg_dump -Fc` from the server's pg16 bindir. require the schema's complete
table roster (19 application tables including `home_notice`, plus alembic,
at `0018`). each subsequent migration owns any new grants and inventory
qualification. fail on an unknown schema. a whole dump retains private
non-memory rows as the cost of one coherent recovery point. [postgres dump contract](https://www.postgresql.org/docs/16/app-pgdump.html)

**storage.** stream through `age`. feed the same bounded plaintext stream
to pinned `pg_restore --file=/dev/null` and check every process exit. use a
separate bounded boto3 multipart client, recipient public key and object-only
credential for a dedicated private backup bucket. the owner vault holds the
bucket endpoint/read credential, image locator and decryption identity. the
owner chose one identity on the mac for this rollout and deferred a spare
until the home workstation is ready. losing the only identity makes the
encrypted copies unreadable. use two create-only objects under each fresh
generation key.

```text
<utc-cut>-<uuid>/database.age    encrypted full dump
<utc-cut>-<uuid>/manifest.age    encrypted completion record, written last
```

manifest version 1 contains generation, utc cut, release commit and lockfile
hash, reader image digest, postgres/pgvector/schema versions, schema/ownership/grant inventory,
dump ciphertext length and sha256, ordered table counts/digests, ready/admitted
bounds and two witness selectors/hashes. choose the newest event with every
declared part below `leaf_count` and newest note with `agent_submission`, by
leaf position. use the library's `retrieval.open_records` on the snapshot
transaction with that cutoff. hash ordered canonical
read records including provenance and omissions, excluding pagination. encode
absence explicitly on an empty source and still back it up. populated live
qualification requires both witnesses. private details stay encrypted.
require successful dump, encryption, transfer and remote byte readback before
publishing the manifest. verify its stored bytes before reporting success.
partial data has no recovery receipt. resolve an ambiguous put against the
exact ciphertext at its key. after process loss a new run uses a fresh uuid.

only the independent cloudflare administrator can change the 30-day bucket
lock or lifecycle. expiry after the lock is asynchronous, per object. an
ordinary generation's promised window ends at cut plus 30 days. expire abandoned
multipart uploads too. after a successful drill, retain both ciphertexts,
hashes and the offline reader image in a private encrypted mac directory
outside scratch and cloudflare. verify the staged successor there, atomically
select it, then release the predecessor. keep its decryption key usable.
this single proven generation can outlive 30 days. cutover evidence follows
its original retention decision. [r2 lock semantics](https://developers.cloudflare.com/r2/buckets/bucket-locks/)

report each backup result in the systemd journal. only a newly verified cut
at most one hour old is a verified run. failures exit nonzero. rediscovering an
old object or skipping a migration window does not advance freshness.
the rollout has local observability. a missed job or host outage may go unseen
and the newest usable cut can age past the 24-hour objective.

**consumer.** `deploy/memory-restore {r2|held}/GENERATION NEW_PRIVATE_DIR` is
operator only. start the clock on a clean, available mac target before staging.
select the exact generation and storage location. the controller fetches only
from the private backup, independent owner kit and digest-pinned image store.
unit c builds `deploy/memory-reader.Dockerfile` on the mac. qualify one linux
image per compatible schema/reader identity containing
pg16, the installed vector version (0.8.6 at baseline), restore code and its
locked dependencies. retain it off-host while referenced. the current development
compose image has vector 0.8.1. decrypt into a new private encrypted-volume
directory. run the database and read in a fresh `--network none` container
with staged read-only inputs and a separate private encrypted-volume directory
for postgres data. omit host sockets, ssh, live
credentials and checkout mounts. create named local roles and a fresh database
from `template0` with local credentials and database-level grants. restore with pg16
`pg_restore --exit-on-error --single-transaction`. admit only a select-only
login for the read. keep serving units, collectors and effects stopped.

compare schema, grants, extension and all table counts/digests. those digests
cover leaf positions, provenance, immutable cuts, checkpoint id/digest pairs,
pending baselines, dream progress and action receipts. sequences are outside
mvcc and write resumption is outside this drill. page both witnesses through
`MemoryStore.open` at the recorded cutoff. the designer's private report gives
generation, cut age, elapsed time to verified read, actual coverage and each
failed comparison. success requires both witnesses and the two-hour deadline.
measure cut age at incident or drill start. the number of later lost records
may be unknowable. an older generation requires explicit
selection and owns its own result. rehearse monthly and after changes to schema,
keys, storage or the read path.

## delivery and acceptance

| unit and exclusive owner | temporary red → green → refactor proof |
| --- | --- |
| a · mac development workflow, shared guidance, codapt2 verification pointer | real checkout and ordinary check on the mac. reopen evidence after removal. interrupt promotion and preserve the only copy. inspect git registration and child termination. inventory legacy work read-only. |
| b · dev-server sampler and ansible | drive healthy, low bytes, low inodes, failed and missing observations against a disposable filesystem. verify credential-free journal reporting and install against the real pg volume. |
| c · jarvis backup, restore, provisioning, units and operations | on pg16, refuse unpaused/live provisioning without mutations, interrupt then retry the paused install with identical grants. dump during concurrent writes. interrupt upload and prove no valid completion. test corruption, wrong key, missing role and stale cut. restore a remotely fetched generation with hetzner unreachable. time both opens, compare inventory, verify retention and local reporting on a failed run. |

assign a content designer to each unit before its first red check. its receipt,
alert or recovery report must meet the quality test above. observe the intended
failure through the normal entrypoint, implement, pass, refactor, rerun. keep
the operator commands, runbooks and dated red/green/refactor receipts. delete only
this delivery's temporary tests, fixtures and disposable resources after proof.
record source, isolated, installed and recovery results separately. a and b can
ship independently of c. c's first full restore precedes scheduled activation
and replacement of a proven copy. ordinary live provisioning requires separate
authorization.

costs include mac availability, manual classification and freshness review,
dump/readback traffic, key custody and monthly drills. hosting moves,
quotas, legacy purges, continuous wal archiving, attachment/notes files and
web staging are separate work. an older ledger can predate a real external
effect. live resumption requires separate reconciliation and authorization.
[production backup evidence](#scheduled-production-backups)

**design review.** three feature designers defined the receipt, alert and
recovery report. after revisions to cross-platform row ordering, read isolation
and same-schema provisioning, `claude-opus-5-5` at high effort found no
remaining implementation blocker. review session `b9b7b8f2-1aa1-46b0-83b2-e35913e1a9b2`.


## implementation evidence

2026-11-20 utc. source is split across the three `implement/adr0088`
worktrees. each unit used the approved content brief and temporary probes.
adversarial opus 5.5 review found the docker image identity mismatch and
stopped credential gaps. the final pass cleared the repaired boundaries.
temporary probes and disposable fixtures were removed. the private unit c
receipt sits beside the unit a inventory under `~/.adr0088-inventory-x0ohbe8w/`.

| unit | isolated or operator proof | installed proof |
| --- | --- | --- |
| a | 15 mac checks, including real docker mounts, interruption, dirty and detached work, escaped users and evidence reopening after git removal. the existing 279 roots were inventoried read-only. private receipt with hashes under `~/.adr0088-inventory-x0ohbe8w/`. | the committed mac checkout command exercised its ordinary path. shared guidance is available in source. |
| b | exact ansible tasks on ubuntu's systemd with postgres 16 and a second mount; idempotent reapply. upstream healthchecks on a disposable network sent failure, overdue and recovery once per transition. | the real sampler is enabled on `/dev/sda1`. at 02:18 utc it logged 8,973,885,440 bytes available and reported the low-byte state. the journal-only release `9cac6a3` published the same low-byte state and exited successfully at 05:15 utc. |
| c | live-service and unpaused refusal, exclusive-lock survival on controller disconnect, interrupted grant retry with identical credential, exact read-only grants and rejected cross-database access. a real pg16 snapshot survived concurrent writes. subprocess interruption left no completion marker, stale cuts signalled failure, and bad ciphertext, wrong identity and missing role failed. normal mac recovery from a disposable s3 endpoint and the held copy took 5.25 and 5.21 seconds, opening ten original parts and an explicit note with matching inventories. a proven successor replaced the prior held copy. | this isolated proof used `0017`. live provisioning and the first provider-backed restore remain open. |

the reader uses the mac's arm64 docker desktop containerd store. it runs from a
release-built image pinned by oci index digest. plaintext and postgres data
use a filevault working directory. schema support is explicit so application
migrations cannot silently assert recovery support. the new role sheds ambient
access to other databases and large-object creation through a narrow hba block
and jarvis-local grants. postgres retains ordinary session and advisory-lock
behavior. archive transport and sender-loss proof used the real sdk and age
against a disposable endpoint. verify the actual cloudflare lock and lifecycle,
and the first production recovery before enabling the schedule. [scheduled production backups](#scheduled-production-backups)

on the installed schema `0018`, the merged preparation preserved the original
adr 0092 v4 stopped receipt byte-for-byte in a populated postgres 16 migration.
the isolated reader matched 20 table digests, grants, the owner-anchor index and
frozen coverage, then opened 10 event parts and an explicit note. it rejected
altered grant/index inventories. a concurrent vector update stayed outside
the exported snapshot. `9538bc8` rebuilt the pinned reader on the mac for the
production drill. the same commit's
journal-only producer streamed a real pg16 dump to age through the ordinary
entrypoint. the mac controller restored it in 4.91 seconds through a disposable
s3 fixture and in 4.88 seconds from the held copy after removing the fixture
endpoint. the producer rejects stale cuts and the retired ping field.

on 2026-11-20 utc the owner recorded web pause 21. the ordinary same-schema
release installed the scoped read-only backup login. the first job failed on
the live systemd credential file mode before any upload. release `e7f5916`
uses a service-owned `0700` runtime directory and an ephemeral `0600` file
for libpq. the ordinary service then verified the production generation
`20261120T055359985334Z-d2aedd79c2ab490f9511a0a4e91ae0ea`. r2 reported 256,198,801 bytes of encrypted
database data and 4,271 bytes of encrypted manifest, with december 20 expiry
headers. the job exited zero and systemd removed the runtime password file.

the mac fetched the generation over r2 with the independent read credential.
the restored postgres and reader ran without network access. both the r2 and
held-copy drills matched schema, grants and all 20 table digests. each reopened
one original event and one explicit note at ready/admitted coverage 5,801/49,129.
the r2 cut was 89 seconds old at drill start. the reads took 45.196 and 42.678
seconds respectively. private reports live beside the production rollout
receipts under `~/.adr0088-inventory-x0ohbe8w/deploy-0018/`.

the timer was enabled only after both restores passed. its first scheduled run
was due 2026-11-20 12:00 utc. both jarvis services were active and retained
owner pause 21 at that verification.

## scheduled production backups

on november 23 the mac used the independent r2 read credential to list the
initial drill and all seven expected 12-hour generations from november 20
12:00 through november 23 12:00 utc. each had a final encrypted manifest
and a dump whose object size matched the decrypted manifest. the latest
database cut was `20261123T120003057880Z-76ce51f38b3b462791c3fb84ad2f2f2e`,
303,888,883 encrypted dump bytes. the november 23 noon run verified its new generation at 12:01:15 utc.
rotated syslog on dev-server records successful completion at all seven scheduled slots.

the november 20 drill reopened both copies. the seven scheduled checks
verified manifests and object sizes. subsequent releases have their own
[restore receipts](0105-native-android.md#installed-release-on-november-24-utc). the second decryption identity
awaits the home workstation.

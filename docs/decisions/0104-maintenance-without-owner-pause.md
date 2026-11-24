# adr 0104. maintenance without an owner pause

**approved implementation scope.** on november 23 pacific, eight production pause/resume pairs stopped 21 distinct requests and cancelled zero actions. the assistant spent 3 h 10 min paused, including necessary maintenance. a previous compatible upgrade already preserved the owner's resume. [installed example](0087-private-web-home.md#production-cut-2026-11-19-utc) · [mail cut](0101-outgoing-mail-attachments.md)

## decisions

1. authorization of a named production change includes restoring service after its stopped checks. this covers migrations and permission changes. ask again for a change of scope or a specific unresolved decision.
2. only the owner changes canonical `pause`/`resume`. a real pause still cancels unentered approvals. maintenance preserves compatible work and creates zero chat controls. honor every committed submission, including a pause racing shutdown. the existing web outage, browser draft and same-id submission retry suffice.
3. go-live follows stopped safety checks. an authorized send may start before web health answers. on observed startup failure, contain further work and reconcile anything that started. controller loss can require an operator retry.
4. an incompatible obligation holds the update unless its exact disposition is already authorized and supported by its original contract. before mutation, return the intact source automatically **only if it can safely serve the decision**. if startup could execute the disputed action, or safety is unproved, keep it held and ask the owner. after mutation, repair forward.

this amends spec §§8–9 and the prospective maintenance rules derived from adr 0072. historical cut records keep their original meaning. [owner control](../one-main-events.md#stop-and-administrative-control) · [native loss and effect recovery](0086-native-recovery-and-memory-availability.md)

## a. deployment owns the hold

**operator api.** use `deploy/activate-release --change ID TARGET`, `deploy/install-private-state --change ID` and `deploy/provision-memory-backup --change ID TARGET [--reader-image DIGEST]`. one operator-generated uuid per named change. use the existing workstation key, `dev-server-deploy` and `sudo -n`. the host runs the operation under the release flock. after a disconnect, inspect `deploy/cutover-hold status ID --json` and retry with the same id and arguments when the facts support continuation. application, web and model grants stay as specified.

**storage.** reuse `/var/lib/jarvis-cutover` on boot-available local storage. one active `held/` directory and a private per-change receipt. bind id, operation, exact source/target release receipts and schemas, staged input references/digests and intended units. keep secrets in protected staging. operation identity cannot substitute for owner authorization. unit marker files under `held/` control systemd start eligibility. a durable `applying` flag means mutation may have begun. terminal receipt locations distinguish `not-applied-ID` and `committed-ID`; a later repair references its parent. no application schema change.

1. **before outage.** stage and authenticate inputs. take the exclusive `/opt/jarvis/.deploy.lock`, letting an existing backup finish. verify source, operation and persistent enablement. preserve masks and disabled services. unexpected active/enablement combinations need an explicit intended state. verify the permanent service guards are installed and loaded while the source still serves. as the last pre-hold check for an assistant stop, wait up to 120 s for zero unfenced native attempts without a product outcome and zero executing actions. refuse busy with the request/action id. a failed precheck leaves the source as found. a wedged predecessor uses named incident recovery.
2. **close.** immediately publish the complete root-owned hold directory by same-filesystem rename and fsync before the first stop. guard the affected services, including the backup service. keep the timer's persistent policy. a hold blocks overlapping installs, pruning and independent maintenance, even after a reboot. stop gracefully, join admitted web callbacks, verify no remaining jobs, pids or populated cgroups, then take the required postgres keys, assistant before memory. helpers use the outer flock once and existing database ownership at the point of use. a turn admitted after the idle check follows normal shutdown recovery. its retry can be spent or its input parked. [unit conditions](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html#ConditionPathExists=) · [directory durability](https://man7.org/linux/man-pages/man2/fsync.2.html)
3. **decide before applying.** for assistant changes, read the control id/sequence/kind/targets and original authority after ingress closes. run b on source obligations against staged target settings. if the target requires the new schema, qualify it on a verified copy of this stopped snapshot before production mutation. apply decision 4 to both obligation conflicts and failed target checks. if zero mutation and safe source startup are proved, durably rename the hold to `not-applied-ID`, start the intended source units and verify readiness. report the failed check or blocker through the operator conversation. otherwise leave it held.
4. **apply and release.** durably mark `applying` before the first change to selected code, configuration, grants or data. apply the named operation. verify target settings, schema, b and the cut's recovery evidence under exclusion. if needed, durably install then release only the contained host to verify its private socket while writers stay held. fsync changed files, unit definitions, selection renames and parent directories. release postgres keys. sync the passing receipt inside the hold, rename the whole directory to `committed-ID` on the same filesystem, and fsync its parent before issuing starts. verify actual processes, sockets, private web and memory. prune only after readiness.
5. **recover.** same-id retry verifies actual state and already-applied steps. after commit it finishes starts/probes only while the bound target still owns the installation and there is no observed startup failure. a superseded receipt reports history. on observed startup failure publish a repair hold referencing the committed receipt before stopping affected services. preserve effect evidence and report the new failure. an observed startup failure or changed repair inputs require a new authorized id with `--repair-of HELD_ID`. verify and transfer custody under the flock without clearing unit guards. a return to the source through this path requires proof of zero mutation and any specific owner decision to run the disputed work. an uncertain or changed installation requires forward repair.

for a successor schema, resume the same named release with `--qualification FILE` after the isolated restore and target checks. when backup is configured, a changed target lock or schema also requires `--reader-image DIGEST` from the verified recovery kit. bind that reader to the release and publish it under the same backup hold. the serving release keeps one verified stopped recovery copy and compact receipts for earlier changes.

## b. jarvis owns work compatibility

extend the read-only `jarvis check-activation`. reuse `require_current_action_binding`, existing receipts and the original reconciler. inventory pending/waiting requests **and** the current pause's stopped targets. preserve input ids, deadlines, waits, native seals, retry budgets and paid-read barriers. the owner control is never restored from a saved copy.

| finding | action |
| --- | --- |
| queued action, awaiting approval or registered worker wait | retain the exact id, payload, consent, attempts and target if the candidate passes the frozen binding and existing owner/resource authority. reject executable foreign-scope rows. |
| authority changes for pending work | compare existing evidence for the affected account, resource and grant. missing original identity blocks a changed-authority cut. do not backfill it. an unchanged verified subject may rotate credentials. an authorized change with zero affected obligations may proceed. |
| executing, uncertain or historical | keep an entered action only when its original binding and authority still validate and startup can settle it under its original recovery procedure. retain supported terminal historical uncertainty and its barriers. unsupported outstanding effects hold. approval cannot prove whether gmail sent a message. |
| target rejects work | to restore the source, prove its selection, schema and settings are intact and its startup recovery cannot enter the disputed effect. prove the source still accepts that work. settle through its existing approval or reconciliation path. a prior exact authorization can use an existing scoped procedure. expose no stopped action-edit capability. |

the stopped check executes nothing. existing entry checks remain authoritative. external workers already running retain their own lifecycle.

## c. adopt through existing commands

implementation starts from the installed `0022` release `ea2b825`, which includes both the `a612c51` lineage and main's chat-order fix from `6d8976e`. verify the source again before adoption. verify no legacy hold is active, install the persistent conditions on the running predecessor, then use the compatible target to adopt the machinery before changing private settings. retire dated migration switches from the active installer. keep issued migrations immutable.

| owner | exclusive patch boundary |
| --- | --- |
| a · custody and operator status | `deploy/{activate-release,cutover-hold,release-functions,install-contained-host}`, release install/prune and unit guards |
| b · obligations and blocker text | `src/jarvis/cli.py` activation verdicts, `native_cutover.py` resumable inventory, existing validation in `actions.py` / `write_dispatch.py` |
| c · consumer commands and runbook | `deploy/{install-private-state,memory_credentials.py,provision-memory-backup,memory_backup_credentials.py,prepare-cutover}`, native inventory/gmail audit guard only, `docs/operations.md` and adoption links |

full release/schema/grant changes use the owning writer locks and held operation. include live agent-client publication inside custody. reader-only mode drains the backup job, including a queued job with snapshotted credentials, under the release flock and backup-service guard. verify the qualified image against the selected lock/schema and atomically publish only `reader_image`. both writers stay online. a backup occurrence during a hold can be skipped until the next schedule. single-writer repairs keep their scope. preserve online backup, isolated restore and virgin bootstrap's first owner enablement. a production restore over newer controls or effects needs its own loss decision. no new control service, maintenance ui or workflow engine.

## acceptance

a and b proceed independently. c consumes both. before red, each feature's content designer freezes good and misleading outputs. a names the actual selection, owner control and serving state. b names the disputed id, evidence and decision. c reports the changed setting/grant and backup policy without credentials. good examples are “source serving. approval `4be9…` still awaits your decision” and “target committed. web startup failed. send `4be9…` may have reached gmail.”

| temporary real-entry journey | observable pass |
| --- | --- |
| a · systemd and pg16 on macbook | busy refusal spends zero retries. force the admission race. interrupt before first stop, between stops, during mutation and immediately after commit. reboot, race another operator/timer, retry. check exclusion, actual selection, enabled services, next backup and post-start containment. |
| b · web submission through activation and startup | race owner pause and lost acknowledgement. carry over an approved send, an awaiting approval, worker wait and native/read evidence. change the account under an equal binding. prove both safe source return and held disputed-send branches, with original ids, status, receipts and executor counts. |
| c · release, private provisioner and backup-reader update | reproduce the old pause refusal. verify target grants, reader restore and zero maintenance control messages under both real owner states. prove the reader change keeps both writers online. wrong release or live required writer refuses mutation. |

use dev-server's `scripts/rehearse-worktree` on macbook with actual packaged services and controlled external effects. independent claude opus reviews each feature and the integrated cut. refactor, rerun the observable journeys, delete only these temporary probes, reopen and hash named evidence outside scratch, and record fixture cleanup. a separately authorized installed journey verifies the real release and owner state without manufactured chat controls.

## implementation evidence

claude opus passed the source at `edf57df`, the protected staging cleanup at `7ffbad9` and the idle preflight diagnostic at `2f71411`. the macbook guest used systemd 255, postgres 16 and packaged jarvis. rehearsal-only schemas exercised transactional migration, rejected a mismatched dump receipt and adopted the qualified reader under the same hold. the packaged release, startup failure and repair, reboot and same-id continuation preserved the exact stopped owner control.

the original activated action's gmail recovery kept one executor entry for both a proved send and an unknown outcome. the connector and native provider were controlled fixtures. private provisioning preserved an owner pause and a resume. the backup run with the old reader completed, the next run used the replacement, and the isolated restore opened the witness event and note. the retained evidence records the exact artifact for each check.

production adoption selected `4d05a9267d123deb4327470606b28145f47bbb12` at
schema `0022` in committed change `5581545e-79a3-4b1e-97cf-3e2d69ea343f`.
all units served, owner resume 42 and the five parked requests matched their
before-cut inventory, and the qualified reader was active with the next
backup scheduled. evidence is in
`~/.local/state/jarvis/qualification/adr0104-installed-adoption/`.

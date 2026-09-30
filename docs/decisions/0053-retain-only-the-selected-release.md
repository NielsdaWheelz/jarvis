# adr 0053: retain only the selected release

- status: accepted by the owner's 2026-09-30 release-cleanup instruction.
- amends: adr 0031's deployment policy and adr 0047's temporary normalizer
  handling. immutable releases, activation checks and journal semantics remain.

## evidence

the host accumulated twenty complete releases using 7.7 gib. installation copied
each commit's interpreter and packages; successful activation never removed old
copies. the runbook assumed installed rollback and migration releases remained.
the owner requires cleanup of every unselected release and prevention of buildup.

## decision

`/opt/jarvis/current` selects the sole retained release, including while the
service is stopped. installation may prepare one additional candidate, clearing
older candidates first. failed construction removes its new tree. successful
activation prunes all other releases after startup checks pass. failed activation
does not prune; the operator repairs it or explicitly discards inactive trees.
installation, activation and pruning share one host file lock.

`deploy/prune-releases` removes abandoned candidates without activation. rollback
and the pinned journal normalizer are rebuilt from their exact commits when
needed. discard a temporary normalizer after preparation. there are no retained
recovery releases; source rebuild replaces immediate local code rollback.
use `deploy/install-release <full-commit>` from the maintained checkout for those
builds, so historical deployment scripts cannot bypass the current policy.

## verification

check shell syntax and exercise selection, staging, invalid-pointer refusal and
running-process refusal in a disposable filesystem. run `scripts/verify` under
adr 0046. live activation remains a separate operation; cleanup neither changes
private state nor starts, stops or resumes the service.

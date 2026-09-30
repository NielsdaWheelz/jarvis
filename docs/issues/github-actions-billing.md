# github actions cannot start

problem: github refuses to start repository workflow jobs because recent account
payments failed or the account spending limit needs to be increased. the
annotation does not distinguish which condition applies.

impact: ci failures supply no verification evidence; no runner executes the
checks. local verification remains available.

evidence (2026-09-30): [pr 44's verify job](https://github.com/NielsdaWheelz/jarvis/actions/runs/36767535267/job/110065360286)
has no logs and reports that billing/spending restriction in its failure
annotation. the push run failed to start as well.

resolved when: the account owner resolves the github billing/spending condition
and a new workflow run actually starts and executes the verification steps.
the separate [dependency audit issue](urllib3-security-update.md) still needs
resolution for a green verification result.

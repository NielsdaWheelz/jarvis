# github actions cannot start

problem: the repository's hosted verification job cannot start because github
reports an account billing or spending-limit restriction. prs receive a failed
check without executing any verification step.

evidence: main commit `011ead27cd935417072e609da2263dbeaa1d36af`,
[run 35031548023](https://github.com/NielsdaWheelz/jarvis/actions/runs/35031548023),
check `104590969543`; its annotation says recent payments failed or the spending
limit must increase. the job has no steps or logs.

2026-09-29: worker-cutover commit `cbd0ccd5a2de49da9c3835825b3b7609146c54aa`
is affected too. push run `36659377425` and pr run `36659380727` have no steps;
the annotation reports the same billing restriction. clean-checkout local
`scripts/verify` passed. hosted verification remains unrun.

resolved when the account restriction is corrected and the exact-head hosted
workflow runs successfully. local `scripts/verify` can establish static and
build verification while this is unresolved; under adr 0046 it runs no behavioral
tests. it does not establish hosted ci success.

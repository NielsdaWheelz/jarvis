# qualify five-minute gmail reception

open, november 24, 2026. [design 0107](../decisions/0107-google-workspace.md) selects an owner-configured gmail filter and one pending label. every five minutes jarvis checks the label count through google mcp. it searches on a positive count and clears only the tag on each message after recording the event. the owner selected standard with the last 1,000 of 5,000 daily gmail units reserved for direct requests. the feature still needs isolated live proof.

**why qualify it.** the installed one-minute rest history feed names new message ids. the public mcp server advertises no such feed. gmail’s documented push uses rest watch and history. the selected design observes surviving, visible labels. an item removed or hidden before observation may leave no evidence. reported counts can lag. an owner or google policy can interrupt an unattended call. [installed contract](../decisions/0096-calendar-on-demand.md) · [gmail push](https://developers.google.com/workspace/gmail/api/guides/push) · [gmail filters](https://developers.google.com/workspace/gmail/api/guides/filter_settings) · [label counts](https://developers.google.com/workspace/gmail/api/reference/mcp/tools_list/list_labels)

**quota estimate.** 288 label checks per 24-hour day cost 288 units. each
search page costs ten units. budget one unit for each thread read, each tagged
message verified, each acknowledgement and each follow-up label count.
restarts, retries and foreground traffic add to the total. on november 24
before 19:00 pacific, 154 installed arrival records occupied 45 buckets.
a simple model with one page per bucket costs 738 units for the initial counts
and searches alone. add the actual thread and message reads and feedback checks
to qualify the workload. an unchanged positive residue triggers 48 rescans per
24-hour day at most. single-page rescans add 480 units for searches plus any
thread and message reads. measure actual mcp usage before any tier decision.
[google’s weights and limits](https://developers.google.com/workspace/gmail/api/guides/quotas#gmail-mcp-toolsets)

**exit.** use an authorized synthetic mailbox to qualify the rule, grant and five-minute cadence through the normal poll task. cover archived and alias/bcc mail, replies to old threads, withheld items followed by a fresh arrival and equal-count turnover, a renamed or recreated label, multi-page drain and restart on both sides of the record/ack boundary. prove delayed polling leaves the backlog in gmail. check foreground use, the reserve, quota reset and truthful reporting of incomplete coverage. verify overlap with the predecessor before retiring it. live source evidence and the separate [history-permission decision](google-workspace-retention.md) still gate real-account rollout.

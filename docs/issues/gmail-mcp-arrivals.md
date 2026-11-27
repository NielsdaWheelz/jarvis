# qualify five-minute gmail reception

open, november 24, 2026. [design 0107](../decisions/0107-google-workspace.md) selects an owner-configured gmail filter and one pending label. every five minutes jarvis checks the label count through google mcp. it searches on a positive count and clears only the tag on each message after recording the event. the installed predecessor reserves the last 1,000 of 5,000 daily units for direct requests. [adr 0132](../decisions/0132-one-main.md) shares the full allowance. the target still needs live proof.

**why qualify it.** the predecessor’s one-minute rest history feed named new message ids. the public mcp server advertises no such feed. gmail’s documented push uses rest watch and history. the selected design observes surviving, visible labels. an item removed or hidden before observation may leave no evidence. reported counts can lag. an owner or google policy can interrupt an unattended call. [predecessor contract](../decisions/0096-calendar-on-demand.md) · [gmail push](https://developers.google.com/workspace/gmail/api/guides/push) · [gmail filters](https://developers.google.com/workspace/gmail/api/guides/filter_settings) · [label counts](https://developers.google.com/workspace/gmail/api/reference/mcp/tools_list/list_labels)

**installed outage, november 27.** at 18:15 utc, release `6e6c8a4` had gmail
enabled, no next poll and no completed scan on the enrolled cursor. the last
recorded arrival was observed at 02:33:42 utc on november 26. the outage
opened at 02:46:58 as `RateLimited`, with a retry scheduled for 08:00 utc.
the same episode now reads `ConsentRequired`. the cursor retains neither the
challenged operation nor the transition time. no pending acknowledgment is
recorded. mail coverage since the last observation is unknown.

the installed poller publishes the first outage and eventual recovery. changing
from a timed retry to an indefinite wait for the owner updates the cursor
without publishing a new status input. the earlier reply therefore describes
the quota limit. subsequent foreground approvals do not re-arm the poller.
[status publication](../../src/jarvis/events.py)

at 20:21:57 utc the owner re-armed reception. by 20:22:02 the same consent
block had recurred. the day's jarvis meter showed 12 gmail units, with no
foreground gmail calls that day. the normal path charges one unit to count
the label, ten to find threads and one to read the first thread's metadata.
this points to `get_thread`; the meter is not a per-call receipt. the previous
foreground google choice for that operation covered one thread. the installed
`gmail.read_thread` calls the same metadata operation from authenticated chat.

**installed recovery.** an owner-present search of the pending label followed
by a metadata read of its first thread produced a google `get_thread` prompt.
at 20:26:42 utc on november 27 google's recorded choice was
`ALLOW_TOOL_ALWAYS`. the read succeeded. `events.configure(enabled=true)`
re-armed the receive loop at 20:26:48. it recorded 34 distinct arrival ids
and committed its first completed scan and recovery fact at 20:27:41.
the label still reported nine messages. the scan found no further eligible
visible arrival. the status therefore retained incomplete coverage and a
rescan deadline of 20:57:41 for an unchanged count. the next automatic
five-minute poll completed at 20:32:41, consumed one gmail unit, retained
the same count and scheduled 20:37:41. no further owner action intervened.

the transition to an owner-required repair remains silent.
[adr 0132](../decisions/0132-one-main.md) owns the interaction. exercise a timed
retry followed by a consent block and check that the owner hears once when
intervention becomes necessary and can tell which operation needs attention.
account separately for surviving backlog and any messages whose arrival can
no longer be verified.

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

**exit.** use approved synthetic mail to qualify the rule, grant and five-minute cadence through the normal poll task. cover archived and alias/bcc mail, replies to old threads, withheld items followed by a fresh arrival and equal-count turnover, a renamed or recreated label, multi-page drain and restart on both sides of the record/ack boundary. prove delayed polling leaves the backlog in gmail. check shared quota, quota reset and truthful reporting of incomplete coverage. carry the stopped predecessor cursor through the hard cut. live source evidence and the separate [history-permission decision](google-workspace-retention.md) still gate real-account rollout.

# openai dots: public product and implementation evidence

as of 2026-11-14. public research only; no account access, signup, grants, or execution trials. “documented” means an official product contract, not independent verification. “vendor claim” marks a stated capability or example without a reproducible acceptance result. “unknown” means the reviewed public evidence does not establish it.

dots launched on september 29. the relevant product is one persistent personal agent, with a cloud computer and optional delegated work. specialist organizational dots are a separate pilot. the launch announcement was updated november 3 to include GPT-6.1 Terra alongside GPT-6 Astra; launch-only descriptions are therefore insufficient. [launch](https://openai.com/index/introducing-dots/)

## feature inventory

ids identify features, not implementation tasks. availability remains subject to plan, rollout, workspace, and connected-service restrictions.

| id | feature | observable behavior or contract | status | evidence/source |
|---|---|---|---|---|
| DOT-01 | personal agent | one personal dot per member; ongoing work across conversations | documented | [meet dots](https://learn.chatgpt.com/docs/dots) |
| DOT-02 | individual eligibility | pro users 18+ outside the eea, uk, and switzerland; business premium in supported regions | gradual rollout | [getting started](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot) |
| DOT-03 | organizational eligibility | enterprise, edu, healthcare; admin preview november 4–18, default access november 18 unless opted out; uae residency excluded | documented | [workspace management](https://help.openai.com/en/articles/20001554-managing-dots-in-chatgpt-workspaces) |
| DOT-04 | setup | mobile app, desktop app, desktop web; optional plugins; mobile web unsupported | documented | [setup guide](https://learn.chatgpt.com/docs/dots/getting-started) |
| DOT-05 | identity and appearance | name, handle, shape, color, eyes, glasses, accessories; change later | documented | [meet dots](https://learn.chatgpt.com/docs/dots) |
| DOT-06 | mobile home | optionally open chatgpt directly to the dot | shipped october update | [mobile update](https://learn.chatgpt.com/docs/whats-new/dots-october-9-2026) |
| DOT-07 | behavior preferences | dot-specific instructions, separate from chatgpt instructions; conversational updates or behavior editor | rollout | [controls](https://learn.chatgpt.com/docs/dots/controls) |
| DOT-08 | voice | user-started call; simultaneous typing; assigned work continues afterward; outgoing calls planned | documented | [messaging](https://learn.chatgpt.com/docs/dots/channels) |
| DOT-09 | voice model | GPT-Live-1.1 is the default voice model including dots; full-duplex audio | documented model assignment | [voice system card](https://deploymentsafety.openai.com/gpt-live-1-1/respecting-warnings) |
| DOT-10 | workplace messaging | slack dm/channel mentions and teams; private context does not automatically authorize disclosure | documented; teams limited | [messaging](https://learn.chatgpt.com/docs/dots/channels), [workspace management](https://help.openai.com/en/articles/20001554-managing-dots-in-chatgpt-workspaces) |
| DOT-11 | texting | limited pro beta in us, canada, mexico; iMessage/RCS; no sms, group texts, or phone-number calls | current help contract | [getting started](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot) |
| DOT-12 | texting payloads | text, photos, voice messages; approval requests link back to chatgpt | shipped beta | [texting update](https://learn.chatgpt.com/docs/whats-new/dots-october-28-2026) |
| DOT-13 | mobile entry points | notification replies, share sheet, widget, shortcuts; messaging, dictation, call modes | rollout | [messaging](https://learn.chatgpt.com/docs/dots/channels) |
| DOT-14 | activity view | inspect progress, files, results, delegated tasks, pending decisions and connections | documented | [controls](https://learn.chatgpt.com/docs/dots/controls) |
| DOT-15 | conversational continuity | new priorities enter the same ongoing relationship; several responsibilities supported | documented | [setup guide](https://learn.chatgpt.com/docs/dots/getting-started) |
| DOT-16 | parallel delegation | background agents report back; visible cloud threads; local tasks remain on their original computer | documented | [tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory) |
| DOT-17 | codex orchestration | start work, follow existing threads, use existing codex context and automations | shipped october update | [mobile update](https://learn.chatgpt.com/docs/whats-new/dots-october-9-2026) |
| DOT-18 | recurring work | saved schedules; inspect, change, cancel; edit existing work automations | documented | [tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory) |
| DOT-19 | event triggers | supported connected-service events; connecting a source alone does not establish monitoring | conditional | [tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory) |
| DOT-20 | autonomous follow-up | dot can decide when to pause and wake for assigned work | documented; timing algorithm unpublished | [meet dots](https://learn.chatgpt.com/docs/dots) |
| DOT-21 | unsolicited research | read permitted sources, keep private notes, suggest useful follow-up; no direct writes/browser/desktop control | restricted background mode | [safety explanation](https://openai.com/index/how-we-build-safety-security-and-privacy-into-dots/) |
| DOT-22 | memory | relevant chatgpt memory plus separate dot notes; selected context, not guaranteed complete transcript | documented | [tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory) |
| DOT-23 | past-chat search | find previous chatgpt discussions; review retrieved decisions before reuse | documented | [personalization walkthrough](https://developers.openai.com/training/walkthroughs/personalize-your-dot) |
| DOT-24 | memory controls | no individual dot-memory viewing, editing, or deletion; delete dot to start context deletion | documented limitation | [privacy faq](https://help.openai.com/en/articles/20001529-dots-privacy-security-and-safety-faqs) |
| DOT-25 | plugin ecosystem | launch claims over 4,000 apps; actual availability and permissions vary | vendor breadth claim | [launch](https://openai.com/index/introducing-dots/) |
| DOT-26 | shared connections | plugin permissions shared with chatgpt, work, codex; disconnection stops new access, not retained knowledge | documented | [privacy faq](https://help.openai.com/en/articles/20001529-dots-privacy-security-and-safety-faqs) |
| DOT-27 | cloud computer | persistent files/software/browser sessions; inspect, take over, return control; works while personal devices are off | documented | [computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps) |
| DOT-28 | local computers | separately opt in on each computer; local work needs computer online and app open | documented | [computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps) |
| DOT-29 | website login | private credential form or manual takeover; saved-login reuse needs confirmation | documented | [computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps) |
| DOT-30 | cloud coding | use a codex cloud environment prepared with repository/setup beforehand | documented | [computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps) |
| DOT-31 | annotations | point to regions of browser pages, pdfs, documents, decks, spreadsheets | desktop rollout | [november update](https://learn.chatgpt.com/docs/whats-new/november-2-6-2026) |
| DOT-32 | deliverables | research, analysis, documents, software; launch examples include tested prs/videos and updated figures | capability claim | [launch](https://openai.com/index/introducing-dots/) |
| DOT-33 | sharing and collaborators | owner directs personal dot; others’ messages do not independently authorize work; owner can authorize engagement | documented | [workspace management](https://help.openai.com/en/articles/20001554-managing-dots-in-chatgpt-workspaces) |
| DOT-34 | action policy | custom rules vary independence, explicit request, confirmation, or human handoff; safeguards remain binding | documented | [controls](https://learn.chatgpt.com/docs/dots/controls) |
| DOT-35 | sensitive operations | password changes and money transfers require takeover; destructive operations may need fresh confirmation | documented | [privacy faq](https://help.openai.com/en/articles/20001529-dots-privacy-security-and-safety-faqs) |
| DOT-36 | automatic review | separate action assessment; may allow, block, request clarification/approval | documented mechanism | [auto-review](https://learn.chatgpt.com/docs/sandboxing/auto-review), [astra appendix](https://deploymentsafety.openai.com/gpt-6-astra/change-log) |
| DOT-37 | wallet payments | dots-only pro us rollout, 18+, eligible us credit card/billing address; biometrics for each purchase | launched november 13 | [wallet help](https://help.openai.com/en/articles/20001654-making-purchases-with-chatgpt-wallet) |
| DOT-38 | payment credentials | network token substitutes for actual card details after approval | documented mechanism | [wallet announcement](https://openai.com/index/introducing-chatgpt-wallet/) |
| DOT-39 | interruption | main pause, delegated-task stop, schedule cancellation are separate controls | documented limitation | [controls](https://learn.chatgpt.com/docs/dots/controls) |
| DOT-40 | reset | deletion irreversible; main conversation archived; separate work/codex chats remain | documented | [getting started](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot) |
| DOT-41 | recovery ux | retry activity loading; visible blockers; correct affected task; no public effect-replay contract | partial disclosure | [mobile update](https://learn.chatgpt.com/docs/whats-new/dots-october-9-2026), [personalization walkthrough](https://developers.openai.com/training/walkthroughs/personalize-your-dot) |
| DOT-42 | enterprise inventory | owner/status/identity; admin pause, resume, delete, revoke; usage and audit exports | documented | [admin guide](https://learn.chatgpt.com/docs/enterprise/dots-admin-guide) |
| DOT-43 | cloud capability controls | browser, code networking, desktop interaction separately configurable; local access separate | documented | [workspace management](https://help.openai.com/en/articles/20001554-managing-dots-in-chatgpt-workspaces) |
| DOT-44 | specialist dots | dedicated organizational identity/responsibility; engineering-assisted pilots; agent 365 integration proposed | pilot/future | [launch](https://openai.com/index/introducing-dots/) |
| DOT-45 | enterprise protection | encrypted transit/storage; eligible enterprise customer-managed keys and HIPAA/BAA configurations, subject to service restrictions | documented | [privacy faq](https://help.openai.com/en/articles/20001529-dots-privacy-security-and-safety-faqs) |

## disclosed mechanisms and their limits

### execution, persistence, and delegation

documented mechanism: the safety article identifies maintained linux/chrome environments, cross-user isolation, sandboxed code, and separation between executable workspace and coordination/safety systems. secure login pauses the model; credentials go directly to the browser. saved passwords use a separate encrypted credential service. proactive research restrictions are enforced in code, not merely requested in its prompt. [safety explanation](https://openai.com/index/how-we-build-safety-security-and-privacy-into-dots/)

the enterprise security guide says dots share work’s infrastructure and preserve snapshots. work’s infrastructure document describes vm-backed sandboxes on shared infrastructure. this supports infrastructure reuse, not an assertion that every dot operation has identical work/codex tools or policies. dedicated physical hosts, exact snapshot cadence, crash-consistent checkpoint contents, and external-effect journaling remain unpublished. [dots security](https://learn.chatgpt.com/docs/enterprise/dots-security), [work cloud security](https://learn.chatgpt.com/docs/enterprise/chatgpt-work-cloud-security)

the astra appendix discloses time-budget and reasoning-effort controls and a dots-specific confirmation policy. it is not evidence of a continuously running inference process, a particular queue/database, or a user-visible one-year execution allowance. [astra appendix](https://deploymentsafety.openai.com/gpt-6-astra/change-log)

inference: “always on” describes availability and continuing responsibility; the documented pause/wake and delegation behavior permits intermittent execution. idk how the production scheduler allocates work or resolves competing goals. no public maximum worker count or concurrency entitlement was established.

### context is selected; memory is not a transcript

the task guide separates active context, chatgpt memory, and the dot’s changing notes. delegated work gets task-specific instructions/context; voice and background work may receive different selections. neither a shared assistant identity nor cross-channel continuity establishes universal context replication. the particular retrieval, compression, embedding, note-schema, or conflict-resolution algorithm is unknown. [tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory)

the training guide recommends correcting reusable guidance, saving a reviewed working guide, and repeating essential requirements. it explicitly warns that a promise to remember is inadequate: inspect a later result. this is an observable preference-learning workflow, not proof of online weight updates or reliable autobiographical recall. [personalization walkthrough](https://developers.openai.com/training/walkthroughs/personalize-your-dot)

### authority is route-specific

documented mechanism: auto-review is a separate reviewer agent. its general documentation describes an action request plus compact transcript/tool evidence, excluding hidden reasoning. dots’ appendix independently confirms adaptation with dots-specific policy. codex cli denial thresholds, local configuration files, and override commands are not established dots contracts. [auto-review](https://learn.chatgpt.com/docs/sandboxing/auto-review), [astra appendix](https://deploymentsafety.openai.com/gpt-6-astra/change-log)

the enterprise guide expressly marks review coverage across browser, desktop, and delegation as under review. a read-only plugin therefore does not prove a global no-write capability if a signed-in browser remains enabled. cloud browser site-policy support is still developing. these are meaningful gaps between policy and enforced routes. [dots security](https://learn.chatgpt.com/docs/enterprise/dots-security)

custom rules are instructions the dot tries to follow; they do not grant missing app access. pause stops the main task without necessarily stopping workers or future schedules. a completed run is not equivalent to achieved delivery. these distinctions matter more than the anthropomorphic surface. [controls](https://learn.chatgpt.com/docs/dots/controls)

### payments: new, narrow, and not fully autonomous

documented mechanism, november 13 launch: the user reviews purchase details and authenticates; the network then supplies tokenized card credentials. parameters for entirely delegated pre-approved purchasing are described as future work. the merchant remains responsible for fulfillment, returns, and support. [wallet announcement](https://openai.com/index/introducing-chatgpt-wallet/)

wallet setup uses a secure form, not chat. debit and externally supplied virtual cards are unsupported. approval means checkout may continue; it does not establish order placement. after ambiguous failure, inspect the merchant’s confirmation before retrying. recurring merchant charges follow the agreement authorized at checkout. [wallet help](https://help.openai.com/en/articles/20001654-making-purchases-with-chatgpt-wallet)

merchant implementation: ordinary checkout pages need no wallet-specific integration. the documented rollout can relay user-related fraud/location signals through `Forwarded`; available fields include observed ip/network, locale, timezone, and user agent. network tokens differ from actual card numbers. consent covers the specific purchase; recurring billing requires separate appropriate consent. this is substantially more concrete than generic “agent can shop” marketing. [payment acceptance](https://developers.openai.com/commerce/guides/accept-payments)

### privacy, transport, retention, and inspection

documented: chatgpt memory sharing is bidirectional and can continue after setup; disabling it does not erase already received context. personal model-improvement settings govern eligible conversations/work; business data is not trained on by default. research notes are not directly training material, but information incorporated into eligible work can become eligible. human safety review remains possible. [privacy faq](https://help.openai.com/en/articles/20001529-dots-privacy-security-and-safety-faqs)

texting uses linq. messages are not end-to-end encrypted between user and dot; linq processes delivery and may retain delivery metadata. the current help page supports canada/mexico as well as the us, while the october rollout announcement describes the us. use the narrower applicable account rollout rather than assuming universal availability. [getting started](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot), [texting update](https://learn.chatgpt.com/docs/whats-new/dots-october-28-2026)

enterprise records identify dots using `client_id = DOTS`; analytics and compliance are distinct. admin actions are audited, while tool-call records do not prove receiving-service completion. review the external service too. admins do not thereby acquire the member’s personal activity/schedule interface. [admin guide](https://learn.chatgpt.com/docs/enterprise/dots-admin-guide), [workspace management](https://help.openai.com/en/articles/20001554-managing-dots-in-chatgpt-workspaces)

enterprise security describes deletion of dot context, research history, and dot-owned backups within 30 days, with other stored artifacts managed separately. compliance records have incomplete outcomes/links and a 30-day platform retention window. granular memory export, portable assistant state, and a full personal audit export were not established. [dots security](https://learn.chatgpt.com/docs/enterprise/dots-security)

## pricing, limits, and evidentiary quality

pro subscriptions are $100/$200/$500 monthly; that is subscription pricing, not a price per dot execution. current dots documentation includes all three pro tiers and business premium, with conversations outside normal chatgpt limits and deeper-work allowances. delegated work/codex still consumes their limits. no precise current universal deeper-work quota was established. [pricing](https://learn.chatgpt.com/docs/pricing), [meet dots](https://learn.chatgpt.com/docs/dots)

enterprise preview is free through november 18; billing then begins for enabled dots. published options are work-type flat rates or consumption, with separate delegated-task charges; exact dollar schedules were not found. admin pause stops dot billing, but separate work needs separate review. [admin guide](https://learn.chatgpt.com/docs/enterprise/dots-admin-guide)

vendor evaluation, not production prevalence: the astra appendix reports 45/49 passes on changing-scope episodes and moderate boundary-violation flags rising from 8.6% to 19.7% with more intervening tasks. it acknowledges known vulnerabilities and adversarial sampling. these results cannot establish a real-world reliability rate. [astra appendix](https://deploymentsafety.openai.com/gpt-6-astra/change-log)

observed third-party report: axios described launch-demo voice lag. that establishes one reported demo failure, not current latency or general service reliability. no independent task trials were performed for this dossier. [axios](https://www.axios.com/2026/09/29/openai-dots-ai-assistant-devday)

## concrete workflows worth understanding

- offsite coordination: explain decisions, deadlines, unanswered questions, source documents, and review boundaries; permit drafts, decide notification criteria, then verify the saved schedule. this is the setup guide’s responsibility-based onboarding pattern. [setup guide](https://learn.chatgpt.com/docs/dots/getting-started)
- distributed coding: begin from a phone, have the dot start or continue codex work, inspect the resulting thread, and steer that work directly. october changes explicitly added existing-thread/automation context and improved thread reuse. [mobile update](https://learn.chatgpt.com/docs/whats-new/dots-october-9-2026)
- targeted revision: annotate a specific browser region or file passage; inspect the actual artifact afterward. the november update documents annotation rollout and windows local-task reliability improvements, rather than promising identical behavior everywhere. [november update](https://learn.chatgpt.com/docs/whats-new/november-2-6-2026)
- purchase completion: ask for a hotel/product, review the payment request and biometric approval, then verify merchant confirmation. existing checkout compatibility is the disclosed integration strategy; acceptance is not universal. [wallet help](https://help.openai.com/en/articles/20001654-making-purchases-with-chatgpt-wallet), [payment acceptance](https://developers.openai.com/commerce/guides/accept-payments)

## unresolved evidence gaps and transferable questions

email identity remains ambiguous: setup help says no standalone dot email address at launch, while the privacy faq mentions an own email account. neither establishes general provisioning today. [setup help](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot), [privacy faq](https://help.openai.com/en/articles/20001529-dots-privacy-security-and-safety-faqs)

unknown: production scheduler/queue, storage schema, compaction/retrieval policy, worker ceilings, model routing, per-operation timeouts, connector polling versus subscriptions by service, tool catalog/versioning, idempotency keys, approval-to-execution binding, crash recovery, duplicate-effect reconciliation, private-network access guarantees, export formats, complete cloud audit coverage, and current account-specific deeper-work quotas. no public source code or backend configuration was found. public capability descriptions cannot fill these gaps.

important distinctions for comparison: one assistant identity does not mean one conversation context; retained notes do not mean transcript retention; revoking an integration does not erase learned data; stopping the coordinator does not stop delegated execution; task completion does not prove an external effect. these are conceptual questions, not evidence that jarvis should acquire dots’ scope.

after reading `AGENTS.md` and `SPEC.md`, the transferable questions are:

1. can the owner tell which work remains live, which work awaits a decision, and which result is actually verified?
2. what exactly does stop fence: coordinator, workers, schedules, and effects already entered?
3. where is the boundary between quiet synthesis and newly authorized outward action?
4. which context crosses a delegation boundary, and how does the owner correct stale guidance?
5. can a capability restriction be bypassed through another permitted route?
6. what evidence survives process loss, and what proves safe non-repetition of an ambiguous effect?
7. which memory and artifact copies survive disconnection or deletion?

these questions do not change jarvis’s accepted contracts or roadmap.

## source ledger and coverage

all sources below accessed 2026-11-14. dates are explicit publication/update dates where available; relative help-center timestamps are not converted into invented absolute dates. titles are normalized to lowercase. official sources were opened, including markdown versions where available; search snippets were discovery only.

| source | date | scope |
|---|---|---|
| [introducing dots](https://openai.com/index/introducing-dots/) | 2026-09-29; update 2026-11-03 | launch, model change, examples, pilot, included usage |
| [getting started with your dot](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot) | undated; relative update shown | eligibility, texting provider, setup, reset |
| [dots privacy, security, and safety faqs](https://help.openai.com/en/articles/20001529-dots-privacy-security-and-safety-faqs) | undated; relative update shown | memory controls, training, sensitive actions |
| [managing dots in chatgpt workspaces](https://help.openai.com/en/articles/20001554-managing-dots-in-chatgpt-workspaces) | undated; relative update shown | enterprise access, settings, owner authority |
| [meet dots](https://learn.chatgpt.com/docs/dots) | undated | identity, availability, responsibility, pricing boundaries |
| [get started with your dot](https://learn.chatgpt.com/docs/dots/getting-started) | undated | onboarding and worked responsibility example |
| [message your dot](https://learn.chatgpt.com/docs/dots/channels) | undated | voice, messaging, widgets, shortcuts |
| [tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory) | undated | delegation, triggers, selected context, notes |
| [connect computers and apps to your dot](https://learn.chatgpt.com/docs/dots/computers-and-apps) | undated | execution targets, browser credentials, local access |
| [control your dot](https://learn.chatgpt.com/docs/dots/controls) | undated | behavior, rules, activity, stopping |
| [personalize your dot](https://developers.openai.com/training/walkthroughs/personalize-your-dot) | undated | review loops, source checking, reusable guidance |
| [how we build safety, security, and privacy into dots](https://openai.com/index/how-we-build-safety-security-and-privacy-into-dots/) | 2026-09-29; update 2026-11-03 | sandbox, credential service, research enforcement |
| [safety and security in dots](https://learn.chatgpt.com/docs/enterprise/dots-security) | undated | control gaps, snapshots, deletion, compliance limits |
| [manage dots permissions and capabilities](https://learn.chatgpt.com/docs/enterprise/dots-admin-guide) | undated | inventory, audit, analytics, billing, offboarding |
| [chatgpt work cloud security](https://learn.chatgpt.com/docs/enterprise/chatgpt-work-cloud-security) | undated | explicitly shared infrastructure; vm sandbox mechanism |
| [auto-review](https://learn.chatgpt.com/docs/sandboxing/auto-review) | undated | shared reviewer mechanism; codex-specific details not imported |
| [gpt-6 astra system card, change log, appendix 12](https://deploymentsafety.openai.com/gpt-6-astra/change-log) | undated appendix in reviewed page | dots harness, time budgets, confirmation/reviewer policy, evaluations |
| [gpt-live-1.1 system card](https://deploymentsafety.openai.com/gpt-live-1-1/respecting-warnings) | 2026-10-15 | default dots voice model and duplex behavior |
| [create your dot in the chatgpt mobile app](https://learn.chatgpt.com/docs/whats-new/dots-october-9-2026) | explicit period 2026-10-05–09 | mobile onboarding, codex context, recovery fixes |
| [text your dot](https://learn.chatgpt.com/docs/whats-new/dots-october-28-2026) | explicit period 2026-10-26–30 | payloads, update channel, approval links |
| [november 2–6, 2026](https://learn.chatgpt.com/docs/whats-new/november-2-6-2026) | explicit entry 2026-11-04 | notification reply, annotations, windows fixes |
| [what’s new](https://learn.chatgpt.com/docs/whats-new) | dated weekly sections | discovery and cross-check of launch/update sequence |
| [pricing](https://learn.chatgpt.com/docs/pricing) | undated | pro subscription amounts; not a dots metering specification |
| [introducing chatgpt wallet](https://openai.com/index/introducing-chatgpt-wallet/) | 2026-11-13 | payment networks, tokenization, future delegation |
| [making purchases with chatgpt wallet](https://help.openai.com/en/articles/20001654-making-purchases-with-chatgpt-wallet) | undated; relative update shown | eligibility, approvals, failures, merchant responsibilities |
| [accept payments](https://developers.openai.com/commerce/guides/accept-payments) | undated | checkout compatibility, tokens, forwarded risk signals |
| [help ensure cloud browser access](https://developers.openai.com/commerce/guides/enable-browser-access) | undated | merchant browser compatibility; no guarantee of universal access |
| [openai debuts dots, its assistant to take on muse](https://www.axios.com/2026/09/29/openai-dots-ai-assistant-devday) | 2026-09-29 | secondary launch observation only |

coverage includes all six dedicated dots guide pages, help-center setup/privacy/admin pages, enterprise admin/security guidance, safety appendix, release updates, voice system card, and wallet product/help/merchant guidance. no relevant reviewed primary page remained inaccessible after resolving canonical/markdown paths. unpublished internal safeguards reports, production source, private account screens, and rollout-specific commercial notices were unavailable. no conclusion here depends on access to them.

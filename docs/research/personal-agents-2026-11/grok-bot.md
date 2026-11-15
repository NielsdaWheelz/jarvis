# grok bot: public product and implementation evidence

snapshot: 2026-11-14. this dossier concerns the separate grok bot product, whose current documentation is branded spacexsi and describes cursor-hosted infrastructure. ordinary grok chat, grok build, and cursor capabilities enter only where bot documentation explicitly connects them. no accounts, integrations, purchases, calls, or controlled task trials were run. the [research method](method.md) governs the comparison.

## product boundary and availability

grok bot 1.0 launched on 2026-11-02. the announcement describes shared teammates, initiative, and improved execution; those are vendor claims about capability and quality, not measured success. the latest desktop release listed when accessed was 1.0.1, dated 2026-11-11, incorporating 1.0.0. [s02] [s03]

availability varies by feature and account: “out of beta” does not make every connected capability generally available. [s01]

below, **documented** means an official usage contract, **mechanism** means disclosed implementation, and **claim** means marketing or a worked demonstration. **available** means documented usable subject to account access; it does not mean independently exercised. rollout, beta, restricted, and unresolved are stated separately.

## feature inventory

| id | behavior and user consequence | status and evidence |
| --- | --- | --- |
| GROK-01 | desktop clients cover macos, windows, and linux, including the documented arm/intel variants. browser sign-in opens the first bot and provisions its shared computer. | available; documented [s04] |
| GROK-02 | authentication normally reuses cursor; linked grok entitlements and business seats have distinct entry paths. legacy privacy mode blocks access because bot requires cloud storage. | available; documented [s04] |
| GROK-03 | new x-subscription premium, super, and ultra include bot; plus excludes it. older cursor/supergrok arrangements continue unless changed. linking and unifying subscriptions are different operations; completed unification is irreversible. | available; documented [s05] |
| GROK-04 | monthly list prices are $30/$100/$200; annual totals are $300/$1,000/$2,000. matching team seats have the same tier prices, with mixed tiers and centralized administration. taxes may apply. | available; documented [s06] |
| GROK-05 | eligible first-party use shares a weekly pool across grok/cursor surfaces, per seat. activity rates differ; team seats do not pool their weekly allowances. public multiples do not establish completed-task capacity. | available; documented [s07] |
| GROK-06 | additional usage consumes prepaid credit. automatic top-up requires opt-in; adding credit does not raise a spending cap. | available; documented [s08] |
| GROK-07 | monthly additional-usage caps stop paid work when reached; alerts merely warn. an empty balance also stops additional usage. these are model-service spending controls, separate from purchase authority. | available; documented [s09] |
| GROK-08 | some accounts receive a nonrenewing seven-day usage-credit trial. a large task can consume it. apple subscription trials are different and can renew into paid service. | restricted; documented [s25] |
| GROK-09 | named bots retain roles; the primary bot is the coordination front door. users can pin, section, hide, rename, and personalize bots. hiding preserves work and routines. | available; documented [s10] |
| GROK-10 | bots retain preferences, rules, facts, and dated work summaries automatically. memory spans chats with that bot; selected personal facts propagate across the roster. inspection, correction, and forgetting use chat, with no personal-memory screen. | available; documented [s10] |
| GROK-11 | templates copy configuration, skills, and routines without computer access, logins, or history. published links can be public; enterprise starts team-only. deleting a bot removes its memory/history/routines, while shared-computer residue can remain. | available; documented [s10] |
| GROK-12 | text, dictation, voice memos, and live voice share a transcript. calls expose settings/reconnection; only one live voice chat runs at once. | available; documented [s11] |
| GROK-13 | editable email/slack draft cards precede sending; owners can disable drafts per bot. changed attachments require renewed review. | available; documented [s11] |
| GROK-14 | direct messages outrank background work; “stop now” stops work without undoing effects. | available; documented [s11] |
| GROK-15 | two-to-six-bot groups expose coordination. asynchronous messages wake other bots. replies consume usage; inter-bot messaging has no disable switch. | available; documented [s11] |
| GROK-16 | us phone calls require terms and per-call confirmation. live cards offer questions/takeover/hangup; transcripts and recordings are exportable. | restricted to us; documented [s11] |
| GROK-17 | x chat reaches the same bots through x clients, with gradual rollout and personal-account linking restrictions. public `@bot` tagging forwards a task to the primary bot, posting only confirmation publicly. | rollout; documented [s11] [s17] |
| GROK-18 | tagging includes the source/replied/quoted posts and still images. accounts based in australia, uk, eu, iceland, liechtenstein, and norway are excluded; videos/gifs, moderation, or exhausted usage can prevent delivery. | region restricted; documented [s17] |
| GROK-19 | persistent cloud browser, shell, and files continue while clients are closed. bots have separate screens but share files, cookies, and command-line credentials; one computer-use task per bot screen. | available; mechanism [s25] |
| GROK-20 | installed apps and authenticated apps are distinct states. catalog installation can be conversational. custom connectors support remote https or commands, headers, and oauth fields; command servers are roster-wide. | available; documented [s12] |
| GROK-21 | documented connector examples include gmail, calendar, drive/docs/sheets, slack, notion, microsoft storage/mail, stripe, power bi, bigquery, databricks genie, and asana. authority remains the connected account's; several need administrator setup. | available with provider restrictions; documented [s12] |
| GROK-22 | one permanent `mail.grokbot.com` address serves the roster, with plus aliases. mail can seed filtered routines; ordinary arrival alone does not wake a bot. unattended outgoing bot-address mail stays a draft. | account/admin restricted; documented [s12] |
| GROK-23 | skills encode reusable methods; routines attach an owner and schedule/event. skills can be private, bot-specific, or published to a team, with explicit sync/unpublish controls. | available; documented [s13] |
| GROK-24 | teach-by-demonstration records visible browser interaction for up to ten minutes, without microphone audio, and produces a draft skill for review. | gradual rollout; documented [s13] |
| GROK-25 | natural-language schedules persist an inspectable timezone/schedule. creation waits for the next due time; desktop test, where offered, performs real work. phone history reports running/succeeded/failed and failure reasons. | available; documented [s13] |
| GROK-26 | triggers include slack, github, linear, sentry, pagerduty, agent email, and webhooks. only new events count. slack watches and connector access are separate connections. webhook bearer authentication returns acceptance/start, not task completion. | available with integration setup; documented [s13] |
| GROK-27 | the primary bot offers work, flags disconnected apps, and follows up. muting notifications does not disable check-ins; the guide directs users to support to turn check-ins off. | available; documented [s18] |
| GROK-28 | attachments support media, office files, notebooks, code, and structured text: up to 20/message; images 25 mb each/200 mb total, other files 250 mb each, video 1 gb each. | available; documented [s14] |
| GROK-29 | bots produce downloadable documents, spreadsheets, decks, images, and short videos. video supports references/keyframes, 1–15 seconds and 480p/720p; generated artifacts appear in conversation/library. | available, account/content-policy dependent; documented [s14] |
| GROK-30 | pages combine reports, tables, charts, and interactive controls; bots edit the persistent page through adjacent chat. controls affect the view, not saved content. | gradual rollout; guide says unavailable on enterprise; documented [s14] |
| GROK-31 | pages default private and can be invitation/team/public-link shared. public pages use stable `pages.grok.bot` addresses, without custom addresses; public enterprise sharing is disabled. library/search retain prior artifacts. | rollout/account dependent; documented [s14] |
| GROK-32 | bot coding delegation explicitly uses cursor cloud agents and attaches returned files. a custom-api helper, `tinkabot`, can build an mcp/plugin wrapper, test it, and await permission to publish. | available as documented; mechanism [s15] |
| GROK-33 | vault stores logins, cards, and contact details across the personal roster, without per-bot restriction. password insertion hides values from models; the detailed guide explicitly permits model access to saved card numbers/security codes. | available; documented [s16] |
| GROK-34 | login resolution tries vault, then 1password, then a secure form. api-key cards hide values from transcript/model; passkeys, sso, captcha, or bank checks can hand the computer to the owner. | available; mechanism [s15] |
| GROK-35 | 1password's new integration is gradually rolling out, using personal/private vault logins and approved access rather than the former service account. it requires 8.12.42+, excludes shared vaults/cards, and may require reconnecting. | rollout; documented [s12] |
| GROK-36 | saved cards can fill checkout without per-use permission. order cards separately request payment approval. up to 500 card payments can share one batch, stopping on decline; authorization lasts 24 hours. | available; documented [s16] |
| GROK-37 | auto review checks actions against owner requests; external mail/page text is not owner consent. it is model based, enabled by default, and configurable with ask-first/allow rules; ask-first wins conflicts. | available; mechanism [s19] |
| GROK-38 | approval cards offer one-time permission, denial, and sometimes persistent allowance. background cards expire after 30 minutes; chat-started cards wait. a new message or policy change closes open cards. | available; documented [s19] |
| GROK-39 | local desktop execution is separately gated: ask every time by default, always allow, or never allow. exact commands are shown. admin ceilings can be stricter; cloud work remains separate. | available; documented [s20] |
| GROK-40 | iphone/ipad and android sync the same bots/work. siri/shortcuts expose listing, messaging, dictation, and voice, with live activities/action-button support on iphone. | available; documented [s21] |
| GROK-41 | foreground phone tools cover calendar, contacts, location, alarms/timers; iphone adds reminders and apple home, including locks/security systems. scope excludes someone else's team bot and group/slack use. | available with os permissions; documented [s21] |
| GROK-42 | phone tools require the app open. team policy and auto review govern execution; without a team limit, disabling auto review allows app use without action checks. android notification reading was removed in 1.18.0. | available/current restriction; documented [s21] |
| GROK-43 | team bots share one identity/configuration across collaborators, while individual chats stay private even from owners/managers. teammate-proposed memory/skill learning waits for manager review; owner/manager changes apply directly. | team/enterprise; documented [s22] |
| GROK-44 | shared connectors can use individual accounts, a bot account, or a manager's account after admin enablement. secrets/files made available to the team bot serve all its users; personal vault does not. | team/enterprise; documented [s22] [s16] |
| GROK-45 | team-bot direct chats usually run on the requester's computer; shared slack/group surfaces use a bot-owned shared computer. replies ordinarily consume the requesting person's allowance, with documented owner/team fallbacks. | team/enterprise; mechanism [s22] |
| GROK-46 | team bots can have slack identities, channel mentions and dms. identity linking attributes requests/approvals; organization sharing may admit full workspace members without seats, but excludes guests/slack connect. | team/enterprise; documented [s22] |
| GROK-47 | microsoft teams requires organization enablement, owner/manager setup, and teams-admin approval. linked users can mention/dm/group-chat; file delivery uses onedrive and may require a direct chat. setup can take an hour. | team/enterprise; documented [s23] |
| GROK-48 | meetings accept meet/zoom/teams links plus approval/host admission, or calendar-following joins. bots transcribe, answer in chat, and return summaries/actions. users can mute interactivity, cancel, quit, and retrieve past transcripts. | team/enterprise/ultra; documented [s24] |
| GROK-49 | attention states separate working, unread results, and needs-attention. active desktop use routes most owner-bot alerts there; input requests can escalate to the phone after roughly three minutes. notifications are per bot. | available; iphone push gradual rollout; documented [s26] |
| GROK-50 | searches span messages, bots, groups, files, and routines; older-message search is explicit. deep links prefill up to 1,000 characters and never send automatically. | available; documented [s21] [s27] |
| GROK-51 | computer update/recover/reset preserve saved state but replace installed packages; recover/reset interrupt work and can lose recent unsynced changes. conversation history is outside the computer. | available; documented [s12] |
| GROK-52 | enterprise admins can recreate with safe-point continuation, terminate current work, delete disks, or delete all bot data. progress survives closing the console; one operation per team and an organization api are disclosed. | enterprise; documented [s28] |
| GROK-53 | inactive-computer retention is optional, 30–365 days, applies only while asleep, warns nobody, and uses the shortest period across memberships. bot/message retention are separate controls. | enterprise; documented [s28] [s29] |
| GROK-54 | enterprise action recording is off by default; sanitized action metadata exports through opentelemetry. audit logs separately record administration/security. team analytics/usage do not establish semantic correctness. | enterprise; documented [s29] |
| GROK-55 | enterprise inference hooks can inspect signed prompt frames and optionally proposed tool-call batches. shadow/fail-open/fail-closed modes, sampling, timeouts and circuit breakers are explicit. | enterprise beta; mechanism [s30] |
| GROK-56 | enterprise network policy and connector policy are separate. remote mcp originates from backend servers and needs explicit network-policy coverage. hostname blocklists are best effort and do not filter search results. | enterprise; mechanism [s20] |
| GROK-57 | traffic can route through a desktop. private-network deployment instead supports customer-installed linux networking clients through enterprise setup scripts; scripts can use temporary team secrets. | available/enterprise by method; mechanism [s31] |
| GROK-58 | bot selects models without a picker; first- and third-party routing can vary, outside the team's model allowlist. computers run in the us; enrolled us-only residency covers inference/processing/storage. | documented; mechanism [s25] [s32] |

## disclosed architecture and its limits

**execution and identity.** official documentation describes thin clients, cursor control services, one firecracker microvm per user, model calls, and connected-app execution. bot roles organize context rather than isolate authority. the boundary is per user, not screen. team-bot routing makes authority depend on the conversation as well as the bot. [s29] [s32]

**integration paths.** the architecture exposes three distinct access routes: structured app calls, cloud computer work, and separately permitted local execution. connector oauth tokens stay in cursor's backend. private-network access does not imply private hosting: setup scripts install customer-maintained clients; no on-premises or bring-your-own-image deployment is documented. desktop routing alone does not open private/vpn destinations. [s15] [s31] [s32]

**security review.** auto review is an independent review model, rather than a universal deterministic authorization classifier. enterprise can enforce it and add locked rules. external material is marked untrusted; this is a disclosed mitigation, not proof against prompt injection. inference hooks add a separate organization-controlled checkpoint, including long-conversation summaries/subagents/routines, but exclude hidden reasoning, system prompts, ancillary memory/review calls, and cloud agents. inference hooks do not check reply text before delivery. [s19] [s20] [s29] [s30]

**failure semantics.** hook failure handling is unusually explicit: block mode can fail open when settings cannot load; vendor emergency pauses also permit requests. sampling leaves turns unchecked. restoring a disk does not establish whether an email, purchase, or delegated job happened. universal idempotency, exactly-once effects, and bounded reconciliation remain undisclosed. [s30]

**data and portability.** privacy mode prevents training; storage remains. provider zero-retention has safety-investigation exceptions. daily encrypted control-plane backups exist; customer point-in-time computer restore does not. memory import is a prompt-copy workflow into the primary bot; files and call recordings have export routes. a complete structured export of bot memory, routines, action history and chats was not established. [s20] [s26]

## concrete workflows and interaction design

**research to operational deliverable.** the marketing guide demonstrates six persistent specialists: research, positioning, paid campaigns, website operations, analysis, and coordination. research flows into google docs; approved copy becomes campaign shells; website work becomes a github pr with screenshots. the analyst recommends changes without changing live budgets. this is a vendor-authored worked example using a fictional airline, not independent production evidence. its useful design claim is that a manager bot absorbs context-transfer work across stable roles. [s33]

**project coordination.** the linear guide offers a preconfigured project-operations bot. it investigates existing issues/discussions, records agreed scope and acceptance criteria, delegates a bounded implementation to an explicitly connected coding agent, follows linked prs/merges when monitoring is configured, reviews diffs/checks, and updates the project. implementation authorization remains separate from investigation. the guide explicitly distinguishes merged from released/verified. these are described workflows and connector-dependent affordances, not evidence of reliable autonomous delivery. [s34]

**personal operations.** the getting-started guide proposes a calendar-aware morning brief, inbox triage/drafts, competitor monitoring, and travel planning, then asks the owner to convert a useful result into a routine. the overview additionally illustrates granola-to-action-items and recurring notion updates. these are starter recipes, not separate domain engines. the distinct product affordance is converting demonstrated work into an inspectable standing commitment rather than repeatedly reconstructing the task. [s04] [s01]

**review as an interface.** the november changelog adds reviewed team learnings, shared connectors and meetings, as well as expiry-price refresh for orders. it also records practical fixes: large computer files could break replies, computer handoff could leave stale waiting status, and notification/spam behavior needed correction. these establish active iteration and historical defects, not their prevalence or a reliability ranking. [s03]

## ambiguities and evidence gaps

- **payment secrecy is internally inconsistent.** security faq broadly says vault cards are filled without model visibility; the detailed vault guide says saved card number/security code can be visible. treat saved card data as model-visible until clarified. [s16] [s32]
- **purchase approval is route dependent.** vault says saved cards have no per-use approval setting; order-card shopping exposes explicit pay approval. neither supports the blanket inference that every charge is confirmed, nor that every charge is unattended. [s16]
- **initiative is narrower in support than marketing.** launch copy discusses noticing/starting work; the dedicated guide says offer first. the source of opportunities, polling cadence, autonomous-work budget and durable commitment representation remain undisclosed. [s02] [s18]
- **plan pages need reconciliation.** current x-subscription docs describe shared per-seat pools; legacy bot guides still refer to earlier entitlements. landing-page usage multiples differ from the general pricing table's first-party multiples. no fixed steps/messages/tasks per dollar can responsibly be derived. the linked canonical help matrix returned 403 during this research. [s05] [s06] [s07] [s35]
- **pages availability conflicts within its guide.** it says pages are unavailable on enterprise, then describes enterprise sharing restrictions. capability rollout and policy documentation may describe different cohorts; enterprise page access is unresolved. mobile recovery guidance similarly says desktop is required while later listing mobile reset. [s14] [s21]
- **memory remains a black box.** retention behavior is described; schemas, selection thresholds, compression/retrieval algorithms, source provenance, stale-fact conflict rules, and guarantees after forgetting are not. reset keeps memory; an empty conversation is therefore not a fresh agent. [s10]
- **stop and delegation need failure trials.** there is no public proof of how stop fences already dispatched remote effects, cascades through cloud agents, or resolves unknown outcomes. reset explicitly leaves some cloud agents/background commands running. concurrency ceilings, queue fairness and bot-loop suppression are not disclosed. [s30]
- **coverage is broad, not exhaustive.** no full connector catalog/export, private beta, hidden scheduler, model-routing implementation, or production task-success measurements were audited. linked secret/plugin help endpoints were inaccessible. no third-party anecdote is used as architecture evidence.

## source ledger

all sources accessed **2026-11-14**. undated means the page supplied no publication/update date used here. markdown endpoints were read where the official documentation exposes them; they are the same source as the corresponding rendered guide.

| id | title | stated date | full url |
| --- | --- | --- | --- |
| s01 | grok bot overview | undated | [https://docs.x.ai/grok-bot/overview](https://docs.x.ai/grok-bot/overview) |
| s02 | introducing grok bot 1.0 | 2026-11-02 | [https://x.ai/news/grok-bot-1-0](https://x.ai/news/grok-bot-1-0) |
| s03 | grok bot changelog | entries through 2026-11-11 | [https://x.ai/changelog/bot](https://x.ai/changelog/bot) |
| s04 | get started | undated | [https://docs.x.ai/grok-bot/get-started](https://docs.x.ai/grok-bot/get-started) |
| s05 | grok bot on the x subscription | undated | [https://docs.x.ai/x-subscription/grok-bot](https://docs.x.ai/x-subscription/grok-bot) |
| s06 | pricing | undated | [https://docs.x.ai/x-subscription/pricing](https://docs.x.ai/x-subscription/pricing) |
| s07 | usage limits | undated | [https://docs.x.ai/x-subscription/usage-limits](https://docs.x.ai/x-subscription/usage-limits) |
| s08 | extra usage credits and top-ups | undated | [https://docs.x.ai/x-subscription/extra-usage](https://docs.x.ai/x-subscription/extra-usage) |
| s09 | spending caps: monthly extra-usage caps and alerts | undated | [https://docs.x.ai/x-subscription/spending-caps](https://docs.x.ai/x-subscription/spending-caps) |
| s10 | create and manage bots | undated | [https://docs.x.ai/grok-bot/bots](https://docs.x.ai/grok-bot/bots) |
| s11 | message and collaborate | undated | [https://docs.x.ai/grok-bot/chat-and-collaboration](https://docs.x.ai/grok-bot/chat-and-collaboration) |
| s12 | use the computer and apps | undated | [https://docs.x.ai/grok-bot/computer-and-apps](https://docs.x.ai/grok-bot/computer-and-apps) |
| s13 | skills and routines | undated | [https://docs.x.ai/grok-bot/skills-routines-and-automations](https://docs.x.ai/grok-bot/skills-routines-and-automations) |
| s14 | files and results | undated | [https://docs.x.ai/grok-bot/files-and-results](https://docs.x.ai/grok-bot/files-and-results) |
| s15 | how grok bot works | undated | [https://docs.x.ai/grok-bot/how-grok-bot-works](https://docs.x.ai/grok-bot/how-grok-bot-works) |
| s16 | vault and secure sign-in | undated | [https://docs.x.ai/grok-bot/vault](https://docs.x.ai/grok-bot/vault) |
| s17 | tag @bot on x | undated | [https://docs.x.ai/grok-bot/tag-on-x](https://docs.x.ai/grok-bot/tag-on-x) |
| s18 | when your bot takes initiative | undated | [https://docs.x.ai/grok-bot/initiative](https://docs.x.ai/grok-bot/initiative) |
| s19 | approvals, security, and privacy | undated | [https://docs.x.ai/grok-bot/approvals-security-and-privacy](https://docs.x.ai/grok-bot/approvals-security-and-privacy) |
| s20 | grok bot security | undated | [https://docs.x.ai/grok-bot/security](https://docs.x.ai/grok-bot/security) |
| s21 | grok bot for mobile | undated | [https://docs.x.ai/grok-bot/mobile](https://docs.x.ai/grok-bot/mobile) |
| s22 | team bots | undated | [https://docs.x.ai/grok-bot/team-bots](https://docs.x.ai/grok-bot/team-bots) |
| s23 | use grok bot in microsoft teams | undated | [https://docs.x.ai/grok-bot/microsoft-teams](https://docs.x.ai/grok-bot/microsoft-teams) |
| s24 | add a bot to your meetings | undated | [https://docs.x.ai/grok-bot/meetings](https://docs.x.ai/grok-bot/meetings) |
| s25 | frequently asked questions | undated | [https://docs.x.ai/grok-bot/faq](https://docs.x.ai/grok-bot/faq) |
| s26 | settings and notifications | undated | [https://docs.x.ai/grok-bot/settings-and-notifications](https://docs.x.ai/grok-bot/settings-and-notifications) |
| s27 | deep links | undated | [https://docs.x.ai/grok-bot/deep-links](https://docs.x.ai/grok-bot/deep-links) |
| s28 | manage grok bot computers | undated | [https://docs.x.ai/grok-bot/computers](https://docs.x.ai/grok-bot/computers) |
| s29 | grok bot for teams and enterprises | undated | [https://docs.x.ai/grok-bot/teams-and-enterprises](https://docs.x.ai/grok-bot/teams-and-enterprises) |
| s30 | grok bot inference hooks | undated | [https://docs.x.ai/grok-bot/inference-hooks](https://docs.x.ai/grok-bot/inference-hooks) |
| s31 | connect to private networks | undated | [https://docs.x.ai/grok-bot/private-networks](https://docs.x.ai/grok-bot/private-networks) |
| s32 | grok bot security faq | undated | [https://docs.x.ai/grok-bot/security-faq](https://docs.x.ai/grok-bot/security-faq) |
| s33 | grok bot for marketing, josh kim | 2026-09-24 | [https://x.ai/bot/guides/grok-bot-for-marketing](https://x.ai/bot/guides/grok-bot-for-marketing) |
| s34 | grok bot for linear, cristina cordova | 2026-11-02 | [https://x.ai/bot/guides/grok-bot-for-linear](https://x.ai/bot/guides/grok-bot-for-linear) |
| s35 | ai teammates that finish the work | undated | [https://x.ai/bot](https://x.ai/bot) |
| gap | plans and billing; connect plugins; store secrets securely | inaccessible, no content evidence | [https://grok.com/help/grok-bot/plans](https://grok.com/help/grok-bot/plans) ; [https://grok.com/help/grok-bot/connect-plugins](https://grok.com/help/grok-bot/connect-plugins) ; [https://grok.com/help/grok-bot/secrets](https://grok.com/help/grok-bot/secrets) |

[s01]: https://docs.x.ai/grok-bot/overview
[s02]: https://x.ai/news/grok-bot-1-0
[s03]: https://x.ai/changelog/bot
[s04]: https://docs.x.ai/grok-bot/get-started
[s05]: https://docs.x.ai/x-subscription/grok-bot
[s06]: https://docs.x.ai/x-subscription/pricing
[s07]: https://docs.x.ai/x-subscription/usage-limits
[s08]: https://docs.x.ai/x-subscription/extra-usage
[s09]: https://docs.x.ai/x-subscription/spending-caps
[s10]: https://docs.x.ai/grok-bot/bots
[s11]: https://docs.x.ai/grok-bot/chat-and-collaboration
[s12]: https://docs.x.ai/grok-bot/computer-and-apps
[s13]: https://docs.x.ai/grok-bot/skills-routines-and-automations
[s14]: https://docs.x.ai/grok-bot/files-and-results
[s15]: https://docs.x.ai/grok-bot/how-grok-bot-works
[s16]: https://docs.x.ai/grok-bot/vault
[s17]: https://docs.x.ai/grok-bot/tag-on-x
[s18]: https://docs.x.ai/grok-bot/initiative
[s19]: https://docs.x.ai/grok-bot/approvals-security-and-privacy
[s20]: https://docs.x.ai/grok-bot/security
[s21]: https://docs.x.ai/grok-bot/mobile
[s22]: https://docs.x.ai/grok-bot/team-bots
[s23]: https://docs.x.ai/grok-bot/microsoft-teams
[s24]: https://docs.x.ai/grok-bot/meetings
[s25]: https://docs.x.ai/grok-bot/faq
[s26]: https://docs.x.ai/grok-bot/settings-and-notifications
[s27]: https://docs.x.ai/grok-bot/deep-links
[s28]: https://docs.x.ai/grok-bot/computers
[s29]: https://docs.x.ai/grok-bot/teams-and-enterprises
[s30]: https://docs.x.ai/grok-bot/inference-hooks
[s31]: https://docs.x.ai/grok-bot/private-networks
[s32]: https://docs.x.ai/grok-bot/security-faq
[s33]: https://x.ai/bot/guides/grok-bot-for-marketing
[s34]: https://x.ai/bot/guides/grok-bot-for-linear
[s35]: https://x.ai/bot

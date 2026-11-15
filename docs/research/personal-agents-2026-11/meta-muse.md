# meta muse personal agent

researched 2026-11-14. public evidence only; no account, signup, connector authorization, purchase, or live task execution. this is a feature and mechanism investigation, not a roadmap.

## identity and evidentiary boundary

the subject is meta's personal agent at [muse.ai](https://muse.ai/), launched on september 8, 2026. the official [announcement](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/) and [app listing](https://apps.apple.com/us/app/muse-from-meta/id6760173601) establish ownership. it is distinct from meta ai, the muse model family, muse code, academic systems called `MUSE`, and the video service whose older muse.ai pages still appear in search. domain identity alone is insufficient when reading older results.

labels throughout:

- **documented functionality**: a first-party help page describes an available user operation; availability may still vary by account or region.
- **documented mechanism**: first-party technical disclosure specifies how it works; this is disclosure, not independent verification.
- **vendor claim**: marketing, demonstrations, or vendor-reported results.
- **third-party observation**: a publicly reported experience, with its scope preserved.
- **inference**: an analytical conclusion, not a disclosed implementation fact.
- **unknown**: the inspected public corpus does not establish the answer.

the product's distinctive proposition is an ongoing relationship attached to a persistent computer, with background work and bespoke interfaces. **inference:** its competitive unit is the continuing delegated task, rather than the individual answer. advertised breadth should not be mistaken for measured completion reliability.

## feature inventory

ids are stable within this investigation. “documented” means available according to the cited vendor documentation, not personally tested.

| id | behavior | status and evidence | source |
| --- | --- | --- | --- |
| MUSE-01 | meta-account onboarding; main chat and separate topic chats | documented; context crosses chats | [getting started](https://www.meta.com/help/superintelligence/1331373868832401/) |
| MUSE-02 | mobile, web, mac, whatsapp continuity | vendor-described available surfaces | [download](https://ai.meta.com/muse/download) |
| MUSE-03 | live voice, interruption, expressive avatars, selectable voices | rolling out; november 5 announcement | [voice](https://about.fb.com/news/2026/11/introducing-muse-ai-voice-expressive-avatars/) |
| MUSE-04 | custom name, personality, tone, identity | documented; persists across conversations | [personality](https://www.meta.com/help/superintelligence/995796179982326/) |
| MUSE-05 | editable memory and identity files; forgetting | documented; deletion is qualified | [data controls](https://www.meta.com/help/superintelligence/2225571704857152/) |
| MUSE-06 | import another assistant's conversation export | documented zip import | [personality](https://www.meta.com/help/superintelligence/995796179982326/) |
| MUSE-07 | goals, plans, personalized ideas, unsolicited updates | vendor-described product behavior | [design](https://muse.ai/blog/how-we-designed-muse) |
| MUSE-08 | timed, location, recurring reminders; cancellation | documented; upcoming view | [schedules](https://www.meta.com/help/superintelligence/1484325780075655/) |
| MUSE-09 | event-driven connected-app context | documented for selected connectors | [connectors](https://www.meta.com/help/superintelligence/1687253048996149/) |
| MUSE-10 | persistent linux cloud workspace and delegated execution | documented mechanism; resource limits undisclosed | [technical disclosure](https://muse.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse) |
| MUSE-11 | shared browser; observe, take control, stop | documented | [browsing](https://www.meta.com/help/superintelligence/2124746764949121/) |
| MUSE-12 | chrome extension acts in grouped local tabs | documented; existing website sessions usable | [browsing](https://www.meta.com/help/superintelligence/2124746764949121/) |
| MUSE-13 | mac files and local application data/actions | documented; system and app permissions | [mac](https://www.meta.com/help/superintelligence/1126304576638594/) |
| MUSE-14 | connector authorization, revocation, custom connectors | documented | [connectors](https://www.meta.com/help/superintelligence/1687253048996149/) |
| MUSE-15 | built-in research, document, image, audio and dashboard skills | documented; automatic skill selection | [skills](https://www.meta.com/help/superintelligence/2797651547267109/) |
| MUSE-16 | files and interactive artifacts; persistent library | documented | [artifacts](https://www.meta.com/help/superintelligence/2074655449783957/) |
| MUSE-17 | custom app spaces with background updates | available announcement, november 6 | [spaces](https://about.fb.com/news/2026/11/introducing-spaces-customize-muse-app/) |
| MUSE-18 | structured approvals and adjustable permission scope | documented | [guidance and approval](https://www.meta.com/help/superintelligence/1385290430137537/) |
| MUSE-19 | purchases through link or merchant saved cards | documented; purchase approval required | [payments](https://www.meta.com/help/superintelligence/1436362127544482/) |
| MUSE-20 | agent-owned email; owner instructions by verified email | documented in current help | [email addresses](https://www.meta.com/help/superintelligence/1149305437517250/) |
| MUSE-21 | business marketing, financial analysis and operations | available skills/connectors; outcome claims | [small business](https://about.fb.com/news/2026/09/introducing-muse-small-business/) |
| MUSE-22 | business-agent interaction through personal agent protocol | version 1.0 support announced november 13 | [poppy](https://muse.ai/blog/poppy-personal-agent-protocol) |
| MUSE-23 | home-network access through home link device | user guide exists; retail access unverified | [home link](https://www.meta.com/help/muse-charm/1645260456993247/) |
| MUSE-24 | activity history, live status, scheduled-work visibility | documented | [guidance and approval](https://www.meta.com/help/superintelligence/1385290430137537/) |
| MUSE-25 | export, reset, model-training control | documented | [data controls](https://www.meta.com/help/superintelligence/2225571704857152/) |
| MUSE-26 | free allowance, paid tiers, purchased extra usage | documented | [plans](https://www.meta.com/help/subscriptions/1021145227643680/), [tokens](https://www.meta.com/help/subscriptions/28153473374286914/) |
| MUSE-27 | watch companion and home-screen feed widget | current vendor release notes | [app store](https://apps.apple.com/us/app/muse-from-meta/id6760173601) |
| MUSE-28 | confidential vm; glasses and charm access | future/limited testing, not established general availability | [privacy help](https://www.meta.com/help/superintelligence/1047255454427887/), [connect](https://about.fb.com/news/2026/09/the-biggest-news-from-connect-2026/) |
| MUSE-29 | finance, family logistics and marketplace task examples | vendor examples; not universal task-completion evidence | [use cases](https://ai.meta.com/muse/agentic-ai-examples/) |
| MUSE-30 | 1password-approved website login | current partner support; scoped account/vault eligibility | [setup](https://support.1password.com/1password-muse/) |

## availability, onboarding and conversation

**documented functionality:** sign in with a meta account, or create one through an existing facebook/instagram account, email, or phone. chat permits successive messages before the previous response finishes. side chats organize topics while the agent remains aware across them. setup need not include every preference or connection immediately. the [getting-started guide](https://www.meta.com/help/superintelligence/1331373868832401/) describes microphone permission, ending voice by speech or control, background voice while using other apps, and a background-listening setting.

**availability:** the september 29 [business announcement](https://about.fb.com/news/2026/09/introducing-muse-small-business/) says us and canada. an explicit november 5 update in the [latin american announcement](https://about.fb.com/ltam/news/2026/09/presentamos-muse-el-primer-agente-de-ia-personal-del-mundo-creado-para-todos/) adds mexico, spanish, ios/android/web/whatsapp, and local connectors including cinépolis, coppel, despegar, kavak, kueski, liverpool, rappi and walmart méxico. this supersedes a simple us-only reading of launch coverage. a complete current global availability matrix was not established.

the [download page](https://ai.meta.com/muse/download) describes carrying the same ongoing work between phone, laptop and whatsapp. **unknown:** feature parity across those clients, whether all approval interfaces work inside whatsapp, and windows-native support.

**vendor claim:** the november [voice announcement](https://about.fb.com/news/2026/11/introducing-muse-ai-voice-expressive-avatars/) describes hundreds of voices, natural interruption, and avatar expressions while listening and speaking. users can select voice only, an avatar beside chat, or fullscreen. rollout begins in the us across mobile, web and mac. glasses and charm remain future in that announcement. no latency distribution, audio-retention mechanism, or independent conversational evaluation is provided there.

## memory, identity and continuing work

**documented functionality:** customize name, tone, communication style, avatar and tagline conversationally or manually. memory draws on conversations, observed preferences and connected context. an [import flow](https://www.meta.com/help/superintelligence/995796179982326/) accepts a previous assistant's exported chat zip through settings → data controls → import memory. supported exporters, schema normalization, duplicate handling and import completeness are unknown.

**documented functionality:** [data controls](https://www.meta.com/help/superintelligence/2225571704857152/) expose `Memory.md`, `Soul.md` and `Identity.md`; the same help corpus also uses `MEMORY.md`. memory, personality boundaries and agent identity therefore have user-visible file representations. users can edit/delete them. deleting source chats or emails can leave learned information behind. the forget skill searches memories and supporting files and removes information only to the agent's best ability. **unknown:** compaction, retrieval ranking, memory-write arbitration, provenance preservation, contradiction handling, and the completeness of a requested erasure.

**vendor claim:** [product design](https://muse.ai/blog/how-we-designed-muse) describes one continuing conversation, parallel tasks, goals and ideas views, schedules and relevant-event responses, and deciding whether background results justify interruption. users can ask for more or less proactivity. this is a policy description, not a disclosed notification-scoring algorithm or service-level promise.

**documented functionality:** [scheduled work](https://www.meta.com/help/superintelligence/1484325780075655/) supports one-time and location reminders, daily/weekly/custom recurrence, inspection, rescheduling and cancellation. reminders arrive in chat; times use the user's timezone; recurring work lasts until cancelled. concrete flow: request a monday reminder, review its confirmed time, inspect upcoming under the assistant icon, then move or cancel it in chat. **unknown:** missed-run handling, daylight-saving ambiguity, retry ceilings, event coalescing, and whether each recurring execution inherits exactly the original permission scope.

## connected context, skills and environments

**documented functionality:** [connector setup](https://www.meta.com/help/superintelligence/1687253048996149/) works through chat or settings → connectors → connect → authorization. email is searched without automatically downloading the entire inbox unless requested. selected calendar connectors can push changes. facebook, instagram and threads can connect automatically through the same accounts center. disconnecting stops exchange but does not erase previously retained context. custom connectors may need the user to retrieve api information; meta does not review them. apple health and android sms also require device-level controls.

**vendor-described capability:** [productivity](https://ai.meta.com/muse/productivity/) covers inbox triage, drafting/sending/organization, calendar conflicts/rescheduling, browser-based customer service, and cloud-file organization. [fitness](https://ai.meta.com/muse/fitness/) describes adaptive training, health-app context, nutrition, and transforming saved instagram inspiration into plans and ingredient orders. these pages establish intended workflows, not medical validation or reliable autonomous negotiation.

**vendor examples:** a broader [agentic use-case guide](https://ai.meta.com/muse/agentic-ai-examples/) describes subscription audits/cancellation after approval, dispute-letter preparation, school-deadline extraction, preparing marketplace listings from photos, birthday planning, recurring follow-up and data-broker opt-outs. it also illustrates health-record preparation and medication reminders. these are suggested delegated workflows, not a verified catalog of domain-specific applications or success guarantees. **unknown:** direct telephone calling, human call-center delegation, and the coverage of any corresponding connector; browser-based customer service does not establish those mechanisms.

the [business landing page](https://muse.ai/business) names asana, box, canva, dropbox, figma, granola, highlevel, intuit quickbooks, klaviyo, lovable, notion, shopify, slack, stripe and zoom, plus facebook/instagram/meta ads. it presents cash-flow, inventory, content and advertising work. **unknown:** the exact read/write methods, event delivery, oauth scopes, regional availability and per-connector limits. the complete live catalog is in settings, outside this investigation.

**documented functionality:** [skills](https://www.meta.com/help/superintelligence/2797651547267109/) are automatically available; the agent chooses them for a request. examples combine browsing with audio generation for a historical podcast, or create comparative pdfs and images. skills can use location and workspace files. activity history exposes their use. **inference:** discoverability is partly conversational and through personalized ideas, rather than requiring users to select a tool before stating intent. this does not establish the tool-selection algorithm.

### disclosed execution mechanism

**documented mechanism, launch architecture:** `Hatch` runs inside a `systemd-nspawn` debian cell; container root maps to an unprivileged host user. external services own postgres state, `privsep` connector execution, `hatch-authd` credentials, `hatch-safety` classifiers and sentinel authority. unix sockets use `SO_PEERCRED`/acls. sentinel checks connector requests and concrete network egress; surrogate credentials become real credentials only at authorized egress. `eBPF` process taint removes automatic allowance after private-data reads. a broker gives a dedicated browser subagent accessibility snapshots, without page javascript or raw dom access. takeover pauses that agent. concurrent subagents, code compilation and crons are disclosed. [technical source](https://muse.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse).

**unknown:** the orchestration graph, model routing, durable task journal, subagent lifecycle, retry/reconciliation rules, storage/compute quotas and crash semantics. independent robustness is not established by naming isolation primitives.

### browser and local computer flows

**documented functionality:** in the [shared cloud browser](https://www.meta.com/help/superintelligence/2124746764949121/), open browser shows current work; take control pauses it; stop task terminates its browser activity. users can ask for visited urls and accepted cookies. the chrome extension instead operates through the user's chrome session in its own tab group, including already signed-in sites. clicking the page, pressing escape or removing a tab from the group stops its control. the guide says saved passwords/history/settings are inaccessible, and page passwords are stripped before reading. activity can still affect website recommendations and advertising. **unknown:** local-extension protections are not proven identical to the disclosed cloud-browser broker.

**documented functionality:** the [mac client](https://www.meta.com/help/superintelligence/1126304576638594/) can organize files and access local messages, notes, reminders, mail and calendars. macos full disk access and automation are broad system grants; muse separately offers app-level off/read-only/read-and-interact. deleting a file moves it to trash. revocation lives in both muse settings and macos privacy/security. interaction data can include screenshots. **inference:** the user must understand two different permission layers; an app-level promise does not narrow the operating system's underlying full-disk grant.

**documented device mechanism:** [home link](https://www.meta.com/help/muse-charm/1645260456993247/) is a continuously powered usb-c home-network bridge, with bluetooth setup, physical-button confirmation and wifi. the guide specifies an `ESP32-C5`, us operation, no microphone/camera and no stored personal content. it reconnects after power/network restoration and supports factory reset. **unknown:** purchasing availability, supported home-service inventory and the actual tunnel/access-control design. the existence of a help page establishes a documented device, not broad retail rollout.

## permissions, payments and email authority

**documented functionality:** [approval settings](https://www.meta.com/help/superintelligence/1385290430137537/) distinguish connector and web defaults, including asking for all actions or selected actions. permission cards offer once, task, site, connector-wide allowance, or denial; task details are inspectable. the avatar exposes activity and upcoming work. users can inspect system files. stopping/undoing is limited by the actual operation; sent email cannot simply be reversed. **unknown:** exact argument binding, permission-expiry races, revocation of an in-flight effect, and guarantees against duplicate execution.

the [security page](https://muse.ai/security-and-privacy) says credentials stay in a separate store, connector permissions are adjustable, and purchases always require explicit approval. it constrains “allow always” to a specific site or task. **source tension:** the help guide also describes connector-wide always-allow. the product's precise grant scope therefore depends on the permission type and interface; a blanket statement that every action always prompts would be false.

**current partner functionality:** [1password's muse page](https://1password.com/partners/meta-muse) now provides setup and describes approved login filling without exposing passwords/codes to muse. this supersedes september's “coming soon.” the [marketplace entry](https://marketplace.1password.com/integration/1password-for-meta-muse) describes device-biometric approval and removing credentials from the form after sign-in; these are partner mechanism claims.

**documented setup and limits:** [1password support](https://support.1password.com/1password-muse/), published november 4, requires an individual/family `1Password.com` account and app 8.12.42+. `.ca`, `.eu`, business/team accounts, shared vaults, passkeys and federated-login items are unsupported. connect in muse settings, authorize 1password, then approve a suggested login. login-use approval expires after 30 days; website sessions have their own lifetime. only one muse account connects per 1password account. disconnecting removes login approvals and prevents future integration sign-ins. **unknown:** whether that also invalidates existing website sessions; connector revocation should not be equated with website logout.

**documented functionality:** [purchase flow](https://www.meta.com/help/superintelligence/1436362127544482/) supports link by stripe or a merchant account's saved card. the user reviews transaction details and merchant terms, approves, then checks confirmations. merchants fulfill orders; availability depends on merchant, region and checkout. the [launch architecture](https://muse.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse) describes single-use wallet credentials constrained by merchant, amount and lifetime. **primary partner evidence:** [link protections](https://support.link.com/questions/what-s-covered-with-protections) lists muse-through-link coverage up to $500 for damage/loss/theft, $250 for no-fee returns, $500 for price protection and $1,000 for the refund guarantee, subject to eligibility. these are bounded protections, not a universal reimbursement promise.

**documented functionality:** [muse mail](https://www.meta.com/help/superintelligence/1149305437517250/) creates a separate `@muse.ai` agent address without connecting the owner's inbox. ask it to contact a restaurant, review its email approval, deny and revise if necessary, then inspect sent/received mail. external correspondents can reply without a muse account. a verified owner email can submit instructions or selected forwarded context. deleting an address loses that address and its emails; sending limits exist but are unspecified.

**documented authority constraint:** [external-email safety](https://www.meta.com/help/superintelligence/1608220770565889/) warns that whoever controls a verified mailbox can send instructions. removing the address stops future instruction use but does not recover the mailbox or remove old emails. sensitive financial/health/credential requests require extra caution and approval. **inference:** email forwarding supplies context; verified sender enrollment additionally creates an authority-bearing ingress. these are different operations and should not be treated as interchangeable convenience features.

## artifacts, spaces and collaboration

**documented functionality:** [artifacts](https://www.meta.com/help/superintelligence/2074655449783957/) cover pdf/docx/text/markdown, xlsx/csv, common images, source files and interactive single-page tools. upload, request changes, or reference an earlier workspace file without reuploading. generated work appears in chat and the library. external sharing requires user action or approval. file-size ceilings, version history, conflict resolution, supported spreadsheet fidelity and public-hosting guarantees are unknown.

**available announcement:** [spaces](https://about.fb.com/news/2026/11/introducing-spaces-customize-muse-app/) turn a description into a persistent custom experience inside the app. examples include gift tracking, school dashboards, music monitoring, wedding planning, games and business order/client hubs. users iteratively revise them, edit data directly, pin them to sidebar/main tabs, hide them, and schedule when they appear. connected context updates them in the background. collaborative space sharing is explicitly exploratory, so it should not be counted as shipped multiuser editing. **unknown:** storage model, application sandbox, refresh triggers and permission propagation.

**inference:** spaces make generated software part of the agent's daily interface. an itinerary or dashboard can become the thing the user revisits, rather than another message to find. that distinction is visible at the product level without assuming a particular frontend or database.

## business interoperability

**available announcement:** [poppy version 1.0](https://muse.ai/blog/poppy-personal-agent-protocol) lets businesses publish `poppy.json` discovery and expose website, api/mcp or business-agent routes. muse is the first supported personal agent. oauth supports user-granted access; one session spans routes. mercury support is described as available, while bylt and hertz examples use future language. meta-verified connectors undergo review and end-to-end testing. this does not mean arbitrary advertised partner actions are universally live.

**documented protocol mechanism:** the [company implementation kit](https://personalagentprotocol.org/kit/company) describes signed `Poppy-Session` headers, published client keys, oauth tokens, scoped browser sessions established through a one-time code, and company-agent conversations/handoff. mcp is optional. a validator tests the company side; it is not the muse harness. **inference:** this supplies a structured path around trial-and-error browsing, while preserving the business's existing identity and authorization systems. protocol support is not evidence that every business endpoint already implements it.

## reliability, privacy, price and limits

**vendor-reported security evidence:** the november [bug-bounty report](https://muse.ai/blog/securing-muse) records over 630 submissions, 64 valid findings and approximately $1.2 million paid. examples include prelaunch trusted-proxy-header authentication failure, tool-output impersonation prompt injection, missed email passcodes, android webview credentials and mac update privilege escalation. fixes are vendor-reported; bounty volume neither proves insecurity relative to peers nor independently establishes robust protection. it does establish concrete classes of failure beyond the happy-path demonstrations.

**documented functionality:** [privacy/safety help](https://www.meta.com/help/superintelligence/1047255454427887/) describes isolated cloud vms, backups, no vm/conversation sharing with meta ad systems, separate permission checks, and issue reporting through settings or a phone shake. training use starts enabled and can be disabled, including for previous interactions. confidential vm remains future there. **unknown:** backup retention, user-controlled restore points, recovery-time guarantees and incident notification policy. no public evidence inspected establishes exact-once effects, reconciled ambiguous payments, or durable execution after vm failure.

**source conflict:** the [ios listing](https://apps.apple.com/us/app/muse-from-meta/id6760173601) carries a broad developer-supplied privacy label including advertising uses, alongside the narrower no-vm-data-to-ad-systems statement. the inaccessible full policy prevents resolving their exact scope. the same listing records a watch companion and feed widget; it requires ios/ipados 18 and watchos 9, and has an 18+ rating. **third-party observation:** one visible reviewer reports repeated wrong website data and transposed numbers; this is an anecdote, not a benchmark or mechanism disclosure.

**documented portability:** settings → data controls → download your muse data exports chats, files and agent information. reset deletes active tasks too. [data controls](https://www.meta.com/help/superintelligence/2225571704857152/).

**documented commercial terms:** [plans](https://www.meta.com/help/subscriptions/1021145227643680/) list power at $20/month with 500 million muse tokens weekly and maximum at $100/month with 3 billion weekly. subscriptions renew monthly; eligibility requires an available region, a meta account and adulthood. benefits vary by account/region. free usage is limited; its quantity was not established. do not read “muse tokens” as ordinary model tokens without an explicit conversion.

**documented functionality:** [additional usage](https://www.meta.com/help/subscriptions/28153473374286914/) can be bought without subscribing; subscribers can top up too. purchased and promotional extra tokens do not expire; included weekly usage does not roll over. entitlements are account-bound, nontransferable and ordinarily nonrefundable. consumption varies by request, model, context, tools and output; no fixed output quality/quantity is guaranteed. **unknown:** top-up price schedule, exact metering formula, concurrent/background task ceilings and behavior when a continuing task exhausts allowance.

## unresolved questions and transferable distinctions

these are research questions, not implementation proposals:

- which continuing-task facts are durable: intent, plan, last completed step, permission, evidence, or all five? public ui visibility does not answer crash recovery.
- does “forget” mean successful deletion across every derivative, or an agent's best-effort search? the current documentation explicitly supports only the latter assurance.
- what prevents a broad existing browser session from becoming authority for an unrelated task? local logged-in access and cloud credential isolation need separate scrutiny.
- how does revocation interact with already-running work, subagents and scheduled artifacts? permission review is visible; cancellation semantics are not.
- are unsolicited ideas cheap suggestions or automatically executing work? the boundary between recommendation, scheduling and effect authority remains underspecified publicly.
- how can users inspect *why* information or a permission influenced a decision? activity lists and editable files establish observability surfaces, not causal explanation or provenance completeness.
- which failures are retried, compensated, escalated or abandoned? advertised follow-through and a backup claim do not supply these contracts.

## corpus coverage and source ledger

all sources below were accessed 2026-11-14. help pages showing only relative update text retain it verbatim as a relative label; no publication date is inferred. full substantive help/blog text was inspected, including continuations. the official help index, four muse blog posts, launch/current feature announcements, product pages, protocol kit, app listing and payment partner coverage were checked. no authenticated surfaces or videos were executed. policy/terms returned a login wall. no inference is drawn from inaccessible text. some ai.meta.com pages rendered empty on direct open but exposed substantive indexed text; claims from them remain vendor descriptions.

| source title | explicit date/update | scope |
| --- | --- | --- |
| [muse — your personal ai agent from meta](https://muse.ai/) | undated | canonical identity and product landing |
| [introducing muse: the world’s first personal ai agent built for everyone](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/) | september 8, 2026; november 10, 2026 displayed | launch; current page retains future items |
| [muse help center](https://www.meta.com/help/superintelligence/1303670544995562/) | undated | official help corpus index |
| [how to get started with muse](https://www.meta.com/help/superintelligence/1331373868832401/) | “a day ago” | account, chat, files, voice |
| [download muse: free ai agent for mac & mobile](https://ai.meta.com/muse/download) | undated | client continuity |
| [give your muse a voice](https://about.fb.com/news/2026/11/introducing-muse-ai-voice-expressive-avatars/) | november 5, 2026; november 6, 2026 displayed | voice rollout and future devices |
| [how to customize muse's personality and memories](https://www.meta.com/help/superintelligence/995796179982326/) | “6 weeks ago” | personalization and zip import |
| [how to manage your muse data](https://www.meta.com/help/superintelligence/2225571704857152/) | “a day ago” | file controls, forget, export/reset |
| [how we designed muse](https://muse.ai/blog/how-we-designed-muse) | september 8, 2026 | goals, ideas, ongoing conversation |
| [how to manage reminders and scheduled tasks with muse](https://www.meta.com/help/superintelligence/1484325780075655/) | “9 weeks ago” | time/location/recurrence flows |
| [how muse works with connectors](https://www.meta.com/help/superintelligence/1687253048996149/) | “a day ago” | authorization, context, custom connectors |
| [how muse works with skills](https://www.meta.com/help/superintelligence/2797651547267109/) | “a day ago” | built-in skills and discovery |
| [muse for productivity: email, calendar, and files](https://ai.meta.com/muse/productivity/) | undated | advertised productivity workflows |
| [muse for fitness: training plans and nutrition](https://ai.meta.com/muse/fitness/) | undated | advertised fitness workflows |
| [agentic ai examples: real-world use cases across industries](https://ai.meta.com/muse/agentic-ai-examples/) | september 8, 2026 | suggested workflows; no live success evidence |
| [muse for small business: build your company with ai](https://muse.ai/business) | undated | named connectors and availability faq |
| [the future is for everyone: muse for small business](https://about.fb.com/news/2026/09/introducing-muse-small-business/) | september 29, 2026; october 8, 2026 displayed | business features and us/canada |
| [presentamos muse: el primer agente de ia personal del mundo creado para todos](https://about.fb.com/ltam/news/2026/09/presentamos-muse-el-primer-agente-de-ia-personal-del-mundo-creado-para-todos/) | explicit november 5 update; original september 8, 2026 | mexico availability and connectors |
| [how we built safety into muse](https://muse.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse) | september 8, 2026 | detailed launch architecture |
| [how your muse agent browses the web](https://www.meta.com/help/superintelligence/2124746764949121/) | “a day ago” | cloud browser, local extension |
| [how muse works with files and apps in your mac](https://www.meta.com/help/superintelligence/1126304576638594/) | “5 weeks ago” | local access and revocation |
| [muse home link user guide](https://www.meta.com/help/muse-charm/1645260456993247/) | “5 weeks ago” | setup, hardware, recovery |
| [how muse works with your guidance and approval](https://www.meta.com/help/superintelligence/1385290430137537/) | “a day ago” | permissions and observation |
| [muse keeps your data safe: security & privacy by design](https://muse.ai/security-and-privacy) | undated | public security promises and faq |
| [how muse works with payments](https://www.meta.com/help/superintelligence/1436362127544482/) | “a day ago” | purchase approval and checkout |
| [connect 1password to muse, by meta](https://support.1password.com/1password-muse/) | november 4, 2026 | available setup, approval expiry and limitations |
| [1password for meta muse: secure ai login](https://1password.com/partners/meta-muse) | undated | current partner functionality and enrollment |
| [1password for muse, from meta](https://marketplace.1password.com/integration/1password-for-meta-muse) | undated | indexed marketplace mechanism description; direct rendering sparse |
| [what’s covered with protections?](https://support.link.com/questions/what-s-covered-with-protections) | undated | partner coverage and ceilings |
| [about muse email addresses](https://www.meta.com/help/superintelligence/1149305437517250/) | “2 days ago” | agent mail and verified sender flow |
| [how to safely use your external email address with muse mail](https://www.meta.com/help/superintelligence/1608220770565889/) | “2 days ago” | email ingress authority and revocation |
| [how to use muse with artifacts](https://www.meta.com/help/superintelligence/2074655449783957/) | “9 weeks ago” | formats, editing, external sharing |
| [design the muse app, just for you](https://about.fb.com/news/2026/11/introducing-spaces-customize-muse-app/) | november 6, 2026 | spaces; collaborative sharing future |
| [more ways for muse to work with businesses](https://muse.ai/blog/poppy-personal-agent-protocol) | november 13, 2026 | protocol launch and partner statuses |
| [personal agent protocol: company implementation kit](https://personalagentprotocol.org/kit/company) | undated | disclosed company-side protocol mechanics |
| [securing muse: more than $1 million in bug bounties paid out](https://muse.ai/blog/securing-muse) | november 2, 2026 | reported bugs and fixes |
| [how muse handles your privacy, safety and security](https://www.meta.com/help/superintelligence/1047255454427887/) | “a day ago” | backups, training, reporting, future confidential vm |
| [muse from meta app — app store](https://apps.apple.com/us/app/muse-from-meta/id6760173601) | current version 15.1, “3d ago”; older explicit release dates | vendor release notes, compatibility, privacy label; user review |
| [about muse subscriptions](https://www.meta.com/help/subscriptions/1021145227643680/) | “9 weeks ago” | prices, allowances, eligibility |
| [how to buy additional muse tokens](https://www.meta.com/help/subscriptions/28153473374286914/) | “3 weeks ago” | usage entitlement and top-ups |
| [the biggest news from connect 2026](https://about.fb.com/news/2026/09/the-biggest-news-from-connect-2026/) | september 24, 2026 | announced glasses, charm and connector additions |
| [introducing muse wonder and muse wonder full: frontier models for agents](https://about.fb.com/news/2026/10/introducing-muse-wonder-models/) | october 12, 2026; october 13, 2026 displayed | product/model distinction; consumer rollout future there |
| [muse privacy policy](https://muse.ai/privacy), [terms](https://muse.ai/terms) | inaccessible without login | inspected entry points only; contents unknown |

the october model announcement says wonder will reach muse later; november's spaces announcement says specialized models trained with wonder learnings are rolling out. neither establishes that every consumer task runs wonder or wonder full. the september connect announcements also cannot independently establish current rollout of shop pay, paypal, expedia, glasses or charm. 1password's current dedicated setup documentation does establish its integration beyond the old future announcement. current help takes precedence for concrete user flows; future language remains future until separately evidenced.

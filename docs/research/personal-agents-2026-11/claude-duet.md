# claude duet: public product and mechanism dossier

as of 2026-11-14. public evidence only; no account, signup, purchase, or live product test. this is a competitor description, not a jarvis proposal. `AGENTS.md` and `SPEC.md` informed the final questions.

duet's research preview opened on 2026-10-21, targeting professionals and small business owners. [launch][launch] its clearest public implementation disclosure concerns credential and external-action boundaries; scheduling, durability, and memory internals remain less visible.

evidence labels mean: **documented mechanism** is a disclosed implementation or explicit operational contract, not independently audited proof; **vendor claim** is advertised behavior; **observed third-party report** is an attributed external observation; **inference** is this report's interpretation; **unknown** means the reviewed corpus does not establish it. none of the inventory's available features was personally tested.

## feature inventory

status “preview” means documented for the research preview, subject to access and connection requirements. source links lead to full pages, not search snippets.

| id | behavior | status | evidence | source |
| --- | --- | --- | --- | --- |
| DUET-01 | us pro/max/ultra; invitation required; team/enterprise excluded | preview | vendor claim | [help][help] |
| DUET-02 | standalone ios/android and web | preview | vendor claim | [launch][launch] |
| DUET-03 | waitlist identity must match claude and phone-store accounts | preview | documented mechanism | [help][help] |
| DUET-04 | typed messages, hold-to-talk, spoken conversations | preview | vendor claim | [ios listing][ios] |
| DUET-05 | voice mute; conversation survives screen lock/app switching | ios release | documented mechanism | [ios history][ios] |
| DUET-06 | topic channels share context | preview | vendor claim | [android listing][android] |
| DUET-07 | inherited claude memory, skills, apps | preview | vendor claim | [launch][launch] |
| DUET-08 | morning brief and initial draft preparation | preview | vendor claim | [launch][launch] |
| DUET-09 | account checks every few hours; neglected-thread follow-up | preview | vendor claim | [android listing][android] |
| DUET-10 | cloud work continues after app closure | preview | vendor claim | [launch][launch] |
| DUET-11 | tasks list; input-needed highlighting; owner marks completion | preview | documented mechanism | [help][help] |
| DUET-12 | files in make tab | preview | vendor claim | [help][help] |
| DUET-13 | briefs, decks, models, dashboards, prototypes, web apps | advertised workflows | vendor claim | [launch][launch] |
| DUET-14 | plugins, including small-business plugin; plugin suggestions | preview | vendor claim | [help][help] |
| DUET-15 | over 6,000 connectors/plugins | advertised aggregate | vendor claim | [product][product] |
| DUET-16 | stripe invoices, payment links, products/prices, revenue, refunds | partner integration | vendor claim | [stripe][stripe] |
| DUET-17 | shopify products, inventory, orders, performance | partner integration | vendor claim | [shopify][shopify] |
| DUET-18 | connector-free websites through cloud browser | preview | vendor claim | [help][help] |
| DUET-19 | browser traffic identifies as `Claude-Agent` | current | documented mechanism | [browser identity][browser] |
| DUET-20 | link purchases require wallet approval | preview | documented mechanism | [link][link] |
| DUET-21 | shop pay purchases require wallet review | preview | documented mechanism | [shop pay][shop] |
| DUET-22 | 1password sign-in integration | documented november support | documented mechanism | [duet setup][password] |
| DUET-23 | follow, message, answer claude code sessions from sessions | ios november 6 release | documented mechanism | [ios history][ios] |
| DUET-24 | share photos/links/text/pdfs into duet | ios october 28 release | documented mechanism | [ios history][ios] |
| DUET-25 | home-screen widget lists open tasks | ios november 2 release | documented mechanism | [ios history][ios] |
| DUET-26 | generated-video playback; code cards; full-screen line numbers | ios releases | documented mechanism | [ios history][ios] |
| DUET-27 | opus 5.5; automatic effort; no model picker | preview | vendor claim | [help][help] |
| DUET-28 | shared past-chat search setting | account feature | documented mechanism | [memory][memory] |
| DUET-29 | memory import/export through claude | account feature | documented mechanism | [memory portability][portability] |
| DUET-30 | no browser watching/takeover; no local-computer files | preview limits | documented mechanism | [help][help] |
| DUET-31 | no outbound calls/texts; approved connected-account email | preview limits | vendor claim | [help][help] |
| DUET-32 | slack limited; personal finance unavailable | preview limits | documented mechanism | [help][help] |
| DUET-33 | no trading, inter-account money transfers, others' accounts | prohibited | documented mechanism | [security][security] |
| DUET-34 | per-task pages; mid-task steering | preview | vendor claim | [security][security] |
| DUET-35 | intent check independent of working model | disclosed | documented mechanism | [security][security] |
| DUET-36 | sensitive-information check on messages/browser uploads | disclosed | documented mechanism | [security][security] |
| DUET-37 | no extra duet subscription charge; background usage counts | preview | documented mechanism | [help][help] |
| DUET-38 | native agent delegation, concurrency ceiling | unestablished | unknown | reviewed corpus |
| DUET-39 | duet artifact collaboration/public publishing | unestablished | unknown | reviewed corpus |
| DUET-40 | custom personality, voice choice, persona controls | unestablished | unknown | reviewed corpus |

## disclosed mechanisms and their limits

### authority, confidentiality, and credentials

the security article describes a command-controlled browser vm, proxy-replaced token placeholders, and passwords encrypted for a single-use browser-held key. approval cards include recipients and content. intent and sensitivity checks run separately. credentials and full financial/government identifiers cannot be shared; other private information requires consent. it reports red-team and external penetration testing without duet-specific failure rates. [security][security]

the directly linked managed-agents engineering article explains the related credential design: oauth secrets live outside the sandbox; a proxy resolves session-associated authority. it separately describes durable event sessions, replaceable harnesses, and execution sandboxes. **scope caution:** duet explicitly adopts credential separation; that does not establish adoption of every managed-agents persistence, recovery, or multi-agent interface. no duet crash-recovery guarantee follows from this lineage. [managed agents][managed]

the linked claude-code auto-mode article describes a two-stage classifier and removal of assistant prose/tool results from classifier input, retaining user messages and executable calls. it also reports imperfect authorization judgments. **scope caution:** duet documents an extension of that classifier, not identical prompts, stages, metrics, exceptions, or delegation checks. code's false-negative rates must not be presented as duet's rates. [auto mode][auto]

the browser-use research describes model training and red-team work against hostile instructions in pages. it predates duet and tests other model/product configurations. it supplies the stated research lineage, not a quantitative duet assurance. a browser vm isolates site execution; it cannot by itself stop page text from persuading the agent to make an authorized-looking external request. that last distinction is architectural inference. [browser research][injection]

duet browsing uses a real browser's user agent plus `Claude-Agent`; published source ips appear at `https://claude.com/.well-known/sail`. website operators should check both, since the header alone is forgeable. agent browsing and anthropic's crawlers have separate controls. this supplies a concrete explanation for some site incompatibility without treating all blocked checkouts as agent failure. [browser identity][browser]

### payments: separate task consent from spending authority

link is distinct from the stripe business connector. connection starts under the duet avatar's payments menu. the user approves a maximum spend through link; duet receives a one-time card constrained by merchant and amount. a us funding method is required. recurring link payments are unsupported. checkout can fail after approval and leave a temporary pending authorization. merchants handle orders/refunds; link handles payment disputes and authorization problems; anthropic handles wrong item/store/quantity selection. approval therefore does not prove purchase completion. [link][link]

shop pay is separately connected inside duet, including a mobile recommended-connectors route. the user selects “Review in Shop Pay” and approves before a scoped one-time card is used. duet can see card last-four/expiry and billing address, not full account numbers. blocked sites can require manual completion. shop pay is neither the shopify store-management connector nor a general expansion of duet's banking authority. [shop pay][shop]

stripe confirms that its mcp server and link wallet are separate integrations. its examples combine buying supplies with business operations such as refunds or invoice issuance. the article does not publish duet's precise approval classification for each stripe operation; the existence of an endpoint is not evidence that the agent may invoke it autonomously. [stripe][stripe]

shopify confirms duet support for shop pay on and off shopify and a separate connector for merchant operations. its account of off-platform purchases uses payment-network tokens. that is partner evidence for payment infrastructure, not proof of universal merchant acceptance or unrestricted merchant-admin permissions. [shopify][shopify]

### 1password: newer support changes the launch-era answer

the october 22 partner announcement said duet integration was forthcoming. the november 5 dedicated support page now gives connection instructions and minimum duet versions: ios `1.261107.0`, android `1.261103.17`, or web. it requires 1password `8.12.42`, an individual/family `.com` account, and approved login items. mobile uses settings/connections; web uses settings/credentials. approvals expire after 30 days. passkeys, sign-in-provider items, shared vaults, business/team accounts, and `.ca`/`.eu` accounts are excluded. this is documented support, not a personally verified rollout. [announcement][password-launch], [duet setup][password]

the general agent contract says the extension fills username/password/otp directly into the website while the agent's view is hidden. connection alone grants no vault browsing; the user selects or rejects a suggested login. website-session lifetime remains the site's decision, distinct from the 30-day credential approval. disconnecting an integration and asking a website to sign out address different authorities. [agent sign-in][password-general]

1password's security description splits decryption material between provider and 1password, uses connection keysets and locally derived item approval keys, and decrypts within a confidential-computing enclave before delivering the item to the hosted browser extension. these are vendor-described mechanisms. credential invisibility to the model still depends on the agent provider honoring its observation boundary; it is not a claim that anthropic infrastructure never processes credentials. [1password security][password-security]

### context, memory, and portability

duet searches duet chats and ordinary claude chats outside projects. [help][help] claude's memory help explicitly includes duet as a reader and contributor. chat search and generated memory are separate controls. duet's search control is shared with claude. memory entries can survive deletion of the conversation that produced them. sensitive memory has its own settings and exclusions. account-level documentation should not be converted into a claim that every chat-level incognito or memory-off control appears in duet's interface. [memory][memory]

disconnecting an app stops new access without removing learned information. duet can file a support report when told what went wrong. [security][security]

memory import/export is available through claude's settings. import extracts entries from pasted material and is explicitly experimental; export exposes the remembered representation for copying. this is useful preference portability, not a lossless archive migration or a supported migration of task state, approvals, browser sessions, connectors, and receipts. [memory portability][portability]

ordinary account export includes chats and account data, excludes original uploaded files, arrives through an authenticated emailed link, and cannot be imported into another personal claude account. the article does not enumerate duet task pages, generated make files, or sessions records, so complete duet export coverage remains unknown. [account export][export]

the consumer training policy permits use after model-improvement opt-in, safety review, or other explicit training consent. raw connector material is excluded, but material copied into the conversation can enter the applicable conversation policy. this account-wide policy is relevant because duet uses a consumer account; the page does not give a separate duet-by-data-type matrix. [training policy][training]

consumer retention documentation distinguishes immediate removal from chat history from backend deletion within 30 days, with training, safety, feedback, and legal exceptions. model-training data can be retained de-identified for up to five years after opt-in; policy-violation and feedback data have separate periods. this qualifies any casual reading of “delete” as instantaneous erasure everywhere. [retention][retention]

## concrete workflows and interaction design

the launch's named examples include calendar-error detection, pre-meeting company preparation, and noticing a meeting immediately before travel. these are vendor-selected accounts, not independent performance measurements. the product page illustrates a business brief, opening checklist, investor deck preparation, a purchase approval, and a dashboard refreshed before the morning brief. **inference:** the intended unit of value is a prepared decision with supporting work already done. the dashboard mockup is not evidence of a general scheduling api or refresh reliability. [launch][launch], [product][product]

the ios history also documents text selection. it does not establish who creates the code sessions, how delegation works, or whether multiple tasks execute concurrently. [ios history][ios]

android's current listing explicitly positions duet as stronger at work than personal errands. its periodic checks mean urgent arrivals can fall between observations. **inference:** the product competes on attention triage, with an intentional latency/cost tradeoff. neither a delivery-time guarantee nor an emergency-notification service is documented. [android listing][android]

the connector help explains that connectors are mcp-backed integrations with differing read/write capabilities and permissions. generic claude supports custom remote servers, but that page does not establish exhaustive duet compatibility. connection metadata, per-operation availability, and duet policy still matter. neither the 6,000 aggregate nor a partner logo is an operation-level support matrix. [connectors][connectors]

## price, limits, and failure visibility

current us web pricing is pro $20 monthly or $200 annually, max $100 monthly, ultra $200 monthly, before tax. max advertises 5× pro usage; ultra 10× weekly usage and no five-hour ceiling for verified accounts. these are plan terms, not guaranteed tasks per dollar. do not substitute historical max tiers for today's price table. [pricing][pricing]

the duet help currently grants three preview limit resets to pro and one to max/ultra, expiring 2026-12-15. the general reset documentation says resets replenish consumption rather than raise limits, cannot be undone, and do not refund paid extra usage. historical snippets describe an earlier reset offer; this report uses the opened current help. [help][help], [resets][resets]

duet's ios privacy label lists identity-linked content, location, identifiers, usage, diagnostics, and purchase categories; apple says it has not verified the developer's declarations. android declares transit encryption, deletion requests, and possible collection/sharing. neither label proves content confidentiality, data residency, or the absence of human access. [ios listing][ios], [android listing][android]

## evidence gaps and transferable questions

these are research questions, not jarvis commitments. absence from documentation is not proof that a feature is absent.

| area | unresolved question / useful next evidence |
| --- | --- |
| task semantics | does user-marked completion control execution, reminders, or only list visibility? what state survives server failure? a task lifecycle contract would settle this. |
| scheduling | can users specify cron-like routines, timezones, missed-run behavior, quiet hours, or event triggers? the marketing refresh example cannot settle these semantics. |
| authority | what exactly may “don't ask again” cover? does an edited draft invalidate consent? what immutable payload does approval bind? |
| recovery | what happens after a timeout between sending and receipt? are duplicates reconciled? no public duet idempotency or uncertain-effect contract was found. |
| concurrency | how many active tasks, browsers, models, or code sessions can run together? how does steering affect already entered effects? |
| observation | can users inspect tool arguments/results, source coverage, retries, usage by task, and the difference between paused and failed? task pages alone cannot answer. |
| memory | how are memories selected, updated, attributed, contradicted, or compacted? what are retrieval bounds and cross-channel precedence? account help describes controls, not duet internals. |
| files/artifacts | exact upload sizes/types, generated-file persistence, version history, publishing, collaboration grants, and complete export coverage are unestablished. |
| personality/voice | continuous voice transport, interruption behavior, available voices, custom style controls, and accessibility parity need direct documentation or authorized testing. |
| connectors | exact slack restrictions and operation-specific parity need a duet support matrix. earlier indexed help excluded microsoft 365; the current directly opened page omits that restriction. current support is unresolved; a logo does not establish it. |
| privacy | cloud region, browser-session retention, classifier retention, support-report payloads, and precise duet training/export coverage need an explicit product matrix. |

for jarvis, [the specification](../../../SPEC.md) already distinguishes owner-requested wakes from autonomous polling and exact action receipts from model assertions. duet raises useful questions about the value of periodic triage and prepared decisions, but offers no public evidence that resolves those tradeoffs for this owner. attention savings should be evaluated against false urgency, background consumption, and the cost of reconstructing a lost plan. richer visible task organization should earn its complexity through actual work, rather than be inferred as a prerequisite for persistence.

## source ledger and coverage

all sources accessed 2026-11-14. “undated” means no explicit publication date; relative “updated today” strings were not converted into publication dates. official support, launch/product/security pages, directly linked mechanism articles, payment partners, credential partner, and both public app listings were opened. translations/search snippets helped discovery but were not treated as extra independent evidence. app reviews were not used to establish features. no inaccessible authenticated product was tested; no public full duet runtime, task schema, recovery specification, or operation-complete connector manifest was found in this search.

| key | full source / explicit date | scope |
| --- | --- | --- |
| launch | [Introducing Claude Duet][launch] — 2026-10-21 | launch, target users, examples |
| help | [Get started with Claude Duet][help] — undated | current support contract |
| product | [Claude Duet][product] — undated | marketing, illustrative ux |
| security | [Claude Duet Safety, Privacy, and Security][security] — 2026-10-23 | duet-specific boundaries |
| managed | [Scaling Managed Agents: Decoupling the brain from the hands][managed] — 2026-04-08 | linked architectural lineage |
| auto | [How we built Claude Code auto mode][auto] — 2026-03-25 | linked classifier lineage |
| injection | [Mitigating the risk of prompt injections in browser use][injection] — 2025-11-24 | linked research lineage |
| browser | [How do Anthropic-hosted browsers identify themselves…][browser] — undated | browser identification |
| link | [How to use Link by Stripe with Claude Duet][link] — undated | wallet setup, settlement limits |
| shop | [How to use Shop Pay with Claude Duet][shop] — undated | wallet setup and limits |
| stripe | [Stripe and Anthropic help entrepreneurs run their business inside Claude Duet][stripe] — 2026-10-21 | partner integration |
| shopify | [Exponential: Shopify's Fall '26 Edition][shopify] — 2026-10-28 | partner integration |
| password-launch | [Introducing 1Password for Agents][password-launch] — 2026-10-22 | historical announcement |
| password | [Connect 1Password to Claude Duet][password] — 2026-11-05 | current product setup |
| password-general | [Use 1Password to sign in to sites with supported agents][password-general] — 2026-11-04 | shared sign-in contract |
| password-security | [About the security of 1Password for Agents][password-security] — undated | cryptographic mechanism |
| memory | [Use Claude's chat search and memory to build on previous context][memory] — undated | account memory, duet inclusion |
| portability | [Import and export your memory from Claude][portability] — undated | memory portability |
| connectors | [Use connectors to extend Claude's capabilities][connectors] — undated | account connector contract |
| export | [Export your Claude data][export] — undated | account export |
| training | [Is my data used for model training?][training] — 2026-03-16 | consumer policy |
| retention | [How long do you store my data?][retention] — 2026-07-01 | consumer retention |
| pricing | [Plans & pricing][pricing] — undated | current us web prices |
| resets | [What is a limit reset?][resets] — undated | usage replenishment |
| ios | [Claude Duet by Anthropic — App Store][ios] — release dates within page | developer descriptions/history |
| android | [Claude Duet — Google Play][android] — updated 2026-11-13 | developer description/privacy |

[launch]: https://claude.com/resources/articles/claude-duet
[help]: https://support.claude.com/en/articles/17631495-get-started-with-claude-duet
[product]: https://claude.com/product/claude-duet
[security]: https://claude.com/resources/articles/claude-duet-safety-privacy-and-security
[managed]: https://www.anthropic.com/research/managed-agents
[auto]: https://www.anthropic.com/research/claude-code-auto-mode
[injection]: https://www.anthropic.com/research/prompt-injection-defenses
[browser]: https://support.claude.com/en/articles/18234133-how-do-anthropic-hosted-browsers-identify-themselves-when-they-browse-the-web-on-a-user-s-behalf
[link]: https://support.claude.com/en/articles/17666484-how-to-use-link-by-stripe-with-claude-duet
[shop]: https://support.claude.com/en/articles/17666489-how-to-use-shop-pay-with-claude-duet
[stripe]: https://stripe.com/newsroom/news/anthropic-and-stripe
[shopify]: https://www.shopify.com/news/fall-26-edition-merchant
[password-launch]: https://1password.com/blog/1password-for-ai-agents
[password]: https://support.1password.com/1password-claude-duet/
[password-general]: https://support.1password.com/1password-for-agents/
[password-security]: https://support.1password.com/1password-for-agents-security/
[memory]: https://support.claude.com/en/articles/11817273-use-claude-s-chat-search-and-memory-to-build-on-previous-context
[portability]: https://support.claude.com/en/articles/12123587-import-and-export-your-memory-from-claude
[connectors]: https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-s-capabilities
[export]: https://support.claude.com/en/articles/9450526-export-your-claude-data
[training]: https://privacy.claude.com/en/articles/10023580-is-my-data-used-for-model-training
[retention]: https://privacy.claude.com/en/articles/10023548-how-long-do-you-store-my-data
[pricing]: https://claude.com/pricing
[resets]: https://support.claude.com/en/articles/17007452-what-is-a-limit-reset
[ios]: https://apps.apple.com/us/app/claude-duet-by-anthropic/id6803276000
[android]: https://play.google.com/store/apps/details?hl=en_US&id=com.anthropic.aibo

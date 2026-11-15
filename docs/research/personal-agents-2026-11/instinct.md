# instinct: public product and implementation evidence

as of 2026-11-14. this dossier concerns spear street technology's instinct, founded by noah shinn. it does not describe an open-source clone. evidence categories and research limits follow [method.md](method.md). no account was created and no task was executed.

instinct's distinctive proposition is delegation through an existing conversation: ask, refine, and receive the result without operating the underlying applications. its most useful disclosed developments are more specific: an independent email identity, private-agent coordination, a separate group agent, interactive deliverables, credential brokering, and two materially different payment approval models. the public engineering evidence is uneven. partner documentation establishes concrete login and payment mechanisms; the agent's memory and execution recovery remain largely undisclosed.

## availability and source quality

the august launch described an invite-only beta constrained by compute availability. the september company release still called the product early access. the current landing page offers login, invitations and a trial entry point but supplies no country matrix or public price schedule. therefore general unrestricted availability is unresolved; a feature becoming available to all existing users does not establish open enrollment. [S01], [S03], [S04]

the reviewed sources include current integration guides, legal pages, founder announcements and first-person accounts. many original x pages returned 403. their full public post text was retrieved through the public fxtwitter mirror, with author, original post id and timestamp retained. the september trusted-network post was also checked against vxtwitter and x's own syndication excerpt. these remain attributed primary statements with an intermediary retrieval dependency, not independently observed behavior.

the september 28 interview's publisher page exposes chapters and an introductory excerpt, but gates the full transcript behind login. youtube yielded no usable transcript. the publisher's own security clip supplies direct architectural statements; detailed model names, inference multipliers and runtime claims repeated in secondary summaries are not promoted to verified disclosures here. [S18], [S19]

## feature inventory

“announced available” means the vendor says users can use it; it does not mean this investigation exercised it. current partner guides provide the stronger “documented available” designation.

| id | behavior and practical boundary | availability | evidence |
| --- | --- | --- | --- |
| INST-01 | text or call a personal assistant; it operates a phone and computer to perform errands. | currently marketed | vendor claim [S01] |
| INST-02 | imessage interaction supports replies in threads and read receipts; whatsapp is another conversation channel. | observed september; whatsapp reaffirmed november | third-party observation [S20]; vendor statement [S29] |
| INST-03 | invitations support onboarding through existing users. unrestricted enrollment and country coverage remain unresolved. | restricted at launch; current boundary unclear | vendor claim [S03], [S04] |
| INST-04 | agent-owned email sends and receives business correspondence, booking confirmations and service signup mail. | announced available september 8 | vendor claim [S05] |
| INST-05 | forward one email or add the agent to a thread without granting an entire mailbox; examples include returns, contractor quotes and scheduling. | announced available september 8 | vendor claim [S06] |
| INST-06 | google workspace connection covers gmail, calendar, drive, docs, sheets, slides and tasks. exact oauth scopes and individual operation coverage are unpublished. | documented integration | policy disclosure [S02] |
| INST-07 | concierge handles business calls and high-touch bookings, including phone-only restaurants and cancellation lists. | early-access rollout september 16; included in september 28 release | vendor claim [S07], [S04] |
| INST-08 | shared imessage location can trigger arrival-aware suggestions and answers. | announced available september 28 | vendor claim [S04] |
| INST-09 | groceries, train trips, gifts and court bookings are advertised everyday tasks. | currently marketed | vendor claim [S01] |
| INST-10 | log into providers for bill negotiation, price monitoring, inbox cleanup, travel, camp registration and supplies. | current partner examples | vendor claim; no success measurement [S21] |
| INST-11 | native vault holds account login information. | documented feature; detailed storage design unknown | legal disclosure [S22] |
| INST-12 | vault can retain an authenticator seed and generate time-based codes, including enrollment on supported services; phone approvals can still interrupt. | announced available to all users september 11 | disclosed mechanism [S08] |
| INST-13 | 1password fills an approved login into the hosted browser; no need to paste it into chat. | documented available november 5 | documented behavior [S09] |
| INST-14 | reuse login approval for 30 days, subject to supported account, vault and item types. | documented available | documented behavior [S09] |
| INST-15 | trusted-person network lets personal agents coordinate only with approved contacts. | september 9 early access; september 14 all users | vendor claim [S12], [S13] |
| INST-16 | recurring coordination can adjust a standing appointment when either participant has a calendar conflict. | september 14 user example reported by vendor | vendor claim [S13] |
| INST-17 | send original files directly between trusted agents for further analysis or editing; transfers are claimed end-to-end encrypted. | announced available september 23 | disclosed mechanism, unaudited [S14] |
| INST-18 | connection invitations require explicit acceptance; owners can replace and invalidate invitation links. | announced available september 23 | vendor claim [S14] |
| INST-19 | create private or link-shared interactive files: comparisons, itineraries, checklists and expense tools; recipients need no instinct account. | announced rolling to all users september 18 | vendor claim [S15] |
| INST-20 | add a separate assistant to an imessage group, including participants without instinct accounts. | october 5 early access; october 27 announced available to everyone on imessage | vendor claim [S16], [S17] |
| INST-21 | group agent has no direct personal-account access; personal agents mediate requests and confirmation. | same group rollout | disclosed authority model [S16], [S17] |
| INST-22 | group trust can be revoked; new membership holds pending personal-agent replies until permission is renewed. | disclosed october 5 | disclosed mechanism [S16] |
| INST-23 | shop pay supports purchases at merchants on and off shopify without exposing the actual card to the agent. | current partner documentation | documented behavior/disclosed mechanism [S23] |
| INST-24 | funded link balance allows purchases below an owner-selected per-purchase approval threshold. | october 26 rollout in eligible us regions; new york pending in reviewed announcement | vendor claim plus partner confirmation [S24], [S25] |
| INST-25 | link threshold can be changed through an owner-facing link; zero requires approval for every purchase. | documented available | documented behavior [S26] |
| INST-26 | opentable partnership supports finding, booking and moving restaurant reservations. | announced available october 30 | vendor claim [S27] |
| INST-27 | decagon names instinct as a partner for a dedicated business-side personal-agent gateway. | partner announcement; end-user coverage unresolved | disclosed partner mechanism [S28] |
| INST-28 | incoming content filters and a separate action monitor can block or pause agent activity. | disclosed september 28 | disclosed mechanism; efficacy unmeasured [S18] |
| INST-29 | small models detect allegedly ungrounded generation and can steer or intercept subsequent thinking/tool execution. | announced deployed september 23 | disclosed mechanism plus performance claims [S30] |
| INST-30 | indexed external data deletion and training opt-out are separate controls from connector disconnection. | documented policy | documented behavior [S02] |
| INST-31 | ongoing conversation accepts constraints and follow-up; a reviewer received a fresh-start response to `/new`. actual memory erasure is not established. | september observation only | third-party observation [S20] |
| INST-32 | task recovery, cancellation guarantees, complete audit export, execution ceilings and concurrency limits lack a reviewed public contract. | unknown | corpus gap |

## workflows and interaction design

### delegate a conversation, not an entire inbox

the agent-owned email feature separates receiving a task from ingesting a whole account. a forwarded order confirmation can become a return workflow: communicate with support, resolve refund-versus-replacement preference, then deliver a label. a contractor thread can become a bounded follow-up task. the announcement explicitly permits this without full mailbox access. the unresolved parts are sender authentication, authority from additional thread participants, unsolicited mail handling and message approval defaults. [S05], [S06]

inference: the useful primitive is a durable delegation address. it lets an owner hand off evidence together with the relevant correspondence. fewer account permissions may be necessary, but an email address is not by itself an authorization boundary. the product still needs to distinguish the owner's request from a merchant's instructions and from an unrelated sender.

### coordinate people through distinct agents

the trusted network first offered private assistant-to-assistant coordination; the later group feature introduces a shared conversational participant. these are different interaction models. september examples include a ten-person dinner and maintaining recurring tennis availability. october's shared agent instead operates in the visible group conversation. [S12], [S13], [S17]

the initial group announcement describes a concrete membership-change safeguard: hold pending private replies when the audience expands. [S16] inference: this addresses a real race between consent and disclosure. permission given for four recipients should not silently authorize a fifth. it is more consequential than simply adding a participant list to a prompt. however, the published statement does not explain how already-disclosed information, copied files, revoked connections or simultaneous membership changes are handled.

### turn results into usable objects

files are described as interactive pages rather than ordinary chat attachments. announced examples include apartment comparisons with photos and commute information, gallery routes, meal checklists and group-expense entry. private versus link-shared delivery allows the owner to choose a wider audience. [S15]

inference: this separates the request surface from the result surface. a text thread is convenient for intent; an itinerary or editable cost split needs spatial organization and persistent state. public evidence does not establish version history, source citations, offline export, collaboration conflict handling, link revocation, execution sandboxing or a portable backing format. “interactive” should not be inflated into a general hosted-app development platform.

### move from plans to external completion

the october opentable announcement explicitly includes rescheduling after plans change. [S27] inference: a booking assistant is incomplete if its only successful state is initial checkout. continuing responsibility includes changes, cancellation terms, confirmations and recovering from partial execution. instinct markets these outcomes, but this review found no general completion protocol describing how it proves that a reservation, payment or cancellation actually succeeded.

## disclosed implementation and its limits

### execution and service integration

the company describes an assistant with its own phone and computer. its september release names isolated sandboxes, temporary local credentials and identity-signed execution. [S04] those names do not establish the isolation technology, signing protocol, persistence lifetime or enforcement completeness. no reviewed source identifies the production database, orchestration framework, browser provider, cloud provider, virtual-machine technology, queue or durable action state machine.

the november evidence rules out the simplistic description “it only clicks websites.” google workspace has documented api access; shopify identifies its catalog and checkout as underlying instinct's commerce experience. shopify separately describes structured storefront tools, but that does not prove instinct calls every such tool. [S02], [S31] inference: the supported account and merchant boundary determines the integration route; browser automation and partner interfaces can coexist.

decagon's gateway detects personal agents and serves them through a channel governed by the business's permissions and procedures. its announcement names instinct and muse. [S28] this is evidence of a counterpart integration, not evidence that instinct has a public developer api or that every decagon customer is reachable. decagon's own model providers and telephony infrastructure must not be attributed to instinct.

### credentials: three separate kinds of authority

vault authenticator support means the agent can possess a seed sufficient to produce future one-time codes. enrollment can need initial owner intervention, and some services support an additional authenticator alongside the owner's existing one. [S08] this is different from repeatedly asking the owner for a current code.

1password's current setup requires an individual/family account on its .com service and mobile app 8.12.42 or later. supported items are username/password/one-time-code logins in personal/private vaults; business/team accounts, .ca/.eu accounts, passkeys, shared vaults and federated sign-in items are excluded. the prompt shows requester, reason and proposed login; the owner selects and approves. website sessions have their own lifetimes. disconnecting removes integration approvals; it does not state that existing website sessions are destroyed. [S09]

1password discloses split decryption material, a connection key held by the developer, a confidential-computing enclave, and encrypted delivery of approved credentials to its extension inside the agent's browser. the owner approves in an unlocked 1password app; the agent cannot approve itself. 1password explicitly limits its guarantee to credential handling: post-login activity depends on the agent's safeguards, and possible model visibility depends on the developer's environment. [S10]

inference: connection consent, item access and authority to act after login are separate. an approved airline login does not establish permission to change a flight. similarly, a 30-day item approval is not a task-bound execution permit. these distinctions should survive any comparison with jarvis.

### payments: checkout approval versus standing spending permission

shopify's october release describes card-network tokens for off-platform purchases and identifies instinct as a supported agent. it does not publish instinct-specific spending ceilings or a merchant-complete availability matrix. [S23]

link balance is different: an owner funds a balance and sets a limit for purchases that may proceed without another approval. tempo confirms its rollout for instinct, stablecoin settlement and the announced geographic restriction. [S24], [S25] link setup requires identity verification using date of birth and social-security-number information. its guide says an invalid setup link should be checked for a usd funding amount no greater than $150. this is a setup condition, not a universal purchase ceiling. it also distinguishes the per-purchase threshold from available funds. [S26]

inference: neither “always asks before paying” nor “autonomous spending” is an adequate global description. the selected payment path matters. a per-purchase threshold does not bound cumulative spending across a series of purchases; the funded balance is a separate control. public evidence does not establish transaction deduplication, refunds after ambiguous outcomes, replenishment policy or a cross-provider lifetime budget.

### filters, monitors and hallucination correction

in the publisher's security clip, shinn describes inbound filters and a separate system observing proposed actions and thinking, with power to pause, intercept or reject what happens next. [S18] a september incident response names small detector models intended to flag ungrounded claims and intervene before subsequent generation or tool execution. the post also denies that the incident involved a cross-user breach. these are company explanations, not an independent forensic conclusion or measured prevention rate. [S30]

unknown: the detectors' input boundaries, training data, false-positive rates, failure modes, grounding receipts and relationship to payment/login enforcement. independent monitoring is a disclosed responsibility split. it is not evidence that every side effect passes through a transactional host gate, or that every claim is checked against a retained original.

### memory and scheduling

public evidence establishes personalization as a product promise, retained external indexing as a policy concern, and recurring coordination as an announced behavior. it does not expose a memory schema, retrieval algorithm, context-compaction strategy, provenance model, correction precedence, expiry policy or recall benchmark. [S01], [S02], [S13]

the `/new` exchange in one review is only a conversational acknowledgment, not proof of a documented command or deletion operation. that review also distinguishes acknowledged tasks from completed results, a useful restraint absent from many promotional lists. [S20]

unknown: what wakes background work; whether monitoring uses polling, events or both; how missed runs are caught up; how ongoing commitments are bounded; whether unfinished work persists across process loss; and whether a new request interrupts, queues or runs concurrently. no public plan limits, task quotas, frequency floors or reliable latency distribution were established.

## privacy, interruption and economics

the privacy policy permits model training on ordinary user material, with a forward-only settings opt-out and a safety-review exception. directly received workspace data is excluded. connector disconnection does not erase indexed data; the workspace provides deletion controls. retention periods, named model subprocessors and end-to-end protection of all user data are not established. [S02]

the terms exclude vault materials from training, authorize the service to make binding commitments on the user's behalf, and warn that action records can be inaccurate. they allow paid services but publish no applicable price here. no reviewed source supplies a general stop/cancel guarantee. [S22]

the november 2 founder statement attributes a whatsapp reply outage to a payment interruption caused by configuration, says incoming messages were received and promises follow-up. [S29] inference: delivery recovery and task recovery are different. “we received your message” cannot tell an owner whether a purchase executed before replies stopped. the public statement does not supply duplicate-execution or reconciliation guarantees.

the interview publisher describes a transaction-take-rate business model and opposition to advertising. it does not provide a current customer tariff or prove merchant commissions cannot affect ranking. [S19] inference: payment adoption and transaction volume measure commercial engagement, not alignment or task reliability. avoiding advertisements would leave the separate question of whether merchant economics influence recommendations. this pass found no public ranking neutrality contract.

## implications for later jarvis planning

these are product hypotheses, not changes to the spec or delivery order:

- an agent email address could reduce the access needed for returns and correspondence. the missing contract is who can initiate work and approve communication, not merely smtp connectivity. see INST-04–05.
- interactive results could make planning useful outside chat without introducing a general app platform. begin with a concrete owner artifact, then identify the smallest durable representation. see INST-19.
- recurring commitments require explicit ownership of follow-up and evidence of completion. a wakeup alone does not establish that responsibility. see INST-16 and INST-32.
- group assistance needs per-person authority and audience-sensitive disclosure. the membership-change hold is a precise behavior worth studying; it would be a substantive expansion of jarvis's single-owner boundary. see INST-20–22.
- partner-held credentials and constrained payment instruments absorb some execution risk, but neither grants product authority. login approval, purchase approval and ongoing spending permission must remain separate concepts. see INST-13–14 and INST-23–25.

## coverage and remaining gaps

the pass covers messaging, voice, email, google workspace, location, vault/authenticators, 1password, files, trusted agents, group agents, shopping, payments, restaurants, counterpart business gateways, filtering, privacy and interruption. the current partner guides are stronger than old promotional shorthand.

no verified public implementation established memory internals, model routing, private model identity, exact compute economics, telephony provider, human involvement in concierge, call recording/disclosure defaults, autonomous task limits or action recovery. leaked desktop screenshots and speculative “agent phone” reports were not used as shipped-feature evidence. the legal pages' mention of desktop/mobile applications does not itself establish app-store availability.

secondary discovery sources included [open-instinct research](https://github.com/mariagorskikh/open-instinct/blob/main/docs/research/INSTINCT.md), [any inkling](https://anyinkling.com/news/?label=Instinct+AI+news), [fourweekmba](https://fourweekmba.com/ai-10b-instinct-adds-opentable-its-4th-integration-in-4-days/) and launch directories. their architecture diagrams, inferred providers, popularity counts and proposed implementations are not evidence about instinct's production internals. technical claims above come from the responsible company or integration implementer.

## source ledger

all sources accessed 2026-11-14. dates below are explicit source dates; “undated” means no publication/update date was established. x titles are descriptive labels, not invented article titles. the original post is cited; retrieved public text came through `https://api.fxtwitter.com/status/<post-id>` where x blocked access. no authenticated content was retrieved.

| id | source and full url | stated date / role |
| --- | --- | --- |
| S01 | [instinct](https://instinct.com/) | undated; current official landing page |
| S02 | [privacy policy](https://instinct.com/privacy-policy) | revised 2026-08-26; official policy |
| S03 | [noah shinn: launch](https://x.com/noahrshinn/status/2092691344456351744) | 2026-08-26; founder announcement |
| S04 | [instinct raises $1 billion in series c funding](https://www.businesswire.com/news/home/20260928153437/en/Instinct-Raises-$1-Billion-in-Series-C-Funding-from-Sequoia-Benchmark-and-Coatue-at-$10-Billion-Valuation) | company release associated with 2026-09-28; retrieved body did not render a date header |
| S05 | [noah shinn: agent email address](https://x.com/noahrshinn/status/2097443132816396649) | 2026-09-08; founder announcement |
| S06 | [noah shinn: forwarding and thread participation](https://x.com/noahrshinn/status/2097443135177798060) | 2026-09-08; founder follow-up |
| S07 | [noah shinn: concierge](https://x.com/noahrshinn/status/2100262985491231101) | 2026-09-16; founder announcement |
| S08 | [noah shinn: authenticator support](https://x.com/noahrshinn/status/2098466184912089143) | 2026-09-11; founder announcement |
| S09 | [connect 1password to instinct](https://support.1password.com/1password-instinct/) | published 2026-11-05; integration support |
| S10 | [about the security of 1password for agents](https://support.1password.com/1password-for-agents-security/) | published 2026-11-03; implementer disclosure |
| S11 | [use 1password to sign in to sites with supported agents](https://support.1password.com/1password-for-agents/) | undated in reviewed excerpt; supporting guide |
| S12 | [noah shinn: trusted-person network](https://x.com/noahrshinn/status/2097794967574028448) | 2026-09-09; founder announcement |
| S13 | [noah shinn: trusted network available to all](https://x.com/noahrshinn/status/2099358203121393851) | 2026-09-14; rollout update |
| S14 | [noah shinn: files and network invitations](https://x.com/noahrshinn/status/2102896414514688212) | 2026-09-23; rollout update |
| S15 | [noah shinn: shareable files](https://x.com/noahrshinn/status/2101080443667767385) | 2026-09-18; founder announcement |
| S16 | [noah shinn: group chats early access](https://x.com/noahrshinn/status/2107161132192690558) | 2026-10-05; founder announcement |
| S17 | [noah shinn: group chats available on imessage](https://x.com/noahrshinn/status/2115143830924341534) | 2026-10-27; rollout update |
| S18 | [invest like the best: security excerpt](https://x.com/InvestLikeBest/status/2104612418047344696) | 2026-09-28; publisher's founder quotation |
| S19 | [instinct: the personal agent](https://colossus.com/episode/instinct-the-personal-agent/) and [publisher episode description](https://podcasts.apple.com/gb/podcast/noah-shinn-building-instinct-the-personal-agent/id1154105909?i=1000792019848) | 2026-09-28; interview description/chapters; full transcript unavailable |
| S20 | [instinct: a capable agent in your dms](https://www.mager.co/blog/2026-09-12-instinct/) | 2026-09-12; first-person use account |
| S21 | [1password for instinct](https://1password.com/partners/instinct) | undated; partner examples |
| S22 | [terms of service](https://instinct.com/terms) | revised 2026-08-26; official terms |
| S23 | [exponential: shopify's fall '26 edition](https://www.shopify.com/news/fall-26-edition-merchant) | 2026-10-28; responsible partner announcement |
| S24 | [instinct: link balance launch](https://x.com/instinct/status/2114799582760861732) | 2026-10-26; company announcement |
| S25 | [link gives personal agents a budget to spend, powered by stablecoins on tempo](https://tempo.xyz/customer-stories/link/) | undated; explicitly dates link introduction 2026-10-26; infrastructure partner |
| S26 | [set up a balance for agent wallet purchases](https://support.link.com/questions/set-up-a-balance-for-agent-wallet-purchases) | undated; current payment-provider support |
| S27 | [noah shinn: opentable](https://x.com/noahrshinn/status/2116244379375694059) | 2026-10-30; founder announcement |
| S28 | [introducing the decagon partner community](https://decagon.ai/blog/decagon-partner-community) | 2026-10-30; counterpart provider announcement |
| S29 | [noah shinn: whatsapp service update](https://x.com/noahrshinn/status/2117063819931590784) | 2026-11-02; vendor incident account |
| S30 | [noah shinn: hallucination incident response](https://x.com/noahrshinn/status/2102896837522804954) | 2026-09-23; vendor explanation and detector disclosure |
| S31 | [bringing shopping into the future: the fall '26 edition for developers](https://www.shopify.com/news/fall-26-edition-developer) | 2026-10-28; integration architecture context |

additional inspected surfaces: [login](https://app.instinct.com/login) and [mailbox](https://app.instinct.com/mailbox) returned no readable public body; [youtube interview](https://www.youtube.com/watch?v=Am7IWP8IpEc) returned no usable transcript; [link balance faq](https://support.link.com/questions/link-balance-faq) was inspected as payment context. these do not silently fill the gaps above.

[S01]: https://instinct.com/
[S02]: https://instinct.com/privacy-policy
[S03]: https://x.com/noahrshinn/status/2092691344456351744
[S04]: https://www.businesswire.com/news/home/20260928153437/en/Instinct-Raises-$1-Billion-in-Series-C-Funding-from-Sequoia-Benchmark-and-Coatue-at-$10-Billion-Valuation
[S05]: https://x.com/noahrshinn/status/2097443132816396649
[S06]: https://x.com/noahrshinn/status/2097443135177798060
[S07]: https://x.com/noahrshinn/status/2100262985491231101
[S08]: https://x.com/noahrshinn/status/2098466184912089143
[S09]: https://support.1password.com/1password-instinct/
[S10]: https://support.1password.com/1password-for-agents-security/
[S11]: https://support.1password.com/1password-for-agents/
[S12]: https://x.com/noahrshinn/status/2097794967574028448
[S13]: https://x.com/noahrshinn/status/2099358203121393851
[S14]: https://x.com/noahrshinn/status/2102896414514688212
[S15]: https://x.com/noahrshinn/status/2101080443667767385
[S16]: https://x.com/noahrshinn/status/2107161132192690558
[S17]: https://x.com/noahrshinn/status/2115143830924341534
[S18]: https://x.com/InvestLikeBest/status/2104612418047344696
[S19]: https://colossus.com/episode/instinct-the-personal-agent/
[S20]: https://www.mager.co/blog/2026-09-12-instinct/
[S21]: https://1password.com/partners/instinct
[S22]: https://instinct.com/terms
[S23]: https://www.shopify.com/news/fall-26-edition-merchant
[S24]: https://x.com/instinct/status/2114799582760861732
[S25]: https://tempo.xyz/customer-stories/link/
[S26]: https://support.link.com/questions/set-up-a-balance-for-agent-wallet-purchases
[S27]: https://x.com/noahrshinn/status/2116244379375694059
[S28]: https://decagon.ai/blog/decagon-partner-community
[S29]: https://x.com/noahrshinn/status/2117063819931590784
[S30]: https://x.com/noahrshinn/status/2102896837522804954
[S31]: https://www.shopify.com/news/fall-26-edition-developer

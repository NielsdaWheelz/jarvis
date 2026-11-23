# native iphone and android clients

on 2026-11-20 the owner endorsed the same handoff on iphone and android and proposed a dedicated mobile pr that retires discord. the native apps would be the usual phone entry point. the [default web home](default-home-work.md) can ship independently.

today the [web composer](../../src/jarvis/static/home/index.html) starts with the owner in jarvis. each app should accept a shared pdf or link into an editable draft, submit to the same authenticated service and return to the same conversation, task or decision as the web. existing https links should open the installed app or the web. the [submission contract](../decisions/0087-private-web-home.md#web-interface) already accepts text and files and returns a durable receipt.

prove the handoff on each platform. share a quote pdf, ask for a comparison and send once. a push received on the locked phone should open the exact reply or decision, including after sign-in. the recommendation, source quotes and drafted reply should also be reachable from the task. check a shared link as well.

discord currently carries [outbound notices](../decisions/0087-private-web-home.md#alerts-ingress-and-cutover). at cutover, account for pending notices, switch delivery to native push and remove the live discord sender, bot credential and alert-channel configuration. retain the stored owner scope, archive key and historical receipts. changing those identities would orphan work or republish memory. [identity contract](../decisions/0087-private-web-home.md#conversation-records-and-decisions)

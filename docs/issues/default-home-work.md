# show current work on the default home

on 2026-11-20 the owner endorsed a default home that answers “what needs me?” when no published page is selected.

the [web shell](../../src/jarvis/static/home/home.js) shows “nothing published yet” in that case. at 09:09 pacific on november 20, production had nine active todos and no published pages. a phone user had to open conversation, then todos, to discover any of them.

on november 22 the owner selected a todo-only home. resolve when the installed site opens the real list without a selected page, shows the right owner-local deadlines, and presents questions and approvals in conversation. [implementation and acceptance](../decisions/0097-todo-home.md) · [original observation](../research/default-web-home.md)

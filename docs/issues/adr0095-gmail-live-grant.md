# gmail review live qualification needs a valid grant

google rejected the macbook's provisioned oauth refresh on 2026-11-23 utc with
http 400 `invalid_grant`. one token request entered and no mailbox request
entered. the encrypted donor stayed unchanged. private evidence is
`qualification/adr0095/mail/authenticated-google-r2/gmail-live.json`, sha256
`243511c695fd4e3aa2d45db613b7c77a7909aeecbad1383ab7ce58e039eb8bf6`.

the implementation and controlled fixtures use the ordinary gmail connector.
release qualification needs a valid owner-authorized grant and a small
read-only run that verifies the review field mask and reopens an exact original
body. [mail acceptance](../decisions/0095-context-cost.md#a-read-a-page-of-mail)

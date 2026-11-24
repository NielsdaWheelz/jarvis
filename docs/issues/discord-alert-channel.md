# retire the jarvis discord bot

the selected android release has no discord sender. the old bot still had
access to the one alert server on november 24 utc. discord returned 429 on
two documented removal requests, including a retry. the installed and local
installer declarations still contain the two retired assignments.

a discord owner removes the bot from the original server, removes any
remaining bot-specific channel permission and resets the token in the
developer portal. verify the guild membership is gone and the old credential
returns 401. remove `JARVIS_DISCORD_BOT_TOKEN` and
`JARVIS_DISCORD_CHANNEL_ID` from the installed and operator source declarations.
preserve `JARVIS_OWNER_SCOPE`, `JARVIS_OWNER_ARCHIVE_KEY` and historical
notice receipts. [android cut](../decisions/0105-native-android.md#installed-release-on-november-24-utc)

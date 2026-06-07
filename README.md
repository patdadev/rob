# Rob Dev Rebuild

Rob is being rebuilt as two separate services that share PostgreSQL:

- `apps/webhook` receives Throne webhooks and writes sends to PostgreSQL.
- `apps/bot` runs the Discord bot, posts queued sends, refreshes leaderboards, and handles user commands.

The legacy single-process bot is preserved under [`legacy/single-process-bot`](legacy/single-process-bot) for behavioural reference only. It is not part of the active runtime.

For the webhook-side Yoti age verification flow, Yoti sandbox uses Client SDK ID + `.pem` private key. Store the `.pem` only on the backend server and never commit it.

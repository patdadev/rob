# Domain Routing

Canonical hostnames:

- `bot-01.robthebot.com`
- `webhook-01.robthebot.com`
- `db-01.robthebot.com`
- `throne.robthebot.com`
- `leaderboard.robthebot.com`

Preferred public webhook route:

- `https://throne.robthebot.com/webhook/{creator_id}/{secret}`

Compatibility webhook route (still supported):

- `https://throne.robthebot.com/throne/webhook/{creator_id}/{secret}`

Future public leaderboard route:

- `https://leaderboard.robthebot.com/guild/{guild_id}`

## Cloudflare guidance

- Prefer Cloudflare Tunnel for:
  - `throne.robthebot.com`
  - `leaderboard.robthebot.com`
- DNS-only is usually right for SSH/admin identity hostnames:
  - `bot-01.robthebot.com`
  - `webhook-01.robthebot.com`

`db-01.robthebot.com` should remain private/internal/admin-only.
Do not expose PostgreSQL publicly.

Webhook origin should stay local:

- `http://127.0.0.1:8080`

Do not open port `8080` publicly.

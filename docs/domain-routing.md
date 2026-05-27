# Domain Routing

## Preferred webhook endpoint

Use:

- `https://throne.robthebot.com/webhook/{creator_id}/{secret}`

Compatibility endpoint remains supported:

- `/throne/webhook/{creator_id}/{secret}`

## Notes

- Keep webhook host/service private behind your reverse proxy.
- Ensure proxy forwards request body exactly for signature verification.
- Keep webhook secret path values confidential.

# Discord Commands

## Public commands

- `/register domme`
- `/register sub`
- `/leaderboard`
- `/achievements`
- `/report`

## Dom/me commands

- `/add`

## Counting commands

- `/count set {number}`

## Developer test commands

- `/test achievements` (requires owner/mod/manage-guild permissions)

## Inactivity commands

- `/inactivitytest`
- `/inactivelist`

## Moderator prefix commands

- `!rob-blacklist <discord_user_id_or_mention> [reason]`
- `!rob-unblacklist <discord_user_id_or_mention>`
- `!throne-blacklist <discord_user_id_or_mention>`

## Removed in rebuild

- `/sendrequest`
- `/privacy`
- `/broadcast`

## Notes

- Registration role checks are runtime-validated from `vib_settings`.
- `/leaderboard` is for user-facing stats and should not create schema changes or admin side effects.
- After deploy, Discord command sync removes retired commands. Guild removals usually appear quickly; global command removal can take longer to propagate.

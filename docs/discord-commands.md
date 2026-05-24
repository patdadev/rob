# Discord Commands

Rob keeps Discord commands user-facing and narrow.

## Public/User Commands

- `/register domme`
- `/register sub`
- `/sendrequest`
- `/leaderboard`
- `/report`
- `/privacy`
- `/broadcast` (DM-only, bot owner only)

## Dom/me Commands

- `/add`

## Counting Commands

- `/count set {number}`

## Inactivity Commands

- `/inactivitytest`
- `/inactivelist`

## Moderator Prefix Commands

- `!rob-blacklist <discord_user_id_or_mention> [reason]`
- `!rob-unblacklist <discord_user_id_or_mention>`
- `!throne-blacklist <discord_user_id_or_mention>`

## Removed/Not Planned

Rob does not expose broad admin dashboards, event control commands, or deployment actions in Discord.

Maintenance mode, queue management, service restarts, database checks, and leaderboard refresh requests should be handled from the backend with `scripts/rob`.

## Registration Notes

- `/register domme` now checks the configured `domme_role_id` in `guild_settings` at runtime.
- `/register sub` now checks the configured `sub_role_id` in `guild_settings` at runtime.
- If the required role is missing from server config or the user does not have it, Rob denies the command with a Components V2 permission card and an ephemeral response.

## Command Behavior Notes

- `/leaderboard` is now a **non-ephemeral** stats response and supports viewing another member with the optional `user` argument.
- `/leaderboard` renders Dom/me and/or Sub sections based on the target member's configured server roles (`domme_role_id` and `sub_role_id`).
- Public leaderboard channel messages are updated by the send queue and `rob leaderboard refresh`, not by `/leaderboard`.
- `/sendrequest` is restricted to users with the configured `sub_role_id` in `guild_settings`.
- `/report` opens a modal for Rob issue reports, includes an optional in-form file upload, and requires acknowledgement that the report is about Rob (not member moderation reports).
- `/privacy` posts a multi-container privacy notice that explains data collection scope, usage, and Rob's data-minimization commitment.
- `/broadcast` is owner-only and DM-only; it opens a modal with an in-form style menu, optional upload field, and a target field using `guild_id:channel_id` or `guild_id:all-members`.
- Warn-log relay is automatic when `guild_settings.warn_log_channel_id` and `guild_settings.carlbot_user_id` are configured.

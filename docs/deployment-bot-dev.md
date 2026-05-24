# Deployment: Bot Dev

For a first-time bootstrap on a fresh Debian or Ubuntu host, run:

```bash
sudo DEPLOY_USER=deployuser bash deploy/scripts/install-bot-dev.sh
```

That installer:

- installs system packages
- clones the configured branch into `/opt/rob-bot/app`
- creates the virtual environment
- installs the systemd unit
- creates `/opt/rob-bot/deploy-bot-dev.sh`
- installs the deploy sudoers entry
- writes a bot `.env` template if one does not already exist
- runs migrations + DB checks before first service start (when real env values exist)

## Target

- App path: `/opt/rob-bot/app`
- Service: `rob-bot-dev.service`

## Setup

Use these steps if you are doing the install manually instead of the bootstrap script above.

1. Create a runtime user such as `rob`.
2. Clone the repo into `/opt/rob-bot/app`.
3. Copy `.env.example` to `/opt/rob-bot/app/.env` and fill the bot values. `DISCORD_TOKEN` is required on the bot server.
4. Create `.venv` and install `requirements.txt`.
5. Copy `deploy/systemd/rob-bot-dev.service` to `/etc/systemd/system/rob-bot-dev.service`.
6. Copy or symlink `deploy/scripts/deploy-bot-dev.sh` to `/opt/rob-bot/deploy-bot-dev.sh`.
7. Enable the service with `sudo systemctl enable --now rob-bot-dev.service`.
8. Verify startup with `PYTHONPATH=. python -m apps.bot.main`.

## Passwordless sudo for deploy user

`deploy-bot-dev.sh` restarts the bot service and reads its status with `sudo systemctl ...`, so the SSH deploy user should be allowed to run those commands without an interactive password prompt.

Example `/etc/sudoers.d/rob-bot-deploy` entry:

```sudoers
Cmnd_Alias ROB_BOT_DEPLOY = /bin/systemctl restart rob-bot-dev.service, /usr/bin/systemctl restart rob-bot-dev.service, /bin/systemctl --no-pager --full status rob-bot-dev.service, /usr/bin/systemctl --no-pager --full status rob-bot-dev.service
deployuser ALL=(root) NOPASSWD: ROB_BOT_DEPLOY
```

## GitHub Actions

Add these secrets:

- `BOT_DEV_HOST`
- `BOT_DEV_USER`
- `BOT_DEV_SSH_KEY`
- `BOT_DEV_PORT`

`Deploy Bot Dev` is now automated:

- runs on `push` to `main` when bot/shared runtime files change
- supports manual `workflow_dispatch` with optional `deploy_ref` override
- deploys the exact commit SHA by default (`DEPLOY_REF=${{ github.sha }}`)

# Deployment: Webhook Dev

For a first-time bootstrap on a fresh Debian or Ubuntu host, run:

```bash
sudo DEPLOY_USER=deployuser bash deploy/scripts/install-webhook-dev.sh
```

That installer:

- installs system packages
- clones the configured branch into `/opt/rob-webhook/app`
- creates the virtual environment
- installs the systemd unit
- creates `/opt/rob-webhook/deploy-webhook-dev.sh`
- installs the deploy sudoers entry
- writes a webhook-only `.env` template if one does not already exist
- runs migrations + DB checks before first service start (when real env values exist)

## Target

- App path: `/opt/rob-webhook/app`
- Service: `rob-webhook-dev.service`
- Public URL: `https://rob-dev.barecoding.com`
- Local bind: `127.0.0.1:8080`

## Setup

Use these steps if you are doing the install manually instead of the bootstrap script above.

1. Create a runtime user such as `rob`.
2. Clone the repo into `/opt/rob-webhook/app`.
3. Copy `.env.example` to `/opt/rob-webhook/app/.env` and fill the webhook values only. Do not set `DISCORD_TOKEN` on the webhook server.
4. Create `.venv` and install `requirements.txt`.
5. Copy `deploy/systemd/rob-webhook-dev.service` to `/etc/systemd/system/rob-webhook-dev.service`.
6. Copy or symlink `deploy/scripts/deploy-webhook-dev.sh` to `/opt/rob-webhook/deploy-webhook-dev.sh`.
7. Enable the service with `sudo systemctl enable --now rob-webhook-dev.service`.
8. Verify `curl http://127.0.0.1:8080/health` returns `OK`.

## Signature mode for dev

- Set `THRONE_WEBHOOK_REQUIRE_SIGNATURE=false` for early dev if you do not yet have the real Throne public key or confirmed signed-message format.
- In that mode, the webhook still validates the URL secret and still writes accepted sends to PostgreSQL.
- Set `THRONE_WEBHOOK_REQUIRE_SIGNATURE=true` once `THRONE_PUBLIC_KEY_PEM` and the signature header format are confirmed for the dev tunnel.
- When `true`, invalid timestamps, missing public key configuration, or invalid signatures are rejected with `401`.

## Passwordless sudo for deploy user

`deploy-webhook-dev.sh` restarts the systemd unit with `sudo systemctl restart rob-webhook-dev.service`, so the SSH deploy user should be allowed to run that command without an interactive password prompt.

Example `/etc/sudoers.d/rob-webhook-deploy` entry:

```sudoers
Cmnd_Alias ROB_WEBHOOK_DEPLOY = /bin/systemctl restart rob-webhook-dev.service, /usr/bin/systemctl restart rob-webhook-dev.service
deployuser ALL=(root) NOPASSWD: ROB_WEBHOOK_DEPLOY
```

## GitHub Actions

Add these secrets:

- `WEBHOOK_DEV_HOST`
- `WEBHOOK_DEV_USER`
- `WEBHOOK_DEV_SSH_KEY`
- `WEBHOOK_DEV_PORT`

`Deploy Webhook Dev` is now automated:

- runs on `push` to `main` when webhook/shared runtime files change
- supports manual `workflow_dispatch` with optional `deploy_ref` override
- deploys the exact commit SHA by default (`DEPLOY_REF=${{ github.sha }}`)

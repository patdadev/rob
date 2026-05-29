# Cloudflared: Webhook Routing

This guide configures Cloudflared for the webhook host only.

Target routing:

- `https://throne.robthebot.com` -> `http://127.0.0.1:8080`
- Route the hostname to the local webhook origin so `/health`, `/webhook/*`, and `/throne/webhook/*` stay reachable through the same tunnel host.

Safety rules:

- Do not open port `8080` publicly.
- Do not commit tunnel tokens or credential JSON files.
- Do not copy random credential JSON files; named tunnels must use `/etc/cloudflared/rob-webhook.json`.
- On Ubuntu/Debian, use the official Cloudflare apt repository (the installer handles this).

## Install sequence

```bash
sudo bash deploy/scripts/install-webhook-dev.sh
sudo nano /opt/rob-webhook/app/.env
sudo chown "${USER}:rob" /opt/rob-webhook/app/.env
sudo chmod 0640 /opt/rob-webhook/app/.env
cd /opt/rob-webhook/app
set -a
source .env
set +a
PYTHONPATH=. .venv/bin/python -m scripts.check_db
sudo systemctl restart rob-webhook-dev.service
curl -fsS http://127.0.0.1:8080/health
sudo bash deploy/scripts/install-cloudflared-webhook.sh
curl -I https://throne.robthebot.com/health
```

## Verify services

```bash
sudo systemctl status cloudflared --no-pager
sudo journalctl -u cloudflared -n 100 --no-pager
sudo systemctl status rob-webhook-dev.service --no-pager
sudo journalctl -u rob-webhook-dev.service -n 100 --no-pager
```

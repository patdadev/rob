# Cloudflared webhook tunnel

This document describes the Cloudflare Tunnel setup for the Rob webhook server.
The webhook app should stay bound to localhost; do **not** expose port `8080`
with a public listener or firewall rule.

Expected route:

- Public hostname: `throne.robthebot.com`
- Local service: `http://127.0.0.1:8080`

Expected webhook environment:

```dotenv
THRONE_WEBHOOK_HOST=127.0.0.1
THRONE_WEBHOOK_PORT=8080
THRONE_WEBHOOK_BASE_URL=https://throne.robthebot.com
```

## Recommended token-based setup

1. In Cloudflare Zero Trust, open **Networks > Tunnels**.
2. Create or select the tunnel for the Rob webhook server.
3. Configure the public hostname route:
   - Hostname: `throne.robthebot.com`
   - Service: `http://127.0.0.1:8080`
4. Copy the Debian/Ubuntu tunnel token install command or token from the
   dashboard.
5. Run the installer on the webhook host:

   ```bash
   sudo bash deploy/scripts/install-cloudflared-webhook.sh
   ```

6. Answer `y` when asked whether you have a Cloudflare tunnel token, then paste
   the token at the hidden prompt.

The script installs `cloudflared`, runs `cloudflared service install` with the
provided token, enables and restarts the `cloudflared` systemd service, and does
not write the token into the repository or print it. `cloudflared` may store
service credentials locally as part of the tunnel service install.

## Locally managed named tunnel setup

Use this only if you have already authenticated the host with:

```bash
cloudflared tunnel login
```

Then run:

```bash
sudo bash deploy/scripts/install-cloudflared-webhook.sh
```

Choose the no-token path. The script can create/configure a named tunnel with
these defaults:

- Tunnel name: `rob-webhook`
- Public hostname: `throne.robthebot.com`
- Local service URL: `http://127.0.0.1:8080`

For locally managed tunnels, the script writes `/etc/cloudflared/config.yml` and
backs up any existing config first as
`/etc/cloudflared/config.yml.bak-YYYYMMDD-HHMMSS`.

## Check the service

```bash
systemctl status cloudflared --no-pager
journalctl -u cloudflared -n 100 --no-pager
```

## Check webhook health

Local health check:

```bash
curl -fsS http://127.0.0.1:8080/health
```

External tunnel health check:

```bash
curl -I https://throne.robthebot.com/health
```

The external HTTPS check may fail immediately after setup while DNS and tunnel
routing propagate.

## Safety reminders

- Keep the webhook app listening on `127.0.0.1:8080`.
- Do not open firewall access to port `8080`.
- Do not commit or print tunnel tokens. The installer does not write the token to the repository or print it, but `cloudflared` may store service credentials locally for the systemd service.
- Keep `THRONE_WEBHOOK_BASE_URL=https://throne.robthebot.com` on the webhook
  host.

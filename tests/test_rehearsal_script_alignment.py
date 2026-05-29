from __future__ import annotations

from pathlib import Path


def test_webhook_installer_uses_prod_role_rehearsal_template():
    text = Path("deploy/scripts/install-webhook-dev.sh").read_text(encoding="utf-8")
    assert "prod_rob_webhook" in text
    assert "rob_dev_v2" in text
    assert "https://throne.robthebot.com" in text
    assert "THRONE_WEBHOOK_HOST=127.0.0.1" in text
    assert "THRONE_WEBHOOK_PORT=8080" in text
    assert "DISCORD_TOKEN=replace" not in text
    assert "Do not add DISCORD_TOKEN on this host" in text


def test_bot_installer_uses_prod_role_rehearsal_template():
    text = Path("deploy/scripts/install-bot-dev.sh").read_text(encoding="utf-8")
    assert "prod_rob_bot" in text
    assert "rob_dev_v2" in text
    assert "DISCORD_TOKEN=replace" in text
    assert "dev_rob_bot:replace@127.0.0.1" not in text


def test_cloudflared_webhook_remains_local_only():
    text = Path("deploy/scripts/install-cloudflared-webhook.sh").read_text(encoding="utf-8")
    assert "throne.robthebot.com" in text
    assert "http://127.0.0.1:8080" in text
    assert "pkg.cloudflare.com/cloudflared" in text
    assert "cloudflare-main.gpg" in text
    assert "lsb_release -cs" in text
    assert "ufw allow 8080" not in text
    assert "firewall-cmd" not in text
    assert "iptables" not in text
    assert "path: /webhook/*" not in text


def test_docs_do_not_reference_old_webhook_domain_or_dev_webhook_user():
    docs = "\n".join(path.read_text(encoding="utf-8") for path in Path("docs").glob("*.md"))
    assert "rob-dev.barecoding.com" not in docs
    assert "dev_rob_webhook" not in docs

from pathlib import Path


def test_deploy_workflow_rebuild():
    workflow = Path('.github/workflows/deploy-codebase.yml')
    assert workflow.exists()
    text = workflow.read_text()
    assert 'resolve_deploy_context:' in text
    assert 'precheck_codebase:' in text
    assert 'bot_server_precheck:' in text
    assert 'webhook_server_precheck:' in text
    assert 'deploy_bot:' in text
    assert 'deploy_webhook:' in text
    assert 'push:' in text and 'main' in text
    assert 'workflow_dispatch:' in text
    assert 'needs: [resolve_deploy_context, precheck_codebase, bot_server_precheck]' in text
    assert 'needs: [resolve_deploy_context, precheck_codebase, webhook_server_precheck]' in text
    assert 'appleboy/ssh-action' in text
    assert "if: ${{ needs.resolve_deploy_context.outputs.deploy_bot == 'true' }}" in text
    assert "if: ${{ needs.resolve_deploy_context.outputs.deploy_webhook == 'true' }}" in text
    assert 'precheck-bot.sh is not present yet. Running bootstrap-safe fallback checks.' in text
    assert 'precheck-webhook.sh is not present yet. Running bootstrap-safe fallback checks.' in text
    assert 'Skipping DB schema check in bootstrap fallback. Full DB check runs in deploy-bot.sh.' in text
    assert 'Skipping DB schema check in bootstrap fallback. Full DB check runs in deploy-webhook.sh.' in text
    for secret in [
        'BOT_DEV_HOST', 'BOT_DEV_USER', 'BOT_DEV_SSH_KEY', 'BOT_DEV_PORT',
        'WEBHOOK_DEV_HOST', 'WEBHOOK_DEV_USER', 'WEBHOOK_DEV_SSH_KEY', 'WEBHOOK_DEV_PORT',
        'ROB_PROD_BOT_HOST', 'ROB_PROD_BOT_USER', 'ROB_PROD_BOT_SSH_KEY', 'ROB_PROD_BOT_SSH_PORT',
        'ROB_PROD_WEBHOOK_HOST', 'ROB_PROD_WEBHOOK_USER', 'ROB_PROD_WEBHOOK_SSH_KEY', 'ROB_PROD_WEBHOOK_SSH_PORT',
    ]:
        assert secret in text
    assert 'scripts/run_migrations.py' not in text
    assert 'scripts/db/build/001_core_schema.sql' not in text


def test_old_workflows_removed():
    assert not Path('.github/workflows/deploy-bot-dev.yml').exists()
    assert not Path('.github/workflows/deploy-webhook-dev.yml').exists()


def test_deploy_scripts_and_docs():
    pre_bot = Path('deploy/scripts/precheck-bot.sh').read_text()
    pre_webhook = Path('deploy/scripts/precheck-webhook.sh').read_text()
    deploy_bot = Path('deploy/scripts/deploy-bot.sh').read_text()
    deploy_webhook = Path('deploy/scripts/deploy-webhook.sh').read_text()
    bot_dev = Path('deploy/scripts/deploy-bot-dev.sh').read_text()
    webhook_dev = Path('deploy/scripts/deploy-webhook-dev.sh').read_text()
    docs = Path('docs/deployment.md').read_text()
    cloudflared_script = Path('deploy/scripts/install-cloudflared-webhook.sh')
    cloudflared_doc = Path('docs/cloudflared-webhook.md')

    assert 'scripts/check_db.py' in pre_bot and 'scripts/check_db.py' in pre_webhook
    assert 'systemctl restart' not in pre_bot and 'systemctl restart' not in pre_webhook
    assert 'echo .env' not in pre_bot and 'echo .env' not in pre_webhook
    assert 'exec "${SCRIPT_DIR}/deploy-bot.sh" "$@"' in bot_dev
    assert 'exec "${SCRIPT_DIR}/deploy-webhook.sh" "$@"' in webhook_dev
    assert 'scripts/db/build/001_core_schema.sql' in deploy_bot
    assert 'scripts/db/build/002_indexes.sql' in deploy_bot
    assert 'SQLite data migration remains separate' in docs
    assert 'Do not expose PostgreSQL publicly' in docs
    assert cloudflared_script.exists()
    assert cloudflared_doc.exists()

    assert deploy_bot
    assert deploy_webhook


def test_cloudflared_webhook_installer_guards():
    script_path = Path('deploy/scripts/install-cloudflared-webhook.sh')
    assert script_path.exists()
    script = script_path.read_text()

    assert 'throne.robthebot.com' in script
    assert 'http://127.0.0.1:8080' in script
    assert 'TUNNEL_TOKEN=' not in script
    assert 'eyJh' not in script
    assert 'ufw allow 8080' not in script
    assert 'firewall-cmd' not in script
    assert 'iptables' not in script
    assert 'head -n 1' not in script
    assert 'source_file=' not in script
    assert '.bak-$(date +%Y%m%d-%H%M%S)' in script
    assert 'cp -a "${CLOUDFLARED_CONFIG}" "${backup_path}"' in script
    assert 'Named tunnel ${tunnel_name} exists, but ${credentials_file} was not found.' in script


def test_webhook_dev_installer_uses_prod_role_rehearsal_env_template():
    script = Path('deploy/scripts/install-webhook-dev.sh').read_text()
    env_template = script.split("cat > \"${env_file}\" <<'EOF'", 1)[1].split('EOF', 1)[0]

    assert 'DATABASE_URL=postgresql://dev_rob_bot:replace@127.0.0.1:5432/rob_dev_v2' not in env_template
    assert 'THRONE_WEBHOOK_BASE_URL=https://rob-dev.barecoding.com' not in env_template
    assert 'prod_rob_webhook' in env_template
    assert 'rob_dev_v2' in env_template
    assert 'https://throne.robthebot.com' in env_template


def test_webhook_dev_installer_warns_about_existing_stale_env():
    script = Path('deploy/scripts/install-webhook-dev.sh').read_text()

    assert 'Existing .env appears to contain old dev webhook values.' in script
    assert 'This installer will not overwrite it.' in script
    assert 'dev_rob_bot|rob-dev\\.barecoding\\.com' in script

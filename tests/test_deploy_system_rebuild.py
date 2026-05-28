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
    for secret in [
        'ROB_DEV_BOT_HOST', 'ROB_DEV_BOT_USER', 'ROB_DEV_BOT_SSH_KEY', 'ROB_DEV_BOT_SSH_PORT',
        'ROB_DEV_WEBHOOK_HOST', 'ROB_DEV_WEBHOOK_USER', 'ROB_DEV_WEBHOOK_SSH_KEY', 'ROB_DEV_WEBHOOK_SSH_PORT',
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

    assert 'scripts/check_db.py' in pre_bot and 'scripts/check_db.py' in pre_webhook
    assert 'systemctl restart' not in pre_bot and 'systemctl restart' not in pre_webhook
    assert 'echo .env' not in pre_bot and 'echo .env' not in pre_webhook
    assert 'exec "${SCRIPT_DIR}/deploy-bot.sh" "$@"' in bot_dev
    assert 'exec "${SCRIPT_DIR}/deploy-webhook.sh" "$@"' in webhook_dev
    assert 'scripts/db/build/001_core_schema.sql' in deploy_bot
    assert 'scripts/db/build/002_indexes.sql' in deploy_bot
    assert 'SQLite data migration remains separate' in docs
    assert 'Do not expose PostgreSQL publicly' in docs

    assert deploy_bot
    assert deploy_webhook

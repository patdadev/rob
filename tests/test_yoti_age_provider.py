from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from rob.services.yoti_age_provider import YotiAgeProvider, YotiConfigurationError


def _write_test_private_key(tmp_path: Path) -> Path:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_path = tmp_path / "yoti-test.pem"
    pem_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return pem_path


def test_yoti_provider_uses_signed_sdk_auth_for_sandbox(tmp_path):
    pem_path = _write_test_private_key(tmp_path)
    provider = YotiAgeProvider(
        environment="sandbox",
        sdk_id="sdk-123",
        private_key_path=str(pem_path),
        public_base_url="https://age.robthebot.com",
    )

    request_url, headers, payload_bytes = provider._build_request(
        "POST",
        "/api/v1/sessions",
        json_payload={"type": "OVER"},
    )

    parsed = urlparse(request_url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "age.yoti.com"
    assert parsed.path == "/api/v1/sessions"
    assert query["sdkId"] == ["sdk-123"]
    assert "nonce" in query
    assert "timestamp" in query
    assert "Authorization" not in headers
    assert headers["X-Yoti-Auth-Id"] == "sdk-123"
    assert headers["Yoti-Sdk-Id"] == "sdk-123"
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json"
    assert headers["X-Yoti-Auth-Digest"]
    assert json.loads((payload_bytes or b"").decode("utf-8")) == {"type": "OVER"}


def test_yoti_provider_requires_existing_private_key_file(tmp_path):
    provider = YotiAgeProvider(
        environment="sandbox",
        sdk_id="sdk-123",
        private_key_path=str(tmp_path / "missing.pem"),
        public_base_url="https://age.robthebot.com",
    )

    with pytest.raises(YotiConfigurationError, match="does not exist"):
        provider.validate_startup_configuration()

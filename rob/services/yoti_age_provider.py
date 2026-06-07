from __future__ import annotations

import base64
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from uuid import uuid4

from aiohttp import ClientResponseError, ClientSession, ClientTimeout
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from rob.database.repositories.age_verification import (
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_MANUAL_REVIEW_REQUIRED,
    STATUS_PENDING,
    STATUS_VERIFIED_18_PLUS,
)

_YOTI_NOTIFICATIONS_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAune8+8vPz/pQD6IzdWvX
Q66nh/RcywopCI01Wjo6i7vlH2iVOP1oCkgbObe12iMmVXKRiXgMNT6aXIGe6Ggw
dodzAmt3vT1fmrgub7Of6MgJ56ri2uH1O54DTjbnEbEcLXX13teOusZavntrkNpp
x1c8L0Ol41mRvImJeMHM6I16rLhqB/w1m7USMvof/K6GaP+VmmciZTPyZ6IsXxvB
k0ZoqWqrt2xENlg4O6LXMo7eHEiG+edm9uDpbZK1RhiCd6hyDZ/t4bBQNg4misFF
WezQSiUlPwBLRg1AJ3CNrtBzs49BZ30U7WSPUS0Gsq1lhhDtUtJUt4CdkDAfkVY6
2C6aaqKV940GcPFN7MjOeFus3VNJE3zyHVLT8DStuLMXHY+gQBGFOyxN6heZbm7a
Sl9fi7VXlDTlv1jpk4DFMQYF2fpAyomm95GavhllJnDxC2t8ebu0O23B88hPGI3K
kyLtPA8ie6UNmwNqLYpOEN/pwayYw75FcENBDxnWhoe9AgMBAAE=
-----END PUBLIC KEY-----"""


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class AgeVerificationStartResult:
    session_id: str
    verification_url: str
    expires_at: datetime | None
    reference_id: str | None = None


@dataclass(frozen=True)
class AgeVerificationProviderResult:
    session_id: str
    status: str
    method: str | None
    summary: str | None
    expires_at: datetime | None
    reference_id: str | None = None


class YotiProviderError(RuntimeError):
    """Raised when Yoti rejects a request or returns unexpected data."""


class YotiConfigurationError(YotiProviderError):
    """Raised when Rob's Yoti configuration is incomplete."""


class YotiAgeProvider:
    api_origin = "https://age.yoti.com"

    def __init__(
        self,
        *,
        environment: str = "sandbox",
        sdk_id: str | None = None,
        api_key: str | None = None,
        private_key_path: str | None = None,
        age_threshold: int = 18,
        age_estimation_threshold: int = 21,
        public_base_url: str | None = None,
        callback_url: str | None = None,
        notification_url: str | None = None,
        success_url: str | None = None,
        cancel_url: str | None = None,
        session_ttl_seconds: int = 900,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.environment = environment
        self.sdk_id = sdk_id
        self.api_key = api_key
        self.private_key_path = private_key_path
        self.age_threshold = age_threshold
        self.age_estimation_threshold = age_estimation_threshold
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self.callback_url = callback_url
        self.notification_url = notification_url
        self.success_url = success_url
        self.cancel_url = cancel_url
        self.session_ttl_seconds = session_ttl_seconds
        self.timeout_seconds = timeout_seconds
        self._session: ClientSession | None = None
        self._private_key: rsa.RSAPrivateKey | None = None

    @classmethod
    def from_settings(cls, settings: Any) -> YotiAgeProvider:
        return cls(
            environment=getattr(settings, "yoti_environment", "sandbox"),
            sdk_id=getattr(settings, "yoti_sdk_id", None),
            api_key=getattr(settings, "yoti_api_key", None),
            private_key_path=getattr(settings, "yoti_private_key_path", None),
            age_threshold=getattr(settings, "yoti_age_threshold", 18),
            age_estimation_threshold=getattr(
                settings,
                "yoti_age_estimation_threshold",
                21,
            ),
            public_base_url=getattr(settings, "yoti_public_base_url", None),
            callback_url=getattr(settings, "yoti_callback_url", None),
            notification_url=getattr(settings, "yoti_notification_url", None),
            success_url=getattr(settings, "yoti_success_url", None),
            cancel_url=getattr(settings, "yoti_cancel_url", None),
        )

    async def close(self) -> None:
        if self._session is None:
            return
        await self._session.close()
        self._session = None

    def validate_startup_configuration(self) -> None:
        self._validate_configuration()

    def build_reference_id(self, *, guild_id: int, discord_user_id: int) -> str:
        return f"rob:{guild_id}:{discord_user_id}"

    def build_verification_url(self, session_id: str) -> str:
        sdk_id = self._require_sdk_id()
        return (
            f"{self.api_origin}?sessionId={quote(session_id, safe='')}"
            f"&sdkId={quote(sdk_id, safe='')}"
        )

    async def create_session(
        self,
        *,
        discord_user_id: int,
        guild_id: int,
    ) -> AgeVerificationStartResult:
        self._validate_configuration()
        reference_id = self.build_reference_id(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
        payload = {
            "type": "OVER",
            "ttl": self.session_ttl_seconds,
            "age_estimation": {
                "allowed": True,
                "threshold": self.age_estimation_threshold,
                "level": "PASSIVE",
                "retry_limit": 1,
            },
            "digital_id": {
                "allowed": True,
                "threshold": self.age_threshold,
                "age_estimation_allowed": True,
                "age_estimation_threshold": self.age_estimation_threshold,
                "retry_limit": 1,
            },
            "doc_scan": {
                "allowed": True,
                "threshold": self.age_threshold,
                "level": "PASSIVE",
                "authenticity": "AUTO",
                "retry_limit": 1,
            },
            "reference_id": reference_id,
            "callback": {
                "url": self._resolve_callback_url(),
                "auto": True,
            },
            "notification_url": self._resolve_notification_url(),
            "retry_enabled": True,
            "resume_enabled": False,
        }
        if self.cancel_url:
            payload["cancel_url"] = self.cancel_url
        data = await self._request_json(
            "POST",
            "/api/v1/sessions",
            json_payload=payload,
        )
        session_id = str(data.get("id") or "")
        if not session_id:
            raise YotiProviderError("Yoti did not return a session ID.")
        return AgeVerificationStartResult(
            session_id=session_id,
            verification_url=self.build_verification_url(session_id),
            expires_at=_parse_datetime(data.get("expires_at")),
            reference_id=reference_id,
        )

    async def get_result(self, session_id: str) -> AgeVerificationProviderResult:
        self._validate_configuration()
        data = await self._request_json(
            "GET",
            f"/api/v1/sessions/{quote(session_id, safe='')}/result",
        )
        return self._map_result_payload(data)

    async def handle_notification(
        self,
        payload: dict[str, Any],
    ) -> AgeVerificationProviderResult:
        self._verify_notification(payload)
        session_id = str(payload.get("session_key") or "").strip()
        if not session_id:
            raise YotiProviderError("Yoti notification was missing a session key.")
        method = str(payload.get("method") or "").strip() or None
        result = await self.get_result(session_id)
        if method and result.method is None:
            result = replace(result, method=method)
        return result

    def _validate_configuration(self) -> None:
        self._require_sdk_id()
        self._load_private_key()
        self._resolve_callback_url()
        self._resolve_notification_url()

    def _require_sdk_id(self) -> str:
        sdk_id = (self.sdk_id or "").strip()
        if not sdk_id:
            raise YotiConfigurationError("YOTI_SDK_ID is not configured.")
        return sdk_id

    def _require_private_key_path(self) -> Path:
        private_key_path = (self.private_key_path or "").strip()
        if not private_key_path:
            raise YotiConfigurationError("YOTI_PRIVATE_KEY_PATH is not configured.")
        return Path(private_key_path).expanduser()

    def _load_private_key(self) -> rsa.RSAPrivateKey:
        if self._private_key is not None:
            return self._private_key

        private_key_path = self._require_private_key_path()
        try:
            pem_bytes = private_key_path.read_bytes()
        except FileNotFoundError as exc:
            raise YotiConfigurationError(
                f"Configured YOTI_PRIVATE_KEY_PATH does not exist: {private_key_path}"
            ) from exc
        except PermissionError as exc:
            raise YotiConfigurationError(
                "Configured YOTI_PRIVATE_KEY_PATH is not readable by the backend "
                f"process: {private_key_path}"
            ) from exc
        except OSError as exc:
            raise YotiConfigurationError(
                "Configured YOTI_PRIVATE_KEY_PATH could not be read by the backend "
                f"process: {private_key_path}"
            ) from exc

        try:
            private_key = serialization.load_pem_private_key(
                pem_bytes,
                password=None,
            )
        except (TypeError, ValueError) as exc:
            raise YotiConfigurationError(
                "Configured YOTI_PRIVATE_KEY_PATH is not a valid PEM private key: "
                f"{private_key_path}"
            ) from exc

        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise YotiConfigurationError(
                f"Configured YOTI_PRIVATE_KEY_PATH is not an RSA private key: {private_key_path}"
            )

        self._private_key = private_key
        return private_key

    def _resolve_callback_url(self) -> str:
        if self.callback_url:
            return self.callback_url
        if self.public_base_url:
            return f"{self.public_base_url}/yoti/callback"
        raise YotiConfigurationError(
            "YOTI_CALLBACK_URL or YOTI_PUBLIC_BASE_URL must be configured."
        )

    def _resolve_notification_url(self) -> str:
        if self.notification_url:
            return self.notification_url
        if self.public_base_url:
            return f"{self.public_base_url}/yoti/notification"
        raise YotiConfigurationError(
            "YOTI_NOTIFICATION_URL or YOTI_PUBLIC_BASE_URL must be configured."
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._session is None:
            self._session = ClientSession(
                timeout=ClientTimeout(total=self.timeout_seconds)
            )
        request_url, headers, payload_bytes = self._build_request(
            method,
            path,
            json_payload=json_payload,
        )
        try:
            async with self._session.request(
                method,
                request_url,
                data=payload_bytes,
                headers=headers,
            ) as response:
                response.raise_for_status()
                data = await response.json()
        except ClientResponseError as exc:
            raise YotiProviderError(
                f"Yoti request failed with status {exc.status}."
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise YotiProviderError("Yoti request failed.") from exc
        if not isinstance(data, dict):
            raise YotiProviderError("Yoti returned an unexpected response body.")
        return data

    def _build_request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, str], bytes | None]:
        if self._auth_mode() == "bearer":
            api_key = (self.api_key or "").strip()
            if not api_key:
                raise YotiConfigurationError("YOTI_API_KEY is not configured.")
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Yoti-Sdk-Id": self._require_sdk_id(),
            }
            payload_bytes = None
            if json_payload is not None:
                payload_bytes = json.dumps(
                    json_payload,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
                headers["Content-Type"] = "application/json"
            return f"{self.api_origin}{path}", headers, payload_bytes

        return self._build_signed_request(
            method,
            path,
            json_payload=json_payload,
        )

    def _auth_mode(self) -> str:
        environment = (self.environment or "").strip().lower()
        if environment == "sandbox":
            return "signed"
        if (self.api_key or "").strip():
            return "bearer"
        return "signed"

    def _build_signed_request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, str], bytes | None]:
        sdk_id = self._require_sdk_id()
        query = urlencode(
            (
                ("sdkId", sdk_id),
                ("nonce", str(uuid4())),
                ("timestamp", str(int(datetime.now(timezone.utc).timestamp()))),
            )
        )
        signed_path = f"{path}?{query}"
        payload_bytes = None
        request_to_sign = f"{method.upper()}&{signed_path}"
        if json_payload is not None:
            payload_bytes = json.dumps(
                json_payload,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            request_to_sign = (
                f"{request_to_sign}&{base64.b64encode(payload_bytes).decode('ascii')}"
            )

        signature = base64.b64encode(
            self._load_private_key().sign(
                request_to_sign.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        ).decode("ascii")
        headers = {
            "Accept": "application/json",
            "X-Yoti-Auth-Digest": signature,
            "X-Yoti-Auth-Id": sdk_id,
            "Yoti-Sdk-Id": sdk_id,
        }
        if payload_bytes is not None:
            headers["Content-Type"] = "application/json"
        return f"{self.api_origin}{signed_path}", headers, payload_bytes

    def _map_result_payload(
        self,
        payload: dict[str, Any],
    ) -> AgeVerificationProviderResult:
        session_id = str(payload.get("id") or "").strip()
        if not session_id:
            raise YotiProviderError("Yoti result payload was missing an ID.")
        raw_status = str(payload.get("status") or "").strip().upper()
        method = str(payload.get("method") or "").strip() or None
        summary_parts = [f"Yoti {raw_status or 'UNKNOWN'}"]
        if method:
            summary_parts.append(f"via {method}")
        if raw_status == "COMPLETE":
            status = STATUS_VERIFIED_18_PLUS
        elif raw_status == "FAIL":
            status = STATUS_FAILED
        elif raw_status == "EXPIRED":
            status = STATUS_EXPIRED
        elif raw_status in {"PENDING", "PROCESSING", "IN_PROGRESS"}:
            status = STATUS_PENDING
        else:
            status = STATUS_MANUAL_REVIEW_REQUIRED
        return AgeVerificationProviderResult(
            session_id=session_id,
            status=status,
            method=method,
            summary=" ".join(summary_parts).strip(),
            expires_at=_parse_datetime(payload.get("expires_at")),
            reference_id=str(payload.get("reference_id") or "").strip() or None,
        )

    def _verify_notification(self, payload: dict[str, Any]) -> None:
        signature = payload.get("signature")
        if not isinstance(signature, str) or not signature.strip():
            raise YotiProviderError("Yoti notification signature is missing.")
        payload_for_signature = {
            key: value
            for key, value in payload.items()
            if key not in {"sequence_number", "signature"}
        }
        message = json.dumps(
            payload_for_signature,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        try:
            signature_bytes = base64.b64decode(signature, validate=True)
            public_key = serialization.load_pem_public_key(
                _YOTI_NOTIFICATIONS_PUBLIC_KEY.encode("utf-8")
            )
            if not isinstance(public_key, rsa.RSAPublicKey):
                raise YotiProviderError("Unexpected Yoti notification public key type.")
            salt_length = getattr(padding.PSS, "AUTO", padding.PSS.MAX_LENGTH)
            public_key.verify(
                signature_bytes,
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=salt_length,
                ),
                hashes.SHA256(),
            )
        except Exception as exc:  # pragma: no cover - crypto paths are hard to branch exhaustively
            raise YotiProviderError("Yoti notification signature verification failed.") from exc

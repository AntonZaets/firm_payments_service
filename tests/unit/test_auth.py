import json
import urllib.request
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from unittest.mock import Mock
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm, RSAAlgorithm
from pydantic import ValidationError

from firm_payments_service.api import routes
from firm_payments_service.auth import authenticate_payment, authorize_payer
from firm_payments_service.config import Settings
from firm_payments_service.main import app

PAYER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ISSUER = "https://issuer.example.test"
JWKS_URL = f"{ISSUER}/keys"


@pytest.fixture
def auth_config(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_TOKEN_PROFILE", "standard")
    monkeypatch.setenv("AUTH_ISSUER", ISSUER)
    monkeypatch.setenv("AUTH_AUDIENCE", "payments")
    monkeypatch.setenv("AUTH_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("AUTH_ALLOW_HTTP", "false")
    return Settings()


@pytest.fixture(scope="session")
def signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def signed_token(
    key: ec.EllipticCurvePrivateKey,
    overrides: dict[str, Any] | None = None,
    missing: str | None = None,
    algorithm: str = "ES256",
    kid: str = "test-key",
) -> str:
    now = int(datetime.now(UTC).timestamp())
    claims: dict[str, Any] = {
        "exp": now + 300,
        "iss": ISSUER,
        "aud": "payments",
        "payer_firm_uuid": PAYER,
    }
    claims.update(overrides or {})
    if missing:
        claims.pop(missing)
    return jwt.encode(claims, key, algorithm=algorithm, headers={"kid": kid})


@pytest.fixture
def jwks(
    monkeypatch: pytest.MonkeyPatch, signing_key: ec.EllipticCurvePrivateKey
) -> Mock:
    key: dict[str, Any] = json.loads(ECAlgorithm.to_jwk(signing_key.public_key()))
    key["kid"] = "test-key"
    data = json.dumps({"keys": [key]}).encode()
    fetch = Mock(side_effect=[BytesIO(data) for _ in range(4)])
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fetch)
    return fetch


def credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_standard_verification_fetches_keys_without_caching(
    auth_config: Settings,
    signing_key: ec.EllipticCurvePrivateKey,
    jwks: Mock,
) -> None:
    token = credentials(signed_token(signing_key))
    for _ in range(2):
        assert authenticate_payment(token, auth_config) == UUID(PAYER)
    assert jwks.call_count == 2
    assert jwks.call_args.kwargs["timeout"] == 30
    assert jwks.call_args.args[0].full_url == JWKS_URL
    authorize_payer(UUID(PAYER), PAYER.upper().replace("-", ""))
    with pytest.raises(HTTPException) as error:
        authorize_payer(UUID(PAYER), "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    assert error.value.status_code == 403


@pytest.mark.parametrize(
    ("overrides", "missing"),
    [
        ({"exp": 0}, None),
        ({"exp": "invalid"}, None),
        ({"exp": float("inf")}, None),
        ({}, "exp"),
        ({}, "iss"),
        ({}, "aud"),
        ({"iss": "https://wrong.example.test"}, None),
        ({"aud": "wrong"}, None),
        ({}, "payer_firm_uuid"),
        ({"payer_firm_uuid": None}, None),
        ({"payer_firm_uuid": 1}, None),
        ({"payer_firm_uuid": "invalid"}, None),
        ({"payer_firm_uuid": []}, None),
        ({"nbf": 4_000_000_000}, None),
    ],
)
def test_invalid_claims_are_unauthorized(
    auth_config: Settings,
    signing_key: ec.EllipticCurvePrivateKey,
    jwks: Mock,
    overrides: dict[str, Any],
    missing: str | None,
) -> None:
    with pytest.raises(HTTPException) as error:
        authenticate_payment(
            credentials(signed_token(signing_key, overrides, missing)), auth_config
        )
    assert error.value.status_code == 401
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}


@pytest.mark.parametrize(
    "failure",
    [
        "unknown_key",
        "wrong_signature",
        "none",
        "HS256",
        "ES384",
        "missing",
        "malformed",
        "timeout",
        "invalid_json",
        "invalid_jwks",
    ],
)
def test_invalid_tokens_and_jwks_fail_closed(
    auth_config: Settings,
    signing_key: ec.EllipticCurvePrivateKey,
    jwks: Mock,
    failure: str,
) -> None:
    token = signed_token(
        signing_key, kid="unknown" if failure == "unknown_key" else "test-key"
    )
    if failure == "wrong_signature":
        token = signed_token(ec.generate_private_key(ec.SECP256R1()))
    elif failure in {"none", "HS256"}:
        token = jwt.encode({}, "" if failure == "none" else "x" * 32, algorithm=failure)
    elif failure == "ES384":
        token = signed_token(ec.generate_private_key(ec.SECP384R1()), algorithm="ES384")
    elif failure == "malformed":
        token = "invalid.jwt"
    elif failure == "timeout":
        jwks.side_effect = TimeoutError("secret network error")
    elif failure in {"invalid_json", "invalid_jwks"}:
        data = b"invalid" if failure == "invalid_json" else b'{"keys": []}'
        jwks.side_effect = [BytesIO(data), BytesIO(data)]
    with pytest.raises(HTTPException) as error:
        authenticate_payment(
            None if failure == "missing" else credentials(token), auth_config
        )
    assert error.value.status_code == 401
    assert "secret" not in str(error.value.detail)
    if failure in {"none", "HS256", "ES384", "missing", "malformed"}:
        jwks.assert_not_called()


@pytest.mark.parametrize(
    "identity",
    [
        {"connector_id": "local", "user_id": PAYER},
        {"connector_id": "other", "user_id": PAYER},
        {"connector_id": "local", "user_id": "invalid"},
        {"connector_id": "local", "user_id": 1},
        {"user_id": PAYER},
        None,
        [],
    ],
)
def test_dex_profile_requires_local_connector_and_uuid(
    auth_config: Settings, monkeypatch: pytest.MonkeyPatch, identity: Any
) -> None:
    auth_config.auth_token_profile = "dex"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key: dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    public_key["kid"] = "dex-key"
    data = json.dumps({"keys": [public_key]}).encode()
    monkeypatch.setattr(
        urllib.request.OpenerDirector, "open", Mock(return_value=BytesIO(data))
    )
    token = jwt.encode(
        {
            "exp": int(datetime.now(UTC).timestamp()) + 300,
            "iss": ISSUER,
            "aud": "payments",
            "federated_claims": identity,
            "payer_firm_uuid": PAYER,
        },
        key,
        algorithm="RS256",
        headers={"kid": "dex-key"},
    )
    if identity == {"connector_id": "local", "user_id": PAYER}:
        assert authenticate_payment(credentials(token), auth_config) == UUID(PAYER)
    else:
        with pytest.raises(HTTPException) as error:
            authenticate_payment(credentials(token), auth_config)
        assert error.value.status_code == 401


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AUTH_ISSUER", ""),
        ("AUTH_AUDIENCE", ""),
        ("AUTH_JWKS_URL", ""),
        ("AUTH_JWKS_URL", "http://issuer.example.test/keys"),
        ("AUTH_JWKS_URL", "file:///tmp/keys"),
        ("AUTH_JWKS_URL", "https://user:password@issuer.example.test/keys"),
        ("AUTH_JWKS_URL", "https://issuer.example.test/keys#fragment"),
        ("AUTH_JWKS_TIMEOUT_SECONDS", "0"),
        ("AUTH_JWKS_TIMEOUT_SECONDS", "nan"),
        ("AUTH_TOKEN_PROFILE", "unknown"),
    ],
)
def test_invalid_auth_configuration(
    auth_config: Settings, monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings()


def test_auth_defaults_and_explicit_opt_out(
    auth_config: Settings, monkeypatch: pytest.MonkeyPatch, jwks: Mock
) -> None:
    monkeypatch.delenv("AUTH_ENABLED")
    monkeypatch.delenv("AUTH_TOKEN_PROFILE")
    monkeypatch.setenv("DATABASE_URL", auth_config.database_url)
    monkeypatch.setenv(
        "OPERATIONAL_API_KEY", auth_config.operational_api_key.get_secret_value()
    )
    monkeypatch.delenv("AUTH_ALLOW_HTTP", raising=False)
    # Ignore local .env overrides to check the actual deployment defaults.
    monkeypatch.setattr(
        Settings, "model_config", {**Settings.model_config, "env_file": None}
    )
    config = Settings()
    assert config.auth_enabled
    assert config.auth_token_profile == "standard"
    assert not config.auth_allow_http
    monkeypatch.setenv("AUTH_ENABLED", "false")
    for name in ("AUTH_ISSUER", "AUTH_AUDIENCE", "AUTH_JWKS_URL"):
        monkeypatch.setenv(name, "")
    config = Settings()
    assert authenticate_payment(None, config) is None
    assert authenticate_payment(credentials("invalid.jwt"), config) is None
    authorize_payer(None, PAYER)
    jwks.assert_not_called()


@pytest.mark.parametrize("enabled", ["true", "false"])
@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/metrics"])
def test_operational_auth_is_independent(
    auth_config: Settings, monkeypatch: pytest.MonkeyPatch, enabled: str, path: str
) -> None:
    monkeypatch.setenv("AUTH_ENABLED", enabled)
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-API-Key": "wrong"}).status_code == 401


def test_authentication_precedes_body_validation(auth_config: Settings) -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/payments/bulk", content="invalid json")
    assert response.status_code == 401
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_standard_http_verifies_once_before_transfer(
    auth_config: Settings,
    signing_key: ec.EllipticCurvePrivateKey,
    jwks: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transfer = Mock()
    monkeypatch.setattr(routes, "transfer", transfer)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/payments/bulk",
            headers={"Authorization": f"Bearer {signed_token(signing_key)}"},
            json={
                "payer_firm_uuid": PAYER,
                "payments": [
                    {
                        "payee_firm_uuid": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                        "amount": "1",
                        "description": "invoice",
                    }
                ],
            },
        )
    assert response.status_code == 201, response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    jwks.assert_called_once()
    transfer.assert_called_once()

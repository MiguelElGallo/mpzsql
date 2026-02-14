"""Security utilities — password hashing (HMAC-SHA256) and JWT helpers."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

# ═══════════════════════════════════════════════════════════════════════════
#  Password Hashing — HMAC-SHA256
# ═══════════════════════════════════════════════════════════════════════════


def hash_password(password: str, secret_key: str) -> str:
    """Hash a password with HMAC-SHA256 using *secret_key* as the key.

    Mirrors the  ``HMAC_SHA256`` function:
    ``HMAC(secret_key, password, SHA-256)`` → hex-encoded digest.

    Args:
        password: The plaintext password.
        secret_key: The server's secret key used as HMAC key.

    Returns:
        Lowercase hex-encoded HMAC-SHA256 digest.
    """
    return hmac.new(
        key=secret_key.encode("utf-8"),
        msg=password.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def verify_password(password: str, secret_key: str, expected_hash: str) -> bool:
    """Verify a password against a stored HMAC-SHA256 hash.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        password: The plaintext password to verify.
        secret_key: The server's secret key used as HMAC key.
        expected_hash: The previously-stored hex-encoded hash.

    Returns:
        ``True`` if the password matches, ``False`` otherwise.
    """
    computed = hash_password(password, secret_key)
    return hmac.compare_digest(computed, expected_hash)


# ═══════════════════════════════════════════════════════════════════════════
#  JWT Token Management
# ═══════════════════════════════════════════════════════════════════════════

# Default issuer matching the project name
DEFAULT_ISSUER = "lakehouse"
DEFAULT_EXPIRY_HOURS = 24


def create_jwt(
    *,
    subject: str,
    secret: str,
    algorithm: str = "HS256",
    issuer: str = DEFAULT_ISSUER,
    expiry_hours: int = DEFAULT_EXPIRY_HOURS,
    instance_id: str = "",
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT token.

    Standard claims follow the pattern:
    ``sub``, ``iss``, ``iat``, ``exp``, ``jti``, ``session_id``,
    ``instance_id``, ``role``, ``auth_method``.

    Args:
        subject: The ``sub`` claim (typically the username).
        secret: Signing key (symmetric key for HS256, PEM private key for RS256).
        algorithm: JWT signing algorithm (``"HS256"`` or ``"RS256"``).
        issuer: The ``iss`` claim.
        expiry_hours: Hours until the token expires.
        instance_id: Server instance identifier for the ``instance_id`` claim.
        extra_claims: Additional claims to merge into the payload.

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iss": issuer,
        "iat": now,
        "exp": now + timedelta(hours=expiry_hours),
        "jti": str(uuid.uuid4()),
        "instance_id": instance_id,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, secret, algorithm=algorithm)


def verify_jwt(
    token: str,
    secret: str,
    *,
    algorithms: list[str] | None = None,
    issuer: str = DEFAULT_ISSUER,
) -> dict[str, Any]:
    """Verify and decode a JWT token.

    Args:
        token: The encoded JWT string.
        secret: Verification key (symmetric key for HS256, PEM public key for RS256).
        algorithms: Accepted signing algorithms. Defaults to ``["HS256"]``.
        issuer: Expected ``iss`` claim value.

    Returns:
        Decoded payload as a dictionary.

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidIssuerError: If the issuer doesn't match.
        jwt.InvalidTokenError: For any other validation failure.
    """
    if algorithms is None:
        algorithms = ["HS256"]

    return jwt.decode(
        token,
        secret,
        algorithms=algorithms,
        issuer=issuer,
    )

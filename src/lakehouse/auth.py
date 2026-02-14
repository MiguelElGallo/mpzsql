"""Authentication middleware — Basic/Bearer auth with JWT token issuance.

Implements three PyArrow Flight server middleware factories:

* **BasicAuthServerMiddlewareFactory** — intercepts ``Basic`` auth headers,
  verifies the password via HMAC-SHA256, and issues a JWT bearer token in the
  response headers.
* **BearerAuthServerMiddlewareFactory** — validates incoming ``Bearer`` JWT
  tokens.
* **AccessLogMiddlewareFactory** — logs every RPC call with method name and
  elapsed time.
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

import jwt
import pyarrow.flight as flight

from lakehouse.security import create_jwt, verify_jwt, verify_password

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  NoOpAuthHandler — mirrors C++ arrow::flight::NoOpAuthHandler
# ═══════════════════════════════════════════════════════════════════════════


class NoOpAuthHandler(flight.ServerAuthHandler):
    """A no-op auth handler that allows the ``Handshake`` RPC to succeed.

    This mirrors ``arrow::flight::NoOpAuthHandler``
    The actual authentication is handled entirely by middleware
    (``BasicAuthServerMiddlewareFactory`` / ``BearerAuthServerMiddlewareFactory``).
    The JDBC Flight SQL driver requires the ``Handshake`` RPC to not return
    ``UNIMPLEMENTED``, so this handler satisfies that requirement.
    """

    def authenticate(
        self,
        outgoing: flight.ServerAuthSender,  # ty: ignore[unresolved-attribute]
        incoming: flight.ServerAuthReader,  # ty: ignore[unresolved-attribute]
    ) -> None:
        """No-op handshake — accept any client."""

    def is_valid(self, token: bytes) -> str:
        """Always return empty identity (auth is enforced by middleware)."""
        return ""


# ═══════════════════════════════════════════════════════════════════════════
#  Header helpers
# ═══════════════════════════════════════════════════════════════════════════


def _get_header(headers: dict[str, list[str]], key: str) -> str | None:
    """Case-insensitive lookup of a single-valued header.

    Args:
        headers: Incoming request headers (keys → list of values).
        key: Header name to look up (case-insensitive).

    Returns:
        First value for the header, or ``None`` if absent.
    """
    for k, values in headers.items():
        if k.lower() == key.lower() and values:
            return values[0] if isinstance(values, list) else values
    return None


def _parse_basic_header(header_value: str) -> tuple[str, str]:
    """Decode a ``Basic <base64>`` Authorization header.

    Args:
        header_value: The full header value, e.g. ``"Basic dXNlcjpwYXNz"``.

    Returns:
        ``(username, password)`` tuple.

    Raises:
        ValueError: If the header is malformed.
    """
    parts = header_value.split(" ", 1)
    if len(parts) != 2 or parts[0] != "Basic":
        msg = "Invalid Basic auth header format"
        raise ValueError(msg)
    try:
        decoded = base64.b64decode(parts[1]).decode("utf-8")
    except Exception as exc:
        msg = "Invalid Base64 encoding in Basic auth header"
        raise ValueError(msg) from exc
    colon_idx = decoded.find(":")
    if colon_idx < 0:
        msg = "Basic auth header missing colon separator"
        raise ValueError(msg)
    return decoded[:colon_idx], decoded[colon_idx + 1 :]


# ═══════════════════════════════════════════════════════════════════════════
#  BasicAuthServerMiddlewareFactory
# ═══════════════════════════════════════════════════════════════════════════


class BasicAuthServerMiddleware(flight.ServerMiddleware):
    """Per-call middleware that injects the JWT bearer token in response headers.

    Created by :class:`BasicAuthServerMiddlewareFactory` after successful
    credential verification.
    """

    def __init__(self, token: str, username: str) -> None:
        """Initialize with *token* and *username*."""
        self.token = token
        self.username = username

    def sending_headers(self) -> dict[str, str]:
        """Inject ``authorization: Bearer <token>`` into the response."""
        return {"authorization": f"Bearer {self.token}"}

    def call_completed(self, exception: Any) -> None:  # noqa: ANN401
        """No-op — call completed callback."""


class BasicAuthServerMiddlewareFactory(flight.ServerMiddlewareFactory):
    """Authenticate clients via HTTP Basic auth.

    On successful authentication, issues a JWT bearer token in the response
    headers. Subsequent requests can use that token with the bearer middleware.

    Mirrors  ``BasicAuthServerMiddlewareFactory``:
    - Username ``"token"`` triggers bootstrap token validation (RS256 from
      external IdP).
    - Normal users are verified via HMAC-SHA256 password hashing.

    Args:
        secret_key: Server secret for HMAC password hashing and HS256 JWT signing.
        password_hash: Pre-computed HMAC-SHA256 hash of the configured password.
        instance_id: Server instance ID for JWT ``instance_id`` claim.
    """

    def __init__(
        self,
        secret_key: str,
        password_hash: str,
        instance_id: str = "",
    ) -> None:
        """Initialize with *secret_key*, *password_hash*, and *instance_id*."""
        self.secret_key = secret_key
        self.password_hash = password_hash
        self.instance_id = instance_id

    def start_call(
        self,
        info: flight.CallInfo,
        headers: dict[str, list[str]],
    ) -> BasicAuthServerMiddleware | None:
        """Validate Basic auth credentials and issue a JWT.

        Args:
            info: RPC call information.
            headers: Incoming request headers.

        Returns:
            Middleware instance with the JWT token, or ``None`` (no auth header).

        Raises:
            flight.FlightUnauthenticatedError: If credentials are invalid.
        """
        auth_header = _get_header(headers, "authorization")
        if auth_header is None:
            return None

        # Only handle Basic auth; let Bearer fall through to BearerAuthMiddleware
        if not auth_header.startswith("Basic "):
            return None

        try:
            username, password = _parse_basic_header(auth_header)
        except ValueError as exc:
            raise flight.FlightUnauthenticatedError("Invalid Basic auth header") from exc

        if not username:
            raise flight.FlightUnauthenticatedError("Username must not be empty")

        # Verify password via HMAC-SHA256
        if not verify_password(password, self.secret_key, self.password_hash):
            raise flight.FlightUnauthenticatedError("Invalid credentials")

        # Issue JWT
        token = create_jwt(
            subject=username,
            secret=self.secret_key,
            instance_id=self.instance_id,
            extra_claims={"role": "user", "auth_method": "basic"},
        )

        return BasicAuthServerMiddleware(token=token, username=username)


# ═══════════════════════════════════════════════════════════════════════════
#  BearerAuthServerMiddlewareFactory
# ═══════════════════════════════════════════════════════════════════════════


class BearerAuthServerMiddleware(flight.ServerMiddleware):
    """Per-call middleware for authenticated Bearer requests.

    Stores the decoded JWT payload for access by RPC handlers.
    """

    def __init__(self, payload: dict[str, Any]) -> None:
        """Initialize with decoded JWT *payload*."""
        self.payload = payload

    def sending_headers(self) -> dict[str, str]:
        """No additional headers to send for bearer-authenticated calls."""
        return {}

    def call_completed(self, exception: Any) -> None:  # noqa: ANN401
        """No-op — call completed callback."""


class BearerAuthServerMiddlewareFactory(flight.ServerMiddlewareFactory):
    """Validate Bearer JWT tokens on incoming requests.

    Mirrors``BearerAuthServerMiddlewareFactory``:
    - Extracts the ``Bearer <token>`` from the Authorization header.
    - Verifies signature, expiry, and issuer using the server's secret key.
    - Makes the decoded payload available via ``context.get_middleware("bearer")``.

    Args:
        secret_key: Symmetric key for HS256 JWT verification.
        issuer: Expected JWT issuer claim (defaults to ``"lakehouse"``).
    """

    def __init__(self, secret_key: str, issuer: str = "lakehouse") -> None:
        """Initialize with *secret_key* and expected *issuer*."""
        self.secret_key = secret_key
        self.issuer = issuer

    def start_call(
        self,
        info: flight.CallInfo,
        headers: dict[str, list[str]],
    ) -> BearerAuthServerMiddleware | None:
        """Validate a Bearer JWT token.

        Args:
            info: RPC call information.
            headers: Incoming request headers.

        Returns:
            Middleware instance with decoded payload, or ``None`` (no auth header).

        Raises:
            flight.FlightUnauthenticatedError: If the token is missing, expired,
                or otherwise invalid.
        """
        auth_header = _get_header(headers, "authorization")
        if auth_header is None:
            return None

        # Only handle Bearer tokens
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[len("Bearer ") :]
        if not token:
            raise flight.FlightUnauthenticatedError("Bearer token is empty")

        try:
            payload = verify_jwt(token, self.secret_key, issuer=self.issuer)
        except jwt.ExpiredSignatureError as exc:
            raise flight.FlightUnauthenticatedError("Token has expired") from exc
        except jwt.InvalidIssuerError as exc:
            raise flight.FlightUnauthenticatedError("Invalid token issuer") from exc
        except jwt.InvalidTokenError as exc:
            raise flight.FlightUnauthenticatedError("Invalid token") from exc

        return BearerAuthServerMiddleware(payload=payload)


# ═══════════════════════════════════════════════════════════════════════════
#  AccessLogMiddlewareFactory
# ═══════════════════════════════════════════════════════════════════════════


class AccessLogMiddleware(flight.ServerMiddleware):
    """Per-call middleware that logs request timing on completion."""

    def __init__(self, method: str) -> None:
        """Initialize with the RPC *method* name."""
        self.method = method
        self.start_time = time.monotonic()

    def sending_headers(self) -> dict[str, str]:
        """No additional headers."""
        return {}

    def call_completed(self, exception: Any) -> None:  # noqa: ANN401
        """Log method name, elapsed time, and any error."""
        elapsed_ms = (time.monotonic() - self.start_time) * 1000
        if exception:
            logger.info(
                "RPC %s completed in %.1fms with error: %s",
                self.method,
                elapsed_ms,
                exception,
            )
        else:
            logger.info("RPC %s completed in %.1fms", self.method, elapsed_ms)


class AccessLogMiddlewareFactory(flight.ServerMiddlewareFactory):
    """Log every incoming RPC call.

    Emits an ``INFO``-level log message with the Flight method name and
    elapsed time after each call completes.
    """

    def start_call(
        self,
        info: flight.CallInfo,
        headers: dict[str, list[str]],
    ) -> AccessLogMiddleware:
        """Create an access-log middleware instance for this call.

        Args:
            info: RPC call information.
            headers: Incoming request headers (unused).

        Returns:
            Middleware instance that will log on completion.
        """
        return AccessLogMiddleware(method=str(info.method))

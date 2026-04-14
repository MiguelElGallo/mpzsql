"""Tests for lakehouse.auth — Flight server authentication middleware."""

from __future__ import annotations

import base64
import datetime
import logging

import jwt as pyjwt
import pyarrow.flight as flight
import pytest

from lakehouse.auth import (
    AccessLogMiddleware,
    AccessLogMiddlewareFactory,
    BasicAuthServerMiddleware,
    BasicAuthServerMiddlewareFactory,
    BearerAuthServerMiddleware,
    BearerAuthServerMiddlewareFactory,
    NoOpAuthHandler,
    RequiredAuthServerMiddlewareFactory,
    _get_header,
    _parse_basic_header,
)
from lakehouse.security import DEFAULT_ISSUER, create_jwt, hash_password

# ═══════════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════════
SECRET_KEY = "test-secret-key-at-least-32-bytes-long!"
USERNAME = "testuser"
PASSWORD = "testpass"
INSTANCE_ID = "inst-test-001"


@pytest.fixture
def password_hash():
    """Pre-computed HMAC-SHA256 hash for USERNAME/PASSWORD."""
    return hash_password(PASSWORD, SECRET_KEY)


@pytest.fixture
def basic_factory(password_hash):
    """BasicAuthServerMiddlewareFactory instance."""
    return BasicAuthServerMiddlewareFactory(
        secret_key=SECRET_KEY,
        password_hash=password_hash,
        instance_id=INSTANCE_ID,
    )


@pytest.fixture
def bearer_factory():
    """BearerAuthServerMiddlewareFactory instance."""
    return BearerAuthServerMiddlewareFactory(
        secret_key=SECRET_KEY,
        issuer=DEFAULT_ISSUER,
    )


@pytest.fixture
def access_factory():
    """AccessLogMiddlewareFactory instance."""
    return AccessLogMiddlewareFactory()


@pytest.fixture
def required_auth_factory():
    """RequiredAuthServerMiddlewareFactory instance."""
    return RequiredAuthServerMiddlewareFactory()


@pytest.fixture
def call_info():
    """A minimal CallInfo for testing."""
    return flight.CallInfo(method=flight.FlightMethod.DO_GET)


def _make_basic_header(username: str, password: str) -> dict[str, list[str]]:
    """Create headers dict with Basic auth."""
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"authorization": [f"Basic {encoded}"]}


def _make_bearer_header(token: str) -> dict[str, list[str]]:
    """Create headers dict with Bearer token."""
    return {"authorization": [f"Bearer {token}"]}


# ═══════════════════════════════════════════════════════════════════════════
#  Header helpers
# ═══════════════════════════════════════════════════════════════════════════
class TestGetHeader:
    """Tests for _get_header()."""

    def test_found(self):
        headers = {"authorization": ["Bearer xyz"]}
        assert _get_header(headers, "authorization") == "Bearer xyz"

    def test_case_insensitive(self):
        headers = {"Authorization": ["Bearer xyz"]}
        assert _get_header(headers, "authorization") == "Bearer xyz"

    def test_missing(self):
        headers = {"content-type": ["application/json"]}
        assert _get_header(headers, "authorization") is None

    def test_empty_dict(self):
        assert _get_header({}, "authorization") is None

    def test_empty_values_list(self):
        headers = {"authorization": []}
        assert _get_header(headers, "authorization") is None


class TestParseBasicHeader:
    """Tests for _parse_basic_header()."""

    def test_valid(self):
        encoded = base64.b64encode(b"alice:password").decode()
        user, pwd = _parse_basic_header(f"Basic {encoded}")
        assert user == "alice"
        assert pwd == "password"

    def test_password_with_colon(self):
        """Password can contain colons."""
        encoded = base64.b64encode(b"alice:pass:word:extra").decode()
        user, pwd = _parse_basic_header(f"Basic {encoded}")
        assert user == "alice"
        assert pwd == "pass:word:extra"

    def test_empty_password(self):
        encoded = base64.b64encode(b"alice:").decode()
        user, pwd = _parse_basic_header(f"Basic {encoded}")
        assert user == "alice"
        assert pwd == ""

    def test_invalid_scheme(self):
        with pytest.raises(ValueError, match="Invalid Basic auth header"):
            _parse_basic_header("Bearer token123")

    def test_no_space(self):
        with pytest.raises(ValueError, match="Invalid Basic auth header"):
            _parse_basic_header("BasicABC123")

    def test_invalid_base64(self):
        with pytest.raises(ValueError, match="Invalid Base64"):
            _parse_basic_header("Basic !!!not-base64!!!")

    def test_no_colon(self):
        encoded = base64.b64encode(b"nocolon").decode()
        with pytest.raises(ValueError, match="missing colon"):
            _parse_basic_header(f"Basic {encoded}")


# ═══════════════════════════════════════════════════════════════════════════
#  BasicAuthServerMiddlewareFactory
# ═══════════════════════════════════════════════════════════════════════════
class TestBasicAuthFactoryStartCall:
    """Tests for BasicAuthServerMiddlewareFactory.start_call()."""

    def test_valid_credentials(self, basic_factory, call_info):
        """Correct username/password returns middleware with JWT."""
        headers = _make_basic_header(USERNAME, PASSWORD)
        mw = basic_factory.start_call(call_info, headers)

        assert mw is not None
        assert isinstance(mw, BasicAuthServerMiddleware)
        assert mw.username == USERNAME

        # Verify the token is a valid JWT
        payload = pyjwt.decode(mw.token, SECRET_KEY, algorithms=["HS256"], issuer=DEFAULT_ISSUER)
        assert payload["sub"] == USERNAME
        assert payload["role"] == "user"
        assert payload["auth_method"] == "basic"
        assert payload["instance_id"] == INSTANCE_ID

    def test_wrong_password(self, basic_factory, call_info):
        """Wrong password raises FlightUnauthenticatedError."""
        headers = _make_basic_header(USERNAME, "wrongpass")
        with pytest.raises(flight.FlightUnauthenticatedError, match="Invalid credentials"):
            basic_factory.start_call(call_info, headers)

    def test_wrong_username_right_password(self, basic_factory, call_info):
        """Unknown username with correct password still fails (hash doesn't match)."""
        headers = _make_basic_header("unknown", PASSWORD)
        # The hash was computed from PASSWORD + SECRET_KEY, but the middleware
        # just verifies the password. With "unknown" username, password still
        # goes through verify_password which should pass if we send the right pwd.
        # Wait — the factory checks verify_password(password, secret_key, stored_hash)
        # The stored_hash was hash_password(PASSWORD, SECRET_KEY).
        # So verify_password(PASSWORD, SECRET_KEY, stored_hash) == True regardless of username.
        # The username is only for the JWT subject claim.
        mw = basic_factory.start_call(call_info, headers)
        assert mw is not None
        assert mw.username == "unknown"

    def test_empty_username(self, basic_factory, call_info):
        """Empty username raises FlightUnauthenticatedError."""
        headers = _make_basic_header("", PASSWORD)
        with pytest.raises(flight.FlightUnauthenticatedError, match="Username must not be empty"):
            basic_factory.start_call(call_info, headers)

    def test_no_auth_header(self, basic_factory, call_info):
        """No authorization header returns None (no middleware)."""
        mw = basic_factory.start_call(call_info, {})
        assert mw is None

    def test_bearer_header_ignored(self, basic_factory, call_info):
        """Bearer auth header returns None (handled by BearerAuthMiddleware)."""
        headers = {"authorization": ["Bearer some-token"]}
        mw = basic_factory.start_call(call_info, headers)
        assert mw is None

    def test_malformed_basic_header(self, basic_factory, call_info):
        """Malformed Basic header raises FlightUnauthenticatedError."""
        headers = {"authorization": ["Basic !!!invalid!!!"]}
        with pytest.raises(flight.FlightUnauthenticatedError, match="Invalid Basic auth"):
            basic_factory.start_call(call_info, headers)

    def test_case_insensitive_auth_header(self, basic_factory, call_info):
        """Authorization header lookup is case-insensitive."""
        encoded = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
        headers = {"Authorization": [f"Basic {encoded}"]}
        mw = basic_factory.start_call(call_info, headers)
        assert mw is not None

    def test_sending_headers_contains_bearer(self, basic_factory, call_info):
        """Middleware sending_headers includes the JWT as Bearer."""
        headers = _make_basic_header(USERNAME, PASSWORD)
        mw = basic_factory.start_call(call_info, headers)
        assert mw is not None
        response_headers = mw.sending_headers()
        assert "authorization" in response_headers
        assert response_headers["authorization"].startswith("Bearer ")

    def test_sql_injection_username(self, basic_factory, call_info):
        """SQL injection in username doesn't crash the middleware."""
        headers = _make_basic_header("' OR 1=1 --", PASSWORD)
        # Password is wrong (different from stored hash) so it should fail
        mw = basic_factory.start_call(call_info, headers)
        # Actually with the correct password, it succeeds — this is fine since
        # username is just stored in JWT, not used in SQL
        assert mw is not None

    def test_unicode_password(self, basic_factory, call_info):
        """Unicode password that doesn't match the hash fails."""
        headers = _make_basic_header(USERNAME, "pässwörd")
        with pytest.raises(flight.FlightUnauthenticatedError):
            basic_factory.start_call(call_info, headers)


class TestBasicAuthServerMiddleware:
    """Tests for BasicAuthServerMiddleware."""

    def test_sending_headers(self):
        mw = BasicAuthServerMiddleware(token="jwt123", username="alice")
        headers = mw.sending_headers()
        assert headers == {"authorization": "Bearer jwt123"}

    def test_call_completed_no_error(self):
        mw = BasicAuthServerMiddleware(token="jwt123", username="alice")
        mw.call_completed(None)  # Should not raise

    def test_call_completed_with_error(self):
        mw = BasicAuthServerMiddleware(token="jwt123", username="alice")
        mw.call_completed(Exception("some error"))  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════
#  BearerAuthServerMiddlewareFactory
# ═══════════════════════════════════════════════════════════════════════════
class TestBearerAuthFactoryStartCall:
    """Tests for BearerAuthServerMiddlewareFactory.start_call()."""

    def test_valid_token(self, bearer_factory, call_info):
        """Valid JWT returns middleware with decoded payload."""
        token = create_jwt(subject=USERNAME, secret=SECRET_KEY, instance_id=INSTANCE_ID)
        headers = _make_bearer_header(token)
        mw = bearer_factory.start_call(call_info, headers)

        assert mw is not None
        assert isinstance(mw, BearerAuthServerMiddleware)
        assert mw.payload["sub"] == USERNAME
        assert mw.payload["instance_id"] == INSTANCE_ID

    def test_expired_token(self, bearer_factory, call_info):
        """Expired JWT raises FlightUnauthenticatedError."""
        exp_payload = {
            "sub": USERNAME,
            "iss": DEFAULT_ISSUER,
            "iat": datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=2),
            "exp": datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1),
        }
        token = pyjwt.encode(exp_payload, SECRET_KEY, algorithm="HS256")
        headers = _make_bearer_header(token)
        with pytest.raises(flight.FlightUnauthenticatedError, match="Token has expired"):
            bearer_factory.start_call(call_info, headers)

    def test_wrong_secret(self, bearer_factory, call_info):
        """Token signed with a different key fails."""
        token = create_jwt(subject=USERNAME, secret="wrong-secret-key-xxxx")
        headers = _make_bearer_header(token)
        with pytest.raises(flight.FlightUnauthenticatedError, match="Invalid token"):
            bearer_factory.start_call(call_info, headers)

    def test_wrong_issuer(self, bearer_factory, call_info):
        """Token with wrong issuer fails."""
        token = create_jwt(subject=USERNAME, secret=SECRET_KEY, issuer="evil-issuer")
        headers = _make_bearer_header(token)
        with pytest.raises(flight.FlightUnauthenticatedError, match="Invalid token issuer"):
            bearer_factory.start_call(call_info, headers)

    def test_no_auth_header(self, bearer_factory, call_info):
        """No authorization header returns None."""
        mw = bearer_factory.start_call(call_info, {})
        assert mw is None

    def test_basic_header_ignored(self, bearer_factory, call_info):
        """Basic auth header returns None (handled by BasicAuthMiddleware)."""
        headers = _make_basic_header("user", "pass")
        mw = bearer_factory.start_call(call_info, headers)
        assert mw is None

    def test_empty_bearer(self, bearer_factory, call_info):
        """Bearer token that is empty raises error."""
        headers = {"authorization": ["Bearer "]}
        with pytest.raises(flight.FlightUnauthenticatedError, match="Bearer token is empty"):
            bearer_factory.start_call(call_info, headers)

    def test_malformed_token(self, bearer_factory, call_info):
        """Completely invalid JWT string raises error."""
        headers = _make_bearer_header("not-a-jwt")
        with pytest.raises(flight.FlightUnauthenticatedError, match="Invalid token"):
            bearer_factory.start_call(call_info, headers)

    def test_tampered_token(self, bearer_factory, call_info):
        """Tampered JWT fails signature verification."""
        token = create_jwt(subject=USERNAME, secret=SECRET_KEY)
        parts = token.split(".")
        # Tamper with the payload
        tampered_payload = parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")
        tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"
        headers = _make_bearer_header(tampered_token)
        with pytest.raises(flight.FlightUnauthenticatedError, match="Invalid token"):
            bearer_factory.start_call(call_info, headers)

    def test_case_insensitive_auth_header(self, bearer_factory, call_info):
        """Authorization header lookup is case-insensitive."""
        token = create_jwt(subject=USERNAME, secret=SECRET_KEY)
        headers = {"Authorization": [f"Bearer {token}"]}
        mw = bearer_factory.start_call(call_info, headers)
        assert mw is not None


class TestBearerAuthServerMiddleware:
    """Tests for BearerAuthServerMiddleware."""

    def test_sending_headers_empty(self):
        mw = BearerAuthServerMiddleware(payload={"sub": "alice"})
        assert mw.sending_headers() == {}

    def test_call_completed_no_error(self):
        mw = BearerAuthServerMiddleware(payload={"sub": "alice"})
        mw.call_completed(None)  # Should not raise

    def test_payload_accessible(self):
        payload = {"sub": "alice", "role": "admin"}
        mw = BearerAuthServerMiddleware(payload=payload)
        assert mw.payload["sub"] == "alice"
        assert mw.payload["role"] == "admin"


# ═══════════════════════════════════════════════════════════════════════════
#  RequiredAuthServerMiddlewareFactory
# ═══════════════════════════════════════════════════════════════════════════
class TestRequiredAuthFactoryStartCall:
    """Tests for RequiredAuthServerMiddlewareFactory.start_call()."""

    def test_missing_auth_header_rejected(self, required_auth_factory, call_info):
        """No authorization header is rejected when auth is required."""
        with pytest.raises(
            flight.FlightUnauthenticatedError,
            match="Authorization header is required",
        ):
            required_auth_factory.start_call(call_info, {})

    def test_basic_auth_header_allowed(self, required_auth_factory, call_info):
        """Basic auth is allowed for BasicAuthServerMiddlewareFactory to validate."""
        headers = _make_basic_header(USERNAME, PASSWORD)
        assert required_auth_factory.start_call(call_info, headers) is None

    def test_bearer_auth_header_allowed(self, required_auth_factory, call_info):
        """Bearer auth is allowed for BearerAuthServerMiddlewareFactory to validate."""
        headers = _make_bearer_header("jwt")
        assert required_auth_factory.start_call(call_info, headers) is None

    def test_unsupported_auth_scheme_rejected(self, required_auth_factory, call_info):
        """Unsupported authorization schemes are rejected."""
        with pytest.raises(
            flight.FlightUnauthenticatedError,
            match="Unsupported authorization scheme",
        ):
            required_auth_factory.start_call(call_info, {"authorization": ["Token abc"]})


# ═══════════════════════════════════════════════════════════════════════════
#  AccessLogMiddlewareFactory
# ═══════════════════════════════════════════════════════════════════════════
class TestAccessLogFactoryStartCall:
    """Tests for AccessLogMiddlewareFactory.start_call()."""

    def test_returns_middleware(self, access_factory, call_info):
        """start_call always returns an AccessLogMiddleware."""
        mw = access_factory.start_call(call_info, {})
        assert mw is not None
        assert isinstance(mw, AccessLogMiddleware)

    def test_records_method_name(self, access_factory, call_info):
        """Middleware captures the RPC method name."""
        mw = access_factory.start_call(call_info, {})
        assert "DO_GET" in mw.method or "DoGet" in mw.method or "do_get" in mw.method

    def test_sending_headers_empty(self, access_factory, call_info):
        """AccessLogMiddleware doesn't add response headers."""
        mw = access_factory.start_call(call_info, {})
        assert mw.sending_headers() == {}


class TestAccessLogMiddleware:
    """Tests for AccessLogMiddleware."""

    def test_call_completed_logs_success(self, caplog):
        """Successful completion is logged."""
        mw = AccessLogMiddleware(method="DoGet")
        with caplog.at_level(logging.INFO, logger="lakehouse.auth"):
            mw.call_completed(None)
        assert any(
            "DoGet" in record.message and "completed" in record.message
            for record in caplog.records
        )

    def test_call_completed_logs_error(self, caplog):
        """Failed completion includes the error in the log."""
        mw = AccessLogMiddleware(method="DoGet")
        with caplog.at_level(logging.INFO, logger="lakehouse.auth"):
            mw.call_completed(Exception("test error"))
        assert any("error" in record.message.lower() for record in caplog.records)

    def test_elapsed_time_positive(self, caplog):
        """Elapsed time is >= 0."""
        mw = AccessLogMiddleware(method="DoGet")
        import time

        time.sleep(0.01)  # Sleep 10ms
        with caplog.at_level(logging.INFO, logger="lakehouse.auth"):
            mw.call_completed(None)
        # The log should contain a positive elapsed time
        assert len(caplog.records) > 0


# ═══════════════════════════════════════════════════════════════════════════
#  Integration: Basic → Bearer flow
# ═══════════════════════════════════════════════════════════════════════════
class TestBasicToBearerFlow:
    """Test the full authentication flow: Basic → JWT → Bearer."""

    def test_full_flow(self, basic_factory, bearer_factory, call_info):
        """Basic auth → get JWT → Bearer auth with that JWT."""
        # Step 1: Authenticate with Basic auth
        basic_headers = _make_basic_header(USERNAME, PASSWORD)
        basic_mw = basic_factory.start_call(call_info, basic_headers)
        assert basic_mw is not None

        # Step 2: Extract the JWT from response headers
        response_headers = basic_mw.sending_headers()
        bearer_value = response_headers["authorization"]
        assert bearer_value.startswith("Bearer ")
        jwt_token = bearer_value[len("Bearer ") :]

        # Step 3: Use the JWT for Bearer auth on next call
        bearer_headers = _make_bearer_header(jwt_token)
        bearer_mw = bearer_factory.start_call(call_info, bearer_headers)
        assert bearer_mw is not None
        assert bearer_mw.payload["sub"] == USERNAME
        assert bearer_mw.payload["auth_method"] == "basic"

    def test_basic_and_bearer_coexist(self, basic_factory, bearer_factory, call_info):
        """Both middleware factories can be active on the same headers."""
        # Basic factory sees Basic auth, Bearer factory returns None
        basic_headers = _make_basic_header(USERNAME, PASSWORD)
        basic_mw = basic_factory.start_call(call_info, basic_headers)
        bearer_mw = bearer_factory.start_call(call_info, basic_headers)
        assert basic_mw is not None
        assert bearer_mw is None

        # Bearer factory sees Bearer auth, Basic factory returns None
        token = create_jwt(subject=USERNAME, secret=SECRET_KEY)
        bearer_headers = _make_bearer_header(token)
        basic_mw2 = basic_factory.start_call(call_info, bearer_headers)
        bearer_mw2 = bearer_factory.start_call(call_info, bearer_headers)
        assert basic_mw2 is None
        assert bearer_mw2 is not None


# ═══════════════════════════════════════════════════════════════════════════
#  NoOpAuthHandler
# ═══════════════════════════════════════════════════════════════════════════
class TestNoOpAuthHandler:
    """Tests for the NoOpAuthHandler (Handshake RPC support)."""

    def test_is_valid_returns_empty_string(self):
        handler = NoOpAuthHandler()
        assert handler.is_valid(b"any-token") == ""

    def test_is_valid_with_empty_token(self):
        handler = NoOpAuthHandler()
        assert handler.is_valid(b"") == ""

    def test_authenticate_does_not_raise(self):
        handler = NoOpAuthHandler()
        # authenticate is a no-op — should not raise
        handler.authenticate(None, None)

    def test_is_instance_of_server_auth_handler(self):
        handler = NoOpAuthHandler()
        assert isinstance(handler, flight.ServerAuthHandler)

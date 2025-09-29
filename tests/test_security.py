"""
Tests for security and TLS module.
Tests for mpzsql.security module providing authentication middleware and TLS support.
"""

import base64
import os
import ssl
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock

import jwt
import pyarrow.flight as pf
import pytest

from mpzsql.config import ServerConfig
from mpzsql.security import (
    AuthMiddleware,
    BearerAuthServerMiddlewareFactory,
    FlightAuthHandler,
    HeaderAuthServerMiddleware,
    HeaderAuthServerMiddlewareFactory,
    NoOpAuthHandler,
    TLSCertificateLoader,
    create_self_signed_cert,
    setup_tls_context,
)


class TestAuthMiddleware:
    """Test cases for AuthMiddleware class."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.config = Mock(spec=ServerConfig)
        self.config.username = "testuser"
        self.config.password = "testpass"
        self.config.secret_key = "test-secret-key"
        self.config.is_auth_enabled = True

        self.auth_middleware = AuthMiddleware(self.config)

    def test_initialization(self) -> None:
        """Test AuthMiddleware initialization."""
        assert self.auth_middleware.config == self.config
        assert self.auth_middleware.username == "testuser"
        assert self.auth_middleware.password == "testpass"
        assert self.auth_middleware.secret_key == "test-secret-key"

    def test_authenticate_auth_disabled(self) -> None:
        """Test authenticate method when auth is disabled."""
        self.config.is_auth_enabled = False
        context = Mock(spec=pf.ServerCallContext)

        # Should return without error when auth is disabled
        self.auth_middleware.authenticate(context)

    def test_authenticate_auth_enabled(self) -> None:
        """Test authenticate method when auth is enabled."""
        context = Mock(spec=pf.ServerCallContext)

        # Should return without error (method is for backwards compatibility)
        self.auth_middleware.authenticate(context)

    def test_authenticate_jwt_valid_token(self) -> None:
        """Test JWT authentication with valid token."""
        payload = {
            "username": "testuser",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, "test-secret-key", algorithm="HS256")

        # Should not raise exception
        self.auth_middleware._authenticate_jwt(token)

    def test_authenticate_jwt_expired_token(self) -> None:
        """Test JWT authentication with expired token."""
        payload = {
            "username": "testuser",
            "exp": datetime.utcnow() - timedelta(hours=1),
            "iat": datetime.utcnow() - timedelta(hours=2),
        }
        token = jwt.encode(payload, "test-secret-key", algorithm="HS256")

        with pytest.raises(pf.FlightUnauthenticatedError, match="Token has expired"):
            self.auth_middleware._authenticate_jwt(token)

    def test_authenticate_jwt_invalid_signature(self) -> None:
        """Test JWT authentication with invalid signature."""
        payload = {
            "username": "testuser",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")

        with pytest.raises(pf.FlightUnauthenticatedError, match="Invalid token"):
            self.auth_middleware._authenticate_jwt(token)

    def test_authenticate_jwt_wrong_username(self) -> None:
        """Test JWT authentication with wrong username in token."""
        payload = {
            "username": "wronguser",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, "test-secret-key", algorithm="HS256")

        with pytest.raises(
            pf.FlightUnauthenticatedError, match="Authentication failed"
        ):
            self.auth_middleware._authenticate_jwt(token)

    def test_authenticate_jwt_malformed_token(self) -> None:
        """Test JWT authentication with malformed token."""
        malformed_token = "not.a.valid.jwt.token"

        with pytest.raises(pf.FlightUnauthenticatedError, match="Invalid token"):
            self.auth_middleware._authenticate_jwt(malformed_token)

    def test_authenticate_jwt_no_username_in_token(self) -> None:
        """Test JWT authentication with token missing username."""
        payload = {
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, "test-secret-key", algorithm="HS256")

        # Should pass when no username in token
        self.auth_middleware._authenticate_jwt(token)

    def test_authenticate_basic_valid_credentials(self) -> None:
        """Test Basic authentication with valid credentials."""
        credentials = base64.b64encode(b"testuser:testpass").decode("utf-8")

        # Should not raise exception
        self.auth_middleware._authenticate_basic(credentials)

    def test_authenticate_basic_invalid_username(self) -> None:
        """Test Basic authentication with invalid username."""
        credentials = base64.b64encode(b"wronguser:testpass").decode("utf-8")

        with pytest.raises(
            pf.FlightUnauthenticatedError, match="Authentication failed"
        ):
            self.auth_middleware._authenticate_basic(credentials)

    def test_authenticate_basic_invalid_password(self) -> None:
        """Test Basic authentication with invalid password."""
        credentials = base64.b64encode(b"testuser:wrongpass").decode("utf-8")

        with pytest.raises(
            pf.FlightUnauthenticatedError, match="Authentication failed"
        ):
            self.auth_middleware._authenticate_basic(credentials)

    def test_authenticate_basic_malformed_credentials(self) -> None:
        """Test Basic authentication with malformed credentials."""
        # Test various malformed credential formats
        malformed_credentials = [
            "not-base64-encoded",
            base64.b64encode(b"missing-colon").decode("utf-8"),
            "invalid-base64-chars!@#",
        ]

        for credentials in malformed_credentials:
            with pytest.raises(pf.FlightUnauthenticatedError):
                self.auth_middleware._authenticate_basic(credentials)

    def test_generate_jwt_token_default_user(self) -> None:
        """Test JWT token generation with default user."""
        token = self.auth_middleware.generate_jwt_token()

        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload["username"] == "testuser"
        assert "iat" in payload
        assert "exp" in payload

    def test_generate_jwt_token_custom_user(self) -> None:
        """Test JWT token generation with custom user."""
        token = self.auth_middleware.generate_jwt_token(username="customuser")

        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload["username"] == "customuser"

    def test_generate_jwt_token_custom_expiry(self) -> None:
        """Test JWT token generation with custom expiry."""
        token = self.auth_middleware.generate_jwt_token(expiry_hours=48)

        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        exp_time = datetime.fromtimestamp(payload["exp"])
        iat_time = datetime.fromtimestamp(payload["iat"])

        # Verify token expires in approximately 48 hours
        time_diff = exp_time - iat_time
        assert (
            abs(time_diff.total_seconds() - (48 * 3600)) < 60
        )  # Within 1 minute tolerance


class TestSetupTLSContext:
    """Test cases for setup_tls_context function."""

    def test_setup_tls_context_no_cert_or_key(self) -> None:
        """Test TLS context setup with no certificate or key."""
        context = setup_tls_context()
        assert context is None

        context = setup_tls_context(cert_file=None, key_file=None)
        assert context is None

        context = setup_tls_context(cert_file="cert.pem", key_file=None)
        assert context is None

    def test_setup_tls_context_with_valid_files(self) -> None:
        """Test TLS context setup with valid certificate files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = os.path.join(temp_dir, "server.crt")
            key_file = os.path.join(temp_dir, "server.key")

            # Create self-signed certificate for testing
            create_self_signed_cert(cert_file=cert_file, key_file=key_file)

            context = setup_tls_context(cert_file=cert_file, key_file=key_file)

            assert context is not None
            assert isinstance(context, ssl.SSLContext)
            assert context.verify_mode == ssl.CERT_NONE
            assert context.minimum_version == ssl.TLSVersion.TLSv1_2

    def test_setup_tls_context_with_mtls(self) -> None:
        """Test TLS context setup with mTLS (client verification)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = os.path.join(temp_dir, "server.crt")
            key_file = os.path.join(temp_dir, "server.key")
            ca_file = os.path.join(temp_dir, "ca.crt")

            # Create self-signed certificate for testing
            create_self_signed_cert(cert_file=cert_file, key_file=key_file)

            # Copy cert to ca file for testing
            with open(cert_file) as src, open(ca_file, "w") as dst:
                dst.write(src.read())

            context = setup_tls_context(
                cert_file=cert_file, key_file=key_file, ca_file=ca_file
            )

            assert context is not None
            assert isinstance(context, ssl.SSLContext)
            assert context.verify_mode == ssl.CERT_REQUIRED

    def test_setup_tls_context_invalid_cert_file(self) -> None:
        """Test TLS context setup with invalid certificate file."""
        with pytest.raises(Exception):
            setup_tls_context(cert_file="nonexistent.crt", key_file="nonexistent.key")

    def test_setup_tls_context_invalid_ca_file(self) -> None:
        """Test TLS context setup with invalid CA file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = os.path.join(temp_dir, "server.crt")
            key_file = os.path.join(temp_dir, "server.key")

            create_self_signed_cert(cert_file=cert_file, key_file=key_file)

            with pytest.raises(Exception):
                setup_tls_context(
                    cert_file=cert_file, key_file=key_file, ca_file="nonexistent-ca.crt"
                )


class TestFlightAuthHandler:
    """Test cases for FlightAuthHandler class."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.config = Mock(spec=ServerConfig)
        self.config.username = "testuser"
        self.config.password = "testpass"
        self.config.secret_key = "test-secret"

        self.auth_middleware = AuthMiddleware(self.config)
        self.auth_handler = FlightAuthHandler(self.auth_middleware)

    def test_initialization(self) -> None:
        """Test FlightAuthHandler initialization."""
        assert self.auth_handler.auth_middleware == self.auth_middleware

    def test_authenticate_valid_credentials(self) -> None:
        """Test authentication with valid credentials."""
        outgoing = Mock()
        incoming = Mock()

        # Mock BasicAuth serialization
        auth = pf.BasicAuth("testuser", "testpass")
        incoming.read.return_value = auth.serialize()

        self.auth_handler.authenticate(outgoing, incoming)

        # Verify token was written
        outgoing.write.assert_called_once()
        written_token = outgoing.write.call_args[0][0].decode()

        # Verify token is valid
        payload = jwt.decode(written_token, "test-secret", algorithms=["HS256"])
        assert payload["username"] == "testuser"

    def test_authenticate_invalid_credentials(self) -> None:
        """Test authentication with invalid credentials."""
        outgoing = Mock()
        incoming = Mock()

        # Mock BasicAuth with wrong credentials
        auth = pf.BasicAuth("testuser", "wrongpass")
        incoming.read.return_value = auth.serialize()

        with pytest.raises(pf.FlightUnauthenticatedError, match="Invalid credentials"):
            self.auth_handler.authenticate(outgoing, incoming)

    def test_authenticate_malformed_data(self) -> None:
        """Test authentication with malformed auth data."""
        outgoing = Mock()
        incoming = Mock()
        incoming.read.return_value = b"invalid-auth-data"

        with pytest.raises(
            pf.FlightUnauthenticatedError, match="Invalid authentication data"
        ):
            self.auth_handler.authenticate(outgoing, incoming)

    def test_is_valid_token_success(self) -> None:
        """Test is_valid with valid token."""
        token = self.auth_middleware.generate_jwt_token("testuser")

        username = self.auth_handler.is_valid(token)
        assert username == "testuser"

    def test_is_valid_token_with_bearer_prefix(self) -> None:
        """Test is_valid with Bearer prefix."""
        token = self.auth_middleware.generate_jwt_token("testuser")
        bearer_token = f"Bearer {token}"

        username = self.auth_handler.is_valid(bearer_token)
        assert username == "testuser"

    def test_is_valid_token_bytes(self) -> None:
        """Test is_valid with token as bytes."""
        token = self.auth_middleware.generate_jwt_token("testuser")
        token_bytes = token.encode()

        username = self.auth_handler.is_valid(token_bytes)
        assert username == "testuser"

    def test_is_valid_invalid_token(self) -> None:
        """Test is_valid with invalid token."""
        with pytest.raises(pf.FlightUnauthenticatedError, match="Invalid token"):
            self.auth_handler.is_valid("invalid-token")

    def test_is_valid_wrong_user(self) -> None:
        """Test is_valid with token for wrong user."""
        # Create token with different username
        payload = {
            "username": "wronguser",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, "test-secret", algorithm="HS256")

        with pytest.raises(pf.FlightUnauthenticatedError, match="Invalid token"):
            self.auth_handler.is_valid(token)


class TestNoOpAuthHandler:
    """Test cases for NoOpAuthHandler class."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.handler = NoOpAuthHandler()

    def test_authenticate_does_nothing(self) -> None:
        """Test that authenticate does nothing."""
        outgoing = Mock()
        incoming = Mock()

        # Should not raise any errors or call any methods
        self.handler.authenticate(outgoing, incoming)

        outgoing.write.assert_not_called()
        incoming.read.assert_not_called()

    def test_is_valid_returns_empty_string(self) -> None:
        """Test that is_valid returns empty string."""
        result = self.handler.is_valid("any-token")
        assert result == ""


class TestHeaderAuthServerMiddleware:
    """Test cases for HeaderAuthServerMiddleware class."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.middleware = HeaderAuthServerMiddleware("testuser", "test-secret")

    def test_initialization(self) -> None:
        """Test middleware initialization."""
        assert self.middleware.username == "testuser"
        assert self.middleware.secret_key == "test-secret"

    def test_sending_headers(self) -> None:
        """Test sending_headers method."""
        headers = self.middleware.sending_headers()

        assert "authorization" in headers
        auth_header = headers["authorization"]
        assert auth_header.startswith("Bearer ")

        # Verify token is valid
        token = auth_header[7:]  # Remove "Bearer " prefix
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
        assert payload["username"] == "testuser"

    def test_call_completed_does_nothing(self) -> None:
        """Test call_completed method does nothing."""
        # Should not raise any errors
        self.middleware.call_completed(None)


class TestHeaderAuthServerMiddlewareFactory:
    """Test cases for HeaderAuthServerMiddlewareFactory class."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.factory = HeaderAuthServerMiddlewareFactory(
            username="testuser", password="testpass", secret_key="test-secret"
        )

    def test_initialization(self) -> None:
        """Test factory initialization."""
        assert self.factory.username == "testuser"
        assert self.factory.password == "testpass"
        assert self.factory.secret_key == "test-secret"

    def test_start_call_valid_basic_auth(self) -> None:
        """Test start_call with valid Basic authentication."""
        # Create valid Basic auth header
        credentials = base64.b64encode(b"testuser:testpass").decode()
        headers = {"authorization": [f"Basic {credentials}"]}

        info = Mock()
        middleware = self.factory.start_call(info, headers)

        assert middleware is not None
        assert isinstance(middleware, HeaderAuthServerMiddleware)

    def test_start_call_no_auth_header(self) -> None:
        """Test start_call with no authorization header."""
        headers = {}
        info = Mock()

        middleware = self.factory.start_call(info, headers)
        assert middleware is None

    def test_start_call_not_basic_auth(self) -> None:
        """Test start_call with non-Basic authorization header."""
        headers = {"authorization": ["Bearer some-token"]}
        info = Mock()

        middleware = self.factory.start_call(info, headers)
        assert middleware is None

    def test_start_call_invalid_credentials(self) -> None:
        """Test start_call with invalid credentials."""
        credentials = base64.b64encode(b"testuser:wrongpass").decode()
        headers = {"authorization": [f"Basic {credentials}"]}

        info = Mock()
        with pytest.raises(pf.FlightUnauthenticatedError, match="Invalid credentials"):
            self.factory.start_call(info, headers)

    def test_start_call_malformed_basic_auth(self) -> None:
        """Test start_call with malformed Basic auth header."""
        headers = {"authorization": ["Basic invalid-base64"]}
        info = Mock()

        with pytest.raises(
            pf.FlightUnauthenticatedError, match="Invalid basic auth header"
        ):
            self.factory.start_call(info, headers)

    def test_start_call_missing_colon_in_credentials(self) -> None:
        """Test start_call with missing colon in credentials."""
        credentials = base64.b64encode(b"userpass").decode()  # Missing colon
        headers = {"authorization": [f"Basic {credentials}"]}

        info = Mock()
        with pytest.raises(
            pf.FlightUnauthenticatedError, match="Invalid basic auth header"
        ):
            self.factory.start_call(info, headers)

    def test_start_call_bytes_auth_header(self) -> None:
        """Test start_call with auth header as bytes."""
        credentials = base64.b64encode(b"testuser:testpass").decode()
        headers = {"authorization": [f"Basic {credentials}".encode()]}

        info = Mock()
        middleware = self.factory.start_call(info, headers)

        assert middleware is not None
        assert isinstance(middleware, HeaderAuthServerMiddleware)

    def test_start_call_padding_missing_base64(self) -> None:
        """Test start_call handles missing base64 padding."""
        # Create credentials that will need padding
        raw_creds = "testuser:testpass"
        b64_creds = base64.b64encode(raw_creds.encode()).decode()

        # Remove some padding to test auto-padding logic
        if b64_creds.endswith("=="):
            b64_creds = b64_creds[:-2]
        elif b64_creds.endswith("="):
            b64_creds = b64_creds[:-1]

        headers = {"authorization": [f"Basic {b64_creds}"]}
        info = Mock()

        middleware = self.factory.start_call(info, headers)
        assert middleware is not None


class TestBearerAuthServerMiddlewareFactory:
    """Test cases for BearerAuthServerMiddlewareFactory class."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.factory = BearerAuthServerMiddlewareFactory("test-secret")

    def test_initialization(self) -> None:
        """Test factory initialization."""
        assert self.factory.secret_key == "test-secret"

    def test_start_call_valid_bearer_token(self) -> None:
        """Test start_call with valid Bearer token."""
        # Create valid JWT token
        payload = {
            "username": "testuser",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, "test-secret", algorithm="HS256")
        headers = {"authorization": [f"Bearer {token}"]}

        info = Mock()
        middleware = self.factory.start_call(info, headers)

        # Should return None (no middleware needed for valid tokens)
        assert middleware is None

    def test_start_call_no_auth_header(self) -> None:
        """Test start_call with no authorization header."""
        headers = {}
        info = Mock()

        middleware = self.factory.start_call(info, headers)
        assert middleware is None

    def test_start_call_not_bearer_token(self) -> None:
        """Test start_call with non-Bearer authorization header."""
        credentials = base64.b64encode(b"user:pass").decode()
        headers = {"authorization": [f"Basic {credentials}"]}

        info = Mock()
        middleware = self.factory.start_call(info, headers)
        assert middleware is None

    def test_start_call_invalid_bearer_token(self) -> None:
        """Test start_call with invalid Bearer token."""
        headers = {"authorization": ["Bearer invalid-token"]}
        info = Mock()

        with pytest.raises(pf.FlightUnauthenticatedError, match="Invalid bearer token"):
            self.factory.start_call(info, headers)

    def test_start_call_expired_bearer_token(self) -> None:
        """Test start_call with expired Bearer token."""
        payload = {
            "username": "testuser",
            "exp": datetime.utcnow() - timedelta(hours=1),  # Expired
            "iat": datetime.utcnow() - timedelta(hours=2),
        }
        token = jwt.encode(payload, "test-secret", algorithm="HS256")
        headers = {"authorization": [f"Bearer {token}"]}

        info = Mock()
        with pytest.raises(pf.FlightUnauthenticatedError, match="Invalid bearer token"):
            self.factory.start_call(info, headers)

    def test_start_call_bytes_auth_header(self) -> None:
        """Test start_call with auth header as bytes."""
        payload = {
            "username": "testuser",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, "test-secret", algorithm="HS256")
        headers = {"authorization": [f"Bearer {token}".encode()]}

        info = Mock()
        middleware = self.factory.start_call(info, headers)
        assert middleware is None


class TestCreateSelfSignedCert:
    """Test cases for create_self_signed_cert function."""

    def test_create_self_signed_cert_default_params(self) -> None:
        """Test creating self-signed certificate with default parameters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = os.path.join(temp_dir, "test.crt")
            key_file = os.path.join(temp_dir, "test.key")

            result_cert, result_key = create_self_signed_cert(
                cert_file=cert_file, key_file=key_file
            )

            assert result_cert == cert_file
            assert result_key == key_file
            assert os.path.exists(cert_file)
            assert os.path.exists(key_file)

            # Verify certificate content
            with open(cert_file) as f:
                cert_content = f.read()
                assert "-----BEGIN CERTIFICATE-----" in cert_content
                assert "-----END CERTIFICATE-----" in cert_content

            # Verify key content
            with open(key_file) as f:
                key_content = f.read()
                assert "-----BEGIN PRIVATE KEY-----" in key_content
                assert "-----END PRIVATE KEY-----" in key_content

    def test_create_self_signed_cert_custom_hostname(self) -> None:
        """Test creating self-signed certificate with custom hostname."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = os.path.join(temp_dir, "custom.crt")
            key_file = os.path.join(temp_dir, "custom.key")

            create_self_signed_cert(
                hostname="example.com", cert_file=cert_file, key_file=key_file
            )

            assert os.path.exists(cert_file)
            assert os.path.exists(key_file)


class TestTLSCertificateLoader:
    """Test cases for TLSCertificateLoader class."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_tls_certificates_success(self) -> None:
        """Test successful TLS certificate loading."""
        cert_file = os.path.join(self.temp_dir, "server.crt")
        key_file = os.path.join(self.temp_dir, "server.key")

        # Create test certificate and key
        create_self_signed_cert(cert_file=cert_file, key_file=key_file)

        cert_pairs = TLSCertificateLoader.load_tls_certificates(cert_file, key_file)

        assert len(cert_pairs) == 1
        assert isinstance(cert_pairs[0], pf.CertKeyPair)

    def test_load_tls_certificates_cert_not_found(self) -> None:
        """Test TLS certificate loading with missing certificate."""
        cert_file = "/nonexistent/cert.pem"
        key_file = os.path.join(self.temp_dir, "key.pem")

        # Create only key file
        with open(key_file, "w") as f:
            f.write("dummy key content")

        with pytest.raises(FileNotFoundError, match="TLS certificate file not found"):
            TLSCertificateLoader.load_tls_certificates(cert_file, key_file)

    def test_load_tls_certificates_key_not_found(self) -> None:
        """Test TLS certificate loading with missing key."""
        cert_file = os.path.join(self.temp_dir, "cert.pem")
        key_file = "/nonexistent/key.pem"

        # Create only cert file
        with open(cert_file, "w") as f:
            f.write("dummy cert content")

        with pytest.raises(FileNotFoundError, match="TLS private key file not found"):
            TLSCertificateLoader.load_tls_certificates(cert_file, key_file)

    def test_load_mtls_ca_certificate_success(self) -> None:
        """Test successful mTLS CA certificate loading."""
        ca_file = os.path.join(self.temp_dir, "ca.crt")

        # Create test CA certificate (use self-signed cert for testing)
        create_self_signed_cert(
            cert_file=ca_file, key_file=os.path.join(self.temp_dir, "ca.key")
        )

        ca_content = TLSCertificateLoader.load_mtls_ca_certificate(ca_file)

        assert isinstance(ca_content, str)
        assert "-----BEGIN CERTIFICATE-----" in ca_content
        assert "-----END CERTIFICATE-----" in ca_content

    def test_load_mtls_ca_certificate_not_found(self) -> None:
        """Test mTLS CA certificate loading with missing file."""
        ca_file = "/nonexistent/ca.crt"

        with pytest.raises(
            FileNotFoundError, match="mTLS CA certificate file not found"
        ):
            TLSCertificateLoader.load_mtls_ca_certificate(ca_file)

    def test_configure_tls_options_tls_enabled(self) -> None:
        """Test TLS options configuration with TLS enabled."""
        cert_file = os.path.join(self.temp_dir, "server.crt")
        key_file = os.path.join(self.temp_dir, "server.key")

        create_self_signed_cert(cert_file=cert_file, key_file=key_file)

        config = Mock(spec=ServerConfig)
        config.is_tls_enabled = True
        config.is_mtls_enabled = False
        config.tls_cert = cert_file
        config.tls_key = key_file

        tls_certs, root_certs, verify_client = (
            TLSCertificateLoader.configure_tls_options(config)
        )

        assert tls_certs is not None
        assert len(tls_certs) == 1
        assert root_certs is None
        assert verify_client is False

    def test_configure_tls_options_mtls_enabled(self) -> None:
        """Test TLS options configuration with mTLS enabled."""
        cert_file = os.path.join(self.temp_dir, "server.crt")
        key_file = os.path.join(self.temp_dir, "server.key")
        ca_file = os.path.join(self.temp_dir, "ca.crt")

        create_self_signed_cert(cert_file=cert_file, key_file=key_file)
        create_self_signed_cert(
            cert_file=ca_file, key_file=os.path.join(self.temp_dir, "ca.key")
        )

        config = Mock(spec=ServerConfig)
        config.is_tls_enabled = True
        config.is_mtls_enabled = True
        config.tls_cert = cert_file
        config.tls_key = key_file
        config.mtls_ca = ca_file

        tls_certs, root_certs, verify_client = (
            TLSCertificateLoader.configure_tls_options(config)
        )

        assert tls_certs is not None
        assert len(tls_certs) == 1
        assert root_certs is not None
        assert verify_client is True

    def test_configure_tls_options_disabled(self) -> None:
        """Test TLS options configuration with TLS disabled."""
        config = Mock(spec=ServerConfig)
        config.is_tls_enabled = False
        config.is_mtls_enabled = False

        tls_certs, root_certs, verify_client = (
            TLSCertificateLoader.configure_tls_options(config)
        )

        assert tls_certs is None
        assert root_certs is None
        assert verify_client is False

    def test_configure_tls_options_mtls_without_tls(self) -> None:
        """Test TLS options configuration with mTLS enabled but TLS disabled."""
        config = Mock(spec=ServerConfig)
        config.is_tls_enabled = False
        config.is_mtls_enabled = True

        with pytest.raises(ValueError, match="mTLS requires TLS to be enabled"):
            TLSCertificateLoader.configure_tls_options(config)

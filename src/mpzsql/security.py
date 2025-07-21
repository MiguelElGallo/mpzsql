"""
Security and authentication module for MPZSQL.

This module provides TLS/mTLS support and authentication middleware
for JWT and Basic authentication.
"""

import base64
import json
import logging
import ssl
from pathlib import Path
from typing import Optional, Tuple, List

import jwt
import pyarrow.flight as pf
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

try:
    from mpzsql.config import ServerConfig
except ImportError:
    from config import ServerConfig

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """Authentication middleware for FlightSQL server."""

    def __init__(self, config: ServerConfig):
        """Initialize authentication middleware."""
        self.config = config
        self.username = config.username
        self.password = config.password
        self.secret_key = config.secret_key

    def authenticate(self, context: pf.ServerCallContext) -> None:
        """Authenticate a client request.

        This method is kept for backwards compatibility but is no longer used
        in the server implementation. Authentication is now handled via Flight
        server middleware which receives the incoming headers directly. The
        method simply returns when authentication is disabled.
        """
        if not self.config.is_auth_enabled:
            return

    def _authenticate_jwt(self, token: str) -> None:
        """Authenticate using JWT token."""
        try:
            # Decode and verify JWT token
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])

            # Check username if present in token
            token_username = payload.get("username")
            if token_username and token_username != self.username:
                raise pf.FlightUnauthenticatedError("Invalid username in token")

            logger.debug(f"JWT authentication successful for user: {token_username}")

        except jwt.ExpiredSignatureError:
            raise pf.FlightUnauthenticatedError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise pf.FlightUnauthenticatedError(f"Invalid token: {e}")
        except Exception as e:
            logger.error(f"JWT authentication error: {e}")
            raise pf.FlightUnauthenticatedError("Authentication failed")

    def _authenticate_basic(self, credentials: str) -> None:
        """Authenticate using Basic authentication."""
        try:
            # Decode base64 credentials
            decoded = base64.b64decode(credentials).decode("utf-8")
            username, password = decoded.split(":", 1)

            # Verify credentials
            if username != self.username or password != self.password:
                raise pf.FlightUnauthenticatedError("Invalid username or password")

            logger.debug(f"Basic authentication successful for user: {username}")

        except ValueError as e:
            raise pf.FlightUnauthenticatedError("Invalid basic authentication format")
        except Exception as e:
            logger.error(f"Basic authentication error: {e}")
            raise pf.FlightUnauthenticatedError("Authentication failed")

    def generate_jwt_token(
        self, username: Optional[str] = None, expiry_hours: int = 24
    ) -> str:
        """Generate a JWT token for a user."""
        import datetime

        payload = {
            "username": username or self.username,
            "iat": datetime.datetime.utcnow(),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=expiry_hours),
        }

        return jwt.encode(payload, self.secret_key, algorithm="HS256")


def setup_tls_context(
    cert_file: Optional[str] = None,
    key_file: Optional[str] = None,
    ca_file: Optional[str] = None,
) -> Optional[ssl.SSLContext]:
    """Set up TLS context for the server."""
    if not cert_file or not key_file:
        return None

    try:
        # Create SSL context
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

        # Load server certificate and key
        context.load_cert_chain(cert_file, key_file)

        # Configure for mTLS if CA file is provided
        if ca_file:
            context.load_verify_locations(ca_file)
            context.verify_mode = ssl.CERT_REQUIRED
            logger.info("mTLS enabled: client certificates will be verified")
        else:
            context.verify_mode = ssl.CERT_NONE
            logger.info("TLS enabled: server certificate only")

        # Security settings
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers(
            "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS"
        )

        logger.info(f"TLS context created with cert: {cert_file}")
        return context

    except Exception as e:
        logger.error(f"Failed to create TLS context: {e}")
        raise


class FlightAuthHandler(pf.ServerAuthHandler):
    """Flight authentication handler."""

    def __init__(self, auth_middleware: AuthMiddleware):
        """Initialize auth handler."""
        super().__init__()
        self.auth_middleware = auth_middleware

    def authenticate(self, outgoing, incoming):
        """Authenticate client during the Flight handshake."""
        try:
            auth_bytes = incoming.read()
            auth = pf.BasicAuth.deserialize(auth_bytes)
            username = auth.username.decode()
            password = auth.password.decode()
        except Exception:
            raise pf.FlightUnauthenticatedError("Invalid authentication data")

        if (
            username != self.auth_middleware.username
            or password != self.auth_middleware.password
        ):
            raise pf.FlightUnauthenticatedError("Invalid credentials")

        token = self.auth_middleware.generate_jwt_token(username)
        outgoing.write(token.encode())
        logger.info(f"Authentication successful for user: {username}")

    def is_valid(self, token):
        """Validate token for subsequent requests.

        Parameters
        ----------
        token : bytes | str
            The bearer token provided by the client.

        Returns
        -------
        str
            The authenticated username if the token is valid.

        Raises
        ------
        pf.FlightUnauthenticatedError
            If the token is invalid or the username does not match.
        """

        try:
            if isinstance(token, bytes):
                token = token.decode()

            if token.startswith("Bearer "):
                token = token[7:]

            payload = jwt.decode(
                token, self.auth_middleware.secret_key, algorithms=["HS256"]
            )

            username = payload.get("username")
            if username != self.auth_middleware.username:
                raise pf.FlightUnauthenticatedError("Invalid token user")

            return username

        except Exception as e:
            logger.warning(f"Token validation failed: {e}")
            raise pf.FlightUnauthenticatedError("Invalid token")


class NoOpAuthHandler(pf.ServerAuthHandler):
    """A no-op authentication handler used when only middleware handles auth."""

    def authenticate(self, outgoing, incoming):
        """Perform no authentication on handshake."""
        return

    def is_valid(self, token):
        """Always return an empty identity string."""
        return ""


class HeaderAuthServerMiddleware(pf.ServerMiddleware):
    """Middleware that returns a bearer token when Basic auth succeeds."""

    def __init__(self, username: str, secret_key: str):
        self.username = username
        self.secret_key = secret_key

    def sending_headers(self):
        token = jwt.encode(
            {"username": self.username}, self.secret_key, algorithm="HS256"
        )
        return {"authorization": f"Bearer {token}"}

    def call_completed(self, status):
        pass


class HeaderAuthServerMiddlewareFactory(pf.ServerMiddlewareFactory):
    """Factory that authenticates Basic auth headers."""

    def __init__(self, username: str, password: str, secret_key: str):
        self.username = username
        self.password = password
        self.secret_key = secret_key

    def start_call(self, info, headers):
        auth_vals = headers.get("authorization")
        logger.debug(f"HeaderAuthMiddleware: auth headers = {headers}")
        if not auth_vals:
            logger.debug("HeaderAuthMiddleware: No authorization header found")
            return None
        header = (
            auth_vals[0].decode() if isinstance(auth_vals[0], bytes) else auth_vals[0]
        )
        logger.debug(f"HeaderAuthMiddleware: auth header = {header}")
        if not header.startswith("Basic "):
            logger.debug(f"HeaderAuthMiddleware: Not Basic auth: {header[:20]}...")
            return None
        try:
            # Handle potential missing padding in base64
            b64_creds = header[6:]
            # Add padding if needed
            missing_padding = len(b64_creds) % 4
            if missing_padding:
                b64_creds += '=' * (4 - missing_padding)
            
            creds = base64.b64decode(b64_creds).decode()
            user, pwd = creds.split(":", 1)
            logger.debug(f"HeaderAuthMiddleware: parsed user = {user}")
        except Exception as e:
            logger.error(f"HeaderAuthMiddleware: Failed to parse basic auth header: {e}")
            logger.error(f"HeaderAuthMiddleware: header = {header}")
            raise pf.FlightUnauthenticatedError("Invalid basic auth header")
        if user == self.username and pwd == self.password:
            logger.info(f"HeaderAuthMiddleware: Authentication successful for user: {user}")
            return HeaderAuthServerMiddleware(user, self.secret_key)
        logger.warning(f"HeaderAuthMiddleware: Invalid credentials for user: {user}")
        raise pf.FlightUnauthenticatedError("Invalid credentials")


class BearerAuthServerMiddlewareFactory(pf.ServerMiddlewareFactory):
    """Factory that validates Bearer tokens on each call."""

    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    def start_call(self, info, headers):
        auth_vals = headers.get("authorization")
        if not auth_vals:
            return None
        header = (
            auth_vals[0].decode() if isinstance(auth_vals[0], bytes) else auth_vals[0]
        )
        if header.startswith("Bearer "):
            token = header[7:]
            try:
                jwt.decode(token, self.secret_key, algorithms=["HS256"])
            except Exception:
                raise pf.FlightUnauthenticatedError("Invalid bearer token")
        return None


def create_self_signed_cert(
    hostname: str = "localhost",
    cert_file: str = "server.crt",
    key_file: str = "server.key",
) -> Tuple[str, str]:
    """Create a self-signed certificate for testing purposes."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import datetime
    import ipaddress

    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Create certificate
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MPZSQL Server"),
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName(hostname),
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    # Write certificate file
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    # Write private key file
    with open(key_file, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    logger.info(f"Created self-signed certificate: {cert_file}, {key_file}")
    return cert_file, key_file


class TLSCertificateLoader:
    """TLS certificate loading utilities for FlightSQL server.
    
    This class provides functionality to load TLS certificates and keys
    for secure connections, following the same pattern as the C++ server.
    """
    
    @staticmethod
    def load_tls_certificates(cert_path: str, key_path: str) -> List[pf.CertKeyPair]:
        """Load TLS certificate and key files.
        
        Args:
            cert_path: Path to the TLS certificate file (PEM format)
            key_path: Path to the TLS private key file (PEM format)
            
        Returns:
            List of CertKeyPair objects for PyArrow Flight server
            
        Raises:
            FileNotFoundError: If certificate or key files don't exist
            ValueError: If files cannot be read or are invalid
        """
        cert_file = Path(cert_path)
        key_file = Path(key_path)
        
        # Validate files exist
        if not cert_file.exists():
            raise FileNotFoundError(f"TLS certificate file not found: {cert_path}")
        if not key_file.exists():
            raise FileNotFoundError(f"TLS private key file not found: {key_path}")
            
        try:
            # Read certificate file
            with open(cert_file, 'r') as f:
                cert_content = f.read()
                
            # Read key file  
            with open(key_file, 'r') as f:
                key_content = f.read()
                
            # Create CertKeyPair
            cert_key_pair = pf.CertKeyPair(cert_content.encode(), key_content.encode())
            
            logger.info(f"Successfully loaded TLS certificate: {cert_path}")
            logger.info(f"Successfully loaded TLS private key: {key_path}")
            
            return [cert_key_pair]
            
        except Exception as e:
            raise ValueError(f"Failed to load TLS certificates: {e}")
    
    @staticmethod 
    def load_mtls_ca_certificate(ca_cert_path: str) -> str:
        """Load mTLS CA certificate for client verification.
        
        Args:
            ca_cert_path: Path to the CA certificate file (PEM format)
            
        Returns:
            CA certificate content as string
            
        Raises:
            FileNotFoundError: If CA certificate file doesn't exist
            ValueError: If file cannot be read
        """
        ca_file = Path(ca_cert_path)
        
        if not ca_file.exists():
            raise FileNotFoundError(f"mTLS CA certificate file not found: {ca_cert_path}")
            
        try:
            with open(ca_file, 'r') as f:
                ca_content = f.read()
                
            logger.info(f"Successfully loaded mTLS CA certificate: {ca_cert_path}")
            return ca_content
            
        except Exception as e:
            raise ValueError(f"Failed to load mTLS CA certificate: {e}")
    
    @staticmethod
    def configure_tls_options(config: ServerConfig) -> Tuple[Optional[List[pf.CertKeyPair]], Optional[str], bool]:
        """Configure TLS options based on server configuration.
        
        Args:
            config: Server configuration object
            
        Returns:
            Tuple of (tls_certificates, root_certificates, verify_client)
            
        Raises:
            ValueError: If TLS configuration is invalid
        """
        tls_certificates = None
        root_certificates = None
        verify_client = False
        
        # Load TLS certificates if configured
        if config.is_tls_enabled:
            tls_certificates = TLSCertificateLoader.load_tls_certificates(
                config.tls_cert, config.tls_key
            )
            logger.info("TLS encryption enabled")
        else:
            logger.warning("TLS disabled - connections are not encrypted")
            
        # Load mTLS CA certificate if configured
        if config.is_mtls_enabled:
            if not config.is_tls_enabled:
                raise ValueError("mTLS requires TLS to be enabled")
                
            root_certificates = TLSCertificateLoader.load_mtls_ca_certificate(config.mtls_ca)
            verify_client = True
            logger.info("mTLS client verification enabled")
            
        return tls_certificates, root_certificates, verify_client

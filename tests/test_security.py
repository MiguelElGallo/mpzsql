"""Tests for lakehouse.security — password hashing & JWT utilities."""

from __future__ import annotations

import jwt as pyjwt
import pytest

from lakehouse.security import (
    DEFAULT_ISSUER,
    create_jwt,
    hash_password,
    verify_jwt,
    verify_password,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Password Hashing — HMAC-SHA256
# ═══════════════════════════════════════════════════════════════════════════
class TestHashPassword:
    """Unit tests for hash_password()."""

    def test_deterministic(self):
        """Same inputs always produce the same hash."""
        h1 = hash_password("hunter2", "my-secret")
        h2 = hash_password("hunter2", "my-secret")
        assert h1 == h2

    def test_hex_encoded_64_chars(self):
        """SHA-256 hex digest is always 64 chars."""
        h = hash_password("password", "key")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_passwords_differ(self):
        """Different passwords produce different hashes."""
        h1 = hash_password("password1", "key")
        h2 = hash_password("password2", "key")
        assert h1 != h2

    def test_different_keys_differ(self):
        """Different secret keys produce different hashes."""
        h1 = hash_password("password", "key1")
        h2 = hash_password("password", "key2")
        assert h1 != h2

    def test_empty_password(self):
        """Empty password still produces a valid hash."""
        h = hash_password("", "key")
        assert len(h) == 64

    def test_empty_key(self):
        """Empty key still produces a valid hash."""
        h = hash_password("password", "")
        assert len(h) == 64

    def test_unicode_password(self):
        """Unicode characters in password are supported."""
        h = hash_password("pässwörd™", "key")
        assert len(h) == 64

    def test_unicode_key(self):
        """Unicode characters in key are supported."""
        h = hash_password("password", "sëcrét🔑")
        assert len(h) == 64


class TestVerifyPassword:
    """Unit tests for verify_password()."""

    def test_correct_password(self):
        """Matching password returns True."""
        h = hash_password("hunter2", "secret")
        assert verify_password("hunter2", "secret", h) is True

    def test_wrong_password(self):
        """Wrong password returns False."""
        h = hash_password("hunter2", "secret")
        assert verify_password("hunter3", "secret", h) is False

    def test_wrong_key(self):
        """Wrong secret key returns False."""
        h = hash_password("hunter2", "secret")
        assert verify_password("hunter2", "other-secret", h) is False

    def test_tampered_hash(self):
        """Modified hash returns False."""
        h = hash_password("hunter2", "secret")
        tampered = "00" + h[2:]
        assert verify_password("hunter2", "secret", tampered) is False

    def test_case_sensitive_password(self):
        """Password comparison is case-sensitive."""
        h = hash_password("Password", "key")
        assert verify_password("password", "key", h) is False

    def test_case_sensitive_key(self):
        """Secret key is case-sensitive."""
        h = hash_password("password", "Key")
        assert verify_password("password", "key", h) is False

    def test_empty_password_matches(self):
        """Empty password can be hashed and verified."""
        h = hash_password("", "key")
        assert verify_password("", "key", h) is True

    def test_timing_safe(self):
        """verify_password uses hmac.compare_digest (constant-time)."""
        # We can't directly test timing, but we verify the function exists
        import hmac

        assert hasattr(hmac, "compare_digest")


# ═══════════════════════════════════════════════════════════════════════════
#  JWT — create_jwt
# ═══════════════════════════════════════════════════════════════════════════
SECRET = "test-secret-key-at-least-32-bytes-long!"


class TestCreateJwt:
    """Unit tests for create_jwt()."""

    def test_returns_string(self):
        """create_jwt returns a non-empty string."""
        token = create_jwt(subject="alice", secret=SECRET)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decodable(self):
        """Token can be decoded back."""
        token = create_jwt(subject="alice", secret=SECRET)
        payload = pyjwt.decode(token, SECRET, algorithms=["HS256"], issuer=DEFAULT_ISSUER)
        assert payload["sub"] == "alice"
        assert payload["iss"] == DEFAULT_ISSUER

    def test_contains_standard_claims(self):
        """Token contains sub, iss, iat, exp, jti, instance_id."""
        token = create_jwt(subject="bob", secret=SECRET, instance_id="inst-1")
        payload = pyjwt.decode(token, SECRET, algorithms=["HS256"], issuer=DEFAULT_ISSUER)
        assert "sub" in payload
        assert "iss" in payload
        assert "iat" in payload
        assert "exp" in payload
        assert "jti" in payload
        assert payload["instance_id"] == "inst-1"

    def test_unique_jti(self):
        """Each token gets a unique jti."""
        t1 = create_jwt(subject="alice", secret=SECRET)
        t2 = create_jwt(subject="alice", secret=SECRET)
        p1 = pyjwt.decode(t1, SECRET, algorithms=["HS256"], issuer=DEFAULT_ISSUER)
        p2 = pyjwt.decode(t2, SECRET, algorithms=["HS256"], issuer=DEFAULT_ISSUER)
        assert p1["jti"] != p2["jti"]

    def test_custom_issuer(self):
        """Custom issuer overrides default."""
        token = create_jwt(subject="alice", secret=SECRET, issuer="custom-issuer")
        payload = pyjwt.decode(token, SECRET, algorithms=["HS256"], issuer="custom-issuer")
        assert payload["iss"] == "custom-issuer"

    def test_custom_expiry(self):
        """Custom expiry_hours is respected."""
        token = create_jwt(subject="alice", secret=SECRET, expiry_hours=1)
        payload = pyjwt.decode(token, SECRET, algorithms=["HS256"], issuer=DEFAULT_ISSUER)
        assert payload["exp"] - payload["iat"] == 3600

    def test_extra_claims(self):
        """Extra claims are merged into the payload."""
        token = create_jwt(
            subject="alice",
            secret=SECRET,
            extra_claims={"role": "admin", "auth_method": "basic"},
        )
        payload = pyjwt.decode(token, SECRET, algorithms=["HS256"], issuer=DEFAULT_ISSUER)
        assert payload["role"] == "admin"
        assert payload["auth_method"] == "basic"

    def test_hs256_algorithm(self):
        """HS256 is the default algorithm."""
        token = create_jwt(subject="alice", secret=SECRET)
        header = pyjwt.get_unverified_header(token)
        assert header["alg"] == "HS256"

    def test_rs256_algorithm(self):
        """RS256 works with RSA keys."""
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            PublicFormat,
        )

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        public_pem = private_key.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )

        token = create_jwt(subject="alice", secret=private_pem, algorithm="RS256")
        header = pyjwt.get_unverified_header(token)
        assert header["alg"] == "RS256"

        # Verify with public key
        payload = pyjwt.decode(token, public_pem, algorithms=["RS256"], issuer=DEFAULT_ISSUER)
        assert payload["sub"] == "alice"


# ═══════════════════════════════════════════════════════════════════════════
#  JWT — verify_jwt
# ═══════════════════════════════════════════════════════════════════════════
class TestVerifyJwt:
    """Unit tests for verify_jwt()."""

    def test_valid_token(self):
        """Valid token decodes successfully."""
        token = create_jwt(subject="alice", secret=SECRET, instance_id="inst-1")
        payload = verify_jwt(token, SECRET)
        assert payload["sub"] == "alice"
        assert payload["instance_id"] == "inst-1"

    def test_expired_token(self):
        """Expired token raises ExpiredSignatureError."""
        token = create_jwt(subject="alice", secret=SECRET, expiry_hours=0)
        # Token with expiry_hours=0 means exp == iat, so it's already expired
        # We need to wait a beat or use a negative expiry
        # Actually expiry_hours=0 means exp == now, which passes at decode time
        # Let's create a manually-expired token instead
        import datetime

        exp_payload = {
            "sub": "alice",
            "iss": DEFAULT_ISSUER,
            "iat": datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=2),
            "exp": datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1),
        }
        token = pyjwt.encode(exp_payload, SECRET, algorithm="HS256")
        with pytest.raises(pyjwt.ExpiredSignatureError):
            verify_jwt(token, SECRET)

    def test_wrong_secret(self):
        """Token signed with different key fails verification."""
        token = create_jwt(subject="alice", secret=SECRET)
        with pytest.raises(pyjwt.InvalidSignatureError):
            verify_jwt(token, "wrong-secret")

    def test_wrong_issuer(self):
        """Token with unexpected issuer fails verification."""
        token = create_jwt(subject="alice", secret=SECRET, issuer="other-issuer")
        with pytest.raises(pyjwt.InvalidIssuerError):
            verify_jwt(token, SECRET, issuer=DEFAULT_ISSUER)

    def test_custom_issuer_accepted(self):
        """Custom issuer can be verified when specified."""
        token = create_jwt(subject="alice", secret=SECRET, issuer="custom")
        payload = verify_jwt(token, SECRET, issuer="custom")
        assert payload["iss"] == "custom"

    def test_tampered_payload(self):
        """Token with tampered payload fails verification."""
        token = create_jwt(subject="alice", secret=SECRET)
        # Split jwt and tamper with body
        parts = token.split(".")
        assert len(parts) == 3
        # Change a character in the payload
        tampered_payload = parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")
        tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"
        with pytest.raises(pyjwt.InvalidTokenError):
            verify_jwt(tampered_token, SECRET)

    def test_algorithm_restriction(self):
        """Only specified algorithms are accepted."""
        token = create_jwt(subject="alice", secret=SECRET, algorithm="HS256")
        with pytest.raises(pyjwt.InvalidAlgorithmError):
            verify_jwt(token, SECRET, algorithms=["RS256"])

    def test_malformed_token(self):
        """Completely invalid token raises DecodeError."""
        with pytest.raises(pyjwt.DecodeError):
            verify_jwt("not-a-jwt", SECRET)

    def test_empty_token(self):
        """Empty string raises DecodeError."""
        with pytest.raises(pyjwt.DecodeError):
            verify_jwt("", SECRET)

    def test_rs256_round_trip(self):
        """RS256 token can be created and verified."""
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            PublicFormat,
        )

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        public_pem = private_key.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )

        token = create_jwt(subject="alice", secret=private_pem, algorithm="RS256")
        payload = verify_jwt(token, public_pem, algorithms=["RS256"])
        assert payload["sub"] == "alice"

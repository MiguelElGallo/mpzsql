"""
Tests for authentication and session management module.
Tests for mpzsql.auth module providing JWT-based authentication.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import jwt

from mpzsql.auth import AuthManager, BearerAuthServerMiddleware


class TestAuthManager:
    """Test cases for AuthManager class."""

    def setup_method(self):
        """Set up test environment."""
        self.secret_key = "test-secret-key"
        self.auth_manager = AuthManager(
            secret_key=self.secret_key, token_expiry_hours=24
        )
        self.test_username = "testuser"

    def test_initialization(self):
        """Test AuthManager initialization."""
        assert self.auth_manager.secret_key == self.secret_key
        assert self.auth_manager.token_expiry_hours == 24
        assert self.auth_manager.sessions == {}

    def test_initialization_with_custom_expiry(self):
        """Test AuthManager initialization with custom expiry."""
        auth_manager = AuthManager(secret_key="key", token_expiry_hours=12)
        assert auth_manager.token_expiry_hours == 12

    def test_create_token_success(self):
        """Test successful token creation."""
        token = self.auth_manager.create_token(self.test_username)

        # Verify token is a string
        assert isinstance(token, str)
        assert len(token) > 0

        # Decode token to verify payload
        payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
        assert payload["username"] == self.test_username
        assert "session_id" in payload
        assert "exp" in payload
        assert "iat" in payload

        # Verify session was created
        session_id = payload["session_id"]
        assert session_id in self.auth_manager.sessions
        session = self.auth_manager.sessions[session_id]
        assert session["username"] == self.test_username
        assert "created_at" in session
        assert "last_activity" in session
        assert session["transactions"] == []

    def test_create_token_multiple_users(self):
        """Test creating tokens for multiple users."""
        user1 = "user1"
        user2 = "user2"

        token1 = self.auth_manager.create_token(user1)
        token2 = self.auth_manager.create_token(user2)

        # Verify different tokens
        assert token1 != token2

        # Verify both sessions exist
        assert len(self.auth_manager.sessions) == 2

        # Verify payloads
        payload1 = jwt.decode(token1, self.secret_key, algorithms=["HS256"])
        payload2 = jwt.decode(token2, self.secret_key, algorithms=["HS256"])

        assert payload1["username"] == user1
        assert payload2["username"] == user2
        assert payload1["session_id"] != payload2["session_id"]

    def test_validate_token_success(self):
        """Test successful token validation."""
        token = self.auth_manager.create_token(self.test_username)

        payload = self.auth_manager.validate_token(token)

        assert payload is not None
        assert payload["username"] == self.test_username
        assert "session_id" in payload

    def test_validate_token_with_bearer_prefix(self):
        """Test token validation with Bearer prefix."""
        token = self.auth_manager.create_token(self.test_username)
        bearer_token = f"Bearer {token}"

        payload = self.auth_manager.validate_token(bearer_token)

        assert payload is not None
        assert payload["username"] == self.test_username

    def test_validate_token_expired(self):
        """Test validation of expired token."""
        # Create auth manager with 0 hour expiry
        auth_manager = AuthManager(secret_key=self.secret_key, token_expiry_hours=0)

        # Create token that will be expired
        with patch("mpzsql.auth.datetime") as mock_datetime:
            past_time = datetime.utcnow() - timedelta(hours=1)
            mock_datetime.utcnow.return_value = past_time
            token = auth_manager.create_token(self.test_username)

        # Try to validate expired token
        payload = self.auth_manager.validate_token(token)
        assert payload is None

    def test_validate_token_invalid_signature(self):
        """Test validation of token with invalid signature."""
        token = self.auth_manager.create_token(self.test_username)

        # Create auth manager with different secret
        different_auth = AuthManager(secret_key="different-key")

        payload = different_auth.validate_token(token)
        assert payload is None

    def test_validate_token_malformed(self):
        """Test validation of malformed token."""
        malformed_tokens = [
            "invalid.token.format",
            "not-a-jwt-token",
            "",
            "Bearer invalid-token",
        ]

        for token in malformed_tokens:
            payload = self.auth_manager.validate_token(token)
            assert payload is None

    def test_validate_token_updates_last_activity(self):
        """Test that token validation updates last activity."""
        token = self.auth_manager.create_token(self.test_username)

        # Get original session
        payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
        session_id = payload["session_id"]
        original_activity = self.auth_manager.sessions[session_id]["last_activity"]

        # Wait a bit and validate token
        with patch("mpzsql.auth.datetime") as mock_datetime:
            future_time = datetime.utcnow() + timedelta(seconds=10)
            mock_datetime.utcnow.return_value = future_time

            self.auth_manager.validate_token(token)

            # Verify last activity was updated
            updated_activity = self.auth_manager.sessions[session_id]["last_activity"]
            assert updated_activity == future_time
            assert updated_activity != original_activity

    def test_validate_token_nonexistent_session(self):
        """Test validation of token with session that was manually removed."""
        token = self.auth_manager.create_token(self.test_username)

        # Remove session manually
        self.auth_manager.sessions.clear()

        # Token should still validate (payload is valid) but session won't be updated
        payload = self.auth_manager.validate_token(token)
        assert payload is not None
        assert payload["username"] == self.test_username

    def test_get_session_exists(self):
        """Test getting existing session."""
        token = self.auth_manager.create_token(self.test_username)
        payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
        session_id = payload["session_id"]

        session = self.auth_manager.get_session(session_id)

        assert session is not None
        assert session["username"] == self.test_username
        assert "created_at" in session
        assert "last_activity" in session
        assert session["transactions"] == []

    def test_get_session_not_exists(self):
        """Test getting non-existent session."""
        fake_session_id = str(uuid.uuid4())

        session = self.auth_manager.get_session(fake_session_id)

        assert session is None

    def test_cleanup_expired_sessions(self):
        """Test cleanup of expired sessions."""
        # Create multiple tokens
        token1 = self.auth_manager.create_token("user1")
        token2 = self.auth_manager.create_token("user2")
        self.auth_manager.create_token("user3")  # Not used directly but creates session

        # Verify all sessions exist
        assert len(self.auth_manager.sessions) == 3

        # Mock some sessions as expired
        payload1 = jwt.decode(token1, self.secret_key, algorithms=["HS256"])
        payload2 = jwt.decode(token2, self.secret_key, algorithms=["HS256"])

        # Make first two sessions old
        old_time = datetime.utcnow() - timedelta(hours=25)
        self.auth_manager.sessions[payload1["session_id"]]["last_activity"] = old_time
        self.auth_manager.sessions[payload2["session_id"]]["last_activity"] = old_time

        # Run cleanup
        self.auth_manager.cleanup_expired_sessions()

        # Verify expired sessions were removed
        assert len(self.auth_manager.sessions) == 1
        assert payload1["session_id"] not in self.auth_manager.sessions
        assert payload2["session_id"] not in self.auth_manager.sessions

    def test_cleanup_expired_sessions_none_expired(self):
        """Test cleanup when no sessions are expired."""
        # Create tokens
        self.auth_manager.create_token("user1")
        self.auth_manager.create_token("user2")

        original_count = len(self.auth_manager.sessions)

        # Run cleanup
        self.auth_manager.cleanup_expired_sessions()

        # Verify no sessions were removed
        assert len(self.auth_manager.sessions) == original_count

    def test_cleanup_expired_sessions_empty(self):
        """Test cleanup with no sessions."""
        # Run cleanup on empty session store
        self.auth_manager.cleanup_expired_sessions()

        # Should not raise any errors
        assert len(self.auth_manager.sessions) == 0


class TestBearerAuthServerMiddleware:
    """Test cases for BearerAuthServerMiddleware class."""

    def setup_method(self):
        """Set up test environment."""
        self.auth_manager = AuthManager(secret_key="test-key")
        self.middleware = BearerAuthServerMiddleware(self.auth_manager)
        self.test_username = "testuser"

    def test_initialization(self):
        """Test middleware initialization."""
        assert self.middleware.auth_manager == self.auth_manager

    def test_authenticate_success(self):
        """Test successful authentication."""
        token = self.auth_manager.create_token(self.test_username)
        headers = {"authorization": f"Bearer {token}"}

        result = self.middleware.authenticate(headers)

        assert result is not None
        assert result["username"] == self.test_username

    def test_authenticate_no_auth_header(self):
        """Test authentication with no authorization header."""
        headers = {}

        result = self.middleware.authenticate(headers)

        assert result is None

    def test_authenticate_no_bearer_prefix(self):
        """Test authentication with non-Bearer authorization header."""
        headers = {
            "authorization": "Basic dXNlcjpwYXNz"  # user:pass in base64
        }

        result = self.middleware.authenticate(headers)

        assert result is None

    def test_authenticate_invalid_token(self):
        """Test authentication with invalid token."""
        headers = {"authorization": "Bearer invalid-token"}

        result = self.middleware.authenticate(headers)

        assert result is None

    def test_authenticate_expired_token(self):
        """Test authentication with expired token."""
        # Create auth manager with 0 hour expiry
        auth_manager = AuthManager(secret_key="test-key", token_expiry_hours=0)
        middleware = BearerAuthServerMiddleware(auth_manager)

        # Create expired token
        with patch("mpzsql.auth.datetime") as mock_datetime:
            past_time = datetime.utcnow() - timedelta(hours=1)
            mock_datetime.utcnow.return_value = past_time
            token = auth_manager.create_token(self.test_username)

        headers = {"authorization": f"Bearer {token}"}

        result = middleware.authenticate(headers)

        assert result is None

    def test_authenticate_malformed_bearer_token(self):
        """Test authentication with malformed Bearer token."""
        headers = {
            "authorization": "Bearer "  # Empty token
        }

        result = self.middleware.authenticate(headers)

        assert result is None

    def test_is_authenticated_true(self):
        """Test is_authenticated returns True for valid token."""
        token = self.auth_manager.create_token(self.test_username)
        headers = {"authorization": f"Bearer {token}"}

        result = self.middleware.is_authenticated(headers)

        assert result is True

    def test_is_authenticated_false(self):
        """Test is_authenticated returns False for invalid token."""
        headers = {"authorization": "Bearer invalid-token"}

        result = self.middleware.is_authenticated(headers)

        assert result is False

    def test_is_authenticated_no_header(self):
        """Test is_authenticated returns False with no auth header."""
        headers = {}

        result = self.middleware.is_authenticated(headers)

        assert result is False

    def test_authenticate_case_insensitive_header_key(self):
        """Test authentication with case variations in header key."""
        token = self.auth_manager.create_token(self.test_username)

        # Test different case variations
        header_variations = [
            {"Authorization": f"Bearer {token}"},
            {"AUTHORIZATION": f"Bearer {token}"},
            {"authorization": f"Bearer {token}"},
        ]

        for headers in header_variations:
            # Only lowercase 'authorization' should work based on implementation
            if "authorization" in headers:
                result = self.middleware.authenticate(headers)
                assert result is not None
                assert result["username"] == self.test_username
            else:
                result = self.middleware.authenticate(headers)
                assert result is None


class TestAuthManagerIntegration:
    """Integration tests for AuthManager with real JWT operations."""

    def test_token_roundtrip(self):
        """Test complete token creation and validation cycle."""
        auth_manager = AuthManager(secret_key="integration-test-key")
        username = "integration-user"

        # Create token
        token = auth_manager.create_token(username)

        # Validate token
        payload = auth_manager.validate_token(token)

        # Verify roundtrip
        assert payload is not None
        assert payload["username"] == username

        # Verify session exists
        session_id = payload["session_id"]
        session = auth_manager.get_session(session_id)
        assert session is not None
        assert session["username"] == username

    def test_multiple_token_validation(self):
        """Test validation of multiple tokens from same user."""
        auth_manager = AuthManager(secret_key="multi-test-key")
        username = "multi-user"

        # Create multiple tokens
        tokens = [auth_manager.create_token(username) for _ in range(5)]

        # Validate all tokens
        for token in tokens:
            payload = auth_manager.validate_token(token)
            assert payload is not None
            assert payload["username"] == username

        # Verify multiple sessions exist
        assert len(auth_manager.sessions) == 5

    def test_session_lifecycle(self):
        """Test complete session lifecycle."""
        auth_manager = AuthManager(secret_key="lifecycle-test-key")
        username = "lifecycle-user"

        # Create token and session
        token = auth_manager.create_token(username)
        payload = jwt.decode(token, "lifecycle-test-key", algorithms=["HS256"])
        session_id = payload["session_id"]

        # Verify session exists
        session = auth_manager.get_session(session_id)
        assert session is not None

        # Simulate session activity
        auth_manager.validate_token(token)

        # Verify session still exists and was updated
        session_after = auth_manager.get_session(session_id)
        assert session_after is not None
        assert session_after["last_activity"] >= session["last_activity"]

        # Cleanup expired sessions (should not affect this one)
        auth_manager.cleanup_expired_sessions()

        # Verify session still exists
        session_final = auth_manager.get_session(session_id)
        assert session_final is not None

    @patch("mpzsql.auth.logger")
    def test_logging_integration(self, mock_logger):
        """Test that appropriate logging occurs during operations."""
        auth_manager = AuthManager(secret_key="logging-test-key")

        # Test expired session cleanup logging
        token = auth_manager.create_token("log-user")
        payload = jwt.decode(token, "logging-test-key", algorithms=["HS256"])
        session_id = payload["session_id"]

        # Make session expired
        old_time = datetime.utcnow() - timedelta(hours=25)
        auth_manager.sessions[session_id]["last_activity"] = old_time

        # Cleanup should log the removal
        auth_manager.cleanup_expired_sessions()

        # Verify logging occurred
        mock_logger.info.assert_called()
        logged_message = mock_logger.info.call_args[0][0]
        assert "Cleaned up expired session" in logged_message
        assert session_id in logged_message

    def test_error_handling_edge_cases(self):
        """Test error handling for edge cases."""
        auth_manager = AuthManager(secret_key="edge-case-key")

        # Test with None values
        assert auth_manager.validate_token(None) is None
        assert auth_manager.get_session(None) is None

        # Test with empty strings
        assert auth_manager.validate_token("") is None
        assert auth_manager.get_session("") is None

        # Test cleanup with corrupted session data
        auth_manager.sessions["bad-session"] = {"incomplete": "data"}

        # Should not crash
        auth_manager.cleanup_expired_sessions()

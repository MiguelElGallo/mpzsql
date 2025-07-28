"""
Comprehensive test suite for authentication and session management.

This module tests the authentication functionality including:
- AuthManager JWT token creation and validation
- Session management and cleanup
- BearerAuthServerMiddleware authentication
- Error handling and security scenarios
"""

import pytest
import jwt
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import logging

from mpzsql.auth import (
    AuthManager,
    BearerAuthServerMiddleware
)


class TestAuthManager:
    """Test AuthManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.secret_key = "test-secret-key-123"
        self.token_expiry_hours = 2
        self.auth_manager = AuthManager(
            secret_key=self.secret_key,
            token_expiry_hours=self.token_expiry_hours
        )
    
    def test_auth_manager_initialization(self):
        """Test auth manager initialization."""
        assert self.auth_manager.secret_key == self.secret_key
        assert self.auth_manager.token_expiry_hours == self.token_expiry_hours
        assert self.auth_manager.sessions == {}
    
    def test_auth_manager_default_initialization(self):
        """Test auth manager with default parameters."""
        manager = AuthManager()
        assert manager.secret_key == "your-secret-key"
        assert manager.token_expiry_hours == 24
        assert manager.sessions == {}
    
    @patch('mpzsql.auth.uuid.uuid4')
    def test_create_token(self, mock_uuid):
        """Test JWT token creation."""
        # Setup mocks
        mock_session = Mock()
        mock_session.hex = "test-session-id-123"
        mock_uuid.return_value = mock_session
        
        username = "testuser"
        token = self.auth_manager.create_token(username)
        
        # Verify token was created
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Decode and verify token contents
        payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
        assert payload['username'] == username
        assert payload['session_id'] == str(mock_session)
        assert 'exp' in payload
        assert 'iat' in payload
        
        # Verify session was stored
        session_id = str(mock_session)
        assert session_id in self.auth_manager.sessions
        session = self.auth_manager.sessions[session_id]
        assert session['username'] == username
        assert 'created_at' in session
        assert 'last_activity' in session
        assert session['transactions'] == []
    
    def test_validate_token_valid(self):
        """Test validation of valid token."""
        username = "testuser"
        token = self.auth_manager.create_token(username)
        
        payload = self.auth_manager.validate_token(token)
        
        assert payload is not None
        assert payload['username'] == username
        assert 'session_id' in payload
        assert 'exp' in payload
        assert 'iat' in payload
    
    def test_validate_token_with_bearer_prefix(self):
        """Test validation of token with Bearer prefix."""
        username = "testuser"
        token = self.auth_manager.create_token(username)
        bearer_token = f"Bearer {token}"
        
        payload = self.auth_manager.validate_token(bearer_token)
        
        assert payload is not None
        assert payload['username'] == username
    
    def test_validate_token_none(self):
        """Test validation of None token."""
        payload = self.auth_manager.validate_token(None)
        assert payload is None
    
    def test_validate_token_empty_string(self):
        """Test validation of empty token."""
        payload = self.auth_manager.validate_token("")
        assert payload is None
    
    def test_validate_token_invalid_format(self):
        """Test validation of invalid token format."""
        with patch('mpzsql.auth.logger') as mock_logger:
            payload = self.auth_manager.validate_token("invalid-token")
        
        assert payload is None
        mock_logger.warning.assert_called_once()
        assert "Invalid token" in mock_logger.warning.call_args[0][0]
    
    def test_validate_token_expired(self):
        """Test validation of expired token."""
        # Create token with current time
        username = "testuser"
        token = self.auth_manager.create_token(username)
        
        # Mock the token to be expired by patching jwt.decode to raise ExpiredSignatureError
        with patch('mpzsql.auth.jwt.decode') as mock_decode:
            mock_decode.side_effect = jwt.ExpiredSignatureError("Token has expired")
            
            with patch('mpzsql.auth.logger') as mock_logger:
                payload = self.auth_manager.validate_token(token)
        
        assert payload is None
        mock_logger.warning.assert_called_once()
        assert "Token has expired" in mock_logger.warning.call_args[0][0]
    
    def test_validate_token_wrong_secret(self):
        """Test validation with wrong secret key."""
        username = "testuser"
        token = self.auth_manager.create_token(username)
        
        # Create another manager with different secret
        wrong_manager = AuthManager(secret_key="wrong-secret")
        
        with patch('mpzsql.auth.logger') as mock_logger:
            payload = wrong_manager.validate_token(token)
        
        assert payload is None
        mock_logger.warning.assert_called_once()
        assert "Invalid token" in mock_logger.warning.call_args[0][0]
    
    def test_validate_token_updates_last_activity(self):
        """Test that token validation updates last activity."""
        username = "testuser"
        token = self.auth_manager.create_token(username)
        
        # Get the session to check original last_activity
        payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
        session_id = payload['session_id']
        original_activity = self.auth_manager.sessions[session_id]['last_activity']
        
        # Mock current time to be later
        with patch('mpzsql.auth.datetime') as mock_datetime:
            later_time = datetime(2023, 1, 1, 13, 0, 0)
            mock_datetime.utcnow.return_value = later_time
            
            validated_payload = self.auth_manager.validate_token(token)
        
        assert validated_payload is not None
        assert self.auth_manager.sessions[session_id]['last_activity'] == later_time
        assert self.auth_manager.sessions[session_id]['last_activity'] != original_activity
    
    def test_validate_token_session_not_found(self):
        """Test validation when session doesn't exist."""
        # Create a valid token manually without creating session
        payload = {
            'username': 'testuser',
            'session_id': 'non-existent-session',
            'exp': datetime.utcnow() + timedelta(hours=1),
            'iat': datetime.utcnow()
        }
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        
        validated_payload = self.auth_manager.validate_token(token)
        
        # Should still return payload even if session doesn't exist
        assert validated_payload is not None
        assert validated_payload['username'] == 'testuser'
    
    def test_get_session_exists(self):
        """Test getting existing session."""
        username = "testuser"
        token = self.auth_manager.create_token(username)
        
        # Get session ID from token
        payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
        session_id = payload['session_id']
        
        session = self.auth_manager.get_session(session_id)
        
        assert session is not None
        assert session['username'] == username
        assert 'created_at' in session
        assert 'last_activity' in session
        assert 'transactions' in session
    
    def test_get_session_not_exists(self):
        """Test getting non-existent session."""
        session = self.auth_manager.get_session("non-existent-session")
        assert session is None
    
    def test_cleanup_expired_sessions(self):
        """Test cleanup of expired sessions."""
        # Create sessions
        username1 = "user1"
        username2 = "user2" 
        username3 = "user3"
        
        token1 = self.auth_manager.create_token(username1)
        token2 = self.auth_manager.create_token(username2)
        token3 = self.auth_manager.create_token(username3)
        
        # Get session IDs
        payload1 = jwt.decode(token1, self.secret_key, algorithms=['HS256'])
        payload2 = jwt.decode(token2, self.secret_key, algorithms=['HS256'])
        payload3 = jwt.decode(token3, self.secret_key, algorithms=['HS256'])
        
        session_id1 = payload1['session_id']
        session_id2 = payload2['session_id']
        session_id3 = payload3['session_id']
        
        # Make some sessions appear expired by setting old last_activity
        expired_time = datetime.utcnow() - timedelta(hours=self.token_expiry_hours + 1)
        recent_time = datetime.utcnow() - timedelta(minutes=30)
        
        self.auth_manager.sessions[session_id1]['last_activity'] = expired_time
        self.auth_manager.sessions[session_id2]['last_activity'] = recent_time
        self.auth_manager.sessions[session_id3]['last_activity'] = expired_time
        
        with patch('mpzsql.auth.logger') as mock_logger:
            self.auth_manager.cleanup_expired_sessions()
        
        # Check that expired sessions were removed
        assert session_id1 not in self.auth_manager.sessions
        assert session_id3 not in self.auth_manager.sessions
        assert session_id2 in self.auth_manager.sessions  # Recent should remain
        
        # Check logging
        assert mock_logger.info.call_count == 2
    
    def test_cleanup_expired_sessions_corrupted_data(self):
        """Test cleanup handles corrupted session data."""
        # Create a normal session
        username = "testuser"
        token = self.auth_manager.create_token(username)
        payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
        session_id = payload['session_id']
        
        # Add corrupted session data that will cause TypeError when subtracting None
        corrupted_session_id = "corrupted-session"
        self.auth_manager.sessions[corrupted_session_id] = {
            'username': 'corrupted',
            'last_activity': "not-a-datetime"  # This will cause TypeError when subtracting timedelta
        }
        
        # Add another corrupted session that will cause AttributeError
        corrupted_session_id2 = "corrupted-session-2"
        self.auth_manager.sessions[corrupted_session_id2] = {
            'username': 'corrupted2',
            'last_activity': Mock()  # Mock object without proper datetime operations
        }
        # Make the mock raise TypeError when used in datetime operations
        self.auth_manager.sessions[corrupted_session_id2]['last_activity'].__rsub__ = Mock(side_effect=TypeError("unsupported operand type"))
        
        initial_session_count = len(self.auth_manager.sessions)
        
        with patch('mpzsql.auth.logger') as mock_logger:
            self.auth_manager.cleanup_expired_sessions()
        
        # Corrupted sessions should be removed due to exceptions
        assert corrupted_session_id not in self.auth_manager.sessions
        assert corrupted_session_id2 not in self.auth_manager.sessions
        assert session_id in self.auth_manager.sessions  # Valid session remains
        
        # Should have fewer sessions now
        assert len(self.auth_manager.sessions) < initial_session_count
        
        # Check that cleanup logged the removal of corrupted sessions
        assert mock_logger.info.call_count == 2
    
    def test_cleanup_expired_sessions_no_expired(self):
        """Test cleanup when no sessions are expired."""
        username = "testuser"
        self.auth_manager.create_token(username)
        
        with patch('mpzsql.auth.logger') as mock_logger:
            self.auth_manager.cleanup_expired_sessions()
        
        assert len(self.auth_manager.sessions) == 1
        mock_logger.info.assert_not_called()


class TestBearerAuthServerMiddleware:
    """Test BearerAuthServerMiddleware class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.auth_manager = AuthManager(secret_key="test-secret-key")
        self.middleware = BearerAuthServerMiddleware(self.auth_manager)
    
    def test_middleware_initialization(self):
        """Test middleware initialization."""
        assert self.middleware.auth_manager == self.auth_manager
    
    def test_authenticate_valid_token(self):
        """Test authentication with valid Bearer token."""
        username = "testuser"
        token = self.auth_manager.create_token(username)
        headers = {'authorization': f'Bearer {token}'}
        
        payload = self.middleware.authenticate(headers)
        
        assert payload is not None
        assert payload['username'] == username
    
    def test_authenticate_no_authorization_header(self):
        """Test authentication without authorization header."""
        headers = {}
        
        payload = self.middleware.authenticate(headers)
        assert payload is None
    
    def test_authenticate_empty_authorization_header(self):
        """Test authentication with empty authorization header."""
        headers = {'authorization': ''}
        
        payload = self.middleware.authenticate(headers)
        assert payload is None
    
    def test_authenticate_no_bearer_prefix(self):
        """Test authentication without Bearer prefix."""
        headers = {'authorization': 'some-token-without-bearer'}
        
        payload = self.middleware.authenticate(headers)
        assert payload is None
    
    def test_authenticate_invalid_token(self):
        """Test authentication with invalid token."""
        headers = {'authorization': 'Bearer invalid-token'}
        
        payload = self.middleware.authenticate(headers)
        assert payload is None
    
    def test_authenticate_case_sensitive_header(self):
        """Test authentication with different case authorization header."""
        username = "testuser"
        token = self.auth_manager.create_token(username)
        
        # Test lowercase
        headers = {'authorization': f'Bearer {token}'}
        payload = self.middleware.authenticate(headers)
        assert payload is not None
        
        # Test uppercase (should not work as it's case sensitive)
        headers = {'Authorization': f'Bearer {token}'}
        payload = self.middleware.authenticate(headers)
        assert payload is None
    
    def test_is_authenticated_valid_token(self):
        """Test is_authenticated with valid token."""
        username = "testuser"
        token = self.auth_manager.create_token(username)
        headers = {'authorization': f'Bearer {token}'}
        
        is_auth = self.middleware.is_authenticated(headers)
        assert is_auth is True
    
    def test_is_authenticated_invalid_token(self):
        """Test is_authenticated with invalid token."""
        headers = {'authorization': 'Bearer invalid-token'}
        
        is_auth = self.middleware.is_authenticated(headers)
        assert is_auth is False
    
    def test_is_authenticated_no_headers(self):
        """Test is_authenticated without headers."""
        headers = {}
        
        is_auth = self.middleware.is_authenticated(headers)
        assert is_auth is False


class TestAuthManagerEdgeCases:
    """Test edge cases and error scenarios."""
    
    def test_create_token_empty_username(self):
        """Test creating token with empty username."""
        manager = AuthManager()
        token = manager.create_token("")
        
        payload = manager.validate_token(token)
        assert payload is not None
        assert payload['username'] == ""
    
    def test_create_token_unicode_username(self):
        """Test creating token with unicode username."""
        manager = AuthManager()
        username = "测试用户"
        token = manager.create_token(username)
        
        payload = manager.validate_token(token)
        assert payload is not None
        assert payload['username'] == username
    
    def test_create_token_special_chars_username(self):
        """Test creating token with special characters in username."""
        manager = AuthManager()
        username = "user@domain.com!#$%"
        token = manager.create_token(username)
        
        payload = manager.validate_token(token)
        assert payload is not None
        assert payload['username'] == username
    
    def test_validate_token_malformed_jwt(self):
        """Test validation of malformed JWT."""
        manager = AuthManager()
        
        # Various malformed tokens
        malformed_tokens = [
            "not.a.jwt",
            "header.payload",  # Missing signature
            "too.many.parts.here.invalid",
            "Bearer ",  # Just Bearer prefix
            "Bearer",   # No space after Bearer
        ]
        
        for token in malformed_tokens:
            with patch('mpzsql.auth.logger'):
                payload = manager.validate_token(token)
            assert payload is None
    
    def test_session_data_integrity(self):
        """Test session data integrity across operations."""
        manager = AuthManager()
        username = "testuser"
        
        # Create token and verify session
        token = manager.create_token(username)
        payload = jwt.decode(token, manager.secret_key, algorithms=['HS256'])
        session_id = payload['session_id']
        
        # Verify initial session state
        session = manager.get_session(session_id)
        assert session['transactions'] == []
        assert session['username'] == username
        
        # Validate token (should update last_activity)
        manager.validate_token(token)
        
        # Session should still be intact
        session_after = manager.get_session(session_id)
        assert session_after['username'] == username
        assert session_after['transactions'] == []
    
    def test_concurrent_token_creation(self):
        """Test creating multiple tokens for same user."""
        manager = AuthManager()
        username = "testuser"
        
        # Create multiple tokens
        token1 = manager.create_token(username)
        token2 = manager.create_token(username)
        
        # Both should be valid
        payload1 = manager.validate_token(token1)
        payload2 = manager.validate_token(token2)
        
        assert payload1 is not None
        assert payload2 is not None
        assert payload1['username'] == username
        assert payload2['username'] == username
        assert payload1['session_id'] != payload2['session_id']  # Different sessions
        
        # Both sessions should exist
        assert len(manager.sessions) == 2


class TestLogging:
    """Test logging functionality."""
    
    def test_auth_logging_import(self):
        """Test that logging is properly imported and configured."""
        from mpzsql.auth import logger, auth_logger
        
        assert logger is not None
        assert logger.name == "mpzsql.auth"
        assert auth_logger is not None


class TestAuthIntegration:
    """Integration tests for auth components."""
    
    def test_full_auth_workflow(self):
        """Test complete authentication workflow."""
        # Setup
        manager = AuthManager(secret_key="integration-test-key")
        middleware = BearerAuthServerMiddleware(manager)
        username = "integration_user"
        
        # Step 1: Create token
        token = manager.create_token(username)
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Step 2: Validate token directly
        payload = manager.validate_token(token)
        assert payload is not None
        assert payload['username'] == username
        
        # Step 3: Authenticate via middleware
        headers = {'authorization': f'Bearer {token}'}
        auth_payload = middleware.authenticate(headers)
        assert auth_payload is not None
        assert auth_payload['username'] == username
        
        # Step 4: Check authentication status
        is_authenticated = middleware.is_authenticated(headers)
        assert is_authenticated is True
        
        # Step 5: Verify session exists
        session_id = payload['session_id']
        session = manager.get_session(session_id)
        assert session is not None
        assert session['username'] == username
    
    def test_auth_workflow_with_expiry(self):
        """Test authentication workflow with token expiry."""
        # Create manager
        manager = AuthManager(secret_key="test-key")
        middleware = BearerAuthServerMiddleware(manager)
        username = "expiry_test_user"
        
        # Create and immediately validate token
        token = manager.create_token(username)
        payload = manager.validate_token(token)
        assert payload is not None
        
        # Mock expired token validation
        headers = {'authorization': f'Bearer {token}'}
        
        # Simulate expired token by mocking jwt.decode to raise ExpiredSignatureError
        with patch('mpzsql.auth.jwt.decode') as mock_decode:
            mock_decode.side_effect = jwt.ExpiredSignatureError("Token has expired")
            
            # Token should now be expired
            expired_payload = manager.validate_token(token)
            assert expired_payload is None
            
            # Middleware should reject expired token
            auth_payload = middleware.authenticate(headers)
            assert auth_payload is None
            
            is_authenticated = middleware.is_authenticated(headers)
            assert is_authenticated is False
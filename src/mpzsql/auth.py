"""
Authentication and session management for FlightSQL server.
Implements JWT-based authentication similar to the Examples server.
"""

import jwt
import uuid
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from mpzsql.logfire_config import get_auth_logger

logger = logging.getLogger(__name__)
auth_logger = get_auth_logger()


class AuthManager:
    """Manages JWT authentication and session tracking."""
    
    def __init__(self, secret_key: str = "your-secret-key", token_expiry_hours: int = 24):
        self.secret_key = secret_key
        self.token_expiry_hours = token_expiry_hours
        self.sessions: Dict[str, Dict[str, Any]] = {}
        
    def create_token(self, username: str) -> str:
        """Create a JWT token for the given username."""
        session_id = str(uuid.uuid4())
        expiry = datetime.utcnow() + timedelta(hours=self.token_expiry_hours)
        
        payload = {
            'username': username,
            'session_id': session_id,
            'exp': expiry,
            'iat': datetime.utcnow()
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        
        # Store session info
        self.sessions[session_id] = {
            'username': username,
            'created_at': datetime.utcnow(),
            'last_activity': datetime.utcnow(),
            'transactions': []
        }
        
        return token
    
    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate a JWT token and return the payload if valid."""
        try:
            # Handle None or empty token
            if not token:
                return None
                
            # Remove 'Bearer ' prefix if present
            if token.startswith('Bearer '):
                token = token[7:]
                
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            session_id = payload.get('session_id')
            
            # Update last activity
            if session_id in self.sessions:
                self.sessions[session_id]['last_activity'] = datetime.utcnow()
                
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session information by session ID."""
        return self.sessions.get(session_id)
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions."""
        current_time = datetime.utcnow()
        expired_sessions = []
        
        for session_id, session in self.sessions.items():
            try:
                last_activity = session.get('last_activity')
                if last_activity and current_time - last_activity > timedelta(hours=self.token_expiry_hours):
                    expired_sessions.append(session_id)
            except (TypeError, AttributeError):
                # Handle corrupted session data by removing it
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del self.sessions[session_id]
            logger.info(f"Cleaned up expired session: {session_id}")


class BearerAuthServerMiddleware:
    """
    Server middleware for Bearer token authentication.
    Matches the Examples server's authentication approach.
    """
    
    def __init__(self, auth_manager: AuthManager):
        self.auth_manager = auth_manager
        
    def authenticate(self, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Authenticate request based on headers."""
        auth_header = headers.get('authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return None
            
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        return self.auth_manager.validate_token(token)
    
    def is_authenticated(self, headers: Dict[str, str]) -> bool:
        """Check if request is authenticated."""
        return self.authenticate(headers) is not None

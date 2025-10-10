"""
Authentication Tests
Tests for JWT authentication, token generation, and validation
"""

import pytest
from datetime import datetime, timedelta
from jose import jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_access_token,
    verify_refresh_token,
    verify_password,
    get_password_hash,
)


class TestPasswordHashing:
    """Test password hashing and verification"""
    
    def test_hash_password(self):
        """Test password hashing"""
        password = "TestPassword123!"
        hashed = get_password_hash(password)
        
        assert hashed is not None
        assert hashed != password
        assert len(hashed) > 0
    
    def test_verify_password_correct(self):
        """Test password verification with correct password"""
        password = "TestPassword123!"
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password"""
        password = "TestPassword123!"
        wrong_password = "WrongPassword456!"
        hashed = get_password_hash(password)
        
        assert verify_password(wrong_password, hashed) is False
    
    def test_different_hashes_for_same_password(self):
        """Test that same password produces different hashes (salt)"""
        password = "TestPassword123!"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)
        
        assert hash1 != hash2
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestAccessToken:
    """Test access token generation and validation"""
    
    def test_create_access_token(self):
        """Test access token creation"""
        user_id = "test-user-123"
        role = "regular"
        
        token = create_access_token(subject=user_id, role=role)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_access_token_payload(self):
        """Test access token contains correct payload"""
        user_id = "test-user-123"
        role = "expert"
        
        token = create_access_token(subject=user_id, role=role)
        payload = decode_token(token)
        
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["role"] == role
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload
    
    def test_access_token_expiration(self):
        """Test access token expiration"""
        user_id = "test-user-123"
        role = "regular"
        
        # Create token with custom expiration
        expires_delta = timedelta(minutes=30)
        token = create_access_token(subject=user_id, role=role, expires_delta=expires_delta)
        payload = decode_token(token)
        
        assert payload is not None
        exp_timestamp = payload["exp"]
        iat_timestamp = payload["iat"]
        
        # Check expiration is approximately 30 minutes from issued time
        exp_delta = exp_timestamp - iat_timestamp
        assert 1790 <= exp_delta <= 1810  # Allow 10 second variance
    
    def test_verify_access_token_valid(self):
        """Test verification of valid access token"""
        user_id = "test-user-123"
        role = "admin"
        
        token = create_access_token(subject=user_id, role=role)
        payload = verify_access_token(token)
        
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["role"] == role
        assert payload["type"] == "access"
    
    def test_verify_access_token_expired(self):
        """Test verification of expired access token"""
        user_id = "test-user-123"
        role = "regular"
        
        # Create token that expires immediately
        expires_delta = timedelta(seconds=-1)
        token = create_access_token(subject=user_id, role=role, expires_delta=expires_delta)
        payload = verify_access_token(token)
        
        assert payload is None
    
    def test_verify_access_token_invalid_signature(self):
        """Test verification of token with invalid signature"""
        user_id = "test-user-123"
        role = "regular"
        
        # Create token with different secret
        to_encode = {
            "exp": datetime.utcnow() + timedelta(minutes=30),
            "iat": datetime.utcnow(),
            "sub": user_id,
            "role": role,
            "type": "access"
        }
        invalid_token = jwt.encode(to_encode, "wrong-secret-key", algorithm=settings.ALGORITHM)
        payload = verify_access_token(invalid_token)
        
        assert payload is None


class TestRefreshToken:
    """Test refresh token generation and validation"""
    
    def test_create_refresh_token(self):
        """Test refresh token creation"""
        user_id = "test-user-123"
        role = "regular"
        
        token, jti = create_refresh_token(subject=user_id, role=role)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        assert jti is not None
        assert isinstance(jti, str)
        assert len(jti) > 0
    
    def test_refresh_token_payload(self):
        """Test refresh token contains correct payload"""
        user_id = "test-user-123"
        role = "expert"
        
        token, jti = create_refresh_token(subject=user_id, role=role)
        payload = decode_token(token)
        
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["role"] == role
        assert payload["type"] == "refresh"
        assert payload["jti"] == jti
        assert "exp" in payload
        assert "iat" in payload
    
    def test_refresh_token_unique_jti(self):
        """Test that each refresh token has unique JTI"""
        user_id = "test-user-123"
        role = "regular"
        
        token1, jti1 = create_refresh_token(subject=user_id, role=role)
        token2, jti2 = create_refresh_token(subject=user_id, role=role)
        
        assert jti1 != jti2
        assert token1 != token2
    
    def test_verify_refresh_token_valid(self):
        """Test verification of valid refresh token"""
        user_id = "test-user-123"
        role = "admin"
        
        token, jti = create_refresh_token(subject=user_id, role=role)
        payload = verify_refresh_token(token)
        
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["role"] == role
        assert payload["type"] == "refresh"
        assert payload["jti"] == jti
    
    def test_verify_refresh_token_expired(self):
        """Test verification of expired refresh token"""
        user_id = "test-user-123"
        role = "regular"
        
        # Create token that expires immediately
        expires_delta = timedelta(seconds=-1)
        token, jti = create_refresh_token(subject=user_id, role=role, expires_delta=expires_delta)
        payload = verify_refresh_token(token)
        
        assert payload is None
    
    def test_verify_refresh_token_wrong_type(self):
        """Test that access token fails refresh token verification"""
        user_id = "test-user-123"
        role = "regular"
        
        # Create access token
        access_token = create_access_token(subject=user_id, role=role)
        payload = verify_refresh_token(access_token)
        
        assert payload is None


class TestTokenDecoding:
    """Test token decoding"""
    
    def test_decode_valid_token(self):
        """Test decoding valid token"""
        user_id = "test-user-123"
        role = "regular"
        
        token = create_access_token(subject=user_id, role=role)
        payload = decode_token(token)
        
        assert payload is not None
        assert isinstance(payload, dict)
        assert "sub" in payload
        assert "role" in payload
        assert "type" in payload
    
    def test_decode_invalid_token(self):
        """Test decoding invalid token"""
        invalid_token = "invalid.token.string"
        payload = decode_token(invalid_token)
        
        assert payload is None
    
    def test_decode_malformed_token(self):
        """Test decoding malformed token"""
        malformed_token = "not-a-jwt-token"
        payload = decode_token(malformed_token)
        
        assert payload is None


class TestRoleBasedTokens:
    """Test role-based token generation"""
    
    def test_regular_user_token(self):
        """Test token for regular user"""
        user_id = "regular-user-123"
        role = "regular"
        
        token = create_access_token(subject=user_id, role=role)
        payload = verify_access_token(token)
        
        assert payload is not None
        assert payload["role"] == "regular"
    
    def test_expert_user_token(self):
        """Test token for expert user"""
        user_id = "expert-user-123"
        role = "expert"
        
        token = create_access_token(subject=user_id, role=role)
        payload = verify_access_token(token)
        
        assert payload is not None
        assert payload["role"] == "expert"
    
    def test_admin_user_token(self):
        """Test token for admin user"""
        user_id = "admin-user-123"
        role = "admin"
        
        token = create_access_token(subject=user_id, role=role)
        payload = verify_access_token(token)
        
        assert payload is not None
        assert payload["role"] == "admin"


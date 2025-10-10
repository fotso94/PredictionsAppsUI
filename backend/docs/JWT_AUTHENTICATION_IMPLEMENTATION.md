# JWT Authentication System Implementation

## Overview
This document describes the implementation of the JWT (JSON Web Token) authentication system with refresh tokens for the Soccer Predictions Platform backend.

## Implementation Date
**Completed:** 2025-10-09

## Jira Ticket
**KAN-23:** Implement JWT authentication system with refresh tokens

## Subtasks Completed
1. **KAN-107:** Install and configure python-jose for JWT ✅
2. **KAN-108:** Create JWT token generation and validation functions ✅
3. **KAN-109:** Implement refresh token mechanism ✅
4. **KAN-110:** Create authentication dependency for protected routes ✅
5. **KAN-111:** Implement password hashing with bcrypt ✅

---

## Architecture

### Token Types

#### Access Token
- **Purpose:** Short-lived token for API authentication
- **Expiration:** 7 days (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- **Storage:** Client-side (memory or secure storage)
- **Payload:**
  ```json
  {
    "sub": "user-id",
    "role": "regular|expert|admin",
    "type": "access",
    "exp": 1234567890,
    "iat": 1234567890
  }
  ```

#### Refresh Token
- **Purpose:** Long-lived token for obtaining new access tokens
- **Expiration:** 30 days (configurable via `REFRESH_TOKEN_EXPIRE_MINUTES`)
- **Storage:** Redis (server-side) + Client-side
- **Payload:**
  ```json
  {
    "sub": "user-id",
    "role": "regular|expert|admin",
    "type": "refresh",
    "jti": "unique-token-id",
    "exp": 1234567890,
    "iat": 1234567890
  }
  ```

### Redis Storage Strategy

#### Database Allocation
- **DB 0 (REDIS_DB_SESSIONS):** User sessions and authentication tokens

#### Key Patterns
1. **Active Refresh Tokens:**
   - Key: `refresh_token:{user_id}:{jti}`
   - Value: `"1"`
   - TTL: Token expiration time

2. **Blacklisted Refresh Tokens:**
   - Key: `blacklist:refresh:{jti}`
   - Value: `"1"`
   - TTL: Remaining token expiration time

---

## Implementation Details

### 1. Core Security Module (`app/core/security.py`)

#### Password Hashing
```python
# Bcrypt configuration with automatic salt generation
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str
def verify_password(plain_password: str, hashed_password: str) -> bool
```

#### Token Generation
```python
def create_access_token(subject: str, role: str, expires_delta: Optional[timedelta]) -> str
def create_refresh_token(subject: str, role: str, expires_delta: Optional[timedelta]) -> tuple[str, str]
```

#### Token Validation
```python
def decode_token(token: str) -> Optional[Dict[str, Any]]
def verify_access_token(token: str) -> Optional[Dict[str, Any]]
def verify_refresh_token(token: str) -> Optional[Dict[str, Any]]
```

### 2. Authentication Dependencies (`app/core/deps.py`)

#### User Authentication
```python
async def get_current_user_token(credentials: HTTPAuthorizationCredentials) -> TokenPayload
async def get_current_user(db: Session, token_data: TokenPayload) -> User
async def get_current_active_user(current_user: User) -> User
```

#### Role-Based Access Control
```python
async def get_current_expert_user(current_user: User) -> User  # Expert or Admin
async def get_current_admin_user(current_user: User) -> User   # Admin only
```

#### Token Management
```python
def store_refresh_token(user_id: str, jti: str, expires_in: int) -> None
def verify_refresh_token_not_blacklisted(refresh_token: str, jti: str) -> bool
def blacklist_refresh_token(jti: str, expires_in: int) -> None
def revoke_user_refresh_tokens(user_id: str) -> None
```

### 3. Authentication Endpoints (`app/api/v1/endpoints/auth.py`)

#### POST /api/v1/auth/login
- **Purpose:** User login
- **Request:** `{ email, password }`
- **Response:** `{ access_token, refresh_token, user_id, email, role, expires_in }`
- **Actions:**
  - Validates credentials
  - Generates access and refresh tokens
  - Stores refresh token in Redis
  - Updates last login timestamp

#### POST /api/v1/auth/refresh
- **Purpose:** Refresh access token
- **Request:** `{ refresh_token }`
- **Response:** `{ access_token, refresh_token, expires_in }`
- **Actions:**
  - Validates refresh token
  - Checks blacklist
  - Blacklists old refresh token
  - Generates new access and refresh tokens
  - Stores new refresh token in Redis

#### POST /api/v1/auth/logout
- **Purpose:** User logout
- **Request:** `{ refresh_token }`
- **Response:** `{ message }`
- **Actions:**
  - Validates refresh token
  - Blacklists refresh token

#### POST /api/v1/auth/register
- **Purpose:** User registration
- **Request:** `{ email, password, full_name, role }`
- **Response:** `{ user_id, email, full_name, role, created_at }`
- **Actions:**
  - Validates email uniqueness
  - Hashes password
  - Creates user account

#### GET /api/v1/auth/me
- **Purpose:** Get current user info
- **Headers:** `Authorization: Bearer {access_token}`
- **Response:** `{ user_id, email, full_name, role, is_active, is_verified, created_at, updated_at }`

#### POST /api/v1/auth/change-password
- **Purpose:** Change user password
- **Headers:** `Authorization: Bearer {access_token}`
- **Request:** `{ current_password, new_password }`
- **Response:** `{ message }`
- **Actions:**
  - Verifies current password
  - Updates password hash
  - Revokes all refresh tokens (security measure)

### 4. Pydantic Schemas (`app/schemas/auth.py`)

All request/response models for authentication endpoints:
- `LoginRequest`, `LoginResponse`
- `RefreshTokenRequest`, `RefreshTokenResponse`
- `LogoutRequest`, `LogoutResponse`
- `RegisterRequest`, `RegisterResponse`
- `PasswordChangeRequest`, `PasswordChangeResponse`
- `UserInfo`
- `Token`, `TokenPayload`

---

## Security Features

### 1. Password Security
- **Algorithm:** Bcrypt with automatic salt generation
- **Rounds:** 12 (default bcrypt configuration)
- **Validation:** Minimum 8 characters (enforced in Pydantic schema)

### 2. Token Security
- **Algorithm:** HS256 (HMAC with SHA-256)
- **Secret Key:** Cryptographically secure random key (32 bytes)
- **Unique Token IDs:** UUID v4 for refresh tokens (JTI)
- **Token Type Validation:** Prevents access token use as refresh token and vice versa

### 3. Token Revocation
- **Refresh Token Blacklisting:** Immediate invalidation on logout
- **Bulk Revocation:** All user tokens revoked on password change
- **Automatic Cleanup:** Redis TTL ensures expired tokens are removed

### 4. Role-Based Access Control
- **Three User Roles:** Regular, Expert, Admin
- **Token-Embedded Roles:** Role included in token payload
- **Dependency-Based Authorization:** FastAPI dependencies enforce role requirements

### 5. Account Status Validation
- **Active Status Check:** Only active accounts can authenticate
- **Email Verification:** Tracked but not enforced (future enhancement)

---

## Testing

### Test Coverage
- **22 Tests Passed** ✅
- **Coverage:** 93% for `app/core/security.py`

### Test Categories
1. **Password Hashing Tests** (4 tests)
   - Hash generation
   - Correct password verification
   - Incorrect password rejection
   - Salt uniqueness

2. **Access Token Tests** (6 tests)
   - Token creation
   - Payload validation
   - Expiration handling
   - Valid token verification
   - Expired token rejection
   - Invalid signature detection

3. **Refresh Token Tests** (6 tests)
   - Token creation with JTI
   - Payload validation
   - Unique JTI generation
   - Valid token verification
   - Expired token rejection
   - Type validation

4. **Token Decoding Tests** (3 tests)
   - Valid token decoding
   - Invalid token handling
   - Malformed token handling

5. **Role-Based Token Tests** (3 tests)
   - Regular user tokens
   - Expert user tokens
   - Admin user tokens

---

## Configuration

### Environment Variables
```bash
# JWT Configuration
SECRET_KEY=<auto-generated-32-byte-key>
ACCESS_TOKEN_EXPIRE_MINUTES=10080  # 7 days
REFRESH_TOKEN_EXPIRE_MINUTES=43200  # 30 days
ALGORITHM=HS256

# Redis Configuration
REDIS_URL=redis://localhost:6379/0
REDIS_DB_SESSIONS=0
```

---

## Usage Examples

### 1. Login
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password123"}'
```

### 2. Access Protected Endpoint
```bash
curl -X GET http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer {access_token}"
```

### 3. Refresh Token
```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "{refresh_token}"}'
```

### 4. Logout
```bash
curl -X POST http://localhost:8000/api/v1/auth/logout \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "{refresh_token}"}'
```

---

## Future Enhancements

1. **Email Verification Enforcement**
   - Require email verification before login
   - Implement verification email sending

2. **Password Reset Flow**
   - Generate password reset tokens
   - Send reset emails
   - Implement reset confirmation

3. **Multi-Factor Authentication (MFA)**
   - TOTP-based 2FA
   - SMS verification
   - Backup codes

4. **Session Management**
   - View active sessions
   - Revoke specific sessions
   - Device tracking

5. **Rate Limiting**
   - Login attempt limiting
   - Token refresh rate limiting
   - Brute force protection

6. **OAuth2 Integration**
   - Google OAuth
   - GitHub OAuth
   - Social login providers

---

## Dependencies

### Required Packages
```
python-jose[cryptography]==3.3.0  # JWT token handling
passlib[bcrypt]==1.7.4            # Password hashing
bcrypt==4.1.1                     # Bcrypt algorithm
redis==5.0.1                      # Redis client
```

### Python Version
- **Minimum:** Python 3.11+

---

## Maintenance Notes

### Token Rotation
- Refresh tokens are rotated on each refresh request
- Old refresh tokens are immediately blacklisted
- Prevents token replay attacks

### Redis Cleanup
- Automatic cleanup via TTL
- No manual cleanup required
- Monitor Redis memory usage

### Security Updates
- Regularly update dependencies
- Monitor security advisories
- Review and update secret keys periodically

---

## Contributors
- **Developer:** fotso94
- **Date:** 2025-10-09
- **Jira Ticket:** KAN-23


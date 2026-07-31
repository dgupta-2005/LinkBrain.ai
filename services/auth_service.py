import os
import json
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
import bcrypt

class AuthService:
    """Service encapsulating user authentication, password hashing, and token cryptography."""

    SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.getenv("SECRET_KEY", "hackathon-super-secret-key"))
    ALGORITHM = "HS256"
    TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week

    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except ValueError:
            return False

    @classmethod
    def get_password_hash(cls, password: str) -> str:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    @classmethod
    def create_access_token(cls, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=cls.TOKEN_EXPIRE_MINUTES))
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, cls.SECRET_KEY, algorithm=cls.ALGORITHM)

    @classmethod
    def decode_access_token(cls, token: str) -> Optional[Dict[str, Any]]:
        try:
            return jwt.decode(token, cls.SECRET_KEY, algorithms=[cls.ALGORITHM])
        except jwt.PyJWTError:
            return None

    @classmethod
    def decode_id_token(cls, id_token_string: str) -> Dict[str, Any]:
        """Decodes base64 Google OAuth JWT ID Tokens."""
        parts = id_token_string.split('.')
        payload_b64 = parts[1] + '=' * (-len(parts[1]) % 4)
        decoded_bytes = base64.b64decode(payload_b64)
        return json.loads(decoded_bytes.decode('utf-8'))
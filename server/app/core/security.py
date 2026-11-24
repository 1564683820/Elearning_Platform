from datetime import datetime, timedelta, timezone
from typing import Any
from jose import jwt, JWTError
from passlib.context import CryptContext
from cryptography.fernet import Fernet
import base64, hashlib
from app.core.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ========== JWT ==========

def create_token(
    user_id: int,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    if expires_delta is None:
        expires_delta = timedelta(days=settings.JWT_EXPIRE_DAYS)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": str(user_id), "exp": expire}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_exam_scan_token(user_id: int, exam_id: int, expires_delta: timedelta) -> str:
    """Create a short-lived token restricted to one exam's mobile scan flow."""
    return create_token(
        user_id,
        expires_delta=expires_delta,
        extra_claims={"purpose": "exam_scan", "exam_id": str(exam_id)},
    )


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


# ========== 密码哈希 ==========

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ========== AES 加解密（API Key 存储）==========

def _get_fernet_key() -> bytes:
    """将 AES_SECRET_KEY 转为 Fernet 兼容的 32 bytes base64 key"""
    key = hashlib.sha256(settings.AES_SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(key)


def encrypt_text(plain_text: str) -> str:
    f = Fernet(_get_fernet_key())
    return f.encrypt(plain_text.encode()).decode()


def decrypt_text(cipher_text: str) -> str:
    f = Fernet(_get_fernet_key())
    return f.decrypt(cipher_text.encode()).decode()

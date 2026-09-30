# app/core/security.py
import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from app.core.config import settings

def _get_fernet_key() -> bytes:
    """Derives a deterministic 32-byte Fernet key from MASTER_ENCRYPTION_SECRET."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"terminus_static_salt",  # Store in env in production
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(settings.MASTER_ENCRYPTION_SECRET.encode()))

def encrypt_private_key(secret_bytes: bytes) -> str:
    """Encrypts raw secret key bytes to AES-256 ciphertext string."""
    fernet = Fernet(_get_fernet_key())
    return fernet.encrypt(secret_bytes).decode('utf-8')

def decrypt_private_key(encrypted_str: str) -> bytes:
    """Decrypts ciphertext string back to raw secret key bytes."""
    fernet = Fernet(_get_fernet_key())
    return fernet.decrypt(encrypted_str.encode('utf-8'))
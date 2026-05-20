from cryptography.fernet import Fernet

from app.core.config import settings


def _build_fernet() -> Fernet:
    if not settings.encryption_key:
        raise RuntimeError("ENCRYPTION_KEY is not configured. Set a persistent key for deployed environments.")
    return Fernet(settings.encryption_key.encode())


def encrypt_secret(value: str) -> str:
    fernet = _build_fernet()
    return fernet.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    fernet = _build_fernet()
    return fernet.decrypt(value.encode()).decode()

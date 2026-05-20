from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

from app.core.config import settings
from app.db.mongo import UserDoc, find_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> UserDoc:
    credentials_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_error
    except JWTError:
        raise credentials_error

    try:
        user = find_user_by_id(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication service unavailable")
    if not user:
        raise credentials_error
    return user


def require_admin(current_user: UserDoc = Depends(get_current_user)) -> UserDoc:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return current_user


def require_employee(current_user: UserDoc = Depends(get_current_user)) -> UserDoc:
    if current_user.role != "employee":
        raise HTTPException(status_code=403, detail="Employee only")
    return current_user


def require_super_admin(current_user: UserDoc = Depends(get_current_user)) -> UserDoc:
    if current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin only")
    return current_user


__all__ = ["get_current_user", "require_admin", "require_employee", "require_super_admin"]

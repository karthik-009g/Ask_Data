from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.mongo import UserDoc, find_user_by_email, get_users_collection
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_organisation(value: str) -> str:
    return value.strip().lower()


def _normalize_email(value: str) -> str:
    return value.strip().lower()


@router.post("/register", response_model=dict)
def register_user(payload: RegisterRequest):
    _ = payload
    raise HTTPException(
        status_code=403,
        detail="Self-signup is disabled. Ask your super admin to provision admin accounts.",
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    organisation = _normalize_organisation(payload.organisation) if payload.organisation else ""
    email = _normalize_email(payload.email)
    user = None

    # Super admins authenticate globally and do not require organisation scoping.
    try:
        super_admin_match = get_users_collection().find_one({"email": email, "role": "super_admin"})
    except Exception:
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    if super_admin_match:
        user = UserDoc(super_admin_match)

    if user is None and organisation:
        try:
            user = find_user_by_email(email, organisation)
        except Exception:
            raise HTTPException(status_code=503, detail="Authentication service unavailable")
    elif user is None:
        try:
            matches = list(get_users_collection().find({"email": email}).limit(2))
        except Exception:
            raise HTTPException(status_code=503, detail="Authentication service unavailable")

        if not matches:
            user = None
        elif len(matches) > 1:
            raise HTTPException(
                status_code=400,
                detail="Organisation is required for this email. Please select your organisation.",
            )
        else:
            user = UserDoc(matches[0])

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    try:
        password_ok = verify_password(payload.password, user["hashed_password"])
    except Exception:
        password_ok = False

    if not password_ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if organisation and user.get("organisation") and user["organisation"] != organisation:
        raise HTTPException(status_code=401, detail="Organisation does not match")
    token = create_access_token(subject=user.id, role=user.role, organisation=user.get("organisation"))
    return TokenResponse(access_token=token)


@router.post("/logout", response_model=dict)
def logout(_: UserDoc = Depends(get_current_user)):
    return {"message": "Logged out"}

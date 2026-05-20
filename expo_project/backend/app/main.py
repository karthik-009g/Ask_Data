import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler

from app.api.v1.router import api_router
from app.api.v1.employee import limiter
from app.core.config import settings
from app.core.security import hash_password
from app.db.mongo import get_users_collection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(title=settings.app_name)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def ensure_super_admin_user() -> None:
    email = settings.super_admin_email.strip().lower()
    password = settings.super_admin_password
    full_name = settings.super_admin_full_name.strip() or "Platform Super Admin"

    if not email or not password:
        return

    users = get_users_collection()
    existing = users.find_one({"email": email, "role": "super_admin"})
    if existing:
        return

    users.insert_one(
        {
            "organisation": "",
            "email": email,
            "full_name": full_name,
            "hashed_password": hash_password(password),
            "role": "super_admin",
            "created_at": datetime.now(timezone.utc),
        }
    )
    logging.getLogger(__name__).info("Bootstrap super admin created for %s", email)


@app.on_event("startup")
def on_startup():
    ensure_super_admin_user()
    return None


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.api_v1_prefix)

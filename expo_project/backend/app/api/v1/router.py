from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.admin import router as admin_router
from app.api.v1.debug import router as debug_router
from app.api.v1.employee import router as employee_router
from app.api.v1.query import router as query_router
from app.api.v1.super_admin import router as super_admin_router
from app.api.v1.system_assistant import router as system_assistant_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(debug_router)
api_router.include_router(employee_router)
api_router.include_router(query_router)
api_router.include_router(super_admin_router)
api_router.include_router(system_assistant_router)

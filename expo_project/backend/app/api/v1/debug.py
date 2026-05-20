from fastapi import APIRouter, Depends

from app.core.dependencies import require_admin
from app.db.mongo import UserDoc
from app.services.ai_service import get_generation_metadata

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/model")
def get_model_runtime(_: UserDoc = Depends(require_admin)):
    metadata = get_generation_metadata()
    return {
        "mode": metadata.get("mode"),
        "provider": metadata.get("provider"),
        "model": metadata.get("model"),
    }

from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user
from app.db.mongo import UserDoc
from app.schemas.system_assistant import SystemAssistantChatRequest, SystemAssistantChatResponse
from app.services.system_assistant.chatbot_service import system_assistant_service

router = APIRouter(prefix="/system-assistant", tags=["system-assistant"])


@router.post("/chat", response_model=SystemAssistantChatResponse)
def chat_system_assistant(payload: SystemAssistantChatRequest, current_user: UserDoc = Depends(get_current_user)):
    role = (current_user.role or "").strip().lower()
    if role not in {"admin", "employee"}:
        raise HTTPException(status_code=403, detail="System assistant is available only for admin and employee roles")

    result = system_assistant_service.handle_chat(
        user_query=payload.user_query,
        user_role=role,
        user_org=(current_user.organisation or ""),
        user=current_user,
    )
    return SystemAssistantChatResponse(**result)

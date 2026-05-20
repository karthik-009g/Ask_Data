from pydantic import BaseModel, Field


class SystemAssistantChatRequest(BaseModel):
    user_query: str = Field(..., min_length=1, max_length=4000)


class SystemAssistantChatResponse(BaseModel):
    type: str
    message: str
    data: dict = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)

from pydantic import BaseModel, Field


class PromptRequest(BaseModel):
    prompt: str
    chart_type: str | None = None
    connection_ids: list[int] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    prompt: str
    connection_ids: list[int] = Field(default_factory=list)
    mode: str = "analytics"


class NLQueryRequest(BaseModel):
    question: str


class ExportRequest(BaseModel):
    question: str
    format: str | None = None


class QueryResponse(BaseModel):
    generated_sql: str
    columns: list[str] = []
    rows: list[dict]
    execution_time: float

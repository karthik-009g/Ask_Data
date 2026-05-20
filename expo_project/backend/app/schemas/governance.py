from pydantic import BaseModel, Field


class GovernanceLimitsUpdate(BaseModel):
    max_queries_per_employee_per_day: int = Field(default=200, ge=1)
    max_exports_per_employee_per_day: int = Field(default=30, ge=1)
    max_rows_per_query: int = Field(default=500, ge=1)


class ScheduledReportCreate(BaseModel):
    name: str
    prompt: str
    connection_ids: list[int] = Field(default_factory=list)
    format: str = "csv"
    interval_minutes: int = Field(default=1440, ge=5)
    recipient_email: str = ""


class PermissionDecisionPayload(BaseModel):
    note: str = ""

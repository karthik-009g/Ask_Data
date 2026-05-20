from pydantic import BaseModel, Field


class DatabaseConnectionCreate(BaseModel):
    name: str
    db_type: str
    method: str
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    database_name: str | None = None
    connection_url: str | None = None


class DatabaseConnectionOut(BaseModel):
    id: int
    name: str
    db_type: str
    host: str | None
    port: int | None
    username: str | None
    database_name: str | None
    connection_url: str | None
    is_active: bool

    class Config:
        from_attributes = True


class ConnectionPermission(BaseModel):
    connection_id: int
    can_read: bool = True
    can_query: bool = True
    can_visualize: bool = True
    can_export: bool = True
    allowed_tables: list[str] = Field(default_factory=lambda: ["*"])


class PermissionAssignment(BaseModel):
    employee_id: str   # MongoDB ObjectId hex string
    connection_ids: list[int] = Field(default_factory=list)
    permissions: list[ConnectionPermission] = Field(default_factory=list)

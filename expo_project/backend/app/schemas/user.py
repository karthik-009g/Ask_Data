from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    id: str          # MongoDB ObjectId as hex string
    email: EmailStr
    full_name: str
    position: str | None = None
    department: str | None = None
    phone: str | None = None
    manager_name: str | None = None
    location: str | None = None
    timezone: str | None = None
    preferred_language: str | None = None
    bio: str | None = None
    role: str


class EmployeeProfileUpdate(BaseModel):
    full_name: str | None = None
    position: str | None = None
    department: str | None = None
    phone: str | None = None
    manager_name: str | None = None
    location: str | None = None
    timezone: str | None = None
    preferred_language: str | None = None
    bio: str | None = None

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    organisation: str = ""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    organisation: str = ""
    email: EmailStr
    full_name: str
    position: str = ""
    password: str
    role: str

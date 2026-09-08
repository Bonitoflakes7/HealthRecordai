from datetime import datetime

from pydantic import BaseModel, Field


class UserRegistration(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=256)


class User(BaseModel):
    id: str
    username: str
    disabled: bool = False


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuditEvent(BaseModel):
    id: int
    user_id: str
    action: str
    resource_type: str
    resource_id: str | None = None
    success: bool = True
    created_at: datetime


class AuditResponse(BaseModel):
    events: list[AuditEvent]

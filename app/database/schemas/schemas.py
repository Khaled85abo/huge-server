from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    org: str = Field(..., description="The organization of the user")
    name: str = Field(..., description="The name of the user")
    email: EmailStr = Field(..., description="The email of the user")

class UserCreate(UserBase):
    pass

class UserRead(UserBase):
    id: int
    created_date: datetime
    updated_date: Optional[datetime] = None

    class Config:
        orm_mode = True

class JobBase(BaseModel):
    source_storage: str
    dest_storage: str
    status: str
    description: str

class JobCreate(JobBase):
    user_id: int

class JobRead(JobBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class TransferRequest(BaseModel):
    source_storage: str
    dest_storage: str


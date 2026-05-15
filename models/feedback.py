from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class FeedbackBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    subject: str
    message: str

class FeedbackCreate(FeedbackBase):
    pass

class FeedbackResponse(FeedbackBase):
    id: str
    created_at: datetime
    status: str = "pending"  # pending, read, resolved

    class Config:
        from_attributes = True

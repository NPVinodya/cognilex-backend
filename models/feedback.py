from datetime import datetime

from pydantic import BaseModel, EmailStr


class FeedbackBase(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
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

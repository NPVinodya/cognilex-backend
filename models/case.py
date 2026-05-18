from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, Field


class LegalCaseModel(BaseModel):
    lawyer_id: str
    title: str
    clientName: str
    caseType: str
    status: str = "In Progress"  # In Progress, Pending Review, Court Phase, Completed, Canceled
    progress: int = 0
    nextHearingDate: str | None = None
    description: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

from pydantic import BaseModel, EmailStr

class UserStats(BaseModel):
    total_users: int
    active_lawyers: int
    chat_sessions: int
    pending_approvals: int

class LawyerApproval(BaseModel):
    id: str
    name: str
    email: str
    bar_number: str
    specialization: str




    experience: int
    status: str = "pending"

class ApprovalRequest(BaseModel):
    lawyer_id: str
    action: str  # "approve" or "reject"


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str



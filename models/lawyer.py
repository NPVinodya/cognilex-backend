# models/lawyer.py
from pydantic import BaseModel, EmailStr
from typing import List, Optional


class LawyerRegistration(BaseModel):
    fullName: str
    email: EmailStr
    phone: str
    address: str
    city: str
    province: str
    nicNumber: str
    lawyerId: str
    barCouncilNumber: str
    specialization: str
    yearsOfExperience: int
    lawFirm: Optional[str] = None
    languagesSpoken: str
    lawSchool: str
    graduationYear: int
    additionalQualifications: Optional[str] = None
    practiceAreas: List[str]
    consultationFee: float
    availability: str
    bio: str


class LawyerResponse(BaseModel):
    id: str
    name: str  # Changed from fullName for frontend compatibility
    email: str
    userType: str = "lawyer"
    createdAt: str
    barNumber: str  # Changed from barCouncilNumber
    province: str
    specializations: List[str]  # Changed from practiceAreas
    yearsOfPractice: int  # Changed from yearsOfExperience
    rating: float
    totalCases: int  # Changed from totalAppointments
    vettingStatus: str  # Changed from status
    address: str
    phone: str
    profilePhotoUrl: Optional[str] = None
    bio: Optional[str] = None
    consultationFee: Optional[float] = None

    class Config:
        populate_by_name = True


class LawyerListResponse(BaseModel):
    success: bool
    count: int
    lawyers: List[LawyerResponse]
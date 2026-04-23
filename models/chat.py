"""
models/chat.py — Pydantic schemas for the Chat API
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class ChatRequest(BaseModel):
    """Request body sent by the frontend."""
    question: str = Field(..., min_length=1, description="The user's legal question")
    user_id: Optional[str] = Field(default="guest_user", description="User identifier for RAG session memory")


class ChatResponse(BaseModel):
    """Response relayed back from the RAG engine."""
    answer: str
    mode: str
    sources: List[str] = []
    latency: Optional[str] = None

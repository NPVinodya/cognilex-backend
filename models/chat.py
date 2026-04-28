"""
models/chat.py — Pydantic schemas for the Chat API
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class ChatRequest(BaseModel):
    """Request body sent by the frontend."""
    question: str = Field(..., min_length=1, description="The user's legal question")
    user_id: Optional[str] = Field(default="guest_user", description="User identifier for RAG session memory")
    session_id: Optional[str] = Field(default=None, description="The unique ID for the chat session")


class ChatResponse(BaseModel):
    """Response relayed back from the RAG engine."""
    answer: str
    mode: str
    sources: List[str] = []
    latency: Optional[str] = None
    session_id: Optional[str] = None


class MessageModel(BaseModel):
    """A single chat message stored in MongoDB."""
    role: str # "user" or "bot"
    content: str
    created_at: str
    sources: Optional[List[str]] = None
    latency: Optional[str] = None
    mode: Optional[str] = None


class SessionModel(BaseModel):
    """A chat session stored in MongoDB."""
    id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str

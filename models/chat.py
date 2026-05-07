"""
models/chat.py — Pydantic schemas for the Chat API
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class ChatRequest(BaseModel):
    """Request body sent by the frontend."""
    question: str = Field(..., min_length=1, description="The user's legal question")
    user_id: Optional[str] = Field(default="guest_user", description="User identifier for RAG session memory")
    session_id: Optional[str] = Field(default=None, description="The unique ID for the chat session")
    mode: Optional[str] = Field(default=None, description="Legal or research mode")
    use_query_engine: Optional[bool] = Field(default=False, description="Use stateless query engine")


class ChatResponse(BaseModel):
    """Response relayed back from the RAG engine."""
    answer: str
    mode: str
    sources: List[str] = Field(default_factory=list)
    related_cases: Optional[List[Dict]] = Field(default_factory=list)
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
    related_cases: Optional[List[Dict]] = None


class SessionModel(BaseModel):
    """A chat session stored in MongoDB."""
    id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str

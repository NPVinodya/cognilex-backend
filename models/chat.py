"""
models/chat.py — Pydantic schemas for the Chat API
"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body sent by the frontend."""
    question: str = Field(..., min_length=1, description="The user's legal question")
    user_id: str | None = Field(default="guest_user", description="User identifier for RAG session memory")
    session_id: str | None = Field(default=None, description="The unique ID for the chat session")
    mode: str | None = Field(default=None, description="Legal or research mode")
    use_query_engine: bool | None = Field(default=False, description="Use stateless query engine")


class ChatResponse(BaseModel):
    """Response relayed back from the RAG engine."""
    answer: str
    mode: str
    sources: list[str] = Field(default_factory=list)
    related_cases: list[dict] | None = Field(default_factory=list)
    latency: str | None = None
    session_id: str | None = None


class MessageModel(BaseModel):
    """A single chat message stored in MongoDB."""
    role: str # "user" or "bot"
    content: str
    created_at: str
    sources: list[str] | None = None
    latency: str | None = None
    mode: str | None = None
    related_cases: list[dict] | None = None


class SessionModel(BaseModel):
    """A chat session stored in MongoDB."""
    id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str

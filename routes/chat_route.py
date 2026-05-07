"""
routes/chat_route.py — REST API routes for the CogniLex AI chat.

Registered prefix: /chat
Full endpoints exposed:
  POST /chat/ask         — authenticated user chat
  POST /chat/guest_mode  — guest mode (unauthenticated)
  GET  /chat/sessions    — get all sessions for a user
  GET  /chat/history     — get message history for a session
  PATCH /chat/session/{session_id}/title — rename a session
  GET  /chat/health      — health check
"""

from typing import Dict, List

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from controllers.chat_controller import (
    ask_rag, guest_mode_chat, get_session_history, get_sessions, update_session_title,
    create_share, get_shared_chat, save_shared_chat,
)
from models.chat import ChatRequest, ChatResponse, MessageModel

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "/ask",
    response_model=ChatResponse,
    summary="Send a legal question to the RAG AI",
    description=(
        "Accepts a user question, forwards it to the local chat controller, "
        "and returns the AI-generated legal answer along with source citations "
        "and response metadata."
    ),
)
async def chat_ask(request: ChatRequest):
    try:
        return await ask_rag(request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat processing error: {str(e)}",
        )


@router.post(
    "/guest_mode",
    response_model=ChatResponse,
    summary="Guest mode chat (unauthenticated)",
    description=(
        "Allows unauthenticated users to chat with CogniLex AI without logging in. "
        "Uses meta-llama/llama-4-scout-17b-16e-instruct for direct conversational response "
        "(no document retrieval). Supports multilingual input."
    ),
)
async def chat_guest_mode(request: ChatRequest):
    try:
        return await guest_mode_chat(request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Guest mode processing error: {str(e)}",
        )


@router.get(
    "/sessions",
    response_model=Dict[str, List[Dict]],
    summary="Get all chat sessions for a user",
)
async def fetch_sessions(user_id: str = Query(..., description="The user's email or ID")):
    try:
        sessions = await get_sessions(user_id)
        return {"sessions": sessions}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching sessions: {str(e)}",
        )


@router.get(
    "/history",
    response_model=Dict[str, List[MessageModel]],
    summary="Get message history for a session",
)
async def fetch_history(session_id: str = Query(..., description="The unique session ID")):
    try:
        messages = await get_session_history(session_id)
        return {"messages": messages}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching history: {str(e)}",
        )


@router.patch(
    "/session/{session_id}/title",
    summary="Rename a chat session",
)
async def chat_rename(session_id: str, title: str = Query(..., description="The new title for the session")):
    try:
        await update_session_title(session_id, title)
        return {"message": "Session renamed successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error renaming session: {str(e)}",
        )


@router.get(
    "/health",
    summary="Check RAG service connectivity",
    description="Checks that the local chat route layer is available.",
)
async def chat_health():
    """GET /chat/health — verify the REST layer is alive."""
    return {
        "rest_api": "ok",
        "rag_service": "local",
        "rag_url": "in-process",
    }


# ── Share Chat Routes ─────────────────────────────────────────────────────────

class ShareRequest(BaseModel):
    session_id: str

class SaveShareRequest(BaseModel):
    user_id: str


@router.post(
    "/share",
    summary="Create a shareable link for a chat session",
    description=(
        "Generates (or retrieves) a unique share_id for the given session. "
        "Subsequent calls with the same session_id return the same share_id (idempotent)."
    ),
)
async def chat_create_share(body: ShareRequest):
    try:
        return await create_share(body.session_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating share: {str(e)}",
        )


@router.get(
    "/share/{share_id}",
    summary="Fetch a shared chat by its share_id",
    description="Public endpoint — returns the session title and all messages. No auth required.",
)
async def chat_get_share(share_id: str):
    try:
        return await get_shared_chat(share_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching shared chat: {str(e)}",
        )


@router.post(
    "/share/{share_id}/save",
    summary="Save a shared chat as a new session",
    description="Clones all messages from the shared session into a new session owned by the requesting user.",
)
async def chat_save_share(share_id: str, body: SaveShareRequest):
    try:
        return await save_shared_chat(share_id, body.user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving shared chat: {str(e)}",
        )

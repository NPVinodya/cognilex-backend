"""
controllers/chat_controller.py — Business logic for the Chat endpoint.

Flow:
    Frontend  →  REST API (this file)  →  RAG API (CogniLex-RAG on port 8001)

The controller forwards the user's question to the RAG FastAPI server at
RAG_API_URL/ask and relays the full response back to the frontend.
"""

import os
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
from fastapi import HTTPException, status
from dotenv import load_dotenv

from models.chat import ChatRequest
from config.cognilex_db import get_database

load_dotenv()

logger = logging.getLogger("chat_controller")

# ── RAG service URL ────────────────────────────────────────────────────────────
RAG_API_URL: str = os.getenv("RAG_API_URL", "http://localhost:8001")


async def ask_rag(request: ChatRequest) -> Dict:
    """
    Forward a chat question to the CogniLex RAG service and return its response.
    Also persists the interaction to MongoDB.
    """
    db = get_database()
    print(f"[DEBUG] ask_rag: user_id={request.user_id}, session_id={request.session_id}")

    # 1. Handle Session
    session_id = request.session_id
    if not session_id:
        session_id = str(uuid.uuid4())
        print(f"[DEBUG] Creating new session: {session_id}")
        # Create a new session document
        session_doc = {
            "id": session_id,
            "user_id": request.user_id or "guest_user",
            "title": request.question[:40] + ("..." if len(request.question) > 40 else ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        db.chat_sessions.insert_one(session_doc)
    else:
        print(f"[DEBUG] Using existing session: {session_id}")
        # Update existing session timestamp
        db.chat_sessions.update_one(
            {"id": session_id},
            {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
        )

    # 2. Save User Message
    user_msg = {
        "session_id": session_id,
        "role": "user",
        "content": request.question.strip(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    db.chat_messages.insert_one(user_msg)
    print(f"[DEBUG] User message saved to session {session_id}")

    # Normalize mode value that may have been supplied by the frontend.
    def _normalize_mode(m: str | None) -> Optional[str]:
        if not m:
            return None
        m_low = m.strip().lower()
        if m_low in ("research", "case", "cases", "judgment", "judgement"):
            return "research"
        if m_low in ("legal", "act", "acts", "statute", "statutes"):
            return "legal"
        # If it's already one of the expected values, pass through; otherwise None
        if m_low in ("legal", "research"):
            return m_low
        return None

    normalized_mode = _normalize_mode(getattr(request, "mode", None))

    # Build payload for the external RAG (ragtwo) HTTP service. We include
    # session_id so the RAG service can optionally correlate conversations
    # and the parsed `mode` so ragtwo can pick the correct engine without
    # re-detecting if the frontend already provided it.
    payload = {
        "question": request.question.strip(),
        "user_id": request.user_id or "guest_user",
        "session_id": session_id,
    }
    if normalized_mode:
        payload["mode"] = normalized_mode
    # Forward any stateless flag if frontend provided it (use_query_engine)
    use_query_flag = getattr(request, "use_query_engine", None)
    if use_query_flag is not None:
        try:
            payload["use_query_engine"] = bool(use_query_flag)
        except Exception:
            payload["use_query_engine"] = False

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            rag_response = await client.post(
                f"{RAG_API_URL}/ask",
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )

        if rag_response.status_code != 200:
            error_body = {}
            try:
                error_body = rag_response.json()
            except Exception:
                pass

            detail = (
                error_body.get("detail")
                or error_body.get("message")
                or f"RAG service returned HTTP {rag_response.status_code}"
            )
            logger.error(f"RAG service error: {rag_response.status_code} — {detail}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=detail,
            )

        data = rag_response.json()

        # 3. Save Bot Response
        # Persist the bot reply we received from the RAG service. Ensure the
        # stored mode is one of the expected values (fallback to 'legal').
        bot_msg = {
            "session_id": session_id,
            "role": "bot",
            "content": data.get("answer", ""),
            "sources": data.get("sources", []),
            "latency": data.get("latency", ""),
            "mode": data.get("mode") if data.get("mode") in ("legal", "research") else (normalized_mode or data.get("mode") or "legal"),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        db.chat_messages.insert_one(bot_msg)
        print(f"[DEBUG] Bot response saved to session {session_id}")

        # Add session_id to response for frontend
        data["session_id"] = session_id

        logger.info(
            f"RAG response: user_id={payload['user_id']} "
            f"session_id={session_id} "
            f"latency={data.get('latency', 'N/A')}"
        )
        return data

    except httpx.ConnectError:
        logger.error(f"Cannot connect to RAG service at {RAG_API_URL}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"RAG service is unreachable at {RAG_API_URL}. Is the RAG server running?",
        )
    except httpx.TimeoutException:
        logger.error("RAG service request timed out")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="RAG service took too long to respond. Please try again.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error calling RAG service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your request.",
        )


async def get_sessions(user_id: str) -> List[Dict]:
    """Fetch all chat sessions for a specific user from MongoDB."""
    print(f"[DEBUG] get_sessions for user_id={user_id}")
    db = get_database()
    sessions = list(db.chat_sessions.find({"user_id": user_id}).sort("updated_at", -1))
    print(f"[DEBUG] Found {len(sessions)} sessions")
    return [{"id": s["id"], "title": s["title"], "updated_at": s["updated_at"]} for s in sessions]


async def get_session_history(session_id: str) -> List[Dict]:
    """Fetch all messages for a specific chat session from MongoDB."""
    print(f"[DEBUG] get_session_history for session_id={session_id}")
    db = get_database()
    messages = list(db.chat_messages.find({"session_id": session_id}).sort("created_at", 1))
    print(f"[DEBUG] Found {len(messages)} messages")
    return [
        {
            "role": m["role"],
            "content": m["content"],
            "created_at": m["created_at"],
            "sources": m.get("sources"),
            "latency": m.get("latency"),
            "mode": m.get("mode")
        } for m in messages
    ]


async def update_session_title(session_id: str, new_title: str):
    """Update the title of a specific chat session in MongoDB."""
    db = get_database()
    db.chat_sessions.update_one(
        {"id": session_id},
        {"$set": {"title": new_title, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    print(f"[DEBUG] Session {session_id} renamed to: {new_title}")
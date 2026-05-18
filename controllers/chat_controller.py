"""
controllers/chat_controller.py — Business logic for the Chat endpoint.

Flow:
    Frontend  →  REST API (this file)  →  RAG API (CogniLex-RAG on port 8001)

The controller forwards the user's question to the RAG FastAPI server at
RAG_API_URL/ask and relays the full response back to the frontend.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException, status

from config.cognilex_db import get_database
from models.chat import ChatRequest

load_dotenv()

logger = logging.getLogger("chat_controller")

# ── RAG service URL ────────────────────────────────────────────────────────────
RAG_API_URL: str = os.getenv("RAG_API_URL", "http://localhost:8001")


async def ask_rag(request: ChatRequest) -> dict:
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
    def _normalize_mode(m: str | None) -> str | None:
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

        # Ensure expected keys exist and have safe types for the frontend/schema
        data["sources"] = data.get("sources", []) or []
        data["related_cases"] = data.get("related_cases", []) or []
        data["latency"] = data.get("latency", "")
        data["mode"] = data.get("mode") or (normalized_mode or "legal")

        # 3. Save Bot Response
        # Persist the bot reply we received from the RAG service. Ensure the
        # stored mode is one of the expected values (fallback to 'legal').
        bot_msg = {
            "session_id": session_id,
            "role": "bot",
            "content": data.get("answer", ""),
            "sources": data.get("sources", []),
            # related_cases may be a list of dicts with metadata about similar cases
            "related_cases": data.get("related_cases", []),
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


async def get_sessions(user_id: str) -> list[dict]:
    """Fetch all chat sessions for a specific user from MongoDB."""
    print(f"[DEBUG] get_sessions for user_id={user_id}")
    db = get_database()
    sessions = list(db.chat_sessions.find({"user_id": user_id}).sort("updated_at", -1))
    print(f"[DEBUG] Found {len(sessions)} sessions")
    return [{"id": s["id"], "title": s["title"], "updated_at": s["updated_at"]} for s in sessions]


async def get_session_history(session_id: str) -> list[dict]:
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
            "mode": m.get("mode"),
            "related_cases": m.get("related_cases", [])
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


async def delete_session(session_id: str) -> dict:
    """Delete a chat session and all its messages from MongoDB."""
    db = get_database()
    session = db.chat_sessions.find_one({"id": session_id})
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    # Delete all messages belonging to this session
    msg_result = db.chat_messages.delete_many({"session_id": session_id})
    # Delete the session itself
    db.chat_sessions.delete_one({"id": session_id})
    print(f"[DEBUG] Deleted session {session_id} and {msg_result.deleted_count} messages")
    return {"deleted": True, "messages_removed": msg_result.deleted_count}


async def guest_mode_chat(request: ChatRequest) -> dict:
    """
    Forward a guest mode question to the CogniLex RAG service's /guest_mode endpoint.

    This is used for unauthenticated users accessing the guest chat on the homepage.
    No session or user tracking is required.
    Uses meta-llama/llama-4-scout-17b-16e-instruct for direct LLM response (no RAG).
    """
    db = get_database()
    print(f"[DEBUG] guest_mode_chat: question='{request.question[:50]}...'")

    # Log the guest interaction to MongoDB for analytics (optional)
    guest_log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "role": "guest",
        "question": request.question.strip(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    try:
        db.guest_interactions.insert_one(guest_log)
    except Exception as e:
        logger.warning(f"Failed to log guest interaction: {e}")

    # Build payload for the RAG /guest_mode endpoint
    payload = {
        "question": request.question.strip(),
        "user_id": "guest_user",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            rag_response = await client.post(
                f"{RAG_API_URL}/guest_mode",
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
            logger.error(f"RAG guest_mode service error: {rag_response.status_code} — {detail}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=detail,
            )

        data = rag_response.json()

        # Normalize fields so frontend and schemas always receive consistent types
        data["sources"] = data.get("sources", []) or []
        data["related_cases"] = data.get("related_cases", []) or []
        data["latency"] = data.get("latency", "")
        data["mode"] = data.get("mode") or "research"

        # Persist the bot reply for guest interactions for analytics/debugging
        guest_response = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "role": "bot",
            "question": request.question.strip(),
            "answer": data.get("answer", ""),
            "sources": data.get("sources", []),
            "related_cases": data.get("related_cases", []),
            "latency": data.get("latency", ""),
            "mode": data.get("mode", ""),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        try:
            db.guest_interactions.insert_one(guest_response)
        except Exception as e:
            logger.warning(f"Failed to persist guest response: {e}")

        logger.info(
            f"RAG guest_mode response: "
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
        logger.error("RAG guest_mode request timed out")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="RAG service took too long to respond. Please try again.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error calling RAG guest_mode service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your request.",
        )


# ── Share Chat Functions ──────────────────────────────────────────────────────

async def create_share(session_id: str) -> dict:
    """
    Generate a unique share_id for the given chat session and persist it.
    Returns { share_id }. Idempotent — re-sharing the same session returns
    the existing share_id if one already exists.
    """
    db = get_database()
    session = db.chat_sessions.find_one({"id": session_id})
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )

    # Reuse existing share_id if already shared
    existing_share_id = session.get("share_id")
    if existing_share_id:
        logger.info(f"[create_share] Session {session_id} already shared as {existing_share_id}")
        return {"share_id": existing_share_id}

    share_id = str(uuid.uuid4())
    db.chat_sessions.update_one(
        {"id": session_id},
        {"$set": {"share_id": share_id, "shared_at": datetime.now(timezone.utc).isoformat()}}
    )
    logger.info(f"[create_share] Session {session_id} shared as {share_id}")
    return {"share_id": share_id}


async def get_shared_chat(share_id: str) -> dict:
    """
    Fetch the session and its messages for the given share_id.
    Returns { title, sharedBy, messages[] }. No auth required.
    """
    db = get_database()
    session = db.chat_sessions.find_one({"share_id": share_id})
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shared chat '{share_id}' not found or link is invalid.",
        )

    session_id = session["id"]
    messages_raw = list(
        db.chat_messages.find({"session_id": session_id}).sort("created_at", 1)
    )
    messages = [
        {
            "role": m["role"],
            "content": m["content"],
            "created_at": m["created_at"],
            "sources": m.get("sources", []),
            "related_cases": m.get("related_cases", []),
            "latency": m.get("latency"),
            "mode": m.get("mode"),
        }
        for m in messages_raw
    ]

    return {
        "title": session.get("title", "Untitled Legal Chat"),
        "sharedBy": session.get("user_id", "Unknown"),
        "sharedAt": session.get("shared_at", session.get("updated_at", "")),
        "messages": messages,
    }


async def save_shared_chat(share_id: str, new_user_id: str) -> dict:
    """
    Clone the shared chat session into a brand-new session owned by new_user_id.
    Returns { new_session_id }.
    """
    db = get_database()
    session = db.chat_sessions.find_one({"share_id": share_id})
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shared chat '{share_id}' not found.",
        )

    # Fetch original messages
    original_messages: list[Any] = list(
        db.chat_messages.find({"session_id": session["id"]}).sort("created_at", 1)
    )

    # Create new session
    new_session_id = str(uuid.uuid4())
    new_session = {
        "id": new_session_id,
        "user_id": new_user_id,
        "title": f"[Saved] {session.get('title', 'Shared Chat')}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    db.chat_sessions.insert_one(new_session)

    # Clone messages under new session_id
    if original_messages:
        cloned_messages = []
        for m in original_messages:
            cloned = {
                "session_id": new_session_id,
                "role": m.get("role", "user"),
                "content": m.get("content", ""),
                "created_at": m.get("created_at", datetime.now(timezone.utc).isoformat()),
                "sources": m.get("sources", []),
                "related_cases": m.get("related_cases", []),
                "latency": m.get("latency"),
                "mode": m.get("mode"),
            }
            cloned_messages.append(cloned)
        db.chat_messages.insert_many(cloned_messages)

    logger.info(
        f"[save_shared_chat] share_id={share_id} cloned to session={new_session_id} "
        f"for user={new_user_id} ({len(original_messages)} messages)"
    )
    return {"new_session_id": new_session_id}

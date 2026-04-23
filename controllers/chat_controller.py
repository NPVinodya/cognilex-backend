"""
controllers/chat_controller.py — Business logic for the Chat endpoint.

Flow:
    Frontend  →  REST API (this file)  →  RAG API (CogniLex-RAG on port 8001)

The controller forwards the user's question to the RAG FastAPI server at
RAG_API_URL/ask and relays the full response back to the frontend.
"""

import os
import logging
from typing import Dict

import httpx
from fastapi import HTTPException, status
from dotenv import load_dotenv

from models.chat import ChatRequest

load_dotenv()

logger = logging.getLogger("chat_controller")

# ── RAG service URL ────────────────────────────────────────────────────────────
# Set RAG_API_URL in .env  (e.g. http://localhost:8001  or  http://168.144.103.11:8001)
RAG_API_URL: str = os.getenv("RAG_API_URL", "http://localhost:8001")


async def ask_rag(request: ChatRequest) -> Dict:
    """
    Forward a chat question to the CogniLex RAG service and return its response.

    RAG endpoint: POST {RAG_API_URL}/ask
    RAG request body : { question: str, user_id: str }
    RAG response body: { answer: str, mode: str, sources: list[str], latency: str }
    """
    payload = {
        "question": request.question.strip(),
        "user_id": request.user_id or "guest_user",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            rag_response = await client.post(
                f"{RAG_API_URL}/ask",
                json=payload,
                headers={"Content-Type": "application/json"},
            )

        # ── Relay non-2xx errors from RAG as 502 Bad Gateway ──────────────────
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
        logger.info(
            f"RAG response: user_id={payload['user_id']} "
            f"latency={data.get('latency', 'N/A')} "
            f"mode={data.get('mode', 'N/A')}"
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
        raise  # re-raise FastAPI exceptions as-is
    except Exception as e:
        logger.exception(f"Unexpected error calling RAG service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your request.",
        )

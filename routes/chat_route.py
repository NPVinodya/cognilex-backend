"""
routes/chat_route.py — REST API routes for the CogniLex AI chat.

Registered prefix: /chat
Full endpoint exposed: POST /chat/ask
"""

from fastapi import APIRouter, HTTPException, status

from models.chat import ChatRequest, ChatResponse
from controllers.chat_controller import ask_rag

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "/ask",
    response_model=ChatResponse,
    summary="Send a legal question to the RAG AI",
    description=(
        "Accepts a user question, forwards it to the CogniLex RAG service, "
        "and returns the AI-generated legal answer along with source citations "
        "and response metadata."
    ),
)
async def chat_ask(request: ChatRequest):
    """
    POST /chat/ask

    Body:
        question  (str)  — the legal question
        user_id   (str)  — optional user identifier for RAG session memory

    Returns:
        answer    (str)  — AI-generated legal response
        mode      (str)  — model/mode used by the RAG engine
        sources   (list) — cited source documents
        latency   (str)  — RAG processing time
    """
    try:
        return await ask_rag(request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat processing error: {str(e)}",
        )


@router.get(
    "/health",
    summary="Check RAG service connectivity",
    description="Pings the RAG API to verify it is reachable from this REST API.",
)
async def chat_health():
    """
    GET /chat/health — verify connectivity to the RAG service.
    """
    import os, httpx
    rag_url = os.getenv("RAG_API_URL", "http://localhost:8001")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{rag_url}/health")
        return {
            "rest_api": "ok",
            "rag_service": "ok" if res.status_code == 200 else "degraded",
            "rag_url": rag_url,
            "rag_response": res.json() if res.status_code == 200 else res.text,
        }
    except Exception as e:
        return {
            "rest_api": "ok",
            "rag_service": "unreachable",
            "rag_url": rag_url,
            "error": str(e),
        }

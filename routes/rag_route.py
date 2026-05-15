"""
routes/rag_route.py — Admin RAG Document Management proxy.

Proxies file-management requests from the CogniLex backend (port 8000)
to the RAG server (port 8001).

Endpoints exposed:
  POST   /rag/upload                      — Upload a PDF to acts/ or cases/
  GET    /rag/documents                   — List all documents
  DELETE /rag/documents/{type}/{filename} — Delete a specific document
  POST   /rag/reindex                     — Trigger RAG index rebuild
  GET    /rag/health                      — RAG server health check
"""

import os
import io

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter(prefix="/rag", tags=["RAG Management"])

RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://localhost:8001")
REQUEST_TIMEOUT = 180  # seconds — reindex can be slow


def _rag_url(path: str) -> str:
    return f"{RAG_SERVER_URL.rstrip('/')}/{path.lstrip('/')}"


# ════════════════════════════════════════════════════════════
#  HEALTH
# ════════════════════════════════════════════════════════════
@router.get("/health")
async def rag_health():
    """Check RAG server availability."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(_rag_url("/health"))
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="RAG server is unreachable.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
#  UPLOAD
# ════════════════════════════════════════════════════════════
@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    file_type: str   = Form(..., description="'acts' or 'cases'"),
):
    """
    Proxy: upload a PDF to the RAG server's acts/ or cases/ folder.
    """
    if file_type not in {"acts", "cases"}:
        raise HTTPException(status_code=400, detail="file_type must be 'acts' or 'cases'.")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    contents = await file.read()

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(
                _rag_url("/documents/upload"),
                files={"file": (file.filename, io.BytesIO(contents), "application/pdf")},
                data={"file_type": file_type},
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail", "Upload failed."))
        return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="RAG server is unreachable.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
#  LIST
# ════════════════════════════════════════════════════════════
@router.get("/documents")
async def list_documents():
    """
    Proxy: list all PDFs on the RAG server (acts + cases).
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(_rag_url("/documents/list"))
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Failed to fetch document list.")
        return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="RAG server is unreachable.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
#  DELETE
# ════════════════════════════════════════════════════════════
@router.delete("/documents/{file_type}/{filename}")
async def delete_document(file_type: str, filename: str):
    """
    Proxy: delete a PDF from the RAG server.
    """
    if file_type not in {"acts", "cases"}:
        raise HTTPException(status_code=400, detail="file_type must be 'acts' or 'cases'.")
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.delete(_rag_url(f"/documents/{file_type}/{filename}"))
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="File not found on RAG server.")
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Delete failed.")
        return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="RAG server is unreachable.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
#  REINDEX
# ════════════════════════════════════════════════════════════
@router.post("/reindex")
async def reindex():
    """
    Proxy: trigger a RAG index rebuild on the RAG server.
    This is a slow operation (30-120s).
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(_rag_url("/documents/reindex"))
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Reindex failed.")
        return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="RAG server is unreachable.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

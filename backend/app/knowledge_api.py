import json
import re
import urllib.error
import urllib.request
from collections import Counter

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .knowledge_models import KnowledgeChunk, KnowledgeDocument
from .models import User, UserRole
from .module_api import require_enabled_module
from .security import get_current_user, require_roles
from .services import AuditService

rag_router = APIRouter(prefix="/rag", tags=["rag"], dependencies=[Depends(require_enabled_module("rag"))])
ai_router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(require_enabled_module("ai"))])
settings = get_settings()

STOPWORDS = {
    "de", "del", "la", "las", "el", "los", "un", "una", "unos", "unas", "y", "o", "a", "al",
    "en", "por", "para", "con", "sin", "que", "qué", "como", "cómo", "cual", "cuál", "cuales",
    "cuáles", "es", "son", "se", "si", "sí", "mi", "mis", "tu", "tus", "su", "sus", "lo", "me",
    "te", "necesito", "puedo", "debo", "hay", "sobre",
}


class KnowledgeIn(BaseModel):
    source_key: str = Field(min_length=2, max_length=180)
    title: str = Field(min_length=2, max_length=240)
    source_type: str = Field(default="manual", max_length=40)
    content: str = Field(min_length=1, max_length=200000)


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10)


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-záéíóúüñ0-9]{2,}", text.lower())
        if token not in STOPWORDS
    ]


def split_content(content: str, max_chars: int = 1800) -> list[str]:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", content) if item.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > max_chars:
            chunks.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars:]
        current = paragraph
    if current:
        chunks.append(current)
    return chunks or [content[:max_chars]]


def retrieve(db: Session, tenant_id: str, question: str, limit: int) -> list[dict]:
    query_terms = Counter(tokenize(question))
    if not query_terms:
        return []
    rows = db.execute(
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeChunk.tenant_id == tenant_id)
    ).all()
    scored = []
    for chunk, document in rows:
        terms = Counter(tokenize(chunk.content))
        overlap = {term for term in query_terms if terms.get(term, 0) > 0}
        score = sum(min(count, terms.get(term, 0)) for term, count in query_terms.items())
        # A single meaningful exact term is accepted; stopwords have already been removed.
        # This keeps retrieval useful for product/policy names while rejecting accidental matches
        # such as common Spanish prepositions.
        if score > 0 and overlap:
            scored.append((score, len(overlap), chunk, document))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [
        {
            "chunk_id": chunk.id,
            "document_id": document.id,
            "title": document.title,
            "source_key": document.source_key,
            "score": score,
            "matched_terms": overlap_count,
            "content": chunk.content,
        }
        for score, overlap_count, chunk, document in scored[:limit]
    ]


def ollama_generate(question: str, sources: list[dict]) -> str | None:
    if not settings.ollama_url:
        return None
    context = "\n\n".join(f"[{index + 1}] {item['title']}\n{item['content']}" for index, item in enumerate(sources))
    prompt = (
        "Responde en español usando únicamente el contexto proporcionado. "
        "Si el contexto no contiene la respuesta, dilo claramente. Cita fuentes como [1], [2].\n\n"
        f"CONTEXTO:\n{context}\n\nPREGUNTA:\n{question}"
    )
    payload = json.dumps({"model": settings.ollama_model, "prompt": prompt, "stream": False}).encode("utf-8")
    request = urllib.request.Request(
        f"{settings.ollama_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.ai_timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
            return str(data.get("response", "")).strip() or None
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


@rag_router.post("/documents", status_code=201)
def add_document(
    payload: KnowledgeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPPORT)),
) -> dict:
    existing = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == user.tenant_id,
            KnowledgeDocument.source_key == payload.source_key,
        )
    )
    if existing:
        chunks = db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.document_id == existing.id)).all()
        for chunk in chunks:
            db.delete(chunk)
        existing.title = payload.title
        existing.source_type = payload.source_type
        document = existing
    else:
        document = KnowledgeDocument(
            tenant_id=user.tenant_id,
            source_key=payload.source_key,
            title=payload.title,
            source_type=payload.source_type,
        )
        db.add(document)
        db.flush()
    pieces = split_content(payload.content)
    for index, content in enumerate(pieces):
        db.add(
            KnowledgeChunk(
                tenant_id=user.tenant_id,
                document_id=document.id,
                chunk_index=index,
                content=content,
            )
        )
    AuditService.record(
        db,
        user,
        "knowledge.upserted",
        "knowledge_document",
        document.id,
        {"source_key": document.source_key, "chunks": len(pieces)},
    )
    db.commit()
    return {"id": document.id, "source_key": document.source_key, "chunks": len(pieces)}


@rag_router.post("/search")
def search_knowledge(payload: AskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return {"query": payload.question, "sources": retrieve(db, user.tenant_id, payload.question, payload.limit)}


@ai_router.post("/ask")
def ask(payload: AskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    sources = retrieve(db, user.tenant_id, payload.question, payload.limit)
    if not sources:
        return {
            "answer": "No encontré información suficiente en el conocimiento autorizado para responder.",
            "mode": "no_context",
            "sources": [],
        }
    generated = ollama_generate(payload.question, sources)
    if generated:
        return {
            "answer": generated,
            "mode": "ollama_rag",
            "model": settings.ollama_model,
            "sources": sources,
        }
    evidence = "\n\n".join(
        f"[{index + 1}] {item['title']}: {item['content']}" for index, item in enumerate(sources)
    )
    return {"answer": evidence, "mode": "retrieval_only", "sources": sources}

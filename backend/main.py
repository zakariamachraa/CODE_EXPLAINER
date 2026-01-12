from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from rag import CodeExplainerRAG, IngestionPayload

# Fix path resolution - works from both project root and backend directory
DATA_PATH = Path(
    os.getenv("CODE_EXPLAINER_DATA") 
    or str(Path(__file__).parent.parent / "data" / "code_samples.json")
)
MODEL_NAME = os.getenv("CODE_EXPLAINER_EMBEDDER", "sentence-transformers/all-MiniLM-L6-v2")

app = FastAPI(title="Code Explainer AI", version="1.0.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

rag_pipeline = CodeExplainerRAG(data_path=DATA_PATH, embedder_name=MODEL_NAME)


class ExplainRequest(BaseModel):
    code: str = Field(..., min_length=10, description="Source code snippet to explain")
    language: Optional[str] = Field(None, description="Optional language override")


class LineExplanation(BaseModel):
    line_number: int
    code: str
    explanation: str


class ExplainResponse(BaseModel):
    language: str
    summary: str
    reasoning: list[str]
    line_by_line: list[LineExplanation]
    references: list[dict]


class IngestRequest(BaseModel):
    language: str
    title: str
    code_fragment: str
    explanation: str
    tags: list[str] = []


@app.on_event("startup")
async def startup() -> None:
    """Load the RAG pipeline on startup."""
    try:
        print(f"Loading knowledge base from: {DATA_PATH}")
        rag_pipeline.load()
        print("Knowledge base loaded successfully!")
    except Exception as e:
        print(f"Error loading knowledge base: {e}")
        raise


@app.on_event("shutdown")
async def shutdown() -> None:
    """Cleanup on shutdown."""
    print("Shutting down...")


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "loaded": len(rag_pipeline.db.entries) > 0}


@app.post("/explain", response_model=ExplainResponse)
async def explain(payload: ExplainRequest) -> ExplainResponse:
    """Explain code using RAG."""
    if not payload.code.strip():
        raise HTTPException(status_code=400, detail="Code snippet cannot be empty")

    result = rag_pipeline.explain(code=payload.code, language_hint=payload.language)
    return ExplainResponse(**result)


@app.post("/ingest")
async def ingest(payload: IngestRequest) -> dict:
    """Add new code example to knowledge base."""
    rag_pipeline.ingest(
        IngestionPayload(
            language=payload.language,
            title=payload.title,
            code_fragment=payload.code_fragment,
            explanation=payload.explanation,
            tags=payload.tags,
        )
    )
    return {"status": "ingested", "total_examples": len(rag_pipeline.db.entries)}
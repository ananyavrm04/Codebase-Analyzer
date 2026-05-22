"""
Codebase Analyzer v2 — FastAPI entry point.

Endpoints:
  POST /index               Submit a GitHub repo for async semantic indexing
  GET  /index/{job_id}/status  Poll indexing job status
  POST /search              Semantic search over an indexed repo
  POST /ask                 Q&A over an indexed codebase (RAG)
  GET  /health              Health check
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import asyncio
import hashlib
import os
import shutil
from typing import Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.responses import FileResponse

from app.github_utils import fetch_repo_zip, unzip_file
from app.file_analyzer import get_python_files
from app.chunker import chunk_python_file, ChunkStrategy
from app.indexer import RepoIndex
from app.llm_client import answer_with_context
from app.rate_limiter import RateLimitMiddleware
from app.security import validate_repo_url, check_repo_size

app = FastAPI(
    title="Codebase Analyzer",
    description="Semantic code search and Q&A over GitHub repositories using FAISS + LLMs",
    version="2.0.0",
)


app.add_middleware(RateLimitMiddleware)
# In-memory job store — swap for Redis in production
_jobs: dict[str, dict] = {}


# ── Request / Response models ──────────────────────────────────────────────────

class IndexRequest(BaseModel):
    repo_url: str
    strategy: ChunkStrategy = ChunkStrategy.FUNCTION


class SearchRequest(BaseModel):
    repo_url: str
    query: str
    top_k: int = 5


class AskRequest(BaseModel):
    repo_url: str
    question: str
    top_k: int = 5


# ── Helpers ────────────────────────────────────────────────────────────────────

def _repo_id(url: str) -> str:
    """Stable short ID for a repo URL."""
    return hashlib.md5(url.strip().lower().encode()).hexdigest()[:12]


# ── Background indexing task ───────────────────────────────────────────────────

async def _run_indexing(repo_url: str, strategy: ChunkStrategy, job_id: str):
    tmp_dir = f"/tmp/codebase_{job_id}"
    try:
        # Security: check repo size before downloading
        _jobs[job_id].update({"status": "validating"})
        repo_info = check_repo_size(repo_url)
        _jobs[job_id].update({"status": "downloading", **repo_info})

        zip_path = await asyncio.to_thread(
            fetch_repo_zip, repo_url, download_dir=tmp_dir
        )

        extract_dir = os.path.join(tmp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        await asyncio.to_thread(unzip_file, zip_path, extract_dir)

        _jobs[job_id].update({"status": "chunking"})
        py_files = [f for f in get_python_files(extract_dir) if not f.endswith("__init__.py")]

        if not py_files:
            raise ValueError("No Python files found in repository.")

        all_chunks = []
        for fp in py_files:
            all_chunks.extend(chunk_python_file(fp, strategy=strategy))

        if not all_chunks:
            raise ValueError("No code chunks produced — repository may be empty.")

        _jobs[job_id].update({
            "status": "indexing",
            "chunks_found": len(all_chunks),
            "files_found": len(py_files),
        })

        repo_idx = RepoIndex(job_id)
        stats = await asyncio.to_thread(repo_idx.build, all_chunks)

        _jobs[job_id].update({"status": "done", **stats})

    except Exception as exc:
        _jobs[job_id].update({"status": "failed", "error": str(exc)})

    finally:
        # Clean up temp files — don't leave extracted repos on disk
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── API endpoints ──────────────────────────────────────────────────────────────

@app.post("/index", summary="Submit a GitHub repo for semantic indexing")
async def index_repo(req: IndexRequest, background_tasks: BackgroundTasks):
    # Security: validate URL + SSRF check before anything else
    try:
        validate_repo_url(req.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    job_id = _repo_id(req.repo_url)

    # Skip re-indexing if already done
    if _jobs.get(job_id, {}).get("status") == "done" and RepoIndex.exists(job_id):
        return {"job_id": job_id, "status": "already_indexed"}

    # Prevent duplicate concurrent jobs
    if _jobs.get(job_id, {}).get("status") in ("downloading", "chunking", "indexing"):
        return {"job_id": job_id, "status": "in_progress"}

    _jobs[job_id] = {"status": "queued", "repo_url": req.repo_url, "strategy": req.strategy}
    background_tasks.add_task(_run_indexing, req.repo_url, req.strategy, job_id)

    return {"job_id": job_id, "status": "queued"}


@app.get("/index/{job_id}/status", summary="Poll indexing job status")
def index_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return _jobs[job_id]


@app.post("/search", summary="Semantic search over an indexed repo")
def semantic_search(req: SearchRequest):
    job_id = _repo_id(req.repo_url)

    if not RepoIndex.exists(job_id):
        raise HTTPException(
            status_code=404,
            detail="Repository not indexed. POST /index first and wait for status=done.",
        )

    idx = RepoIndex(job_id)
    results = idx.search(req.query, top_k=req.top_k)

    return {
        "query": req.query,
        "search_ms": results[0][0].get("_search_ms") if results else None,
        "results": [
            {
                "file": r[0]["file_path"],
                "name": r[0]["name"],
                "type": r[0]["chunk_type"],
                "lines": f"{r[0]['start_line']}–{r[0]['end_line']}",
                "score": round(r[1], 4),
                "preview": r[0]["content"][:400],
            }
            for r in results
        ],
    }


@app.post("/ask", summary="Q&A over an indexed codebase using retrieved context")
def ask_codebase(req: AskRequest):
    job_id = _repo_id(req.repo_url)

    if not RepoIndex.exists(job_id):
        raise HTTPException(
            status_code=404,
            detail="Repository not indexed. POST /index first and wait for status=done.",
        )

    idx = RepoIndex(job_id)
    context_chunks = idx.search(req.question, top_k=req.top_k)
    answer = answer_with_context(req.question, context_chunks)

    return {
        "question": req.question,
        "answer": answer,
        "sources": [
            {
                "file": c[0]["file_path"],
                "name": c[0]["name"],
                "lines": f"{c[0]['start_line']}–{c[0]['end_line']}",
            }
            for c in context_chunks
        ],
    }

@app.get("/", include_in_schema=False)
def serve_frontend():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}

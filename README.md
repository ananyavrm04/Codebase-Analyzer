# Codebase Analyzer

Semantic code search and Q&A over GitHub repositories. Give it a repo URL — it downloads, parses, chunks by AST, embeds with sentence-transformers, indexes with FAISS HNSW, and lets you search or ask questions in sub-200ms.

## How it works

```
POST /index  →  Download repo  →  Parse .py files  →  AST chunk (function/class)
                                                           ↓
              FAISS HNSW index  ←  Embed chunks  ←  sentence-transformers
                    ↓
POST /search  →  Embed query  →  FAISS top-k  →  Ranked code chunks (sub-200ms)
POST /ask     →  Embed query  →  FAISS top-k  →  LLM answers with context (RAG)
```

## Key design decisions

**AST-based chunking over character splits.** Each chunk is a complete Python function or class extracted via `ast.parse()`, not an arbitrary 500-character window. This means embeddings capture real semantic units — a full function with its docstring, not half of one function and half of another. Falls back to sliding-window for files with syntax errors.

**FAISS HNSW over IVF.** Codebase repos produce < 100k chunks. HNSW gives sub-10ms search with high recall at this scale, no training step needed. IVF is better for millions of vectors — overkill here.

**Configurable embeddings.** Default: `all-MiniLM-L6-v2` via sentence-transformers (local, free, 384-dim). Set `EMBEDDING_PROVIDER=openai` for OpenAI `text-embedding-3-small` (1536-dim, paid). Swap models via env var — zero code changes.

**LLM fallback chain.** Groq (primary, free) → Together AI → Anthropic Claude. If the primary LLM fails, the Q&A endpoint automatically routes to the fallback.

**Async indexing.** Indexing is a background task — POST `/index` returns immediately with a `job_id`. Poll `/index/{job_id}/status` for progress. No request timeouts on large repos.

## API

### `POST /index` — Index a repository
```json
{
  "repo_url": "https://github.com/psf/requests",
  "strategy": "function"
}
```
Returns `{ "job_id": "a1b2c3", "status": "queued" }`. Strategies: `function` (default), `class`, `sliding`.

### `GET /index/{job_id}/status` — Poll indexing progress
```json
{
  "status": "done",
  "chunks_indexed": 847,
  "embed_time_ms": 3200,
  "index_time_ms": 45,
  "index_size_mb": 1.24
}
```

### `POST /search` — Semantic search
```json
{
  "repo_url": "https://github.com/psf/requests",
  "query": "how are SSL certificates verified",
  "top_k": 5
}
```
Returns ranked code chunks with file path, function name, line numbers, and similarity score.

### `POST /ask` — Q&A with context retrieval (RAG)
```json
{
  "repo_url": "https://github.com/psf/requests",
  "question": "How does the retry mechanism work?"
}
```
Retrieves relevant chunks via FAISS, passes them as context to the LLM, returns a natural-language answer with source citations.

## Project structure

```
Codebase-Analyzer/
├── app/
│   ├── github_utils.py     # Repo download + ZIP extraction
│   ├── file_analyzer.py    # Python file discovery and parsing
│   ├── chunker.py          # AST-based code chunking (function/class/sliding)
│   ├── embedder.py         # Configurable embeddings (sentence-transformers / OpenAI)
│   ├── indexer.py          # FAISS HNSW index with disk persistence
│   └── llm_client.py       # LLM client with fallback (Together AI / Anthropic)
├── main.py                 # FastAPI app — /index, /search, /ask, /health
├── requirements.txt
├── .env.example
└── .gitignore
```

## Setup

```bash
git clone https://github.com/ananyavrm04/Codebase-Analyzer.git
cd Codebase-Analyzer
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env`:
```bash
# Required — at least one LLM
TOGETHER_API_KEY=your_key_here

# Optional — enables fallback LLM
ANTHROPIC_API_KEY=sk-ant-...

# Optional — use OpenAI embeddings instead of local
# EMBEDDING_PROVIDER=openai
# OPENAI_API_KEY=sk-...
```

Run:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Stack

| Component | Technology |
|---|---|
| Framework | FastAPI |
| Embeddings | sentence-transformers (default) / OpenAI |
| Vector search | FAISS HNSW |
| Code parsing | Python `ast` module |
| LLM | Together AI (primary) / Anthropic (fallback) |
| Async | FastAPI BackgroundTasks + asyncio |

## Performance

| Metric | Value |
|---|---|
| Search latency (FAISS) | < 10ms |
| End-to-end search (embed + search) | < 200ms |
| Indexing (1000 chunks) | ~3-5s |
| Max repo size tested | 80MB+ |

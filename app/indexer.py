"""
FAISS HNSW index manager with disk persistence.

Why HNSW over IVF:
- Codebase repos produce < 100k chunks — HNSW is fast and exact at this scale
- IVF needs a training step and is optimised for millions of vectors
- HNSW gives sub-10ms search with high recall out of the box

Index lives at INDEX_DIR/{repo_id}.faiss + {repo_id}.json (metadata).
"""
import os
import json
import time
import numpy as np
import faiss
from dataclasses import asdict
from typing import List, Tuple

from app.chunker import CodeChunk
from app.embedder import get_embedder

INDEX_DIR = os.getenv("INDEX_DIR", ".indexes")
os.makedirs(INDEX_DIR, exist_ok=True)

HNSW_M = 32              # graph connectivity — higher = better recall, more memory
EF_CONSTRUCTION = 200    # build quality — higher = better graph at build time
EF_SEARCH = 50           # search quality — higher = better recall at query time


class RepoIndex:
    """FAISS HNSW index for a single repository."""

    def __init__(self, repo_id: str):
        self.repo_id = repo_id
        self.index_path = os.path.join(INDEX_DIR, f"{repo_id}.faiss")
        self.meta_path = os.path.join(INDEX_DIR, f"{repo_id}.json")
        self.index: faiss.Index | None = None
        self.chunks: List[dict] = []

    def build(self, chunks: List[CodeChunk]) -> dict:
        """
        Embed all chunks and build the HNSW index.
        Returns build stats for logging/response.
        """
        embedder = get_embedder()
        texts = [c.content for c in chunks]

        # --- Embedding ---
        t0 = time.perf_counter()
        embeddings = embedder.embed(texts)
        embed_ms = (time.perf_counter() - t0) * 1000

        dim = embeddings.shape[1]

        # --- Index construction ---
        self.index = faiss.IndexHNSWFlat(dim, HNSW_M, faiss.METRIC_INNER_PRODUCT)
        self.index.hnsw.efConstruction = EF_CONSTRUCTION
        self.index.hnsw.efSearch = EF_SEARCH

        t1 = time.perf_counter()
        self.index.add(embeddings)
        index_ms = (time.perf_counter() - t1) * 1000

        self.chunks = [asdict(c) for c in chunks]
        self._save()

        return {
            "chunks_indexed": len(chunks),
            "embed_time_ms": round(embed_ms, 1),
            "index_time_ms": round(index_ms, 1),
            "index_size_mb": round(embeddings.nbytes / 1024 / 1024, 2),
        }

    def search(self, query: str, top_k: int = 5) -> List[Tuple[dict, float]]:
        """
        Semantic search over the index.
        Returns list of (chunk_metadata, similarity_score) tuples.
        Typical latency: sub-10ms on repo-scale indexes.
        """
        if self.index is None:
            self._load()

        embedder = get_embedder()

        t0 = time.perf_counter()
        query_vec = embedder.embed([query])
        scores, indices = self.index.search(query_vec, top_k)
        search_ms = (time.perf_counter() - t0) * 1000

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue  # FAISS returns -1 for empty result slots
            chunk = dict(self.chunks[idx])
            chunk["_search_ms"] = round(search_ms, 2)
            results.append((chunk, float(score)))

        return results

    def _save(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.meta_path, "w") as f:
            json.dump(
                {"repo_id": self.repo_id, "chunks": self.chunks},
                f,
                indent=2,
            )

    def _load(self):
        if not os.path.exists(self.index_path):
            raise FileNotFoundError(f"No FAISS index found for repo: {self.repo_id}")
        self.index = faiss.read_index(self.index_path)
        with open(self.meta_path) as f:
            data = json.load(f)
        self.chunks = data["chunks"]

    @classmethod
    def exists(cls, repo_id: str) -> bool:
        return os.path.exists(os.path.join(INDEX_DIR, f"{repo_id}.faiss"))

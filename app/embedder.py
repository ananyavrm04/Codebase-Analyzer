"""
Configurable embedding module.
Default: sentence-transformers all-MiniLM-L6-v2 (local, free, 384-dim).
Switch to OpenAI via EMBEDDING_PROVIDER=openai in .env.

Why sentence-transformers as default:
- Zero API cost — runs locally
- 384-dim vectors → smaller FAISS index, faster search
- all-MiniLM-L6-v2 is strong for code similarity at this dimension
"""
import os
import numpy as np
from typing import List

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))


class Embedder:
    def __init__(self):
        self.provider = EMBEDDING_PROVIDER
        self._model = None

    def _load(self):
        """Lazy-load the model on first use."""
        if self._model is not None:
            return

        if self.provider == "local":
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(EMBEDDING_MODEL)

        elif self.provider == "openai":
            import openai
            self._client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self._model = "loaded"  # sentinel

        else:
            raise ValueError(f"Unknown EMBEDDING_PROVIDER: {self.provider}")

    def embed(self, texts: List[str]) -> np.ndarray:
        """
        Embed a list of strings.
        Returns float32 numpy array of shape (n, embedding_dim).
        Vectors are L2-normalised for cosine similarity via inner product.
        """
        self._load()

        if self.provider == "local":
            embeddings = self._model.encode(
                texts,
                batch_size=64,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            return embeddings.astype(np.float32)

        elif self.provider == "openai":
            response = self._client.embeddings.create(
                model="text-embedding-3-small",
                input=texts,
            )
            vecs = np.array(
                [item.embedding for item in response.data],
                dtype=np.float32,
            )
            # normalise for inner product similarity
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            return vecs / np.maximum(norms, 1e-10)

    @property
    def dimension(self) -> int:
        """Return embedding dimension based on active provider/model."""
        if self.provider == "openai":
            return 1536  # text-embedding-3-small
        return EMBEDDING_DIM


# Module-level singleton — instantiated once, shared across all requests
_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder

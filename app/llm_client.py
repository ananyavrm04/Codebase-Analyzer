"""
LLM client for code Q&A and summarisation.
Primary: Groq (free, fastest inference via LPU).
Fallback: Together AI → Anthropic Claude.
"""
import os
from typing import List, Tuple


# ── Groq (primary — free, fast) ───────────────────────────────────────────────

def _groq_complete(prompt: str, system: str = "", max_tokens: int = 1024) -> str:
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


# ── Together AI (fallback) ────────────────────────────────────────────────────

def _together_complete(prompt: str, system: str = "", max_tokens: int = 1024) -> str:
    from together import Together
    client = Together(api_key=os.getenv("TOGETHER_API_KEY"))

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=os.getenv("TOGETHER_MODEL", "meta-llama/Llama-3-70b-chat-hf"),
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


# ── Anthropic (second fallback) ───────────────────────────────────────────────

def _anthropic_complete(prompt: str, system: str = "", max_tokens: int = 1024) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system or "You are a helpful code assistant.",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ── Router with fallback chain ─────────────────────────────────────────────────

def _complete(prompt: str, system: str = "", max_tokens: int = 1024) -> str:
    """Try Groq → Together AI → Anthropic. First success wins."""
    providers = [
        ("groq", _groq_complete),
        ("together", _together_complete),
        ("anthropic", _anthropic_complete),
    ]

    last_error = None
    for name, fn in providers:
        try:
            return fn(prompt, system, max_tokens)
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")


# ── Public API ─────────────────────────────────────────────────────────────────

def summarize_code(code: str, file_path: str = "") -> str:
    """Summarise a single code file or snippet."""
    system = "You are a senior software engineer. Summarise code concisely."
    prompt = f"""Summarise what this code does in 2-3 sentences.

File: {file_path}
```python
{code[:3000]}
```"""
    return _complete(prompt, system, max_tokens=256)


def answer_with_context(
    question: str,
    context_chunks: List[Tuple[dict, float]],
) -> str:
    """
    RAG-style Q&A: answer a question using retrieved code chunks as context.
    context_chunks comes from RepoIndex.search() — list of (chunk_dict, score).
    """
    if not context_chunks:
        return "No relevant code found for this question."

    # Build context from retrieved chunks
    context_parts = []
    for chunk, score in context_chunks:
        header = f"File: {chunk['file_path']} | {chunk['name']} (lines {chunk['start_line']}-{chunk['end_line']})"
        context_parts.append(f"{header}\n```python\n{chunk['content'][:2000]}\n```")

    context = "\n\n---\n\n".join(context_parts)

    system = (
        "You are a code assistant answering questions about a codebase. "
        "Use ONLY the provided code context to answer. "
        "Cite the file and function name when referencing code. "
        "If the context doesn't contain enough information, say so."
    )

    prompt = f"""Code context (retrieved by semantic search):

{context}

Question: {question}

Answer concisely, citing file/function names:"""

    return _complete(prompt, system, max_tokens=512)

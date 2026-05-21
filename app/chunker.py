"""
AST-based code chunker for Python files.
Supports function-level, class-level, and sliding-window strategies.
Function chunking is the default — one chunk per function/method.
Falls back to sliding window if AST parsing fails.
"""
import ast
import os
from dataclasses import dataclass
from typing import List
from enum import Enum


class ChunkStrategy(str, Enum):
    FUNCTION = "function"       # one chunk per function/method (default)
    CLASS = "class"             # one chunk per class (includes all methods)
    SLIDING_WINDOW = "sliding"  # fixed-size overlapping lines


@dataclass
class CodeChunk:
    content: str
    file_path: str
    start_line: int
    end_line: int
    chunk_type: str   # "function" | "class" | "module" | "window"
    name: str         # function/class name, or filename for module-level chunks


def chunk_python_file(
    file_path: str,
    strategy: ChunkStrategy = ChunkStrategy.FUNCTION,
    window_size: int = 50,
    overlap: int = 10,
) -> List[CodeChunk]:
    """
    Chunk a Python file using the given strategy.
    Returns a list of CodeChunk objects ready for embedding.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            source = f.read()
    except OSError:
        return []

    lines = source.splitlines()

    if strategy == ChunkStrategy.SLIDING_WINDOW:
        return _sliding_window_chunks(source, file_path, window_size, overlap)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        # file has syntax errors — fall back gracefully
        return _sliding_window_chunks(source, file_path, window_size, overlap)

    chunks: List[CodeChunk] = []

    for node in ast.walk(tree):
        if strategy == ChunkStrategy.FUNCTION and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            chunk = _node_to_chunk(node, lines, file_path, "function")
            if chunk:
                chunks.append(chunk)

        elif strategy == ChunkStrategy.CLASS and isinstance(node, ast.ClassDef):
            chunk = _node_to_chunk(node, lines, file_path, "class")
            if chunk:
                chunks.append(chunk)

    # No AST-level chunks found — treat whole file as one chunk
    if not chunks:
        chunks.append(
            CodeChunk(
                content=source[:4000],
                file_path=file_path,
                start_line=1,
                end_line=len(lines),
                chunk_type="module",
                name=os.path.basename(file_path),
            )
        )

    return chunks


def _node_to_chunk(
    node: ast.AST,
    lines: List[str],
    file_path: str,
    chunk_type: str,
) -> CodeChunk | None:
    start = node.lineno - 1
    end = node.end_lineno
    content = "\n".join(lines[start:end])

    if len(content.strip()) < 10:
        return None  # skip trivial stubs

    return CodeChunk(
        content=content[:4000],  # cap to stay within embedding token limits
        file_path=file_path,
        start_line=node.lineno,
        end_line=node.end_lineno,
        chunk_type=chunk_type,
        name=getattr(node, "name", os.path.basename(file_path)),
    )


def _sliding_window_chunks(
    source: str,
    file_path: str,
    window_size: int,
    overlap: int,
) -> List[CodeChunk]:
    lines = source.splitlines()
    step = max(1, window_size - overlap)
    chunks = []

    for i in range(0, len(lines), step):
        window = lines[i : i + window_size]
        content = "\n".join(window)
        if content.strip():
            chunks.append(
                CodeChunk(
                    content=content[:4000],
                    file_path=file_path,
                    start_line=i + 1,
                    end_line=min(i + window_size, len(lines)),
                    chunk_type="window",
                    name=f"{os.path.basename(file_path)}:L{i + 1}",
                )
            )

    return chunks

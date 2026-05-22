"""
Security utilities: SSRF protection, input validation, repo size limits.
All limits configurable via env vars — nothing hardcoded.

Protections:
  1. SSRF: blocks private IPs, loopback, AWS metadata, non-HTTPS schemes
  2. Input validation: only GitHub URLs in expected format
  3. Size limit: checks repo size via GitHub API before downloading
"""
import os
import re
import socket
import ipaddress
from urllib.parse import urlparse

MAX_REPO_SIZE_MB = int(os.getenv("MAX_REPO_SIZE_MB", "100"))

# GitHub URL pattern: https://github.com/{owner}/{repo} with optional .git
GITHUB_URL_PATTERN = re.compile(
    r"^https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(\.git)?/?$"
)

# Blocked IP ranges — private networks, loopback, link-local, metadata
BLOCKED_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),       # loopback
    ipaddress.ip_network("10.0.0.0/8"),         # private class A
    ipaddress.ip_network("172.16.0.0/12"),      # private class B
    ipaddress.ip_network("192.168.0.0/16"),     # private class C
    ipaddress.ip_network("169.254.0.0/16"),     # link-local — AWS metadata endpoint
    ipaddress.ip_network("0.0.0.0/8"),          # unspecified
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 private
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]


def validate_repo_url(url: str) -> str:
    """
    Validate and sanitize a repository URL.
    Returns cleaned URL or raises ValueError with reason.

    Checks:
      - HTTPS only (blocks file://, ftp://, http://)
      - GitHub.com domain only
      - Valid {owner}/{repo} format
      - DNS resolves to non-private IP (SSRF protection)
    """
    url = url.strip()

    # ── Scheme check ──────────────────────────────────────────────
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(
            f"Only HTTPS URLs are allowed. Received scheme: '{parsed.scheme or 'none'}'"
        )

    # ── Format check ──────────────────────────────────────────────
    if not GITHUB_URL_PATTERN.match(url):
        raise ValueError(
            "Invalid repository URL. "
            "Expected: https://github.com/{owner}/{repo}"
        )

    # ── SSRF: DNS resolution check ───────────────────────────────
    hostname = parsed.hostname
    try:
        resolved = socket.getaddrinfo(hostname, None)
        for entry in resolved:
            ip = ipaddress.ip_address(entry[4][0])
            for blocked in BLOCKED_RANGES:
                if ip in blocked:
                    raise ValueError(
                        f"Blocked: URL resolves to private/reserved IP range ({ip})"
                    )
    except socket.gaierror:
        raise ValueError(f"Could not resolve hostname: {hostname}")

    return url


def check_repo_size(url: str) -> dict:
    """
    Check repository size via GitHub API before downloading.
    Raises ValueError if repo exceeds MAX_REPO_SIZE_MB.
    Returns repo metadata dict on success.

    Degrades gracefully: if GitHub API fails, allows the request through.
    """
    import httpx

    # Extract owner/repo from URL
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").replace(".git", "").split("/")
    if len(path_parts) < 2:
        raise ValueError("Could not extract owner/repo from URL")

    owner, repo = path_parts[0], path_parts[1]
    api_url = f"https://api.github.com/repos/{owner}/{repo}"

    try:
        resp = httpx.get(api_url, timeout=10, follow_redirects=True)

        if resp.status_code == 404:
            raise ValueError(f"Repository not found: {owner}/{repo}")

        if resp.status_code != 200:
            # GitHub API rate limit or other issue — don't block, allow through
            return {"size_mb": -1, "check_skipped": True}

        data = resp.json()
        size_kb = data.get("size", 0)
        size_mb = size_kb / 1024

        if size_mb > MAX_REPO_SIZE_MB:
            raise ValueError(
                f"Repository too large: {size_mb:.1f}MB "
                f"(limit: {MAX_REPO_SIZE_MB}MB — configurable via MAX_REPO_SIZE_MB env var)"
            )

        return {
            "size_mb": round(size_mb, 2),
            "full_name": data.get("full_name"),
        }

    except httpx.RequestError:
        # Network error hitting GitHub API — allow through
        return {"size_mb": -1, "check_skipped": True}

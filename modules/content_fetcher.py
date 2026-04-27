"""Lightweight full-content fetcher for external-learning candidates."""

from __future__ import annotations

import re
import subprocess
import tempfile
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"}
try:
    import sys
    from pathlib import Path as _Path
    _parent = _Path(__file__).resolve().parent.parent.parent.parent.parent
    if str(_parent) not in sys.path:
        sys.path.insert(0, str(_parent))
    from runtime_config import WORKSPACE as WORKSPACE_ROOT
except ImportError:
    WORKSPACE_ROOT = _Path("/root/.openclaw/workspace")
CONTENT_CACHE_DIR = WORKSPACE_ROOT / "memory" / "learning" / "raw" / "content-cache"
MAX_CONTENT_CHARS = 12000


def _trim(text: str, max_chars: int = MAX_CONTENT_CHARS) -> str:
    normalized = re.sub(r"\n{3,}", "\n\n", text or "").strip()
    return normalized[:max_chars]


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</p\s*>", "\n\n", html)
    html = re.sub(r"(?is)<[^>]+>", " ", html)
    html = html.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"[ \t]{2,}", " ", html)



def _cache_key(candidate: dict[str, Any]) -> str:
    raw = candidate.get("url") or candidate.get("title") or json.dumps(candidate, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(str(raw).encode("utf-8")).hexdigest()[:16]


def _cache_path(candidate: dict[str, Any]) -> Path:
    return CONTENT_CACHE_DIR / f"{_cache_key(candidate)}.json"


def _read_cache(candidate: dict[str, Any], max_chars: int) -> dict[str, Any] | None:
    path = _cache_path(candidate)
    if not path.exists():
        return None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    text = str(cached.get("content_text", ""))
    if not text:
        return None
    return {
        **candidate,
        "content_text": _trim(text, max_chars=max_chars),
        "content_source": cached.get("content_source", "content_cache"),
        "content_url": cached.get("content_url", candidate.get("url", "")),
        "content_chars": min(len(text), max_chars),
        "content_cache_path": str(path.relative_to(WORKSPACE_ROOT)),
        "fetch_error": cached.get("fetch_error", ""),
    }


def _write_cache(candidate: dict[str, Any], enriched: dict[str, Any]) -> dict[str, Any]:
    CONTENT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(candidate)
    payload = {
        "url": candidate.get("url", ""),
        "title": candidate.get("title", ""),
        "content_text": enriched.get("content_text", ""),
        "content_source": enriched.get("content_source", ""),
        "content_url": enriched.get("content_url", ""),
        "content_chars": enriched.get("content_chars", 0),
        "fetch_error": enriched.get("fetch_error", ""),
        "cached_at": datetime.now().isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    enriched["content_cache_path"] = str(path.relative_to(WORKSPACE_ROOT))
    return enriched

def _fetch_text_url(url: str, timeout: int = 15) -> str:
    res = requests.get(url, headers=HEADERS, timeout=timeout)
    res.raise_for_status()
    ctype = res.headers.get("content-type", "").lower()
    if "text/plain" in ctype or url.endswith(('.md', '.txt')):
        return res.text
    return _html_to_text(res.text)


def _arxiv_pdf_url(url: str) -> str | None:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#/]+)", url)
    if not match:
        return None
    arxiv_id = match.group(1).removesuffix(".pdf")
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def _fetch_arxiv_pdf_text(url: str) -> tuple[str, str]:
    pdf_url = _arxiv_pdf_url(url)
    if not pdf_url:
        raise ValueError("not an arXiv URL")

    res = requests.get(pdf_url, headers=HEADERS, timeout=30)
    res.raise_for_status()
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "paper.pdf"
        txt_path = Path(tmpdir) / "paper.txt"
        pdf_path.write_bytes(res.content)
        completed = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(txt_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "pdftotext failed")
        return txt_path.read_text(encoding="utf-8", errors="ignore"), pdf_url


def _github_readme_urls(url: str) -> list[str]:
    parsed = urlparse(url)
    if parsed.netloc.lower() != "github.com":
        return []
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return []
    owner, repo = parts[0], parts[1]
    return [
        f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md",
        f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md",
        f"https://raw.githubusercontent.com/{owner}/{repo}/main/readme.md",
        f"https://raw.githubusercontent.com/{owner}/{repo}/master/readme.md",
    ]


def _fetch_github_readme(url: str) -> tuple[str, str]:
    for readme_url in _github_readme_urls(url):
        try:
            text = _fetch_text_url(readme_url)
            if text.strip():
                return text, readme_url
        except Exception:
            continue
    raise RuntimeError("README not found")


def fetch_candidate_content(candidate: dict[str, Any], max_chars: int = MAX_CONTENT_CHARS, use_cache: bool = True) -> dict[str, Any]:
    """Fetch lightweight full text for a candidate, falling back to its summary."""
    if use_cache:
        cached = _read_cache(candidate, max_chars=max_chars)
        if cached is not None:
            return cached

    url = candidate.get("url", "") or ""
    errors: list[str] = []

    fetchers = []
    if "arxiv.org/" in url:
        fetchers.append(("arxiv_pdf", _fetch_arxiv_pdf_text))
    if "github.com/" in url:
        fetchers.append(("github_readme", _fetch_github_readme))
    fetchers.append(("web_text", lambda target: (_fetch_text_url(target), target)))

    for content_source, fetcher in fetchers:
        try:
            text, source_url = fetcher(url)
            text = _trim(text, max_chars=max_chars)
            if len(text) >= 300:
                enriched = {
                    **candidate,
                    "content_text": text,
                    "content_source": content_source,
                    "content_url": source_url,
                    "content_chars": len(text),
                    "fetch_error": "",
                }
                return _write_cache(candidate, enriched)
        except Exception as exc:
            errors.append(f"{content_source}: {exc}")

    fallback = "\n\n".join(
        str(candidate.get(key, ""))
        for key in ("title", "description", "reason")
        if candidate.get(key)
    )
    enriched = {
        **candidate,
        "content_text": _trim(fallback, max_chars=max_chars),
        "content_source": "summary_fallback",
        "content_url": url,
        "content_chars": len(fallback),
        "fetch_error": "; ".join(errors),
    }
    return _write_cache(candidate, enriched)


def enrich_candidates_with_content(candidates: list[dict[str, Any]], max_chars: int = MAX_CONTENT_CHARS) -> list[dict[str, Any]]:
    return [fetch_candidate_content(candidate, max_chars=max_chars) for candidate in candidates]

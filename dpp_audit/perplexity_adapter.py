"""Perplexity source-discovery adapter. Results are candidates, never verified evidence.

The API key is read from PERPLEXITY_API_KEY and must never be committed or logged.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = "https://api.perplexity.ai/chat/completions"
DEFAULT_MODEL = "sonar"


@dataclass(frozen=True)
class SourceCandidate:
    url: str
    title: str = ""
    snippet: str = ""
    provider: str = "perplexity"
    discovery_status: str = "candidate_unverified"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def normalize_response(payload: dict[str, Any]) -> list[SourceCandidate]:
    """Normalize citations and any structured source entries without trusting their claims."""
    citations = payload.get("citations") or []
    if not isinstance(citations, list):
        raise ValueError("Perplexity response citations must be a list")
    content = ""
    try:
        content = payload["choices"][0]["message"].get("content", "") or ""
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    results: list[SourceCandidate] = []
    seen: set[str] = set()
    for item in citations:
        if isinstance(item, str):
            url, title, snippet = item.strip(), "", content[:1000]
        elif isinstance(item, dict):
            url = str(item.get("url") or item.get("link") or "").strip()
            title = str(item.get("title") or "").strip()
            snippet = str(item.get("snippet") or item.get("text") or content[:1000]).strip()
        else:
            continue
        if not url.startswith(("https://", "http://")) or url in seen:
            continue
        seen.add(url)
        results.append(SourceCandidate(url=url, title=title, snippet=snippet))
    return results


def _http_transport(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Do not include request headers or secrets in the raised message.
        raise RuntimeError(f"Perplexity API returned HTTP {exc.code}") from None
    except URLError as exc:
        raise RuntimeError(f"Perplexity API connection failed: {exc.reason}") from None
    except json.JSONDecodeError:
        raise RuntimeError("Perplexity API returned invalid JSON") from None


def discover_sources(
    query: str,
    *,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    timeout: float = 30.0,
    transport: Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]] = _http_transport,
) -> list[SourceCandidate]:
    """Search for source candidates; caller must independently inspect and assess each result."""
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query must not be empty")
    key = api_key or os.getenv("PERPLEXITY_API_KEY")
    if not key:
        raise RuntimeError("PERPLEXITY_API_KEY is not configured")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Find potentially relevant sources for research. Do not claim that any source is verified or that it proves a claim. Return a concise answer with citations."},
            {"role": "user", "content": clean_query},
        ],
        "temperature": 0,
    }
    payload = transport(API_URL, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, body, timeout)
    if not isinstance(payload, dict):
        raise ValueError("Perplexity response must be a JSON object")
    return normalize_response(payload)

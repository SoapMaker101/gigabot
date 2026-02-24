"""Web tool: search and fetch in a single tool."""

import html
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger

from gigabot.agent.tools.base import Tool

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5


def _strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate URL: must be http(s) with valid domain."""
    try:
        p = urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


class WebTool(Tool):
    """Unified web tool: search the internet and fetch page content."""

    def __init__(self, api_key: str | None = None, max_results: int = 5, max_chars: int = 50000):
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY", "")
        self.max_results = max_results
        self.max_chars = max_chars

    @property
    def name(self) -> str:
        return "web"

    @property
    def description(self) -> str:
        return "Поиск в интернете и получение содержимого веб-страниц"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "read_url"],
                    "description": "search — поиск в интернете, read_url — прочитать содержимое сайта по URL",
                },
                "query": {
                    "type": "string",
                    "description": "Search query (for search action)",
                },
                "url": {
                    "type": "string",
                    "description": "URL сайта для чтения (для read_url)",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of search results (1-10)",
                    "minimum": 1,
                    "maximum": 10,
                },
                "extract_mode": {
                    "type": "string",
                    "enum": ["markdown", "text"],
                    "description": "Extraction mode for fetch (default: markdown)",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Max characters for fetch result",
                    "minimum": 100,
                },
            },
            "required": ["action"],
        }

    async def execute(self, action: str, **kwargs: Any) -> str:
        if action == "search":
            return await self._search(**kwargs)
        if action in ("read_url", "fetch"):
            return await self._fetch(**kwargs)
        return f"Error: unknown action '{action}'. Use: search, read_url"

    async def _search(self, query: str = "", count: int | None = None, **_: Any) -> str:
        if not query:
            return "Error: 'query' is required for search"
        if not self.api_key:
            return "Error: BRAVE_API_KEY not configured"

        try:
            n = min(max(count or self.max_results, 1), 10)
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": self.api_key,
                    },
                    timeout=10.0,
                )
                r.raise_for_status()

            results = r.json().get("web", {}).get("results", [])
            if not results:
                return f"No results for: {query}"

            lines = [f"Results for: {query}\n"]
            for i, item in enumerate(results[:n], 1):
                lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
                if desc := item.get("description"):
                    lines.append(f"   {desc}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    async def _fetch(
        self, url: str = "", extract_mode: str = "markdown", max_chars: int | None = None, **_: Any,
    ) -> str:
        if not url:
            return "Error: 'url' is required. Пример: web(action='read_url', url='https://example.com')"

        limit = max_chars or self.max_chars

        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            logger.warning("web_fetch: invalid URL '{}': {}", url, error_msg)
            return json.dumps(
                {"error": f"URL validation failed: {error_msg}", "url": url},
                ensure_ascii=False,
            )

        try:
            from readability import Document
        except ImportError:
            logger.error("web_fetch: readability-lxml not installed")
            return json.dumps(
                {"error": "readability-lxml not installed. Run: pip install readability-lxml", "url": url},
                ensure_ascii=False,
            )

        try:
            logger.info("web_fetch: fetching {}", url)
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                timeout=30.0,
                verify=True,
            ) as client:
                r = await client.get(url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()
            logger.info("web_fetch: {} → status {}", url, r.status_code)

            ctype = r.headers.get("content-type", "")

            if "application/json" in ctype:
                text, extractor = json.dumps(r.json(), indent=2, ensure_ascii=False), "json"
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                doc = Document(r.text)
                if extract_mode == "markdown":
                    content = self._to_markdown(doc.summary())
                else:
                    content = _strip_tags(doc.summary())
                text = f"# {doc.title()}\n\n{content}" if doc.title() else content
                extractor = "readability"
            else:
                text, extractor = r.text, "raw"

            truncated = len(text) > limit
            if truncated:
                text = text[:limit]

            return json.dumps(
                {
                    "url": url,
                    "finalUrl": str(r.url),
                    "status": r.status_code,
                    "extractor": extractor,
                    "truncated": truncated,
                    "length": len(text),
                    "text": text,
                },
                ensure_ascii=False,
            )
        except httpx.ConnectError as e:
            logger.error("web_fetch: connection failed for {}: {}", url, e)
            return json.dumps({"error": f"Connection failed: {e}", "url": url}, ensure_ascii=False)
        except httpx.TimeoutException as e:
            logger.error("web_fetch: timeout for {}: {}", url, e)
            return json.dumps({"error": f"Request timed out: {e}", "url": url}, ensure_ascii=False)
        except httpx.HTTPStatusError as e:
            logger.error("web_fetch: HTTP {} for {}", e.response.status_code, url)
            return json.dumps(
                {"error": f"HTTP {e.response.status_code}: {e.response.reason_phrase}", "url": url},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error("web_fetch: unexpected error for {}: {} ({})", url, e, type(e).__name__)
            return json.dumps({"error": f"{type(e).__name__}: {e}", "url": url}, ensure_ascii=False)

    def _to_markdown(self, raw_html: str) -> str:
        """Convert HTML to markdown."""
        text = re.sub(
            r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
            lambda m: f'[{_strip_tags(m[2])}]({m[1]})',
            raw_html,
            flags=re.I,
        )
        text = re.sub(
            r'<h([1-6])[^>]*>([\s\S]*?)</h\1>',
            lambda m: f'\n{"#" * int(m[1])} {_strip_tags(m[2])}\n',
            text,
            flags=re.I,
        )
        text = re.sub(
            r'<li[^>]*>([\s\S]*?)</li>',
            lambda m: f'\n- {_strip_tags(m[1])}',
            text,
            flags=re.I,
        )
        text = re.sub(r'</(p|div|section|article)>', '\n\n', text, flags=re.I)
        text = re.sub(r'<(br|hr)\s*/?>', '\n', text, flags=re.I)
        return _normalize(_strip_tags(text))

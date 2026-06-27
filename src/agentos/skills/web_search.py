"""Web search skill."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from agentos.skills.base import Skill, SkillResult
from agentos.core.config import get_config

logger = logging.getLogger(__name__)


class WebSearchSkill(Skill):
    name = "web_search"
    description = "Web search and content extraction"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.default_limit = config.get("default_limit", 5) if config else 5
        self.timeout = config.get("timeout", 15) if config else 15

    async def search(self, query: str, limit: Optional[int] = None) -> SkillResult:
        """Search the web using DuckDuckGo HTML (no API key needed)."""
        try:
            limit = limit or self.default_limit
            url = "https://html.duckduckgo.com/html/"
            params = {"q": query}
            headers = {"User-Agent": "Mozilla/5.0 (compatible; AgentOS/1.0)"}

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, data=params, headers=headers)
                resp.raise_for_status()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")

            results = []
            for result in soup.select(".result")[:limit]:
                title_elem = result.select_one(".result__title")
                snippet_elem = result.select_one(".result__snippet")
                url_elem = result.select_one(".result__url")

                if title_elem:
                    results.append({
                        "title": title_elem.get_text(strip=True),
                        "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                        "url": url_elem.get_text(strip=True) if url_elem else "",
                    })

            return SkillResult(success=True, data={"query": query, "results": results})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def extract(self, url: str) -> SkillResult:
        """Extract full content from a URL."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove scripts, styles, nav, footer
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            # Get main content
            main = soup.select_one("main, article, .content, .post, #content, #main")
            if main:
                text = main.get_text(separator="\n", strip=True)
            else:
                text = soup.get_text(separator="\n", strip=True)

            return SkillResult(success=True, data={
                "url": url,
                "title": soup.title.string if soup.title else "",
                "content": text[:10000],  # Limit
            })
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def summarize(self, url: str, max_length: int = 500) -> SkillResult:
        """Extract and summarize content (requires LLM)."""
        extract_result = await self.extract(url)
        if not extract_result.success:
            return extract_result

        # Return extracted content for LLM to summarize
        return SkillResult(
            success=True,
            data={
                "url": url,
                "content": extract_result.data["content"],
                "title": extract_result.data["title"],
                "max_length": max_length,
            },
            meta={"needs_llm_summarization": True},
        )
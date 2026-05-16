from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx


class ConfluenceError(Exception):
    pass


@dataclass
class ConfluenceConfig:
    url: str
    auth_type: str = "token"
    token: str = ""
    email: str = ""  # required for Cloud

    def __post_init__(self) -> None:
        self.url = self.url.rstrip("/")
        if self.is_cloud and not self.email:
            raise ValueError("email is required for Confluence Cloud (atlassian.net)")

    @property
    def is_cloud(self) -> bool:
        return "atlassian.net" in self.url


@dataclass
class ConfluencePage:
    id: str
    title: str
    space_key: str
    html_body: str
    url: str
    version: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "ConfluencePage":
        return cls(
            id=str(data["id"]),
            title=data["title"],
            space_key=data.get("space", {}).get("key", ""),
            html_body=data.get("body", {}).get("storage", {}).get("value", ""),
            url=data.get("_links", {}).get("webui", ""),
            version=data.get("version", {}).get("number", 1),
        )

    def to_markdown(self) -> str:
        """Convert Confluence HTML body to plain markdown."""
        md = self.html_body

        # headings
        for i in range(6, 0, -1):
            md = re.sub(rf"<h{i}[^>]*>(.*?)</h{i}>", "#" * i + r" \1\n", md, flags=re.DOTALL)

        # bold/italic
        md = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", md, flags=re.DOTALL)
        md = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", md, flags=re.DOTALL)
        md = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", md, flags=re.DOTALL)

        # lists
        md = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1", md, flags=re.DOTALL)
        md = re.sub(r"<[uo]l[^>]*>|</[uo]l>", "", md)

        # paragraphs and line breaks
        md = re.sub(r"<br\s*/?>", "\n", md)
        md = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", md, flags=re.DOTALL)

        # code blocks
        md = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", md, flags=re.DOTALL)
        md = re.sub(
            r'<ac:structured-macro[^>]*ac:name="code"[^>]*>.*?<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>.*?</ac:structured-macro>',
            r"```\n\1\n```",
            md,
            flags=re.DOTALL,
        )

        # strip remaining tags
        md = re.sub(r"<[^>]+>", "", md)

        # clean up whitespace
        md = re.sub(r"\n{3,}", "\n\n", md)
        md = md.strip()

        return f"# {self.title}\n\n{md}"


class ConfluenceClient:
    def __init__(self, config: ConfluenceConfig) -> None:
        self.config = config
        self._client = httpx.Client(
            base_url=self._base_url,
            auth=self._build_auth() if config.is_cloud else None,
            headers=self._build_headers(),
            timeout=30.0,
        )

    @property
    def _base_url(self) -> str:
        if self.config.is_cloud:
            return f"{self.config.url}/wiki/rest/api"
        return f"{self.config.url}/rest/api"

    def _build_auth(self) -> tuple[str, str] | None:
        if self.config.is_cloud:
            return (self.config.email, self.config.token)
        return None

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if not self.config.is_cloud and self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        return headers

    def _get(self, path: str, params: dict | None = None) -> dict:
        response = self._client.get(path, params=params)
        if response.status_code != 200:
            raise ConfluenceError(f"Confluence API error {response.status_code}: {response.text[:200]}")
        return response.json()

    def get_page(self, page_id: str) -> ConfluencePage:
        data = self._get(f"/content/{page_id}", params={"expand": "body.storage,space,version"})
        return ConfluencePage.from_api(data)

    def get_children(self, page_id: str, limit: int = 25) -> list[ConfluencePage]:
        """Recursively fetch all descendant pages of page_id."""
        pages: list[ConfluencePage] = []
        start = 0
        while True:
            data = self._get(
                f"/content/{page_id}/child/page",
                params={"expand": "body.storage,space,version", "limit": limit, "start": start},
            )
            results = data.get("results", [])
            direct_children = [ConfluencePage.from_api(r) for r in results]
            pages.extend(direct_children)
            # recurse only into direct children fetched this batch
            for child in direct_children:
                pages.extend(self.get_children(child.id, limit=limit))
            if len(results) < limit:
                break
            start += limit
        return pages

    def get_space_pages(self, space_key: str, limit: int = 25) -> list[ConfluencePage]:
        pages: list[ConfluencePage] = []
        start = 0
        while True:
            data = self._get(
                "/content",
                params={
                    "spaceKey": space_key,
                    "type": "page",
                    "expand": "body.storage,space,version",
                    "limit": limit,
                    "start": start,
                },
            )
            results = data.get("results", [])
            pages.extend(ConfluencePage.from_api(r) for r in results)
            if len(results) < limit:
                break
            start += limit
        return pages

    def get_pages_by_label(self, label: str, limit: int = 25) -> list[ConfluencePage]:
        pages: list[ConfluencePage] = []
        start = 0
        while True:
            data = self._get(
                "/content/search",
                params={
                    "cql": f'label = "{label}" AND type = "page"',
                    "expand": "body.storage,space,version",
                    "limit": limit,
                    "start": start,
                },
            )
            results = data.get("results", [])
            pages.extend(ConfluencePage.from_api(r) for r in results)
            if len(results) < limit:
                break
            start += limit
        return pages

    def get_all_pages(self, limit: int = 25) -> list[ConfluencePage]:
        pages: list[ConfluencePage] = []
        start = 0
        while True:
            data = self._get(
                "/content",
                params={
                    "type": "page",
                    "expand": "body.storage,space,version",
                    "limit": limit,
                    "start": start,
                },
            )
            results = data.get("results", [])
            pages.extend(ConfluencePage.from_api(r) for r in results)
            if len(results) < limit:
                break
            start += limit
        return pages

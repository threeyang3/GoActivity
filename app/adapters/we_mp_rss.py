import hashlib
import xml.etree.ElementTree as ET
from typing import Any

from bs4 import BeautifulSoup
import requests

from app.config import get_settings


def normalize_payload(payload: dict[str, Any]) -> dict[str, str]:
    payload = _unwrap_payload(payload)
    title = _first(payload, "title", "article_title", "name")
    url = _first(payload, "url", "link", "article_url", "source_url")
    markdown = _first(payload, "markdown", "md", "content_markdown")
    html = _first(payload, "html", "content_html", "content", "description")
    article_id = _first(payload, "article_id", "id", "guid")
    if not article_id:
        article_id = hashlib.sha256((url or title or repr(payload)).encode("utf-8")).hexdigest()[:24]
    if not markdown and html:
        markdown = html_to_markdownish(html)
    pic_url = _first(payload, "pic_url", "image", "cover", "cover_url")
    if pic_url and pic_url not in (markdown or ""):
        markdown = _merge_cover_image(markdown, pic_url)
    return {
        "article_id": article_id,
        "title": title,
        "mp_name": _first(payload, "mp_name", "author", "account_name", "source_name"),
        "publish_time": _first(payload, "publish_time", "published", "pub_time", "created_at"),
        "markdown": markdown,
        "url": url,
        "pic_url": pic_url or "",
    }


def html_to_markdownish(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src:
            img.replace_with(f"\n![]({src})\n")
    text = soup.get_text("\n")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _merge_cover_image(markdown: str, pic_url: str) -> str:
    image_markdown = f"![]({pic_url})"
    if not markdown:
        return image_markdown
    return f"{image_markdown}\n\n{markdown}"


def _first(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return str(value)
    return ""


def _unwrap_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("article", "data", "item"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


class WeMpRssClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.we_mp_rss_base_url.rstrip("/")
        self.api_base = self.settings.we_mp_rss_api_base.rstrip("/")

    def fetch_articles(self, limit: int = 20, offset: int = 0, has_content: bool = True) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.base_url}{self.api_base}/articles",
            params={"limit": limit, "offset": offset, "has_content": str(has_content).lower()},
            headers=self._auth_headers(),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", {}).get("list", [])

    def fetch_article_detail(self, article_id: str) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url}{self.api_base}/articles/{article_id}",
            headers=self._auth_headers(),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", {})

    def fetch_rss_articles(self, feed_id: str = "all", limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.base_url}/rss/{feed_id}",
            params={"limit": limit, "offset": offset},
            timeout=30,
        )
        response.raise_for_status()
        return _parse_rss_items(response.text)

    def _auth_headers(self) -> dict[str, str]:
        access_key = self.settings.we_mp_rss_access_key.strip()
        secret_key = self.settings.we_mp_rss_secret_key.strip()
        if not access_key or not secret_key:
            raise RuntimeError("WE_MP_RSS_ACCESS_KEY and WE_MP_RSS_SECRET_KEY are required for JSON article sync.")
        return {"Authorization": f"AK-SK {access_key}:{secret_key}"}


def _parse_rss_items(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = _xml_text(item, "title")
        link = _xml_text(item, "link")
        description = _xml_text(item, "description")
        author = _xml_text(item, "author")
        pub_date = _xml_text(item, "pubDate")
        content = _xml_text(item, "{http://purl.org/rss/1.0/modules/content/}encoded")
        items.append(
            {
                "title": title,
                "url": link,
                "mp_name": author,
                "publish_time": pub_date,
                "html": content or description,
                "description": description,
            }
        )
    return items


def _xml_text(node: ET.Element, tag: str) -> str:
    value = node.findtext(tag)
    return value.strip() if value else ""

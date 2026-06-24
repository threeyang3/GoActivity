from app.adapters.we_mp_rss import WeMpRssClient, _parse_rss_items
from app.config import get_settings
from app.services.article_service import ArticleService


def test_parse_rss_items_extracts_basic_fields() -> None:
    xml_text = """
    <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
      <channel>
        <item>
          <title>Test Item</title>
          <link>https://example.com/item</link>
          <author>Campus Center</author>
          <pubDate>Sat, 14 Jun 2026 12:00:00 GMT</pubDate>
          <description><![CDATA[summary]]></description>
          <content:encoded><![CDATA[<p>body</p>]]></content:encoded>
        </item>
      </channel>
    </rss>
    """

    items = _parse_rss_items(xml_text)

    assert items == [
        {
            "title": "Test Item",
            "url": "https://example.com/item",
            "mp_name": "Campus Center",
            "publish_time": "Sat, 14 Jun 2026 12:00:00 GMT",
            "html": "<p>body</p>",
            "description": "summary",
        }
    ]


def test_we_mp_rss_client_requires_credentials_for_json_sync() -> None:
    settings = get_settings()
    original_ak = settings.we_mp_rss_access_key
    original_sk = settings.we_mp_rss_secret_key
    try:
        settings.we_mp_rss_access_key = ""
        settings.we_mp_rss_secret_key = ""
        client = WeMpRssClient()
        try:
            client._auth_headers()
            assert False, "Expected credentials error"
        except RuntimeError as exc:
            assert "WE_MP_RSS_ACCESS_KEY" in str(exc)
    finally:
        settings.we_mp_rss_access_key = original_ak
        settings.we_mp_rss_secret_key = original_sk


class _FakeClient:
    def fetch_article_detail(self, article_id: str) -> dict:
        return {"id": article_id, "content_html": "<p>detail</p><img src='https://example.com/cover.png'/>"}


def test_article_service_enriches_list_payload_with_detail() -> None:
    service = ArticleService(None)  # type: ignore[arg-type]
    payload = {"id": "detail-123", "title": "Brief", "description": "summary"}

    enriched = service._enrich_we_mp_rss_article_payload(_FakeClient(), payload)

    assert enriched["id"] == "detail-123"
    assert "content_html" in enriched

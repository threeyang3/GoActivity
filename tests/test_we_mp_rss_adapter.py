from app.adapters.we_mp_rss import normalize_payload


def test_normalize_payload_unwraps_nested_data() -> None:
    payload = {
        "data": {
            "article_id": "nested-001",
            "title": "Nested payload",
            "url": "https://example.com/nested",
            "markdown": "# Nested payload",
        }
    }

    result = normalize_payload(payload)

    assert result["article_id"] == "nested-001"
    assert result["title"] == "Nested payload"
    assert result["url"] == "https://example.com/nested"


def test_normalize_payload_falls_back_to_hashed_id() -> None:
    payload = {"title": "Only title"}

    result = normalize_payload(payload)

    assert result["title"] == "Only title"
    assert len(result["article_id"]) == 24


def test_normalize_payload_uses_content_html_and_keeps_images() -> None:
    payload = {
        "id": "detail-001",
        "title": "Detail payload",
        "url": "https://example.com/detail",
        "content_html": "<p>hello</p><p><img src='https://example.com/a.png'/></p>",
    }

    result = normalize_payload(payload)

    assert result["article_id"] == "detail-001"
    assert "![](https://example.com/a.png)" in result["markdown"]


def test_normalize_payload_prepends_cover_when_only_pic_url_exists() -> None:
    payload = {
        "id": "cover-001",
        "title": "Cover payload",
        "url": "https://example.com/cover",
        "description": "summary",
        "pic_url": "https://example.com/cover.jpg",
    }

    result = normalize_payload(payload)

    assert result["markdown"].startswith("![](https://example.com/cover.jpg)")

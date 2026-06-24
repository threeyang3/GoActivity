import pytest

from app.config import get_settings
from app.services.providers import (
    OpenAIOCRProvider,
    OpenAIVisionProvider,
    ProviderSelectionError,
    get_ocr_provider,
    get_vision_provider,
)


def test_get_mock_providers() -> None:
    settings = get_settings()
    original_ocr = settings.ocr_provider
    original_vision = settings.vision_api_provider
    try:
        settings.ocr_provider = "mock"
        settings.vision_api_provider = "mock"
        assert get_ocr_provider().extract(["a.png"]) == "[mock OCR] a.png"
        assert get_vision_provider().analyze("t", "body", ["a.png"], "")["event_name"] == "t"
    finally:
        settings.ocr_provider = original_ocr
        settings.vision_api_provider = original_vision


def test_get_vision_provider_requires_key_for_openai() -> None:
    settings = get_settings()
    original_provider = settings.vision_api_provider
    original_key = settings.vision_api_key
    try:
        settings.vision_api_provider = "openai"
        settings.vision_api_key = ""
        with pytest.raises(ProviderSelectionError):
            get_vision_provider()
    finally:
        settings.vision_api_provider = original_provider
        settings.vision_api_key = original_key


def test_openai_vision_provider_parses_json_response(monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "poster.jpg"
    image_path.write_bytes(b"fake-image")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"event_name":"AI Lecture","category_1":"学术讲座","tags":["AI"]}'
                        }
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr("app.services.providers.requests.post", fake_post)

    provider = OpenAIVisionProvider(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4.1-mini",
        timeout_seconds=30,
    )
    result = provider.analyze("Fallback title", "body", [str(image_path)], "")

    assert result["event_name"] == "AI Lecture"
    assert result["category_1"] == "学术讲座"
    assert result["tags"] == ["AI"]
    assert result["poster_images"] == [str(image_path)]


def test_openai_ocr_provider_returns_plain_text(monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "poster.jpg"
    image_path.write_bytes(b"fake-image")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Time: 19:00\nLocation: Lecture Hall"
                        }
                    }
                ]
            }

    monkeypatch.setattr("app.services.providers.requests.post", lambda *args, **kwargs: FakeResponse())

    provider = OpenAIOCRProvider(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4.1-mini",
        timeout_seconds=30,
    )
    result = provider.extract([str(image_path)])

    assert "Time: 19:00" in result
    assert "Location: Lecture Hall" in result

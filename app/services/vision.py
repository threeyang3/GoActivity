from typing import Any

from app.services.providers import VisionProvider, get_vision_provider


class VisionExtractor:
    def __init__(self, provider: VisionProvider | None = None) -> None:
        self.provider = provider or get_vision_provider()

    def analyze(self, title: str, markdown: str, image_paths: list[str], ocr_text: str) -> dict[str, Any]:
        return self.provider.analyze(title, markdown, image_paths, ocr_text)

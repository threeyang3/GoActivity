from app.services.providers import OCRProvider, get_ocr_provider


class OCRExtractor:
    def __init__(self, provider: OCRProvider | None = None) -> None:
        self.provider = provider or get_ocr_provider()

    def extract(self, image_paths: list[str]) -> str:
        return self.provider.extract(image_paths)

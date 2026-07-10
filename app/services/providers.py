from __future__ import annotations

from abc import ABC, abstractmethod
import base64
import json
import logging
from pathlib import Path
from typing import Any

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)

from app.exceptions import ProviderError


class ProviderSelectionError(ProviderError):
    """Legacy alias – prefer raising ProviderError directly in new code."""
    pass


class OCRProvider(ABC):
    @abstractmethod
    def extract(self, image_paths: list[str]) -> str:
        raise NotImplementedError


class VisionProvider(ABC):
    @abstractmethod
    def analyze(self, title: str, markdown: str, image_paths: list[str], ocr_text: str) -> dict[str, Any]:
        raise NotImplementedError


class MockOCRProvider(OCRProvider):
    def extract(self, image_paths: list[str]) -> str:
        return "\n".join(f"[mock OCR] {Path(path).name}" for path in image_paths)


class OpenAIOCRProvider(OCRProvider):
    def __init__(self, api_key: str, base_url: str, model: str, timeout_seconds: float) -> None:
        if not api_key:
            raise ProviderSelectionError("VISION_API_KEY is required when OCR_PROVIDER=openai")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def extract(self, image_paths: list[str]) -> str:
        if not image_paths:
            return ""
        paths = image_paths[:5]
        if len(paths) == 1:
            # 单张图片直接调用，不创建线程池
            result = self._extract_single_image(paths[0])
            return result if result.strip() else ""

        from concurrent.futures import ThreadPoolExecutor, as_completed
        extracted_parts: list[str] = []
        with ThreadPoolExecutor(max_workers=min(5, len(paths))) as executor:
            futures = {executor.submit(self._extract_single_image, p): p for p in paths}
            for future in as_completed(futures):
                try:
                    part = future.result()
                    if part.strip():
                        extracted_parts.append(part)
                except Exception:
                    pass
        return "\n".join(extracted_parts)

    def _extract_single_image(self, image_path: str) -> str:
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "system",
                        "content": "Read the poster image and return only the extracted text. Do not summarize.",
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract all visible text from this image."},
                            {
                                "type": "image_url",
                                "image_url": {"url": _image_data_url(image_path)},
                            },
                        ],
                    },
                ],
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        message = payload["choices"][0]["message"]["content"]
        return message.strip() if isinstance(message, str) else ""


class MockVisionProvider(VisionProvider):
    def analyze(self, title: str, markdown: str, image_paths: list[str], ocr_text: str) -> dict[str, Any]:
        source = (markdown or ocr_text or "").replace("\n", " ").strip()
        return {
            "is_event": True,
            "event_name": title,
            "category_1": "其他",
            "category_2": "",
            "start_time": "",
            "end_time": "",
            "location": "",
            "speaker": "",
            "organizer": "",
            "registration": "",
            "summary": source[:180] if source else "待抽取活动摘要。",
            "tags": [],
            "poster_images": image_paths,
            "confidence": 0.35 if image_paths else 0.2,
            "vision_notes": [f"[mock Vision] {Path(path).name}" for path in image_paths],
        }


class OpenAIVisionProvider(VisionProvider):
    def __init__(self, api_key: str, base_url: str, model: str, timeout_seconds: float) -> None:
        if not api_key:
            raise ProviderSelectionError("VISION_API_KEY is required when VISION_API_PROVIDER=openai")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def analyze(self, title: str, markdown: str, image_paths: list[str], ocr_text: str) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": self._prompt(title=title, markdown=markdown, ocr_text=ocr_text),
            }
        ]
        for image_path in image_paths[:5]:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": _image_data_url(image_path),
                    },
                }
            )

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "system",
                        "content": "You extract campus event data from WeChat articles and posters. Return valid JSON only.",
                    },
                    {
                        "role": "user",
                        "content": content,
                    },
                ],
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        message = payload["choices"][0]["message"]["content"]
        result = _extract_json_object(message)

        # 处理新的 events 数组格式（向后兼容旧的单对象格式）
        events_list = result.get("events")
        if isinstance(events_list, list) and len(events_list) > 0:
            # 新格式：为每个事件填充默认值
            for evt in events_list:
                evt.setdefault("event_name", title)
                evt.setdefault("summary", _fallback_summary(markdown, ocr_text))
                evt.setdefault("poster_images", image_paths)
                evt.setdefault("tags", [])
                evt.setdefault("confidence", 0.5 if image_paths else 0.3)
                evt.setdefault("is_event", True)
            result["events"] = events_list
        else:
            # 旧格式：单对象，填充默认值
            result.setdefault("event_name", title)
            result.setdefault("summary", _fallback_summary(markdown, ocr_text))
            result.setdefault("poster_images", image_paths)
            result.setdefault("tags", [])
            result.setdefault("confidence", 0.5 if image_paths else 0.3)
            result.setdefault("is_event", True)
        return result

    @staticmethod
    def _prompt(title: str, markdown: str, ocr_text: str) -> str:
        return (
            "你是一个校园活动信息抽取专家。从提供的文章文本、OCR 文本和海报图片中提取结构化的活动信息。\n\n"
            "**重要：如果一篇文章包含多个不同的活动（如多天的放映、多场讲座），请返回 events 数组。**\n"
            "**如果只有一个活动，也用 events 数组返回（数组只有一个元素）。**\n\n"
            "返回一个 JSON 对象：\n"
            "{\n"
            '  "events": [\n'
            "    {\n"
            '      "is_event": true,\n'
            '      "event_name": "活动名称",\n'
            '      "category_1": "一级分类",\n'
            '      "category_2": "二级分类",\n'
            '      "start_time": "YYYY-MM-DD HH:MM:SS",\n'
            '      "end_time": "YYYY-MM-DD HH:MM:SS",\n'
            '      "location": "活动地点",\n'
            '      "organizer": "主办方",\n'
            '      "summary": "活动摘要",\n'
            '      "tags": [],\n'
            '      "confidence": 0.9,\n'
            '      "performance_type": "",\n'
            '      "performance_name": "",\n'
            '      "performer": "",\n'
            '      "ticket_info": "",\n'
            '      "lecture_topic": "",\n'
            '      "speaker": "",\n'
            '      "speaker_title": "",\n'
            '      "lecture_series": "",\n'
            '      "competition_name": "",\n'
            '      "competition_type": "",\n'
            '      "deadline": "",\n'
            '      "prize_info": "",\n'
            '      "registration": "",\n'
            '      "registration_url": "",\n'
            '      "registration_deadline": "",\n'
            '      "participant_limit": ""\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "**字段说明**：\n"
            "- is_event: 是否是活动（true/false）\n"
            "- event_name: 活动名称\n"
            "- category_1: 讲座/演出/比赛/招募/展览/工作坊/分享会/其他\n"
            "- category_2: 学术/科技/艺术/公益/体育/娱乐/招聘/其他\n"
            "- start_time/end_time: 活动时间（尽量精确到分钟）\n"
            "- location: 活动地点\n"
            "- performance_type: 电影放映/音乐会/话剧/舞蹈/歌剧等\n"
            "- performance_name: 演出作品名称\n"
            "- ticket_info: 票价信息\n"
            "- speaker: 主讲人\n"
            "- registration: 报名方式\n\n"
            "使用空字符串表示未知的标量值，使用空数组 [] 表示未知的标签。\n"
            "尽量从海报图片中提取信息，海报通常包含最完整的活动信息。\n\n"
            f"文章标题：\n{title}\n\n"
            f"文章内容：\n{markdown[:6000]}\n\n"
            f"OCR 文本：\n{ocr_text[:4000]}\n\n"
            "注意：以上内容可能因长度限制被截断，请基于可见内容抽取，不要推测截断后的部分。"
        )


class DisabledOCRProvider(OCRProvider):
    def extract(self, image_paths: list[str]) -> str:
        return ""


class RapidOCRProvider(OCRProvider):
    """使用 RapidOCR（基于 PaddleOCR ONNX 推理）的本地 OCR Provider。

    优点：免费、快速（<1秒/张）、不依赖网络。
    缺点：对复杂排版的识别质量可能不如 Vision API。
    """

    def __init__(self) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
        except ImportError:
            raise ProviderSelectionError("rapidocr_onnxruntime is not installed. Run: pip install rapidocr_onnxruntime")

    def extract(self, image_paths: list[str]) -> str:
        if not image_paths:
            return ""

        extracted_parts: list[str] = []
        for path in image_paths[:5]:
            try:
                result, _ = self._ocr(path)
                if result:
                    texts = [line[1] for line in result if line[1].strip()]
                    if texts:
                        extracted_parts.append("\n".join(texts))
            except Exception as e:
                logger.warning("RapidOCR failed for %s: %s", path, e)

        return "\n".join(extracted_parts)


class TextAIVisionProvider(VisionProvider):
    """使用纯文本 AI API（如 DeepSeek、Qwen-Text）的 Vision Provider。

    流程：先用本地 OCR 提取文字，再用文本 AI 分析文字内容。
    优点：成本低（约为多模态 API 的 1/100）、速度快。
    缺点：丢失图片的视觉信息（颜色、布局、字体等）。
    """

    def __init__(self, api_key: str, base_url: str, model: str, timeout_seconds: float,
                 ocr_provider: OCRProvider | None = None) -> None:
        if not api_key:
            raise ProviderSelectionError("VISION_API_KEY is required for TextAIVisionProvider")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._ocr = ocr_provider or RapidOCRProvider()

    def analyze(self, title: str, markdown: str, image_paths: list[str], ocr_text: str) -> dict[str, Any]:
        # 如果没有 OCR 文本，先用本地 OCR 提取
        if not ocr_text and image_paths:
            ocr_text = self._ocr.extract(image_paths)

        # 用文本 AI 分析
        prompt = self._prompt(title=title, markdown=markdown, ocr_text=ocr_text)
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "system",
                        "content": "You extract campus event data from WeChat articles. Return valid JSON only.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        message = payload["choices"][0]["message"]["content"]
        result = _extract_json_object(message)

        # 处理 events 数组格式
        events_list = result.get("events")
        if isinstance(events_list, list) and len(events_list) > 0:
            for evt in events_list:
                evt.setdefault("event_name", title)
                evt.setdefault("summary", _fallback_summary(markdown, ocr_text))
                evt.setdefault("poster_images", image_paths)
                evt.setdefault("tags", [])
                evt.setdefault("confidence", 0.4)  # 纯文本分析置信度略低
                evt.setdefault("is_event", True)
            result["events"] = events_list
        else:
            result.setdefault("event_name", title)
            result.setdefault("summary", _fallback_summary(markdown, ocr_text))
            result.setdefault("poster_images", image_paths)
            result.setdefault("tags", [])
            result.setdefault("confidence", 0.4)
            result.setdefault("is_event", True)
        return result

    @staticmethod
    def _prompt(title: str, markdown: str, ocr_text: str) -> str:
        return (
            "你是一个校园活动信息抽取专家。从提供的文章文本和 OCR 文本中提取结构化的活动信息。\n\n"
            "**重要：如果一篇文章包含多个不同的活动（如多天的放映、多场讲座），请返回 events 数组。**\n"
            "**如果只有一个活动，也用 events 数组返回（数组只有一个元素）。**\n\n"
            "返回一个 JSON 对象：\n"
            "{\n"
            '  "events": [\n'
            "    {\n"
            '      "is_event": true,\n'
            '      "event_name": "活动名称",\n'
            '      "category_1": "一级分类",\n'
            '      "category_2": "二级分类",\n'
            '      "start_time": "YYYY-MM-DD HH:MM:SS",\n'
            '      "end_time": "YYYY-MM-DD HH:MM:SS",\n'
            '      "location": "活动地点",\n'
            '      "organizer": "主办方",\n'
            '      "summary": "活动摘要",\n'
            '      "tags": [],\n'
            '      "confidence": 0.9,\n'
            '      "performance_type": "",\n'
            '      "performance_name": "",\n'
            '      "performer": "",\n'
            '      "ticket_info": "",\n'
            '      "lecture_topic": "",\n'
            '      "speaker": "",\n'
            '      "speaker_title": "",\n'
            '      "lecture_series": "",\n'
            '      "competition_name": "",\n'
            '      "competition_type": "",\n'
            '      "deadline": "",\n'
            '      "prize_info": "",\n'
            '      "registration": "",\n'
            '      "registration_url": "",\n'
            '      "registration_deadline": "",\n'
            '      "participant_limit": ""\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "**字段说明**：\n"
            "- is_event: 是否是活动（true/false）\n"
            "- event_name: 活动名称\n"
            "- category_1: 讲座/演出/比赛/招募/展览/工作坊/分享会/其他\n"
            "- category_2: 学术/科技/艺术/公益/体育/娱乐/招聘/其他\n"
            "- start_time/end_time: 活动时间（尽量精确到分钟）\n"
            "- location: 活动地点\n"
            "- performance_type: 电影放映/音乐会/话剧/舞蹈/歌剧等\n"
            "- performance_name: 演出作品名称\n"
            "- ticket_info: 票价信息\n"
            "- speaker: 主讲人\n"
            "- registration: 报名方式\n\n"
            "使用空字符串表示未知的标量值，使用空数组 [] 表示未知的标签。\n\n"
            f"文章标题：\n{title}\n\n"
            f"文章内容：\n{markdown[:6000]}\n\n"
            f"OCR 文本：\n{ocr_text[:4000]}\n\n"
            "注意：以上内容可能因长度限制被截断，请基于可见内容抽取，不要推测截断后的部分。"
        )


def get_ocr_provider() -> OCRProvider:
    settings = get_settings()
    if settings.ocr_provider == "mock":
        return MockOCRProvider()
    if settings.ocr_provider == "disabled":
        return DisabledOCRProvider()
    if settings.ocr_provider == "rapid":
        return RapidOCRProvider()
    if settings.ocr_provider == "openai":
        return OpenAIOCRProvider(
            api_key=settings.vision_api_key,
            base_url=settings.vision_api_base_url,
            model=settings.vision_api_model,
            timeout_seconds=settings.vision_api_timeout_seconds,
        )
    raise ProviderSelectionError(f"Unsupported OCR_PROVIDER: {settings.ocr_provider}")


def get_vision_provider() -> VisionProvider:
    settings = get_settings()
    if settings.vision_api_provider == "mock":
        return MockVisionProvider()
    if settings.vision_api_provider == "openai":
        return OpenAIVisionProvider(
            api_key=settings.vision_api_key,
            base_url=settings.vision_api_base_url,
            model=settings.vision_api_model,
            timeout_seconds=settings.vision_api_timeout_seconds,
        )
    if settings.vision_api_provider == "textai":
        return TextAIVisionProvider(
            api_key=settings.vision_api_key,
            base_url=settings.vision_api_base_url,
            model=settings.vision_api_model,
            timeout_seconds=settings.vision_api_timeout_seconds,
        )
    raise ProviderSelectionError(f"Unsupported VISION_API_PROVIDER: {settings.vision_api_provider}")


def _image_data_url(image_path: str) -> str:
    path = Path(image_path)
    data = path.read_bytes()
    mime = _detect_mime(data, path.suffix.lower())
    # GIF/WEBP 转 JPEG（部分 API 不支持这些格式）
    if mime in ("image/gif", "image/webp"):
        from PIL import Image as PILImage
        from io import BytesIO
        with PILImage.open(path) as img:
            if img.mode in ("P", "RGBA"):
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            data = buf.getvalue()
        mime = "image/jpeg"
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _detect_mime(data: bytes, suffix: str) -> str:
    """从文件头检测实际 MIME 类型，比扩展名更可靠。"""
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:4] == b"GIF8":
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"



def _extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderSelectionError(f"Vision provider returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ProviderSelectionError("Vision provider returned a non-object JSON payload.")
    return parsed


def _fallback_summary(markdown: str, ocr_text: str) -> str:
    source = (markdown or ocr_text or "").replace("\n", " ").strip()
    return source[:180] if source else "待抽取活动摘要。"

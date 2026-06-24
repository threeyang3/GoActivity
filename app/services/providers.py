from __future__ import annotations

from abc import ABC, abstractmethod
import base64
import json
from pathlib import Path
from typing import Any

import requests

from app.config import get_settings


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
        extracted_parts: list[str] = []
        for image_path in image_paths[:5]:
            extracted_parts.append(self._extract_single_image(image_path))
        return "\n".join(part for part in extracted_parts if part.strip())

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
            "你是一个校园活动信息抽取专家。从提供的文章文本、OCR 文本和海报图片中提取结构化的活动信息。\n"
            "返回一个 JSON 对象，包含以下字段：\n\n"
            "**基础信息**：\n"
            "- is_event: 是否是活动（true/false）\n"
            "- event_name: 活动名称（从标题或内容中提取）\n"
            "- category_1: 一级分类（讲座/演出/比赛/招募/展览/工作坊/分享会/其他）\n"
            "- category_2: 二级分类（学术/科技/艺术/公益/体育/娱乐/招聘/其他）\n"
            "- start_time: 开始时间（格式：YYYY-MM-DD HH:MM:SS）\n"
            "- end_time: 结束时间（格式：YYYY-MM-DD HH:MM:SS）\n"
            "- location: 活动地点\n"
            "- organizer: 主办方\n"
            "- summary: 活动摘要（简洁描述活动内容，不超过 200 字）\n"
            "- tags: 标签数组（如：免费/收费/线上/线下/报名中/已截止等）\n"
            "- confidence: 置信度（0-1）\n\n"
            "**演出信息**（如果是演出/放映/音乐会）：\n"
            "- performance_type: 演出类型（电影放映/音乐会/话剧/舞蹈/歌剧等）\n"
            "- performance_name: 演出作品名称（如：《实习生》、《天鹅湖》）\n"
            "- performer: 演出团体/演员\n"
            "- ticket_info: 票价信息\n\n"
            "**讲座信息**（如果是讲座/论坛/沙龙）：\n"
            "- lecture_topic: 讲座主题\n"
            "- speaker: 主讲人\n"
            "- speaker_title: 主讲人头衔/简介\n"
            "- lecture_series: 讲座系列（如：人文讲座第476讲）\n\n"
            "**比赛信息**（如果是比赛/征稿/大赛）：\n"
            "- competition_name: 比赛名称\n"
            "- competition_type: 比赛类型（征稿/竞赛/评选等）\n"
            "- deadline: 报名/投稿截止时间\n"
            "- prize_info: 奖项设置\n\n"
            "**报名信息**：\n"
            "- registration: 报名方式（如：扫描二维码、填写问卷、发送邮件等）\n"
            "- registration_url: 报名链接（如果有）\n"
            "- registration_deadline: 报名截止时间\n"
            "- participant_limit: 人数限制\n\n"
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


def get_ocr_provider() -> OCRProvider:
    settings = get_settings()
    if settings.ocr_provider == "mock":
        return MockOCRProvider()
    if settings.ocr_provider == "disabled":
        return DisabledOCRProvider()
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

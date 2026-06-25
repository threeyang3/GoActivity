import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image as PILImage
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Article, Image
from app.utils.ids import stable_id

logger = logging.getLogger(__name__)

MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((?P<url>[^)]+)\)")
HTML_IMAGE_RE = re.compile(r"<img[^>]+(?:src|data-src)=[\"'](?P<url>[^\"']+)[\"'][^>]*>", re.IGNORECASE)

# 装饰性图片过滤阈值
_MIN_FILE_SIZE = 50 * 1024      # 50KB — 小于此大小多为图标、分隔线、小装饰
_MIN_DIMENSION = 80              # 像素 — 宽或高小于此值为小图标
_MIN_AREA = 80 * 80              # 面积 — 总像素小于此值为装饰
_MAX_ASPECT_RATIO = 15.0         # 极端比例 — 如 1000x20 的分隔线


class ImageService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def process_article(self, article: Article) -> tuple[str, list[Image]]:
        urls = extract_images(article.raw_markdown)
        image_map: dict[str, str] = {}
        images: list[Image] = []

        # 先确保所有 image 记录存在
        for url in urls:
            images.append(self._ensure_image(article.article_id, url))

        # 并行下载未下载的图片
        to_download = [img for img in images if img.download_status != "downloaded"]
        if to_download:
            max_workers = min(5, len(to_download))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(self._download_image, article.article_id, img)
                    for img in to_download
                ]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        logger.warning("Image download failed: %s", e)

        # 构建 image map
        for img in images:
            if img.local_path and img.download_status == "downloaded":
                if not _is_decorative(img):
                    image_map[img.original_url] = img.local_path

        return rewrite_markdown(article.raw_markdown, image_map), images

    def _ensure_image(self, article_id: str, url: str) -> Image:
        image = (
            self.db.query(Image)
            .filter(Image.article_id == article_id, Image.original_url == url)
            .one_or_none()
        )
        if image is None:
            image = Image(image_id=stable_id("image", article_id, url), article_id=article_id, original_url=url)
            self.db.add(image)
            self.db.flush()
        return image

    def _download_image(self, article_id: str, image: Image) -> None:
        target_dir = self.settings.images_dir / article_id
        target_dir.mkdir(parents=True, exist_ok=True)
        extension = _extension(image.original_url)
        target = target_dir / f"{hashlib.sha256(image.original_url.encode('utf-8')).hexdigest()[:16]}{extension}"
        try:
            response = requests.get(image.original_url, timeout=20)
            response.raise_for_status()
            content = response.content
            target.write_bytes(content)
            image.local_path = str(target)
            image.failure_reason = ""
            _fill_dimensions(target, image)

            # 下载后检查：文件太小直接标记为 filtered
            if _is_too_small(content, image):
                image.download_status = "filtered_decorative"
                logger.debug("Filtered decorative image: %s (%d bytes, %dx%d)",
                             image.original_url, len(content), image.width, image.height)
            else:
                image.download_status = "downloaded"
        except Exception as exc:  # Keep ingestion alive when a poster CDN flakes.
            image.download_status = "failed"
            image.failure_reason = str(exc)


def extract_images(markdown: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for match in MARKDOWN_IMAGE_RE.finditer(markdown or ""):
        _add_url(match.group("url"), seen, urls)
    for match in HTML_IMAGE_RE.finditer(markdown or ""):
        _add_url(match.group("url"), seen, urls)
    return urls


def select_key_images(images: list[Image], limit: int = 6) -> list[Image]:
    """选出最可能是活动海报的图片，排除装饰性图片。"""
    candidates = [
        image for image in images
        if image.local_path
        and image.download_status == "downloaded"
        and not _is_decorative(image)
    ]
    ranked = sorted(candidates, key=_poster_score, reverse=True)
    return ranked[:limit]


def rewrite_markdown(markdown: str, image_map: dict[str, str]) -> str:
    result = markdown or ""
    for original, local in image_map.items():
        result = result.replace(original, local.replace("\\", "/"))
    return result


def _add_url(url: str, seen: set[str], urls: list[str]) -> None:
    clean = url.strip()
    if clean and clean not in seen and clean.startswith(("http://", "https://")):
        seen.add(clean)
        urls.append(clean)


def _extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return suffix
    return ".jpg"


def _fill_dimensions(path: Path, image: Image) -> None:
    try:
        with PILImage.open(path) as opened:
            image.width, image.height = opened.size
    except Exception as exc:
        logger.warning("Failed to read image dimensions %s: %s", path, exc)
        image.width = 0
        image.height = 0


def _is_too_small(content: bytes, image: Image) -> bool:
    """下载后检查：文件大小或尺寸是否过小（装饰性图片）。"""
    # 文件大小过滤
    if len(content) < _MIN_FILE_SIZE:
        return True
    # 尺寸过滤（如果能读到尺寸信息）
    w, h = image.width or 0, image.height or 0
    if w > 0 and h > 0:
        # 单边太小
        if w < _MIN_DIMENSION or h < _MIN_DIMENSION:
            return True
        # 面积太小
        if w * h < _MIN_AREA:
            return True
        # 极端比例（分隔线）
        ratio = max(w, h) / max(min(w, h), 1)
        if ratio > _MAX_ASPECT_RATIO:
            return True
    return False


def _is_decorative(image: Image) -> bool:
    """判断已下载的图片是否为装饰性图片（用于 select_key_images 过滤）。"""
    w, h = image.width or 0, image.height or 0
    if w > 0 and h > 0:
        if w < _MIN_DIMENSION or h < _MIN_DIMENSION:
            return True
        if w * h < _MIN_AREA:
            return True
        ratio = max(w, h) / max(min(w, h), 1)
        if ratio > _MAX_ASPECT_RATIO:
            return True
    return False


def _poster_score(image: Image) -> tuple[float, int, int]:
    width = image.width or 0
    height = image.height or 0
    area = width * height

    # 太小的图（二维码、图标）直接降权
    if width < 200 or height < 200:
        return (0.0, height, width)

    aspect_score = _aspect_score(width, height)
    return (aspect_score * 1_000_000 + area, height, width)


def _aspect_score(width: int, height: int) -> float:
    """海报比例评分。竖版海报优先，但不碾压大图。"""
    if width <= 0 or height <= 0:
        return 0.0
    ratio = height / max(width, 1)
    if ratio >= 1.8:
        return 3.0   # 竖版海报（常见）
    if ratio >= 1.3:
        return 2.5
    if ratio >= 0.9:
        return 2.0   # 接近正方形
    return 1.0       # 横版

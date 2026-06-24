from types import SimpleNamespace

from app.services.image_service import extract_images, rewrite_markdown, select_key_images


def test_extract_images_from_markdown_and_html() -> None:
    markdown = """
    ![](https://example.com/a.jpg)
    <img src="https://example.com/b.png" />
    ![dup](https://example.com/a.jpg)
    """

    assert extract_images(markdown) == ["https://example.com/a.jpg", "https://example.com/b.png"]


def test_rewrite_markdown() -> None:
    markdown = "![](https://example.com/a.jpg)"

    assert rewrite_markdown(markdown, {"https://example.com/a.jpg": "storage/images/a.jpg"}) == "![](storage/images/a.jpg)"


def test_select_key_images_prefers_poster_like_images() -> None:
    images = [
        SimpleNamespace(local_path="a.jpg", download_status="downloaded", width=1200, height=2200),
        SimpleNamespace(local_path="b.jpg", download_status="downloaded", width=1600, height=900),
        SimpleNamespace(local_path="c.jpg", download_status="downloaded", width=1080, height=1920),
        SimpleNamespace(local_path="d.jpg", download_status="failed", width=2000, height=3000),
    ]

    selected = select_key_images(images, limit=2)

    assert [image.local_path for image in selected] == ["a.jpg", "c.jpg"]

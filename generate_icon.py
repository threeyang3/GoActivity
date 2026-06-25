"""
生成 GoActivity 托盘图标和快捷方式图标
运行: python generate_icon.py
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math


def create_icon(size=256):
    """生成 GoActivity 图标 — 深绿底 + 白色 GA 字母"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    s = size
    pad = int(s * 0.06)
    radius = int(s * 0.22)

    # 深森林绿圆角矩形背景
    draw.rounded_rectangle(
        [(pad, pad), (s - pad, s - pad)],
        radius=radius,
        fill=(26, 46, 35, 255)  # #1a2e23
    )

    # 内部浅绿圆角矩形（微妙的层次感）
    inner_pad = int(s * 0.14)
    inner_radius = int(s * 0.16)
    draw.rounded_rectangle(
        [(inner_pad, inner_pad), (s - inner_pad, s - inner_pad)],
        radius=inner_radius,
        fill=(26, 92, 58, 255)  # #1a5c3a
    )

    # 右下角琥珀色小圆点（状态指示器占位）
    dot_r = int(s * 0.09)
    dot_x = s - inner_pad - dot_r - int(s * 0.02)
    dot_y = s - inner_pad - dot_r - int(s * 0.02)
    draw.ellipse(
        [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
        fill=(200, 149, 108, 255),  # #c8956c
        outline=(255, 255, 255, 200),
        width=max(1, s // 80)
    )

    # GA 文字
    try:
        font = ImageFont.truetype("segoeui.ttf", int(s * 0.32))
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("arial.ttf", int(s * 0.32))
        except (OSError, IOError):
            font = ImageFont.load_default()

    # 居中偏上绘制
    text_y = int(s * 0.30)
    draw.text(
        (s // 2, text_y),
        "GA",
        fill=(255, 255, 255, 255),
        font=font,
        anchor="mt",
        align="center"
    )

    # 底部小字 "Activity"
    try:
        small_font = ImageFont.truetype("segoeui.ttf", int(s * 0.09))
    except (OSError, IOError):
        try:
            small_font = ImageFont.truetype("arial.ttf", int(s * 0.09))
        except (OSError, IOError):
            small_font = ImageFont.load_default()

    draw.text(
        (s // 2, int(s * 0.65)),
        "Activity",
        fill=(255, 255, 255, 180),
        font=small_font,
        anchor="mt",
        align="center"
    )

    return img


def main():
    base = Path(__file__).parent
    print("Generating GoActivity icons...")

    # 生成主图标 (256px)
    icon_256 = create_icon(256)

    # 保存 .ico 文件（多尺寸）
    ico_path = base / "app_icon.ico"
    icon_256.save(
        str(ico_path),
        format='ICO',
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    print(f"[OK] {ico_path} - multi-size ICO")

    # 保存 PNG 预览
    png_path = base / "app_icon.png"
    icon_256.save(str(png_path), format='PNG')
    print(f"[OK] {png_path} - PNG preview")

    # 保存各尺寸 PNG（供不同场景使用）
    for sz in [16, 32, 48, 64, 128]:
        p = base / f"app_icon_{sz}.png"
        icon_resized = icon_256.resize((sz, sz), Image.Resampling.LANCZOS)
        icon_resized.save(str(p), format='PNG')
        print(f"[OK] {p}")

    print("\nDone! Run create_shortcut.bat to update shortcut icons.")


if __name__ == '__main__':
    main()

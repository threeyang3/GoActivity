"""
创建 GoActivity 图标
生成 .ico 文件用于桌面快捷方式
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os


def create_gradient(width, height, start_color, end_color):
    """创建渐变背景"""
    image = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(image)

    for y in range(height):
        # 计算当前行的颜色
        r = int(start_color[0] + (end_color[0] - start_color[0]) * y / height)
        g = int(start_color[1] + (end_color[1] - start_color[1]) * y / height)
        b = int(start_color[2] + (end_color[2] - start_color[2]) * y / height)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    return image


def create_goactivity_icon(output_path='app_icon.ico', size=256):
    """创建 GoActivity 图标"""

    # 创建渐变背景
    start_color = (41, 128, 185)  # 深蓝色
    end_color = (52, 152, 219)  # 浅蓝色
    image = create_gradient(size, size, start_color, end_color)
    draw = ImageDraw.Draw(image)

    # 绘制外圆
    circle_margin = 15
    draw.ellipse(
        [(circle_margin, circle_margin),
         (size - circle_margin, size - circle_margin)],
        fill=(41, 128, 185, 240)
    )

    # 绘制内圆
    inner_margin = 30
    draw.ellipse(
        [(inner_margin, inner_margin),
         (size - inner_margin, size - inner_margin)],
        fill=(52, 152, 219, 250)
    )

    # 绘制装饰环
    ring_margin = 45
    draw.ellipse(
        [(ring_margin, ring_margin),
         (size - ring_margin, size - ring_margin)],
        fill=None,
        outline=(255, 255, 255, 80),
        width=3
    )

    # 加载字体
    try:
        font_size = size // 3
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)
        except:
            font = ImageFont.load_default()

    # 绘制 "G"
    g_x = size // 2 - 35
    g_y = size // 2 - 10
    draw.text(
        (g_x, g_y),
        "G",
        fill=(255, 255, 255, 255),
        font=font,
        anchor='mm'
    )

    # 绘制 "A"
    a_x = size // 2 + 35
    a_y = size // 2 - 10
    draw.text(
        (a_x, a_y),
        "A",
        fill=(255, 255, 255, 255),
        font=font,
        anchor='mm'
    )

    # 绘制连接线
    line_y = size // 2
    draw.line(
        [(size // 2 - 15, line_y), (size // 2 + 15, line_y)],
        fill=(46, 204, 113, 200),
        width=3
    )

    # 绘制装饰点
    dot_radius = 6
    accent_color = (46, 204, 113, 255)

    # 左边装饰点
    draw.ellipse(
        [(25, size // 2 - dot_radius), (25 + 2 * dot_radius, size // 2 + dot_radius)],
        fill=accent_color
    )

    # 右边装饰点
    draw.ellipse(
        [(size - 25 - 2 * dot_radius, size // 2 - dot_radius), (size - 25, size // 2 + dot_radius)],
        fill=accent_color
    )

    # 绘制底部装饰线
    bottom_y = size * 3 // 4
    draw.line(
        [(50, bottom_y), (size - 50, bottom_y)],
        fill=(255, 255, 255, 60),
        width=2
    )

    # 保存为 .ico 格式
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icons = []
    for s in sizes:
        resized = image.resize(s, Image.Resampling.LANCZOS)
        icons.append(resized)

    icons[0].save(
        output_path,
        format='ICO',
        sizes=[(s.width, s.height) for s in icons],
        append_images=icons[1:]
    )

    print(f"Icon created: {output_path}")
    return output_path


def create_modern_icon(output_path='app_icon_modern.ico', size=256):
    """创建现代风格图标"""

    # 创建基础图像
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # 绘制圆角正方形背景
    margin = 20
    radius = 50
    draw.rounded_rectangle(
        [(margin, margin), (size - margin, size - margin)],
        radius=radius,
        fill=(52, 152, 219, 255)
    )

    # 绘制内边框
    inner_margin = 30
    draw.rounded_rectangle(
        [(inner_margin, inner_margin), (size - inner_margin, size - inner_margin)],
        radius=radius - 5,
        fill=(41, 128, 185, 255)
    )

    # 绘制装饰线条
    line_y = size // 3
    draw.line(
        [(50, line_y), (size - 50, line_y)],
        fill=(46, 204, 113, 200),
        width=4
    )

    # 加载字体
    try:
        font_size = size // 3
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)
        except:
            font = ImageFont.load_default()

    # 绘制文字 "GA"
    draw.text(
        (size // 2, size // 2),
        "GA",
        fill=(255, 255, 255, 255),
        font=font,
        anchor='mm'
    )

    # 绘制底部装饰线
    bottom_y = size * 2 // 3
    draw.line(
        [(50, bottom_y), (size - 50, bottom_y)],
        fill=(46, 204, 113, 200),
        width=4
    )

    # 绘制装饰点
    dot_radius = 5
    accent_color = (46, 204, 113, 255)

    # 底部装饰点
    for i in range(3):
        dot_x = size // 2 - 30 + i * 30
        dot_y = size - 45
        draw.ellipse(
            [(dot_x - dot_radius, dot_y - dot_radius),
             (dot_x + dot_radius, dot_y + dot_radius)],
            fill=accent_color
        )

    # 保存为 .ico 格式
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icons = []
    for s in sizes:
        resized = image.resize(s, Image.Resampling.LANCZOS)
        icons.append(resized)

    icons[0].save(
        output_path,
        format='ICO',
        sizes=[(s.width, s.height) for s in icons],
        append_images=icons[1:]
    )

    print(f"Icon created: {output_path}")
    return output_path


if __name__ == '__main__':
    # 创建两种风格的图标
    icon1 = create_goactivity_icon('app_icon.ico')
    icon2 = create_modern_icon('app_icon_modern.ico')

    print(f"\nIcons created:")
    print(f"  1. {icon1} - 圆形风格")
    print(f"  2. {icon2} - 现代方形风格")

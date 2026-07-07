"""
BubbleTrans 图标 v3.1 — 极简风 + 海鸥书
上方：三个线框漫画气泡
下方：海鸥式摊开书本（椭圆弧线 + 书脊）
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw


TEAL = "#1DE9B6"
WHITE = "#FFFFFF"


def hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def draw_bubble(draw, cx, cy, w, h, tail_x, tail_y, tail_w, tail_h, color):
    """线框气泡：椭圆 + 尾巴"""
    left = cx - w // 2
    top = cy - h // 2
    right = cx + w // 2
    bottom = cy + h // 2
    r = h // 3
    draw.rounded_rectangle([left, top, right, bottom], radius=r,
                           outline=color, width=3)
    draw.polygon([
        (tail_x, tail_y),
        (tail_x - tail_w, tail_y - tail_h),
        (tail_x + tail_w, tail_y - tail_h),
    ], fill=color)


def draw_seagull_book(draw, cx, top_y, bottom_y, half_width, color):
    """海鸥式摊开书本 — 两条椭圆弧线 + 书脊"""

    # 左侧书页弧线：从书脊底部 → 左侧 → 书脊顶部
    l_box = (cx - half_width, top_y - 20, cx, bottom_y)
    draw.arc(l_box, start=90, end=270, fill=color, width=3)

    # 右侧书页弧线：从书脊顶部 → 右侧 → 书脊底部
    r_box = (cx, top_y - 20, cx + half_width, bottom_y)
    draw.arc(r_box, start=270, end=90, fill=color, width=3)

    # 书脊竖线
    spine_top = top_y - 6
    spine_bot = bottom_y - 2
    draw.line([(cx, spine_top), (cx, spine_bot)], fill=color, width=2)

    # 内层页线（左）
    inner_offset = 10
    l_inner = (cx - half_width + inner_offset, top_y - 14,
               cx - inner_offset, bottom_y - inner_offset)
    draw.arc(l_inner, start=90, end=270, fill=color, width=2)

    # 内层页线（右）
    r_inner = (cx + inner_offset, top_y - 14,
               cx + half_width - inner_offset, bottom_y - inner_offset)
    draw.arc(r_inner, start=270, end=90, fill=color, width=2)


def create_icon(size: int = 256) -> Image.Image:
    bg = hex_to_rgb(TEAL)
    fg = hex_to_rgb(WHITE)

    img = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(img)

    # 圆角背景
    m = 8
    draw.rounded_rectangle([m, m, size - m, size - m], radius=36, fill=bg)

    # ===== 上方：三个漫画气泡 =====
    # 左
    draw_bubble(draw, cx=82, cy=90, w=70, h=46,
                tail_x=68, tail_y=114, tail_w=9, tail_h=13, color=fg)
    # 右
    draw_bubble(draw, cx=178, cy=76, w=74, h=48,
                tail_x=192, tail_y=100, tail_w=9, tail_h=13, color=fg)
    # 中（最前）
    draw_bubble(draw, cx=128, cy=106, w=86, h=54,
                tail_x=128, tail_y=134, tail_w=10, tail_h=15, color=fg)

    # ===== 下方：海鸥式书本 =====
    draw_seagull_book(draw, cx=128, top_y=148, bottom_y=232,
                      half_width=76, color=fg)

    return img


def save_ico(image, output_path):
    sizes = [256, 128, 64, 48, 32, 16]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(output_path), format="ICO", sizes=[(s, s) for s in sizes])
    print(f"  OK {output_path} ({', '.join(str(s) for s in sizes)}px)")


def main():
    root = Path(__file__).parent.parent
    assets = root / "file"

    print("[BubbleTrans] Generating icon v3.1...")
    icon = create_icon(256)

    png = assets / "icon.png"
    icon.save(str(png), format="PNG")
    print(f"  OK {png} (256x256)")

    ico = assets / "icon.ico"
    save_ico(icon, ico)

    print("\n[Done] PyInstaller: --icon=file/icon.ico")


if __name__ == "__main__":
    main()

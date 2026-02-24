#!/usr/bin/env python3
"""
Generate 5 XHS marketing slides for 100baggers.club

Input:  screenshots in images/ (1.png - 5.png)
Output: final/ at 1080x1440 (3:4, XHS optimal)
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# === Paths ===
BASE = Path(__file__).parent
SRC = BASE / "images"
OUT = BASE / "final"
OUT.mkdir(exist_ok=True)

# === Dimensions ===
W, H = 1080, 1440
PX = 48   # horizontal padding
PY = 36   # top padding

# === Colors ===
WHITE = (255, 255, 255, 255)
DARK = (26, 26, 46)
MID = (85, 85, 112)
ACCENT = (67, 97, 238)
LIGHT = (160, 163, 185)
FOOTER_C = (192, 192, 210)
DIVIDER = (230, 230, 240)

# Badge colors per ticker
BADGE_COLORS = {
    "ANET": (67, 97, 238),
    "ORCL": (42, 157, 143),
    "APP": (232, 98, 90),
    "AAPL": (90, 90, 90),
}


# === Font loading ===
def _font(size, bold=False):
    """Load a Chinese-capable font from system."""
    fp = "/System/Library/Fonts/PingFang.ttc"
    if bold:
        # Try heavier weights first (Medium, Semibold)
        for idx in [8, 5, 4, 3, 2, 1, 0]:
            try:
                return ImageFont.truetype(fp, size, index=idx)
            except Exception:
                continue
    # Regular
    for idx in [0, 3, 6]:
        try:
            return ImageFont.truetype(fp, size, index=idx)
        except Exception:
            continue
    # Fallback
    for fallback in [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]:
        try:
            return ImageFont.truetype(fallback, size, index=0)
        except Exception:
            continue
    return ImageFont.load_default()


# Pre-loaded fonts
F = {
    "title": _font(44, bold=True),
    "sub": _font(28),
    "body": _font(24),
    "small": _font(20),
    "brand": _font(28, bold=True),
    "footer": _font(17),
    "badge": _font(20, bold=True),
    "cta_btn": _font(30, bold=True),
    "offer_title": _font(30, bold=True),
    "offer": _font(24),
    "check": _font(24, bold=True),
}


# === Drawing helpers ===

def new_canvas():
    return Image.new("RGBA", (W, H), WHITE)


def text_w(draw, text, font):
    """Get text width, compatible with old and new Pillow."""
    try:
        return draw.textlength(text, font=font)
    except AttributeError:
        return draw.textsize(text, font=font)[0]


def brand_header(draw):
    """Draw consistent brand header across all slides."""
    draw.text((PX, PY), "100BAGGERS.CLUB", fill=ACCENT, font=F["brand"])
    t = "深度研报"
    tw = text_w(draw, t, F["small"])
    draw.text((W - PX - tw, PY + 6), t, fill=LIGHT, font=F["small"])


def ticker_badge(draw, ticker, y=PY):
    """Draw colored ticker badge on the right side."""
    color = BADGE_COLORS.get(ticker, ACCENT)
    tw = text_w(draw, ticker, F["badge"])
    bw = int(tw) + 28
    x = W - PX - bw
    draw.rounded_rectangle([(x, y), (x + bw, y + 34)], radius=8, fill=color)
    draw.text((x + 14, y + 5), ticker, fill=(255, 255, 255), font=F["badge"])


def footer(draw, text):
    draw.text((PX, H - 52), text, fill=FOOTER_C, font=F["footer"])


def crop_pct(img, l=0, t=0, r=1, b=1):
    """Crop image by percentage coordinates [0-1]."""
    iw, ih = img.size
    return img.crop((int(iw * l), int(ih * t), int(iw * r), int(ih * b)))


def fit_to(img, max_w, max_h=None):
    """Scale image to fit within max_w (and optionally max_h)."""
    ratio = max_w / img.width
    nw, nh = max_w, int(img.height * ratio)
    if max_h and nh > max_h:
        ratio = max_h / img.height
        nw, nh = int(img.width * ratio), max_h
    return img.resize((nw, nh), Image.LANCZOS)


def round_corners(img, r=16):
    """Apply rounded corners via alpha mask."""
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (img.width - 1, img.height - 1)], radius=r, fill=255
    )
    img.putalpha(mask)
    return img


def paint_shadow(canvas, x, y, w, h, r=16, blur=18, offset=4, opacity=40):
    """Composite a soft drop shadow onto the canvas."""
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(
        [(x + offset, y + offset), (x + w + offset, y + h + offset)],
        radius=r, fill=(0, 0, 0, opacity)
    )
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(layer)


def place(canvas, img, x, y, corner_r=16):
    """Place screenshot with rounded corners + shadow."""
    rimg = round_corners(img, corner_r)
    paint_shadow(canvas, x, y, img.width, img.height)
    canvas.paste(rimg, (x, y), rimg)


def save(canvas, name):
    canvas.convert("RGB").save(OUT / name, quality=95)
    print(f"  -> {name}")


# === Slide builders ===

def slide1():
    """Cover: ecosystem relationship map + report cards."""
    c = new_canvas()
    d = ImageDraw.Draw(c)
    brand_header(d)

    # Title block
    y = 88
    d.text((PX, y), "穿越周期", fill=DARK, font=F["title"])
    d.text((PX, y + 54), "寻找值得持有十年的公司", fill=DARK, font=F["title"])
    d.text(
        (PX, y + 116),
        "AI × 人类协作 · 机构级深度调研 · 25家公司",
        fill=MID, font=F["sub"],
    )

    # Ecosystem map (top portion of reports page)
    src = Image.open(SRC / "1.png").convert("RGBA")
    eco = crop_pct(src, 0.02, 0.04, 0.98, 0.57)
    eco = fit_to(eco, W - PX * 2, 520)
    eco_y = y + 162
    place(c, eco, PX, eco_y)

    # Report cards (bottom portion)
    cards_y = eco_y + eco.height + 14
    cards = crop_pct(src, 0.04, 0.57, 0.96, 0.92)
    cards = fit_to(cards, W - PX * 2, H - cards_y - 68)
    place(c, cards, PX, cards_y)

    footer(d, "100baggers.club · 穿越周期 · 只做深度")
    save(c, "1.png")


def slide2():
    """ANET: Token economy deep analysis."""
    c = new_canvas()
    d = ImageDraw.Draw(c)
    brand_header(d)
    ticker_badge(d, "ANET")

    y = 82
    d.text((PX, y), "每份报告 40+ 分析模块", fill=DARK, font=F["title"])
    d.text(
        (PX, y + 54),
        "Token经济爆发与推理基础设施新范式",
        fill=MID, font=F["sub"],
    )

    # Screenshot: crop out left sidebar + top nav
    src = Image.open(SRC / "2.png").convert("RGBA")
    content = crop_pct(src, 0.20, 0.06, 0.99, 0.97)
    shot_y = y + 120
    content = fit_to(content, W - PX * 2, H - shot_y - 72)
    place(c, content, PX, shot_y)

    footer(d, "摘自 ANET 深度研报 · 226张数据表 · 25章节")
    save(c, "2.png")


def slide3():
    """ORCL: Financial stress testing."""
    c = new_canvas()
    d = ImageDraw.Draw(c)
    brand_header(d)
    ticker_badge(d, "ORCL")

    y = 82
    d.text((PX, y), "财务韧性压力测试", fill=DARK, font=F["title"])
    d.text(
        (PX, y + 54),
        "债务到期建模 · 利息覆盖率 · Altman Z-Score",
        fill=MID, font=F["sub"],
    )

    src = Image.open(SRC / "3.png").convert("RGBA")
    content = crop_pct(src, 0.20, 0.06, 0.99, 0.97)
    shot_y = y + 120
    content = fit_to(content, W - PX * 2, H - shot_y - 72)
    place(c, content, PX, shot_y)

    footer(d, "摘自 ORCL 深度研报 · 177张数据表 · 36张图表")
    save(c, "3.png")


def slide4():
    """APP: Cascade dependency analysis."""
    c = new_canvas()
    d = ImageDraw.Draw(c)
    brand_header(d)
    ticker_badge(d, "APP")

    y = 82
    d.text((PX, y), "承重墙级联依赖分析", fill=DARK, font=F["title"])
    d.text(
        (PX, y + 54),
        "概率 × 影响矩阵 · 级联路径 · 脆弱度评估",
        fill=MID, font=F["sub"],
    )

    src = Image.open(SRC / "4.png").convert("RGBA")
    content = crop_pct(src, 0.20, 0.04, 0.99, 0.97)
    shot_y = y + 120
    content = fit_to(content, W - PX * 2, H - shot_y - 72)
    place(c, content, PX, shot_y)

    footer(d, "摘自 APP 深度研报 · 166张数据表 · 86张图表")
    save(c, "4.png")


def slide5():
    """CTA: offering + call to action."""
    c = new_canvas()
    d = ImageDraw.Draw(c)
    brand_header(d)

    # Title
    y = 100
    d.text((PX, y), "25家公司深度研报", fill=DARK, font=F["title"])
    d.text((PX, y + 56), "每周持续上新", fill=DARK, font=F["title"])

    # Divider
    div_y = y + 128
    d.line([(PX, div_y), (W - PX, div_y)], fill=DIVIDER, width=2)

    # Benefits
    benefits = [
        "所有深度报告无限访问与下载",
        "40+ 分析模块：护城河量化 · 财务建模 · Reverse DCF",
        "每家公司上百张数据表与可视化图表",
        "AI广度 × 人类判断力，机构级调研深度",
    ]
    by = div_y + 28
    for b in benefits:
        d.text((PX, by), "✦", fill=ACCENT, font=F["check"])
        d.text((PX + 36, by), b, fill=MID, font=F["offer"])
        by += 48

    # Report cards preview from image 1
    cards_y = by + 24
    src = Image.open(SRC / "1.png").convert("RGBA")
    cards = crop_pct(src, 0.04, 0.55, 0.96, 0.95)
    cards = fit_to(cards, W - PX * 2, 520)
    place(c, cards, PX, cards_y)

    # AAPL core findings teaser from image 5
    aapl_y = cards_y + cards.height + 16
    src5 = Image.open(SRC / "5.png").convert("RGBA")
    aapl = crop_pct(src5, 0.20, 0.06, 0.99, 0.50)
    remaining_h = H - aapl_y - 180  # leave room for CTA + footer
    aapl = fit_to(aapl, W - PX * 2, max(remaining_h, 200))
    place(c, aapl, PX, aapl_y)

    # CTA button
    btn_y = aapl_y + aapl.height + 28
    btn_w, btn_h = 360, 56
    btn_x = (W - btn_w) // 2
    d.rounded_rectangle(
        [(btn_x, btn_y), (btn_x + btn_w, btn_y + btn_h)],
        radius=14, fill=ACCENT,
    )
    cta = "100baggers.club"
    tw = text_w(d, cta, F["cta_btn"])
    d.text((int((W - tw) / 2), btn_y + 10), cta, fill=(255, 255, 255), font=F["cta_btn"])

    # Tagline
    tag = "穿越周期 · 只做深度"
    tw2 = text_w(d, tag, F["small"])
    d.text((int((W - tw2) / 2), btn_y + btn_h + 16), tag, fill=LIGHT, font=F["small"])

    # Disclaimer
    d.text(
        (PX, H - 48),
        "⚠️ 所有数据来自深度研究报告，不构成投资建议",
        fill=FOOTER_C, font=F["footer"],
    )
    save(c, "5.png")


# === Main ===
if __name__ == "__main__":
    print("Composing XHS marketing slides (1080x1440)...")
    print(f"  Source: {SRC}/")
    print(f"  Output: {OUT}/\n")
    slide1()
    slide2()
    slide3()
    slide4()
    slide5()
    print(f"\nDone! 5 slides in {OUT}/")

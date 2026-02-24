#!/usr/bin/env python3
"""Compose final XHS slides: white background + real website screenshots + text."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CAPTURES = Path(__file__).parent / "captures"
OUTPUT = Path(__file__).parent / "images"
OUTPUT.mkdir(exist_ok=True)

# Final slide dimensions (XHS 3:4)
W, H = 1080, 1440
# Captures are 2x retina (2880x1800), so scale factor
CAP_SCALE = 2


def load_capture(name):
    """Load a capture and return at 1x scale."""
    img = Image.open(CAPTURES / name)
    return img.resize((img.width // CAP_SCALE, img.height // CAP_SCALE), Image.LANCZOS)


def crop_capture(img, x, y, w, h):
    """Crop a region from a 1x-scaled capture."""
    return img.crop((x, y, x + w, y + h))


def try_load_font(size):
    """Try to load a Chinese-capable font."""
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def try_load_bold_font(size):
    """Try to load a bold Chinese font."""
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",  # index 0 is regular, but still good
        "/System/Library/Fonts/STHeiti Medium.ttc",
    ]
    for fp in font_paths:
        try:
            # Try bold variant (index 1 or 2 in .ttc)
            for idx in [1, 2, 0]:
                try:
                    return ImageFont.truetype(fp, size, index=idx)
                except Exception:
                    continue
        except (OSError, IOError):
            continue
    return try_load_font(size)


# Fonts
FONT_TITLE = try_load_bold_font(42)
FONT_SUB = try_load_font(28)
FONT_SMALL = try_load_font(22)
FONT_BRAND = try_load_bold_font(26)
FONT_TINY = try_load_font(18)

COLOR_TITLE = "#1a1a2e"
COLOR_SUB = "#555570"
COLOR_ACCENT = "#4361ee"
COLOR_LIGHT = "#8a8fa8"
COLOR_BRAND = "#4361ee"


def draw_brand_header(draw):
    """Draw 100BAGGERS.CLUB brand at top."""
    draw.text((48, 36), "100BAGGERS.CLUB", fill=COLOR_BRAND, font=FONT_BRAND)
    draw.text((W - 200, 40), "深度研报", fill=COLOR_LIGHT, font=FONT_SMALL)


def draw_footer(draw, text="100baggers.club"):
    """Draw footer text."""
    draw.text((48, H - 52), text, fill="#b0b0c0", font=FONT_TINY)


def make_slide1():
    """Cover: ecosystem relationship map from reports page."""
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)

    draw_brand_header(draw)

    # Title
    draw.text((48, 90), "穿越周期", fill=COLOR_TITLE, font=FONT_TITLE)
    draw.text((48, 140), "寻找值得持有十年的公司", fill=COLOR_TITLE, font=FONT_TITLE)
    draw.text((48, 198), "AI × 人类协作 · 机构级深度调研", fill=COLOR_SUB, font=FONT_SUB)

    # Load ecosystem map screenshot - crop just the map area
    cap = load_capture("reports_page_top.png")
    # The ecosystem map starts around y=210 in the 1x image, full width
    map_crop = crop_capture(cap, 0, 200, cap.width, cap.height - 200)
    # Scale to fit slide width with padding
    target_w = W - 32
    scale = target_w / map_crop.width
    target_h = int(map_crop.height * scale)
    map_resized = map_crop.resize((target_w, target_h), Image.LANCZOS)
    canvas.paste(map_resized, (16, 248))

    # Load report cards below the map
    cap2 = load_capture("reports_scroll_01.png")
    cards_crop = crop_capture(cap2, 60, 80, cap2.width - 120, 440)
    card_w = W - 32
    card_scale = card_w / cards_crop.width
    card_h = int(cards_crop.height * card_scale)
    cards_resized = cards_crop.resize((card_w, card_h), Image.LANCZOS)

    card_y = 248 + target_h + 10
    if card_y + card_h <= H - 60:
        canvas.paste(cards_resized, (16, card_y))

    draw_footer(draw)
    canvas.save(OUTPUT / "slide1.png", quality=95)
    print("  -> slide1.png (cover + ecosystem map)")


def make_slide2():
    """Tesla: profitability trend + financial table."""
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)

    draw_brand_header(draw)

    # Ticker badge
    draw.rounded_rectangle([(W - 220, 32), (W - 140, 64)], radius=6, fill="#e8625a")
    draw.text((W - 212, 34), "TSLA", fill="white", font=FONT_SMALL)

    # Title
    draw.text((48, 86), "特斯拉：$425 背后你在押注什么？", fill=COLOR_TITLE, font=FONT_TITLE)
    draw.text((48, 140), "Reverse DCF 拆解 · 三情景估值 · 盈利趋势", fill=COLOR_SUB, font=FONT_SUB)

    # Load Tesla profitability trend flowchart
    cap1 = load_capture("tsla_scroll_05.png")
    # Crop the flowchart area (it's roughly centered, y=60 to y=430 in 1x)
    flow_crop = crop_capture(cap1, 260, 50, 580, 400)
    flow_w = W - 64
    flow_scale = flow_w / flow_crop.width
    flow_h = int(flow_crop.height * flow_scale)
    flow_resized = flow_crop.resize((flow_w, flow_h), Image.LANCZOS)
    canvas.paste(flow_resized, (32, 188))

    # Load Tesla financial table
    cap2 = load_capture("tsla_scroll_03.png")
    # Crop the 4-year income table area
    table_crop = crop_capture(cap2, 130, 120, 590, 340)
    table_w = W - 64
    table_scale = table_w / table_crop.width
    table_h = int(table_crop.height * table_scale)
    table_resized = table_crop.resize((table_w, table_h), Image.LANCZOS)
    table_y = 188 + flow_h + 24
    canvas.paste(table_resized, (32, table_y))

    # Load key findings
    cap3 = load_capture("tsla_scroll_04.png")
    findings_crop = crop_capture(cap3, 130, 260, 590, 190)
    find_w = W - 64
    find_scale = find_w / findings_crop.width
    find_h = int(findings_crop.height * find_scale)
    findings_resized = findings_crop.resize((find_w, find_h), Image.LANCZOS)
    findings_y = table_y + table_h + 16
    if findings_y + find_h <= H - 80:
        canvas.paste(findings_resized, (32, findings_y))

    draw.text((48, H - 60), "摘自特斯拉深度研报 · 356,374 字 · 254 张数据表", fill="#b0b0c0", font=FONT_TINY)
    draw_footer(draw, "100baggers.club")
    canvas.save(OUTPUT / "slide2.png", quality=95)
    print("  -> slide2.png (Tesla analysis)")


def make_slide3():
    """TSMC: attention ranking + revenue structure."""
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)

    draw_brand_header(draw)

    # Ticker badge
    draw.rounded_rectangle([(W - 210, 32), (W - 140, 64)], radius=6, fill="#2a9d8f")
    draw.text((W - 204, 34), "TSM", fill="white", font=FONT_SMALL)

    draw.text((48, 86), "台积电：核心问题评分矩阵", fill=COLOR_TITLE, font=FONT_TITLE)
    draw.text((48, 140), "10 大关键问题 · 注意力排名 · 置信度评估", fill=COLOR_SUB, font=FONT_SUB)

    # Load attention ranking table
    cap1 = load_capture("tsm_scroll_06.png")
    # Crop the ranking table
    rank_crop = crop_capture(cap1, 130, 30, 590, 310)
    rank_w = W - 48
    rank_scale = rank_w / rank_crop.width
    rank_h = int(rank_crop.height * rank_scale)
    rank_resized = rank_crop.resize((rank_w, rank_h), Image.LANCZOS)
    canvas.paste(rank_resized, (24, 188))

    # Load revenue structure tables
    cap2 = load_capture("tsm_scroll_08.png")
    rev_crop = crop_capture(cap2, 130, 40, 590, 410)
    rev_w = W - 48
    rev_scale = rev_w / rev_crop.width
    rev_h = int(rev_crop.height * rev_scale)
    rev_resized = rev_crop.resize((rev_w, rev_h), Image.LANCZOS)
    rev_y = 188 + rank_h + 24
    if rev_y + rev_h <= H - 80:
        canvas.paste(rev_resized, (24, rev_y))

    draw.text((48, H - 60), "摘自台积电深度研报 · 68,000 字 · 225 张数据表 · 29 章节", fill="#b0b0c0", font=FONT_TINY)
    draw_footer(draw, "100baggers.club")
    canvas.save(OUTPUT / "slide3.png", quality=95)
    print("  -> slide3.png (TSMC analysis)")


def make_slide4():
    """Google: key signals + org chart."""
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)

    draw_brand_header(draw)

    # Ticker badge
    draw.rounded_rectangle([(W - 240, 32), (W - 140, 64)], radius=6, fill="#4361ee")
    draw.text((W - 232, 34), "GOOGL", fill="white", font=FONT_SMALL)

    draw.text((48, 86), "谷歌：$311 的三面承重墙", fill=COLOR_TITLE, font=FONT_TITLE)
    draw.text((48, 140), "关键信号 · 核心问题 · 组织架构", fill=COLOR_SUB, font=FONT_SUB)

    # Load key signals (positive/negative/neutral labels)
    cap1 = load_capture("googl_scroll_03.png")
    signals_crop = crop_capture(cap1, 130, 100, 590, 280)
    sig_w = W - 48
    sig_scale = sig_w / signals_crop.width
    sig_h = int(signals_crop.height * sig_scale)
    sig_resized = signals_crop.resize((sig_w, sig_h), Image.LANCZOS)
    canvas.paste(sig_resized, (24, 188))

    # Load org chart
    cap2 = load_capture("googl_scroll_07.png")
    org_crop = crop_capture(cap2, 130, 250, 600, 200)
    org_w = W - 48
    org_scale = org_w / org_crop.width
    org_h = int(org_crop.height * org_scale)
    org_resized = org_crop.resize((org_w, org_h), Image.LANCZOS)
    org_y = 188 + sig_h + 20
    canvas.paste(org_resized, (24, org_y))

    # Load CQ questions section
    cap3 = load_capture("googl_scroll_03.png")
    cq_crop = crop_capture(cap3, 130, 370, 590, 80)
    cq_w = W - 48
    cq_scale = cq_w / cq_crop.width
    cq_h = int(cq_crop.height * cq_scale)
    cq_resized = cq_crop.resize((cq_w, cq_h), Image.LANCZOS)
    cq_y = org_y + org_h + 20
    if cq_y + cq_h <= H - 80:
        canvas.paste(cq_resized, (24, cq_y))

    draw.text((48, H - 60), "摘自谷歌深度研报 · 287,613 字 · 182 张数据表 · 145 张图表", fill="#b0b0c0", font=FONT_TINY)
    draw_footer(draw, "100baggers.club")
    canvas.save(OUTPUT / "slide4.png", quality=95)
    print("  -> slide4.png (Google analysis)")


def make_slide5():
    """CTA: report cards + offering."""
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)

    draw_brand_header(draw)

    draw.text((48, 90), "25 家公司深度研报", fill=COLOR_TITLE, font=FONT_TITLE)
    draw.text((48, 142), "每周持续上新", fill=COLOR_TITLE, font=FONT_TITLE)
    draw.text((48, 198), "AI × 人类协作 · 机构级深度调研", fill=COLOR_SUB, font=FONT_SUB)

    # Load report cards showing TSLA, GOOGL, PLTR
    cap = load_capture("reports_scroll_01.png")
    cards_crop = crop_capture(cap, 50, 70, cap.width - 100, 420)
    card_w = W - 32
    card_scale = card_w / cards_crop.width
    card_h = int(cards_crop.height * card_scale)
    cards_resized = cards_crop.resize((card_w, card_h), Image.LANCZOS)
    canvas.paste(cards_resized, (16, 254))

    # Load second row of cards (META, RDDT, RBLX)
    cap2 = load_capture("reports_scroll_02.png")
    cards2_crop = crop_capture(cap2, 50, 50, cap2.width - 100, 320)
    card2_w = W - 32
    card2_scale = card2_w / cards2_crop.width
    card2_h = int(cards2_crop.height * card2_scale)
    cards2_resized = cards2_crop.resize((card2_w, card2_h), Image.LANCZOS)
    cards2_y = 254 + card_h + 8
    canvas.paste(cards2_resized, (16, cards2_y))

    # Offering text
    offer_y = cards2_y + card2_h + 36
    draw.text((48, offer_y), "你将获得：", fill=COLOR_TITLE, font=FONT_SUB)
    draw.text((48, offer_y + 40), "· 一个月内所有深度报告的无限访问与下载", fill=COLOR_SUB, font=FONT_SMALL)
    draw.text((48, offer_y + 72), "· 从 25 家热门公司起步，每周持续上新", fill=COLOR_SUB, font=FONT_SMALL)
    draw.text((48, offer_y + 104), "· 40+ 分析模块：护城河量化 · 财务建模 · Reverse DCF", fill=COLOR_SUB, font=FONT_SMALL)

    # CTA
    cta_y = offer_y + 160
    draw.rounded_rectangle([(W // 2 - 180, cta_y), (W // 2 + 180, cta_y + 56)], radius=12, fill=COLOR_ACCENT)
    draw.text((W // 2 - 110, cta_y + 12), "100baggers.club", fill="white", font=FONT_SUB)

    draw.text((W // 2 - 90, cta_y + 70), "穿越周期 · 只做深度", fill=COLOR_LIGHT, font=FONT_SMALL)

    # Disclaimer
    draw.text((48, H - 52), "⚠️ 所有数据来自 100baggers.club 深度研究报告，不构成投资建议", fill="#c0c0c0", font=FONT_TINY)

    canvas.save(OUTPUT / "slide5.png", quality=95)
    print("  -> slide5.png (CTA)")


def main():
    print("Composing slides with real screenshots...")
    make_slide1()
    make_slide2()
    make_slide3()
    make_slide4()
    make_slide5()
    print(f"\nDone! All slides in {OUTPUT}/")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Render 5 XHS marketing slides using HTML+CSS via Playwright.

Pre-crops screenshots with PIL to remove sidebar/nav,
then renders beautiful HTML slides at 1080x1440.

Input:  images/1.png - 5.png (website screenshots)
Output: final/1.png - 5.png
"""

import base64
import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = Path(__file__).parent
SRC = BASE / "images"
OUT = BASE / "final"
OUT.mkdir(exist_ok=True)

W, H = 1080, 1440


# ── Image helpers ───────────────────────────────────────────

def crop_b64(name, left=0, top=0, right=1, bottom=1):
    """Load image, crop by percentages, return as base64 data URI."""
    img = Image.open(SRC / name)
    w, h = img.size
    cropped = img.crop((int(w * left), int(h * top), int(w * right), int(h * bottom)))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG", quality=95)
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"


def full_b64(name):
    """Encode full image as base64."""
    data = (SRC / name).read_bytes()
    return f"data:image/png;base64,{base64.b64encode(data).decode()}"


# ── Pre-crop all screenshots ────────────────────────────────

def prepare_images():
    """Pre-crop all screenshots and return base64 URIs."""
    return {
        # Slide 1: ecosystem map (top portion, full width, include more)
        "eco_map": crop_b64("1.png", 0.02, 0.05, 0.98, 0.60),
        # Slide 1: report cards (full card row with stats)
        "cards": crop_b64("1.png", 0.04, 0.62, 0.96, 0.96),
        # Slide 2: ANET content area (remove sidebar + nav)
        "anet": crop_b64("2.png", 0.22, 0.08, 0.99, 0.97),
        # Slide 3: ORCL content area
        "orcl": crop_b64("3.png", 0.22, 0.06, 0.99, 0.97),
        # Slide 4: APP content area
        "app": crop_b64("4.png", 0.22, 0.05, 0.99, 0.97),
        # Slide 5: semiconductor reports grid (remove nav bar)
        "semi_grid": crop_b64("6.png", 0.02, 0.04, 0.98, 0.92),
        # Logo: icon + text cropped from website
        "logo": crop_b64("logo_crop.png", 0, 0, 1, 1),
    }


# ── Shared CSS ──────────────────────────────────────────────

COMMON_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    width: 1080px;
    height: 1440px;
    background: #ffffff;
    font-family: -apple-system, 'PingFang SC', 'SF Pro Display',
                 'Noto Sans SC', 'Helvetica Neue', sans-serif;
    color: #1a1a2e;
    overflow: hidden;
    position: relative;
    -webkit-font-smoothing: antialiased;
}

.brand {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 42px 52px 0;
}
.brand-logo {
    height: 36px;
    display: block;
}
.brand-tag {
    font-size: 17px;
    color: #b0b3c8;
    font-weight: 500;
    letter-spacing: 1px;
}

.badge {
    display: inline-block;
    padding: 6px 18px;
    border-radius: 8px;
    color: #fff;
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 1.5px;
}

.shot {
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 6px 28px rgba(0,0,0,0.09), 0 1.5px 6px rgba(0,0,0,0.05);
    border: 1px solid rgba(0,0,0,0.05);
}
.shot img {
    display: block;
    width: 100%;
    height: auto;
}

.footer {
    position: absolute;
    bottom: 38px;
    left: 52px;
    right: 52px;
    font-size: 14px;
    color: #c0c3d6;
    letter-spacing: 0.3px;
}

.accent-bar {
    width: 44px;
    height: 4px;
    background: #4361ee;
    border-radius: 2px;
    margin-bottom: 14px;
}

h1 {
    font-size: 48px;
    font-weight: 800;
    line-height: 1.28;
    color: #1a1a2e;
    letter-spacing: 1.5px;
}

.subtitle {
    font-size: 22px;
    color: #6b6f8a;
    font-weight: 500;
    margin-top: 12px;
    letter-spacing: 0.5px;
    line-height: 1.5;
}
.subtitle em {
    font-style: normal;
    color: #4361ee;
    font-weight: 600;
}
"""


# ── Slide HTML ──────────────────────────────────────────────

def slide1_html(imgs):
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{COMMON_CSS}
.hero {{ padding: 0 52px; margin-top: 28px; }}
.screenshots {{
    padding: 0 40px;
    margin-top: 42px;
    display: flex;
    flex-direction: column;
    gap: 12px;
}}
.screenshots .shot img {{
    width: 100%;
    height: auto;
    max-height: 640px;
    object-fit: cover;
    object-position: center top;
}}
.cards-shot img {{
    max-height: 540px !important;
    object-position: center top !important;
}}
</style></head><body>
<div class="brand">
    <img class="brand-logo" src="{imgs['logo']}">
    <span class="brand-tag">深度研报</span>
</div>
<div class="hero">
    <div class="accent-bar"></div>
    <h1>穿越周期<br>寻找值得持有十年的公司</h1>
    <p class="subtitle"><em>AI × 人类协作</em> · 机构级深度调研 · 25家公司</p>
</div>
<div class="screenshots">
    <div class="shot"><img src="{imgs['eco_map']}"></div>
    <div class="shot cards-shot"><img src="{imgs['cards']}"></div>
</div>
<div class="footer">穿越周期 · 只做深度</div>
</body></html>"""


def slide_content_html(imgs, img_key, badge_text, badge_color,
                       title, subtitle, footer_text, img_max_h="1060px"):
    """Generic template for slides 2-4."""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{COMMON_CSS}
.header {{ padding: 0 52px; margin-top: 22px; }}
.content {{
    padding: 0 40px;
    margin-top: 20px;
}}
.content .shot img {{
    max-height: {img_max_h};
    object-fit: cover;
    object-position: center top;
}}
</style></head><body>
<div class="brand">
    <img class="brand-logo" src="{imgs['logo']}">
    <span class="badge" style="background:{badge_color};">{badge_text}</span>
</div>
<div class="header">
    <div class="accent-bar"></div>
    <h1>{title}</h1>
    <p class="subtitle">{subtitle}</p>
</div>
<div class="content">
    <div class="shot"><img src="{imgs[img_key]}"></div>
</div>
<div class="footer">{footer_text}</div>
</body></html>"""


def slide5_html(imgs):
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{COMMON_CSS}
.hero {{ padding: 0 52px; margin-top: 28px; }}
.hero h1 {{ font-size: 48px; }}
.hero .subtitle {{ margin-top: 8px; }}
.preview {{
    padding: 0 36px;
    margin-top: 40px;
}}
.preview .shot img {{
    max-height: 1080px;
    object-fit: cover;
    object-position: center top;
}}
.footer {{
    text-align: center;
    left: 0; right: 0;
    font-size: 13px;
}}
</style></head><body>
<div class="brand">
    <img class="brand-logo" src="{imgs['logo']}">
    <span class="brand-tag">深度研报</span>
</div>
<div class="hero">
    <div class="accent-bar"></div>
    <h1>25家公司深度研报<br>每周持续上新</h1>
    <p class="subtitle">半导体 · AI平台 · 基础设施 · 数据平台 — 全产业链覆盖</p>
</div>
<div class="preview">
    <div class="shot"><img src="{imgs['semi_grid']}"></div>
</div>
<div class="footer">⚠️ 所有数据来自深度研究报告，不构成投资建议</div>
</body></html>"""


# ── Render ──────────────────────────────────────────────────

def render_slides():
    print("Pre-cropping screenshots...")
    imgs = prepare_images()

    slides = [
        ("1.png", slide1_html(imgs)),
        ("2.png", slide_content_html(
            imgs, "anet", "ANET", "#4361ee",
            "每份报告 40+ 分析模块",
            "Token经济爆发与推理基础设施新范式",
            "摘自 ANET 深度研报 · 226张数据表 · 25章节",
        )),
        ("3.png", slide_content_html(
            imgs, "orcl", "ORCL", "#2a9d8f",
            "财务韧性压力测试",
            "债务到期建模 · 利息覆盖率 · Altman Z-Score",
            "摘自 ORCL 深度研报 · 177张数据表 · 36张图表",
        )),
        ("4.png", slide_content_html(
            imgs, "app", "APP", "#e8625a",
            "承重墙级联依赖分析",
            "概率 × 影响矩阵 · 级联路径 · 脆弱度评估",
            "摘自 APP 深度研报 · 166张数据表 · 86张图表",
            img_max_h="1080px",
        )),
        ("5.png", slide5_html(imgs)),
    ]

    print("Rendering with Playwright...\n")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H})

        for name, html in slides:
            page.set_content(html, wait_until="load")
            page.wait_for_timeout(800)
            page.screenshot(path=str(OUT / name), full_page=False)
            print(f"  -> {name}")

        browser.close()

    print(f"\nDone! 5 slides in {OUT}/")


if __name__ == "__main__":
    render_slides()

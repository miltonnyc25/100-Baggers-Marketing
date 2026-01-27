#!/usr/bin/env python3
"""
小红书封面图生成器
- 从 HTML 模板生成封面图
- 使用 Playwright 渲染
- 统一风格：深蓝背景 + 金色高亮
"""

import os
import sys
import re
from pathlib import Path
from datetime import datetime


def generate_cover_html(template_path, output_path, data):
    """
    从模板生成 HTML 文件
    
    data = {
        'date': '2026.01.26',
        'items': [
            {'ticker': 'IRDM', 'title': '全球唯一卫星网络垄断者', 'highlight': '📉 低估 75%'},
            {'ticker': 'ASML', 'title': 'EUV光刻机龙头 AI芯片必经之路', 'highlight': '📈 5个月翻倍'},
            {'ticker': 'GOLD', 'title': '黄金历史性突破 白银冲上$100', 'highlight': '💰 突破 $5000'},
        ]
    }
    """
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # 替换日期
    html = html.replace('{{DATE}}', data.get('date', datetime.now().strftime('%Y.%m.%d')))
    
    # 替换股票信息
    items = data.get('items', [])
    for i, item in enumerate(items[:3], 1):
        html = html.replace(f'{{{{TICKER{i}}}}}', item.get('ticker', ''))
        html = html.replace(f'{{{{TITLE{i}}}}}', item.get('title', ''))
        html = html.replace(f'{{{{HIGHLIGHT{i}}}}}', item.get('highlight', ''))
    
    # 写入输出文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ HTML 生成: {output_path}")
    return output_path


def html_to_image(html_path, image_path, width=1242, height=1660):
    """
    使用 Playwright 将 HTML 渲染为图片
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ 请安装 playwright: pip install playwright && playwright install chromium")
        return None
    
    print(f"🎨 正在渲染封面图...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': width, 'height': height})
        
        # 加载本地 HTML 文件
        html_url = f"file://{os.path.abspath(html_path)}"
        page.goto(html_url)
        
        # 等待渲染完成
        page.wait_for_load_state('networkidle')
        
        # 截图
        page.screenshot(path=image_path, type='jpeg', quality=95)
        
        browser.close()
    
    size_kb = os.path.getsize(image_path) / 1024
    print(f"✅ 封面图生成: {image_path} ({size_kb:.1f}KB)")
    return image_path


def generate_cover(output_dir, date_str, items):
    """
    完整封面生成流程
    
    Args:
        output_dir: 输出目录
        date_str: 日期字符串 (YYYY-MM-DD)
        items: 股票列表 [{'ticker': 'IRDM', 'title': '...', 'highlight': '...'}, ...]
    
    Returns:
        封面图路径
    """
    # 获取模板路径
    script_dir = Path(__file__).parent
    template_path = script_dir / 'templates' / 'cover.html'
    
    if not template_path.exists():
        raise FileNotFoundError(f"模板文件不存在: {template_path}")
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 格式化日期
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        display_date = dt.strftime('%Y.%m.%d')
    except:
        display_date = date_str.replace('-', '.')
    
    # 生成 HTML
    html_output = output_dir / f"{date_str}-xhs-cover.html"
    data = {
        'date': display_date,
        'items': items
    }
    generate_cover_html(template_path, html_output, data)
    
    # 渲染图片
    image_output = output_dir / f"{date_str}-xhs-cover.jpg"
    html_to_image(html_output, str(image_output))
    
    return str(image_output)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python generate_cover.py <输出目录> <日期YYYY-MM-DD>")
        print("示例: python generate_cover.py ~/clawd/newsletters 2026-01-26")
        sys.exit(1)
    
    output_dir = sys.argv[1]
    date_str = sys.argv[2]
    
    # 示例数据
    items = [
        {'ticker': 'IRDM', 'title': '全球唯一卫星网络垄断者', 'highlight': '📉 低估 75%'},
        {'ticker': 'ASML', 'title': 'EUV光刻机龙头 AI芯片必经之路', 'highlight': '📈 5个月翻倍'},
        {'ticker': 'GOLD', 'title': '黄金历史性突破 白银冲上$100', 'highlight': '💰 突破 $5000'},
    ]
    
    cover_path = generate_cover(output_dir, date_str, items)
    print(f"\n📸 封面图: {cover_path}")

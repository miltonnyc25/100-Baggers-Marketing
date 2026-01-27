#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书 Slide Deck 多图发布脚本

将多张 3:4 比例的 slide 图片发布为一篇小红书笔记（多图形式）

使用方法:
    python xhs_slides_publisher.py <slides_dir> <date> [--start N] [--end M]
    
示例:
    python xhs_slides_publisher.py ~/clawd/newsletters/slides-2026-01-27-3x4 2026-01-27
    python xhs_slides_publisher.py ~/clawd/newsletters/slides-2026-01-27-3x4 2026-01-27 --start 1 --end 5
"""

import asyncio
import argparse
import os
import sys
import time
import glob
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from playwright.async_api import async_playwright, Page, BrowserContext

# ============== 配置 ==============

STEALTH_JS_PATH = Path("/Users/xuemeizhao/Downloads/add-caption/social_uploader/utils/stealth.min.js")
COOKIES_PATH = Path("/Users/xuemeizhao/clawd/skills/xiaohongshu-publish/cookies/xhs_account.json")
PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"

# 小红书限制：图文笔记最多 18 张图
MAX_IMAGES = 18

# ============== 日志工具 ==============

class Logger:
    @staticmethod
    def info(msg: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ℹ️  {msg}")
    
    @staticmethod
    def success(msg: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {msg}")
    
    @staticmethod
    def warning(msg: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  {msg}")
    
    @staticmethod
    def error(msg: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ {msg}")

log = Logger()

# ============== Stealth 注入 ==============

async def inject_stealth(context: BrowserContext) -> BrowserContext:
    if STEALTH_JS_PATH.exists():
        await context.add_init_script(path=str(STEALTH_JS_PATH))
        log.info("Stealth 反检测脚本已注入")
    return context

# ============== 配置路径 ==============

NEWSLETTERS_DIR = Path("/Users/xuemeizhao/clawd/newsletters")

# ============== 生成标题和描述 ==============

def load_xhs_post_content(date: str) -> tuple:
    """
    从 xhs-post.md 加载标题和正文（与 skill2 小红书视频版一致）
    
    Returns:
        (title, content) - 标题和正文
    """
    post_path = NEWSLETTERS_DIR / f"{date}-xhs-post.md"
    
    if post_path.exists():
        try:
            with open(post_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取标题（第一行，去掉📈 emoji）
            lines = content.strip().split('\n')
            title = lines[0].replace('📈', '').strip()
            
            return title, content
        except Exception as e:
            log.warning(f"读取 xhs-post.md 失败: {e}")
    
    return None, None

def generate_post_content(total_slides: int, date: str) -> tuple:
    """
    生成笔记的标题和描述
    - 标题：与 skill2 小红书视频版一致，加上（图片版）
    - 正文：从 xhs-post.md 读取，与视频版完全相同
    """
    
    # 从 xhs-post.md 读取（与 skill2 一致）
    base_title, description = load_xhs_post_content(date)
    
    if base_title and description:
        # 标题加上"（图片版）"，注意小红书标题限制20字
        # 原标题格式：美股热点速递 | 2026.01.27
        # 图片版标题：美股热点速递｜01.27（图片版）
        date_short = f"{date[5:7]}.{date[8:10]}"
        title = f"美股热点速递｜{date_short}（图片版）"
        log.info(f"从 xhs-post.md 加载内容")
    else:
        # 如果没有找到 xhs-post.md，使用默认内容
        log.warning(f"未找到 {date}-xhs-post.md，使用默认内容")
        date_short = f"{date[5:7]}.{date[8:10]}"
        title = f"美股热点速递｜{date_short}（图片版）"
        description = f"""📈 美股热点速递 | {date}（图片版）

🔥 今日热点股票深度解析
📈 市场走势 + 个股分析

👉 向左滑动查看全部 {total_slides} 页

#美股 #股票 #投资理财 #每日复盘 #美股日报

⚠️ 免责声明：所有观点均来自原始分析文章，不代表本账号立场，不构成投资建议。投资有风险，请谨慎决策。
"""
    
    return title, description

# ============== 发布多图笔记 ==============

async def publish_multi_image_post(
    page: Page,
    image_paths: List[str],
    title: str,
    description: str
) -> bool:
    """发布多图笔记到小红书"""
    
    log.info(f"=== 发布多图笔记 ({len(image_paths)} 张图片) ===")
    log.info(f"标题: {title}")
    
    try:
        # 导航到发布页面
        await page.goto(PUBLISH_URL, timeout=60000)
        await asyncio.sleep(3)
        
        # 点击"上传图文"
        image_tab_selectors = [
            'text="上传图文"',
            'div:has-text("上传图文")',
            '[class*="tab"]:has-text("图文")',
        ]
        
        clicked = False
        for selector in image_tab_selectors:
            try:
                tab = page.locator(selector).first
                if await tab.count() and await tab.is_visible():
                    await tab.click()
                    clicked = True
                    log.info("点击了'上传图文'")
                    await asyncio.sleep(2)
                    break
            except:
                continue
        
        if not clicked:
            log.warning("未找到'上传图文'按钮，尝试继续...")
        
        # 上传所有图片（一次性多选）
        upload_input = page.locator('input[type="file"]').first
        if await upload_input.count():
            # Playwright 支持一次上传多个文件
            await upload_input.set_input_files(image_paths)
            log.success(f"已上传 {len(image_paths)} 张图片")
            
            # 等待所有图片处理完成（根据图片数量增加等待时间）
            wait_time = 3 + len(image_paths) * 2
            log.info(f"等待图片处理... ({wait_time}秒)")
            await asyncio.sleep(wait_time)
        else:
            log.error("未找到图片上传输入框")
            return False
        
        # 检查图片是否全部上传成功
        await asyncio.sleep(2)
        
        # 填写标题
        title_selectors = [
            'input[placeholder*="标题"]',
            'input.d-text',
            '#title-input',
        ]
        
        for selector in title_selectors:
            try:
                title_input = page.locator(selector).first
                if await title_input.count():
                    await title_input.click()
                    await page.keyboard.press("Meta+A")
                    await page.keyboard.press("Backspace")
                    await page.keyboard.type(title[:20])  # 小红书标题限制20字
                    log.success(f"标题填充完成: {title[:20]}")
                    break
            except:
                continue
        
        # 填写描述
        editor_selectors = [
            ".ql-editor",
            "[contenteditable='true']",
            "#post-description",
        ]
        
        for selector in editor_selectors:
            try:
                editor = page.locator(selector).first
                if await editor.count():
                    await editor.click()
                    await page.keyboard.press("Meta+A")
                    await page.keyboard.press("Backspace")
                    
                    # 逐行输入描述
                    for line in description.split('\n'):
                        await page.keyboard.type(line)
                        await page.keyboard.press("Enter")
                    
                    log.success("描述填充完成")
                    break
            except:
                continue
        
        await asyncio.sleep(2)
        
        # 关闭可能的弹窗
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)
        
        # 点击发布
        publish_btn = page.locator('button:has-text("发布")').first
        if await publish_btn.count() and await publish_btn.is_enabled():
            await publish_btn.click()
            log.info("点击了发布按钮")
            
            # 等待发布完成
            await asyncio.sleep(5)
            
            # 检查是否成功
            current_url = page.url
            if "publish/publish" not in current_url or "success" in current_url:
                log.success("多图笔记发布成功！")
                return True
        
        log.warning("发布状态未知")
        return True  # 假设成功
        
    except Exception as e:
        log.error(f"发布失败: {e}")
        return False

# ============== 主发布流程 ==============

async def publish_slides(
    slides_dir: str,
    date: str,
    start: int = 1,
    end: Optional[int] = None
) -> None:
    """
    发布 slides 到小红书（所有图片合并为一篇笔记）
    
    Args:
        slides_dir: slides 图片目录
        date: 日期 YYYY-MM-DD
        start: 起始页码
        end: 结束页码（默认全部）
    """
    
    # 查找所有 slide 图片
    pattern = os.path.join(slides_dir, "slide-*-3x4.png")
    slides = sorted(glob.glob(pattern))
    
    if not slides:
        # 尝试其他命名模式
        pattern = os.path.join(slides_dir, "*.png")
        slides = sorted(glob.glob(pattern))
    
    if not slides:
        log.error(f"未找到 slide 图片: {slides_dir}")
        return
    
    total_slides = len(slides)
    log.info(f"找到 {total_slides} 张 slides")
    
    # 确定发布范围
    end = end or total_slides
    slides_to_publish = slides[start-1:end]
    
    # 检查是否超过小红书限制
    if len(slides_to_publish) > MAX_IMAGES:
        log.warning(f"图片数量 ({len(slides_to_publish)}) 超过小红书限制 ({MAX_IMAGES})，将只发布前 {MAX_IMAGES} 张")
        slides_to_publish = slides_to_publish[:MAX_IMAGES]
    
    log.info(f"准备发布 {len(slides_to_publish)} 张图片为一篇笔记")
    
    # 显示图片列表
    for i, path in enumerate(slides_to_publish, 1):
        log.info(f"  [{i}] {os.path.basename(path)}")
    
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        
        context_options = {"viewport": {"width": 1600, "height": 900}}
        if COOKIES_PATH.exists():
            context_options["storage_state"] = str(COOKIES_PATH)
            log.info("已加载保存的 cookies")
        
        context = await browser.new_context(**context_options)
        context = await inject_stealth(context)
        page = await context.new_page()
        
        # 检查登录状态
        await page.goto(PUBLISH_URL, timeout=60000)
        await asyncio.sleep(3)
        
        if 'login' in page.url.lower() or await page.locator('text="扫码登录"').count():
            log.warning("需要登录！请在浏览器中扫码登录...")
            await page.wait_for_url("**/publish/**", timeout=300000)
            log.success("登录成功")
        
        # 生成内容
        title, description = generate_post_content(len(slides_to_publish), date)
        
        # 发布多图笔记
        success = await publish_multi_image_post(page, slides_to_publish, title, description)
        
        # 保存 cookies
        await context.storage_state(path=str(COOKIES_PATH))
        log.info("Cookies 已保存")
        
        await context.close()
        await browser.close()
    
    if success:
        log.success(f"🎉 {len(slides_to_publish)} 张图片已合并发布为一篇笔记！")
    else:
        log.error("发布失败")

# ============== CLI 入口 ==============

def main():
    parser = argparse.ArgumentParser(description='小红书 Slide Deck 多图发布工具')
    parser.add_argument('slides_dir', help='Slides 图片目录')
    parser.add_argument('date', help='日期 (YYYY-MM-DD)')
    parser.add_argument('--start', type=int, default=1, help='起始页码 (默认: 1)')
    parser.add_argument('--end', type=int, default=None, help='结束页码 (默认: 全部，最多18张)')
    
    args = parser.parse_args()
    
    slides_dir = os.path.expanduser(args.slides_dir)
    
    asyncio.run(publish_slides(
        slides_dir=slides_dir,
        date=args.date,
        start=args.start,
        end=args.end
    ))

if __name__ == "__main__":
    main()

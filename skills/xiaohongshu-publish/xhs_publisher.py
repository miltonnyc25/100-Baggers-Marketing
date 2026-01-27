#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书视频发布脚本 - Robust & Reliable
基于 add-caption/social_uploader 代码库的最佳实践

使用方法:
    python xhs_publisher.py <video_path> <cover_path> <post_md_path> [--headless]
    
示例:
    python xhs_publisher.py \
        ~/clawd/newsletters/2026-01-27-video-with-subs.mp4 \
        ~/clawd/newsletters/2026-01-27-cover-xhs.jpg \
        ~/clawd/newsletters/2026-01-27-xhs-post.md
"""

import asyncio
import argparse
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

# Playwright
from playwright.async_api import async_playwright, Page, BrowserContext

# ============== 配置 ==============

# Stealth 脚本路径
STEALTH_JS_PATH = Path("/Users/xuemeizhao/Downloads/add-caption/social_uploader/utils/stealth.min.js")

# Cookie 存储路径
COOKIES_PATH = Path("/Users/xuemeizhao/clawd/skills/xiaohongshu-publish/cookies/xhs_account.json")

# 发布页面 URL
PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video"

# 默认 headless 模式（False = 显示浏览器窗口）
DEFAULT_HEADLESS = False

# ============== 日志工具 ==============

class Logger:
    """简单日志工具"""
    
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
    """注入 stealth.min.js 反检测脚本"""
    if STEALTH_JS_PATH.exists():
        await context.add_init_script(path=str(STEALTH_JS_PATH))
        log.info("Stealth 反检测脚本已注入")
    else:
        log.warning(f"Stealth 脚本不存在: {STEALTH_JS_PATH}")
    return context

# ============== Shepherd 弹窗处理 ==============

async def dismiss_shepherd_overlay(page: Page):
    """关闭 Shepherd.js 新手引导遮罩层"""
    try:
        shepherd_overlay = page.locator('svg.shepherd-modal-is-visible, .shepherd-modal-overlay-container')
        if await shepherd_overlay.count():
            log.info("检测到 Shepherd 新手引导遮罩，尝试关闭...")
            
            # 方法1: 点击"跳过"按钮
            skip_buttons = [
                'button:has-text("跳过")',
                'button:has-text("Skip")',
                '.shepherd-cancel-icon',
                '.shepherd-button-secondary',
                '[class*="shepherd"] button:has-text("关闭")',
                '[class*="shepherd"] button:has-text("知道了")',
                '[class*="shepherd"] button:has-text("我知道了")',
            ]
            
            dismissed = False
            for btn_selector in skip_buttons:
                try:
                    btn = page.locator(btn_selector).first
                    if await btn.count() and await btn.is_visible():
                        await btn.click(force=True, timeout=3000)
                        log.success(f"通过点击 '{btn_selector}' 关闭了引导弹窗")
                        dismissed = True
                        await asyncio.sleep(1)
                        break
                except:
                    continue
            
            # 方法2: 按 Escape 键
            if not dismissed:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
                await page.keyboard.press("Escape")
                log.info("尝试通过 Escape 键关闭引导弹窗")
                await asyncio.sleep(1)
            
            # 方法3: JS 强制移除
            if await shepherd_overlay.count():
                await page.evaluate('''() => {
                    const overlay = document.querySelector('.shepherd-modal-overlay-container');
                    if (overlay) overlay.remove();
                    document.querySelectorAll('[class*="shepherd"]').forEach(el => {
                        if (el.classList.contains('shepherd-modal-is-visible') || 
                            el.classList.contains('shepherd-element')) {
                            el.remove();
                        }
                    });
                    if (window.Shepherd && window.Shepherd.activeTour) {
                        window.Shepherd.activeTour.complete();
                    }
                }''')
                log.success("通过 JS 强制移除了引导遮罩层")
                await asyncio.sleep(1)
                
    except Exception as e:
        log.warning(f"处理 Shepherd 遮罩时出错: {str(e)[:50]}")

# ============== 视频上传 ==============

async def upload_video(page: Page, video_path: str) -> bool:
    """上传视频文件"""
    log.info(f"正在上传视频: {video_path}")
    
    upload_selectors = [
        "div.video-uploader input[type='file']",
        "div[class^='upload-content'] input[class='upload-input']",
        "input[type='file']"
    ]
    
    for selector in upload_selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count():
                await locator.set_input_files(video_path)
                log.success("视频文件已选择，开始上传...")
                return True
        except:
            continue
    
    log.error("未找到视频上传输入框")
    return False

async def wait_for_video_upload(page: Page, timeout_seconds: int = 180) -> bool:
    """等待视频上传完成"""
    log.info(f"等待视频上传完成（最多等待 {timeout_seconds} 秒）...")
    
    start_time = time.time()
    check_interval = 2
    
    while (time.time() - start_time) < timeout_seconds:
        elapsed = int(time.time() - start_time)
        
        try:
            # 检查上传成功标志
            upload_input = await page.wait_for_selector('input.upload-input', timeout=3000)
            if upload_input:
                preview_new = await upload_input.query_selector(
                    'xpath=following-sibling::div[contains(@class, "preview-new")]')
                
                if preview_new:
                    stage_elements = await preview_new.query_selector_all('div.stage')
                    for stage in stage_elements:
                        text_content = await page.evaluate('(element) => element.textContent', stage)
                        if '上传成功' in text_content:
                            # 额外检查：暂存按钮是否可用
                            save_btn_selectors = ['button:has-text("暂存离开")', 'button:has-text("保存草稿")']
                            for s in save_btn_selectors:
                                btn = page.locator(s).first
                                if await btn.count() and await btn.is_enabled():
                                    log.success(f"视频上传成功！（耗时 {elapsed} 秒）")
                                    return True
            
            if elapsed % 10 == 0:
                log.info(f"视频上传中... 已等待 {elapsed} 秒")
            
        except Exception as e:
            if elapsed % 15 == 0:
                log.warning(f"检测过程出错: {str(e)[:50]}，继续等待...")
        
        await asyncio.sleep(check_interval)
    
    log.error(f"视频上传超时（已等待 {timeout_seconds} 秒）")
    return False

# ============== 封面上传 ==============

async def upload_cover(page: Page, cover_path: str) -> bool:
    """
    上传封面图片（⚠️ 必须使用预生成的封面！）
    
    小红书封面上传流程：
    1. 点击"选择封面"或"设置封面"按钮
    2. 等待封面设置弹窗出现
    3. 点击"设置竖封面"或选择 3:4 比例
    4. 找到隐藏的 input 元素上传图片
    5. 点击"完成"或"确定"保存
    """
    log.info(f"正在上传封面: {cover_path}")
    
    try:
        # ============ 方法 1: 使用原始代码库的方法 ============
        # 步骤 1: 点击"选择封面"按钮
        cover_btn_selectors = [
            'text="选择封面"',
            'text="设置封面"',
            'div:has-text("选择封面")',
            'div:has-text("设置封面")',
            'button:has-text("选择封面")',
            'button:has-text("设置封面")',
            '[class*="cover-btn"]',
            '[class*="coverBtn"]',
        ]
        
        clicked = False
        for selector in cover_btn_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.count() and await btn.is_visible():
                    await btn.click()
                    clicked = True
                    log.info(f"点击了封面按钮: {selector}")
                    await asyncio.sleep(2)
                    break
            except:
                continue
        
        if not clicked:
            # 尝试用 JS 查找并点击
            clicked = await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('*'));
                const target = btns.find(el => 
                    el.innerText && 
                    (el.innerText.includes('选择封面') || el.innerText.includes('设置封面')) &&
                    el.offsetParent !== null
                );
                if (target) {
                    target.click();
                    return true;
                }
                return false;
            }''')
            if clicked:
                log.info("通过 JS 点击了封面按钮")
                await asyncio.sleep(2)
        
        if not clicked:
            log.warning("未找到'设置封面'按钮")
            return False
        
        # 步骤 2: 等待封面设置弹窗出现
        modal_appeared = False
        modal_selectors = [
            "div.semi-modal-content:visible",
            "[class*='modal']:visible",
            "[class*='dialog']:visible",
            "[class*='popup']:visible",
        ]
        
        for selector in modal_selectors:
            try:
                await page.wait_for_selector(selector, timeout=5000)
                modal_appeared = True
                log.info("封面设置弹窗已出现")
                break
            except:
                continue
        
        if not modal_appeared:
            log.warning("封面弹窗未出现，尝试继续...")
        
        # 步骤 3: 选择 3:4 比例（竖版封面）
        ratio_selected = False
        
        # 方法 1: 点击"设置竖封面"按钮
        vertical_selectors = [
            'text="设置竖封面"',
            'text="竖封面"',
            'div:has-text("设置竖封面")',
            'div:has-text("竖封面")',
            '[class*="vertical"]',
        ]
        
        for selector in vertical_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.count() and await btn.is_visible():
                    await btn.click()
                    log.success(f"已选择竖封面: {selector}")
                    ratio_selected = True
                    await asyncio.sleep(2)
                    break
            except:
                continue
        
        # 方法 2: 找到封面比例选择器，选择 3:4
        # 小红书的比例选择器：点击 "4:3 ▼" 后会展开三个按钮 [3:4] [4:3] [1:1]
        # 调试发现: class='ratio-select' 是下拉触发器
        if not ratio_selected:
            try:
                # 步骤 1: 点击下拉触发器展开选项
                # 使用更精确的选择器，确保点击的是下拉控件而不是其他元素
                ratio_trigger_selectors = [
                    'div.ratio-select',  # 精确的类名
                    '[class*="ratio-select"]',
                    'div.base-item:has-text("封面比例")',  # 包含封面比例的容器
                ]
                
                trigger_clicked = False
                for trigger_sel in ratio_trigger_selectors:
                    try:
                        trigger = page.locator(trigger_sel).first
                        if await trigger.count() and await trigger.is_visible():
                            await trigger.click()
                            log.info(f"点击了比例下拉触发器: {trigger_sel}")
                            trigger_clicked = True
                            await asyncio.sleep(2)  # 等待选项按钮展开
                            break
                    except:
                        continue
                
                # 如果上面的选择器都没找到，用 JS 查找并点击
                if not trigger_clicked:
                    trigger_clicked = await page.evaluate('''() => {
                        // 查找 ratio-select 元素
                        const ratioSelect = document.querySelector('.ratio-select, [class*="ratio-select"]');
                        if (ratioSelect && ratioSelect.offsetParent) {
                            ratioSelect.click();
                            return true;
                        }
                        return false;
                    }''')
                    if trigger_clicked:
                        log.info("通过 JS 点击了比例下拉触发器 (.ratio-select)")
                        await asyncio.sleep(2)
                
                if trigger_clicked:
                    # 步骤 2: 等待选项展开，然后点击 "3:4" 按钮
                    # 选项是按钮形式：[3:4] [4:3] [1:1]
                    await asyncio.sleep(2)  # 等待选项完全展开
                    
                    # 先打印页面中包含比例相关文字的所有元素（调试用）
                    debug_info = await page.evaluate('''() => {
                        const results = [];
                        const allElements = document.querySelectorAll('*');
                        for (const el of allElements) {
                            const text = (el.innerText || el.textContent || '').trim();
                            // 查找包含比例相关文字的元素
                            if ((text.includes('3:4') || text.includes('4:3') || text.includes('1:1')) 
                                && el.offsetParent !== null 
                                && text.length < 10) {
                                const rect = el.getBoundingClientRect();
                                results.push({
                                    tag: el.tagName,
                                    text: text,
                                    class: el.className.substring(0, 50),
                                    w: Math.round(rect.width),
                                    h: Math.round(rect.height)
                                });
                            }
                        }
                        return results.slice(0, 10);  // 只返回前10个
                    }''')
                    
                    if debug_info and len(debug_info) > 0:
                        log.info(f"找到 {len(debug_info)} 个比例相关元素: {debug_info}")
                    
                    # 用 JS 精确查找并点击 "3:4" 按钮
                    js_clicked = await page.evaluate('''() => {
                        // 查找所有元素，找到文本精确为 "3:4" 的按钮
                        const allElements = Array.from(document.querySelectorAll('div, span, button'));
                        let found = [];
                        
                        for (const el of allElements) {
                            // 精确匹配 "3:4"，排除包含其他文字的元素
                            const text = (el.innerText || el.textContent || '').trim();
                            if (text === '3:4' && el.offsetParent !== null) {
                                const rect = el.getBoundingClientRect();
                                found.push({
                                    tag: el.tagName,
                                    class: el.className,
                                    width: rect.width,
                                    height: rect.height
                                });
                                // 检查是否是可点击的按钮样式元素
                                if (rect.width > 20 && rect.height > 20) {
                                    el.click();
                                    return { success: true, text: '3:4', method: 'direct' };
                                }
                            }
                        }
                        
                        // 备选：查找 class 包含 option 或 ratio 的元素
                        const options = document.querySelectorAll('[class*="option"], [class*="ratio"], [class*="item"]');
                        for (const opt of options) {
                            const text = (opt.innerText || opt.textContent || '').trim();
                            if (text === '3:4' && opt.offsetParent !== null) {
                                opt.click();
                                return { success: true, text: '3:4', method: 'option class' };
                            }
                        }
                        
                        return { success: false, found: found };
                    }''')
                    
                    if js_clicked and js_clicked.get('success'):
                        log.success(f"✅ 已选择 3:4 比例 (方法: {js_clicked.get('method', '')})")
                        ratio_selected = True
                        await asyncio.sleep(1)
                    else:
                        # 记录找到的元素用于调试
                        if js_clicked and js_clicked.get('found'):
                            log.info(f"找到 {len(js_clicked['found'])} 个 '3:4' 元素但未能点击: {js_clicked['found']}")
                        
                        # 备选：用 Playwright locator 尝试
                        ratio_btn = page.locator('div:text-is("3:4"), span:text-is("3:4"), button:text-is("3:4")').first
                        if await ratio_btn.count() and await ratio_btn.is_visible():
                            await ratio_btn.click()
                            log.success("✅ 已选择 3:4 比例 (Playwright text-is)")
                            ratio_selected = True
                            await asyncio.sleep(1)
                            
            except Exception as e:
                log.warning(f"选择比例时出错: {e}")
        
        # 方法 3: 用 JS 强制选择 3:4
        if not ratio_selected:
            try:
                js_result = await page.evaluate('''() => {
                    // 查找包含 3:4 的元素并点击
                    const elements = Array.from(document.querySelectorAll('*'));
                    const target = elements.find(el => 
                        el.innerText === '3:4' && 
                        el.offsetParent !== null
                    );
                    if (target) {
                        target.click();
                        return '3:4';
                    }
                    
                    // 查找竖封面选项
                    const vertical = elements.find(el => 
                        el.innerText && 
                        el.innerText.includes('竖封面') && 
                        el.offsetParent !== null
                    );
                    if (vertical) {
                        vertical.click();
                        return '竖封面';
                    }
                    
                    return null;
                }''')
                
                if js_result:
                    log.success(f"通过 JS 选择了: {js_result}")
                    ratio_selected = True
                    await asyncio.sleep(1)
            except:
                pass
        
        if not ratio_selected:
            log.warning("未能选择 3:4 比例，将使用默认比例（封面图片本身是 3:4，应该会自动适配）")
        
        # 步骤 4: 找到隐藏的 input 元素并上传图片
        # 小红书使用 semi-upload 组件，input 通常是隐藏的
        upload_input_selectors = [
            "div[class^='semi-upload'] input.semi-upload-hidden-input",
            "div[class*='upload'] input[type='file']",
            "input.semi-upload-hidden-input",
            "input[type='file'][accept*='image']",
            "input[type='file']",
        ]
        
        uploaded = False
        for selector in upload_input_selectors:
            try:
                inputs = page.locator(selector)
                count = await inputs.count()
                log.info(f"找到 {count} 个上传输入框 ({selector})")
                
                for i in range(count):
                    input_el = inputs.nth(i)
                    try:
                        # 先让 input 可见（某些情况需要）
                        await page.evaluate('''(selector) => {
                            const input = document.querySelector(selector);
                            if (input) {
                                input.style.display = 'block';
                                input.style.opacity = '1';
                                input.style.visibility = 'visible';
                            }
                        }''', selector)
                        
                        await input_el.set_input_files(cover_path)
                        uploaded = True
                        log.success(f"封面图片已上传 (使用 {selector})")
                        break
                    except Exception as e:
                        log.warning(f"尝试上传到 {selector}[{i}] 失败: {str(e)[:50]}")
                        continue
                
                if uploaded:
                    break
            except Exception as e:
                continue
        
        if not uploaded:
            log.warning("未能找到可用的图片上传输入框")
            return False
        
        # 步骤 5: 等待图片加载和处理
        await asyncio.sleep(3)
        
        # 步骤 6: 点击"完成"或"确定"保存
        confirm_selectors = [
            "div[class^='extractFooter'] button:visible:has-text('完成')",
            "button:has-text('完成')",
            "button:has-text('确定')",
            "button:has-text('确认')",
            "[class*='footer'] button:has-text('完成')",
            "[class*='footer'] button:has-text('确定')",
        ]
        
        confirmed = False
        for selector in confirm_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.count() and await btn.is_visible():
                    await btn.click()
                    confirmed = True
                    log.success(f"点击了确认按钮: {selector}")
                    await asyncio.sleep(2)
                    break
            except:
                continue
        
        if not confirmed:
            # 尝试用 JS 点击
            confirmed = await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const target = btns.find(b => 
                    (b.innerText.includes('完成') || b.innerText.includes('确定')) &&
                    b.offsetParent !== null
                );
                if (target) {
                    target.click();
                    return true;
                }
                return false;
            }''')
            if confirmed:
                log.success("通过 JS 点击了确认按钮")
                await asyncio.sleep(2)
        
        if confirmed:
            log.success("封面设置完成！")
            return True
        else:
            log.warning("未找到确认按钮，但图片可能已上传")
            return uploaded
        
    except Exception as e:
        log.error(f"封面上传失败: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============== 标题和正文 ==============

async def fill_title(page: Page, title: str) -> bool:
    """填充标题"""
    log.info(f"正在填充标题: {title}")
    
    try:
        title_selectors = [
            'div.plugin.title-container input.d-text',
            'input.d-text[placeholder*="标题"]',
            '#title-input',
            '.title-input input',
            '[class*="title"] input',
            'input[placeholder*="填写标题"]'
        ]
        
        for selector in title_selectors:
            try:
                input_el = page.locator(selector).first
                if await input_el.count():
                    await input_el.click()
                    await page.keyboard.press("Meta+A")
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
                    await asyncio.sleep(0.3)
                    await page.keyboard.type(title[:20])  # 小红书标题限制 20 字
                    log.success(f"标题填充完成: {title[:20]}")
                    return True
            except:
                continue
        
        # JS fallback
        await page.evaluate(f'''() => {{
            const input = document.querySelector('input[placeholder*="标题"]');
            if (input) {{
                input.value = '{title[:20]}';
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        }}''')
        
        return True
        
    except Exception as e:
        log.error(f"填充标题失败: {e}")
        return False

async def fill_description(page: Page, content: str) -> bool:
    """填充正文描述（使用 xhs-post.md 的内容）"""
    log.info("正在填充正文...")
    
    try:
        editor_selectors = [
            ".ql-editor",
            "[contenteditable='true']",
            ".p-details-editor",
            "#post-description"
        ]
        
        editor = None
        for selector in editor_selectors:
            try:
                el = page.locator(selector).first
                if await el.count():
                    editor = el
                    break
            except:
                continue
        
        if editor:
            await editor.click()
            # 清空现有内容
            if sys.platform == 'darwin':
                await page.keyboard.press("Meta+A")
            else:
                await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.3)
            
            # 输入内容（逐行输入以保持格式）
            lines = content.split('\n')
            for i, line in enumerate(lines):
                await page.keyboard.type(line)
                if i < len(lines) - 1:
                    await page.keyboard.press("Enter")
                await asyncio.sleep(0.05)  # 小延迟防止输入太快
            
            # 关闭可能出现的标签下拉框
            await asyncio.sleep(1)
            await page.keyboard.press("Escape")
            await page.keyboard.press("Escape")
            await page.click("body", position={"x": 10, "y": 10})
            
            log.success("正文填充完成")
            return True
        else:
            log.warning("未找到描述输入框")
            return False
            
    except Exception as e:
        log.error(f"填充正文失败: {e}")
        return False

# ============== 发布按钮 ==============

async def click_publish_button(page: Page, max_attempts: int = 6) -> bool:
    """点击发布按钮（多种方法尝试）"""
    
    for attempt in range(max_attempts):
        if attempt > 0:
            log.info(f"第 {attempt + 1} 次尝试点击发布按钮...")
            await asyncio.sleep(2)
        
        # 方法 1: 直接点击
        publish_selectors = [
            'button:has-text("发布")',
            '.publish-footer button.primary:has-text("发布")',
            'button.el-button--primary:has-text("发布")',
            'button[class*="publish"]'
        ]
        
        clicked = False
        for selector in publish_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.count() and await btn.is_visible() and await btn.is_enabled():
                    await btn.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)
                    await btn.click(timeout=5000)
                    clicked = True
                    log.info(f"已点击发布按钮 (选择器: {selector})")
                    break
            except Exception as e:
                continue
        
        # 方法 2: JS 点击
        if not clicked:
            clicked = await page.evaluate('''() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const target = buttons.find(b => b.innerText.trim() === '发布' && !b.disabled);
                if (target) {
                    // 模拟完整的鼠标事件序列
                    const rect = target.getBoundingClientRect();
                    ['mousedown', 'mouseup', 'click'].forEach(type => {
                        target.dispatchEvent(new MouseEvent(type, {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            clientX: rect.left + rect.width / 2,
                            clientY: rect.top + rect.height / 2
                        }));
                    });
                    return true;
                }
                return false;
            }''')
            
            if clicked:
                log.info("通过 JS 点击了发布按钮")
        
        # 方法 3: React 内部事件
        if not clicked:
            clicked = await page.evaluate('''() => {
                const btn = document.querySelector('button.css-k3lmfk') ||
                            Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('发布'));
                if (btn) {
                    const key = Object.keys(btn).find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'));
                    if (key) {
                        const fiber = btn[key];
                        const onClick = fiber.memoizedProps?.onClick || fiber.pendingProps?.onClick;
                        if (onClick) {
                            onClick({stopPropagation: ()=>{}, preventDefault: ()=>{}});
                            return true;
                        }
                    }
                    btn.click();
                    return true;
                }
                return false;
            }''')
            
            if clicked:
                log.info("通过 React 内部事件点击了发布按钮")
        
        if not clicked:
            log.warning("未找到可点击的发布按钮")
            continue
        
        # 等待发布完成
        initial_url = page.url
        max_wait = 30
        
        for check in range(max_wait // 3):
            await asyncio.sleep(3)
            current_url = page.url
            
            # 检查 URL 跳转（发布成功）
            if any(p in current_url for p in ["note-manager", "publish/success", "content/manage", "creator-micro/home"]):
                log.success(f"发布成功！已跳转到: {current_url}")
                return True
            
            if "publish/publish" not in current_url:
                log.success(f"发布成功！已离开发布页")
                return True
            
            # 检查成功提示
            try:
                success_toast = page.locator('div[class*="toast"], div[class*="message"]').get_by_text("成功")
                if await success_toast.count():
                    log.success("发布成功！检测到成功提示")
                    return True
            except:
                pass
        
        # 检查错误提示
        try:
            error_msg = await page.evaluate('''() => {
                const els = Array.from(document.querySelectorAll('*'));
                const errorEl = els.find(e => 
                    e.innerText && 
                    (e.innerText.includes('失败') || e.innerText.includes('错误')) &&
                    e.offsetParent !== null
                );
                return errorEl ? errorEl.innerText : null;
            }''')
            if error_msg:
                log.warning(f"检测到错误提示: {error_msg[:100]}")
        except:
            pass
    
    log.error(f"发布失败，已尝试 {max_attempts} 次")
    return False

# ============== 主发布流程 ==============

async def publish_to_xiaohongshu(
    video_path: str,
    cover_path: str,
    post_md_path: str,
    headless: bool = DEFAULT_HEADLESS
) -> bool:
    """
    发布视频到小红书
    
    Args:
        video_path: 视频文件路径
        cover_path: 封面图片路径（必须是预生成的 3:4 封面）
        post_md_path: xhs-post.md 文件路径（包含标题和正文）
        headless: 是否使用无头模式
    
    Returns:
        bool: 是否发布成功
    """
    
    # 验证文件存在
    for path, name in [(video_path, "视频"), (cover_path, "封面"), (post_md_path, "文案")]:
        if not os.path.exists(path):
            log.error(f"{name}文件不存在: {path}")
            return False
    
    # 读取文案内容
    with open(post_md_path, 'r', encoding='utf-8') as f:
        post_content = f.read()
    
    # 提取标题（第一行）
    lines = post_content.strip().split('\n')
    title = lines[0].replace('📈', '').strip()
    
    # 如果标题是 "美股热点速递 | YYYY.MM.DD" 格式，使用它
    if '美股热点速递' not in title:
        # 从文件名提取日期
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', post_md_path)
        if date_match:
            year, month, day = date_match.groups()
            title = f"美股热点速递 | {year}.{month}.{day}"
    
    log.info("=" * 50)
    log.info("小红书视频发布")
    log.info("=" * 50)
    log.info(f"视频: {video_path}")
    log.info(f"封面: {cover_path}")
    log.info(f"文案: {post_md_path}")
    log.info(f"标题: {title}")
    log.info("=" * 50)
    
    async with async_playwright() as playwright:
        # 启动浏览器
        browser = await playwright.chromium.launch(
            headless=headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        # 创建上下文
        context_options = {
            "viewport": {"width": 1600, "height": 900}
        }
        
        # 加载 cookies（如果存在）
        if COOKIES_PATH.exists():
            context_options["storage_state"] = str(COOKIES_PATH)
            log.info("已加载保存的 cookies")
        
        context = await browser.new_context(**context_options)
        
        # 注入 stealth 脚本
        context = await inject_stealth(context)
        
        # 创建页面
        page = await context.new_page()
        
        try:
            # 访问发布页面
            log.info("正在打开小红书发布页面...")
            await page.goto(PUBLISH_URL, timeout=60000)
            await asyncio.sleep(3)
            
            # 检查是否需要登录
            if 'login' in page.url.lower() or await page.locator('text="扫码登录"').count():
                log.warning("需要登录！请在浏览器中扫码登录...")
                await page.wait_for_url("**/publish/**", timeout=300000)  # 等待5分钟
                log.success("登录成功")
                
                # 登录成功后重新导航到发布页面
                log.info("重新加载发布页面...")
                await page.goto(PUBLISH_URL, timeout=60000)
                await asyncio.sleep(3)
            
            # 关闭新手引导
            await dismiss_shepherd_overlay(page)
            
            # 上传视频
            if not await upload_video(page, video_path):
                return False
            
            # 等待上传完成
            if not await wait_for_video_upload(page):
                return False
            
            # 再次关闭可能的弹窗
            await dismiss_shepherd_overlay(page)
            await asyncio.sleep(2)
            
            # 上传封面（⚠️ 使用预生成的封面）
            await upload_cover(page, cover_path)
            
            # 填充标题
            await fill_title(page, title)
            
            # 填充正文（使用 xhs-post.md 的完整内容）
            await fill_description(page, post_content)
            
            await asyncio.sleep(2)
            
            # 点击发布
            success = await click_publish_button(page)
            
            # 保存 cookies
            COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(COOKIES_PATH))
            log.info("Cookies 已保存")
            
            return success
            
        except Exception as e:
            log.error(f"发布过程出错: {e}")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            await asyncio.sleep(2)
            await context.close()
            await browser.close()


# ============== CLI 入口 ==============

def main():
    parser = argparse.ArgumentParser(description='小红书视频发布工具')
    parser.add_argument('video_path', help='视频文件路径')
    parser.add_argument('cover_path', help='封面图片路径（必须是预生成的 3:4 封面）')
    parser.add_argument('post_md_path', help='xhs-post.md 文件路径')
    parser.add_argument('--headless', action='store_true', help='使用无头模式（不显示浏览器）')
    
    args = parser.parse_args()
    
    # 展开路径
    video_path = os.path.expanduser(args.video_path)
    cover_path = os.path.expanduser(args.cover_path)
    post_md_path = os.path.expanduser(args.post_md_path)
    
    # 运行发布
    success = asyncio.run(publish_to_xiaohongshu(
        video_path=video_path,
        cover_path=cover_path,
        post_md_path=post_md_path,
        headless=args.headless
    ))
    
    if success:
        log.success("🎉 发布完成！")
        sys.exit(0)
    else:
        log.error("发布失败")
        sys.exit(1)


if __name__ == "__main__":
    main()

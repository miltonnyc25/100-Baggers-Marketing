#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雪球热门股票评论发布脚本

从 daily newsletter 提取热门股票，结合 100baggers.club 数据，
生成雪球风格评论并发布到对应股票页面。

使用方法:
    python xueqiu_hottopics.py <date> [--dry-run] [--ticker TICKER]
    
示例:
    python xueqiu_hottopics.py 2026-01-27
    python xueqiu_hottopics.py 2026-01-27 --dry-run
    python xueqiu_hottopics.py 2026-01-27 --ticker AAPL
"""

import asyncio
import argparse
import os
import sys
import re
import json
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

# ============== 配置 ==============

CLAWD_DIR = Path("/Users/xuemeizhao/clawd")
NEWSLETTERS_DIR = CLAWD_DIR / "newsletters"

# 100baggers API
INVESTVIEW_BASE_URL = "https://www.100baggers.club"
INTERNAL_API_KEY = os.environ.get('INTERNAL_API_KEY', '')

# 雪球 cookie 路径
XUEQIU_COOKIE_PATH = Path("/Users/xuemeizhao/Downloads/add-caption/social_uploader/xueqiu_uploader/xueqiu_account.json")

# AI 模型配置
GEMINI_MODEL = "gemini-3-pro-preview"

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

# ============== 提取热门股票 ==============

def extract_hot_stocks_from_newsletter(date: str) -> List[Dict]:
    """
    从 newsletter 提取热门股票
    
    Returns:
        [{'ticker': 'NVO', 'name': 'Novo Nordisk', 'summary': '...'}, ...]
    """
    # 尝试多种文件名格式
    possible_files = [
        NEWSLETTERS_DIR / f"{date}-xhs-post.md",
        NEWSLETTERS_DIR / f"{date}-newsletter.md",
        NEWSLETTERS_DIR / f"{date}.md",
    ]
    
    content = None
    for file_path in possible_files:
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            log.info(f"从 {file_path.name} 提取股票")
            break
    
    if not content:
        log.error(f"未找到 {date} 的 newsletter 文件")
        return []
    
    # 提取股票代码和摘要
    stocks = []
    
    # 匹配模式: $TICKER 或 (TICKER)
    ticker_pattern = r'\$([A-Z]{1,5})|\(([A-Z]{2,5})\)'
    
    # 按段落分析
    lines = content.split('\n')
    current_stock = None
    current_summary = []
    
    for line in lines:
        # 检查是否是新股票段落（以数字+emoji开头）
        if re.match(r'^[1-9]️⃣|^[1-9]\.|^\d+\.', line):
            # 保存之前的股票
            if current_stock:
                stocks.append({
                    'ticker': current_stock['ticker'],
                    'name': current_stock.get('name', ''),
                    'summary': '\n'.join(current_summary).strip()
                })
            
            # 提取新股票
            tickers = re.findall(ticker_pattern, line)
            if tickers:
                ticker = tickers[0][0] or tickers[0][1]
                # 提取公司名称（在 ticker 前面的文字）
                name_match = re.search(r'([A-Za-z\s]+)\s*\$' + ticker, line)
                name = name_match.group(1).strip() if name_match else ''
                
                current_stock = {'ticker': ticker, 'name': name}
                current_summary = [line]
            else:
                current_stock = None
                current_summary = []
        elif current_stock and line.strip():
            current_summary.append(line)
    
    # 保存最后一个股票
    if current_stock:
        stocks.append({
            'ticker': current_stock['ticker'],
            'name': current_stock.get('name', ''),
            'summary': '\n'.join(current_summary).strip()
        })
    
    log.info(f"提取到 {len(stocks)} 只热门股票")
    return stocks

# ============== 获取 100baggers 数据 ==============

def fetch_100baggers_data(ticker: str) -> Optional[str]:
    """
    从 100baggers.club 获取股票数据
    """
    log.info(f"获取 {ticker} 的 100baggers 数据...")
    
    try:
        headers = {
            'Content-Type': 'application/json',
        }
        if INTERNAL_API_KEY:
            headers['x-api-key'] = INTERNAL_API_KEY
        
        response = requests.post(
            f"{INVESTVIEW_BASE_URL}/api/generate-summary",
            json={'symbol': ticker},
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('markdown'):
                log.success(f"获取 {ticker} 数据成功")
                return data['markdown']
        
        log.warning(f"获取 {ticker} 数据失败: {response.status_code}")
        return None
        
    except Exception as e:
        log.error(f"获取 {ticker} 数据出错: {e}")
        return None

# ============== AI 生成评论 ==============

XUEQIU_COMMENT_PROMPT = """你是一个资深美股投资者，经常在雪球上和球友讨论股票。现在需要你针对一只热门股票写一段评论。

## 要求

1. **字数**：300-500字，不要太长
2. **风格**：
   - 像真人在雪球发帖，不是机器人或AI
   - 可以有个人观点和判断，但要有理有据
   - 语气自然，可以用一些口语化表达
   - 不要说教，不要用"首先、其次、最后"这种套路
   - 可以适当用一些雪球常见的表达，如"看多/看空"、"建仓/加仓"、"回调"等
3. **内容结构**：
   - 开头直接切入主题，说明这只股票最近为什么值得关注
   - 中间结合数据分析，说明你的看法
   - 可以提出一些值得思考的问题或风险点
   - 不需要面面俱到，抓住1-2个关键点深入分析即可
4. **禁止**：
   - 不要用"作为一个..."、"我认为..."这种开头
   - 不要用markdown格式，纯文本
   - 不要用emoji过多（最多1-2个）
   - 不要给出具体的买入/卖出建议
5. **结尾**：在文章最后另起一行写上"数据参考了100baggers.club"

## 股票信息

**股票代码**: {ticker}
**公司名称**: {name}
**今日热点摘要**:
{summary}

**100baggers数据**:
{data}

请直接输出评论内容，不要有任何前言。
"""

def generate_xueqiu_comment(ticker: str, name: str, summary: str, data: str) -> Optional[str]:
    """
    使用 AI 生成雪球风格评论
    """
    log.info(f"为 {ticker} 生成雪球评论...")
    
    prompt = XUEQIU_COMMENT_PROMPT.format(
        ticker=ticker,
        name=name,
        summary=summary,
        data=data[:3000] if data else "暂无详细数据"  # 限制数据长度
    )
    
    try:
        # 使用 Gemini API
        import google.generativeai as genai
        
        api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
        if not api_key:
            log.error("未设置 GEMINI_API_KEY 或 GOOGLE_API_KEY")
            return None
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        response = model.generate_content(prompt)
        comment = response.text.strip()
        
        log.success(f"评论生成成功 ({len(comment)} 字)")
        return comment
        
    except Exception as e:
        log.error(f"生成评论失败: {e}")
        return None

# ============== 发布到雪球 ==============

async def publish_to_xueqiu(ticker: str, comment: str) -> bool:
    """
    发布评论到雪球股票页面
    """
    log.info(f"发布到雪球 {ticker}...")
    
    # 动态导入雪球上传器
    sys.path.insert(0, str(Path("/Users/xuemeizhao/Downloads/add-caption/social_uploader")))
    
    try:
        from xueqiu_uploader.main import XueqiuUploader, xueqiu_setup
        
        cookie_file = str(XUEQIU_COOKIE_PATH)
        
        # 检查登录状态
        if not await xueqiu_setup(cookie_file, handle=False):
            log.error("雪球未登录，请先运行 xueqiu_setup")
            return False
        
        uploader = XueqiuUploader(cookie_file)
        await uploader.post_to_ticker(ticker, comment)
        
        log.success(f"成功发布到 https://xueqiu.com/S/{ticker}")
        return True
        
    except Exception as e:
        log.error(f"发布失败: {e}")
        return False

# ============== 主流程 ==============

async def process_single_stock(ticker: str, name: str, summary: str, dry_run: bool = False) -> bool:
    """
    处理单只股票：获取数据 -> 生成评论 -> 发布
    """
    print("\n" + "=" * 60)
    log.info(f"处理股票: {ticker} ({name})")
    print("=" * 60)
    
    # 1. 获取 100baggers 数据
    data = fetch_100baggers_data(ticker)
    
    # 2. 生成评论
    comment = generate_xueqiu_comment(ticker, name, summary, data or "")
    
    if not comment:
        log.error(f"无法为 {ticker} 生成评论")
        return False
    
    # 打印评论预览
    print("\n--- 评论预览 ---")
    print(comment)
    print("--- 预览结束 ---\n")
    
    # 3. 发布
    if dry_run:
        log.info("[DRY-RUN] 跳过发布")
        return True
    
    return await publish_to_xueqiu(ticker, comment)

async def main_async(date: str, dry_run: bool = False, single_ticker: str = None):
    """
    主异步流程
    """
    print("\n" + "=" * 60)
    print(f"🔥 雪球热门股票评论发布 - {date}")
    print("=" * 60 + "\n")
    
    # 1. 提取热门股票
    stocks = extract_hot_stocks_from_newsletter(date)
    
    if not stocks:
        log.error("未找到热门股票")
        return
    
    # 如果指定了单只股票
    if single_ticker:
        stocks = [s for s in stocks if s['ticker'].upper() == single_ticker.upper()]
        if not stocks:
            log.error(f"未找到股票 {single_ticker}")
            return
    
    # 2. 处理每只股票
    success_count = 0
    for stock in stocks:
        try:
            success = await process_single_stock(
                ticker=stock['ticker'],
                name=stock['name'],
                summary=stock['summary'],
                dry_run=dry_run
            )
            if success:
                success_count += 1
            
            # 发布间隔，避免被限流
            if not dry_run and stock != stocks[-1]:
                log.info("等待 30 秒...")
                await asyncio.sleep(30)
                
        except Exception as e:
            log.error(f"处理 {stock['ticker']} 时出错: {e}")
    
    print("\n" + "=" * 60)
    log.success(f"完成！成功处理 {success_count}/{len(stocks)} 只股票")
    print("=" * 60)

def main():
    parser = argparse.ArgumentParser(description='雪球热门股票评论发布工具')
    parser.add_argument('date', help='日期 (YYYY-MM-DD)')
    parser.add_argument('--dry-run', action='store_true', help='仅生成评论，不发布')
    parser.add_argument('--ticker', '-t', help='只处理指定股票')
    
    args = parser.parse_args()
    
    asyncio.run(main_async(
        date=args.date,
        dry_run=args.dry_run,
        single_ticker=args.ticker
    ))

if __name__ == "__main__":
    main()

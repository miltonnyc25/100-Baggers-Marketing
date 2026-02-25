#!/usr/bin/env python3
"""
Scrape all 452 notes from XHS creator note manager (Milton聊商业).
Uses infinite scroll on the content area + API response interception.
"""
import asyncio
import json
import re
import os
import sys
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright

COOKIES_PATH = os.path.expanduser(
    "~/clawd/skills/earnings-video/cookies/xhs_earnings_account.json"
)
STEALTH_JS = os.path.expanduser(
    "~/Downloads/add-caption/social_uploader/utils/stealth.min.js"
)
SCRIPT_DIR = Path(__file__).parent
OUTPUT_PATH = SCRIPT_DIR / "xhs_notes_raw.json"
STOCK_OUTPUT_PATH = SCRIPT_DIR / "xhs_stock_mentions.json"

# ── Comprehensive US stock tickers → Chinese/English aliases ─────────────────
US_STOCK_MAP = {
    "AAPL": ["苹果", "Apple"], "MSFT": ["微软", "Microsoft"],
    "GOOGL": ["谷歌", "Google", "Alphabet"], "AMZN": ["亚马逊", "Amazon"],
    "META": ["脸书", "Facebook"], "NVDA": ["英伟达", "Nvidia", "NVIDIA", "黄仁勋"],
    "TSLA": ["特斯拉", "Tesla", "马斯克"], "NFLX": ["奈飞", "Netflix"],
    "AVGO": ["博通", "Broadcom"], "ORCL": ["甲骨文", "Oracle"],
    "CRM": ["Salesforce"], "AMD": ["超威半导体"],
    "INTC": ["英特尔", "Intel"], "QCOM": ["高通", "Qualcomm"],
    "ADBE": ["Adobe"], "CSCO": ["思科", "Cisco"],
    "TXN": ["德州仪器"], "MU": ["美光", "Micron"],
    "DELL": ["戴尔", "Dell"], "IBM": [],
    "PLTR": ["Palantir"], "SNOW": ["Snowflake"],
    "DDOG": ["Datadog"], "NET": ["Cloudflare"],
    "CRWD": ["CrowdStrike"], "ZS": ["Zscaler"],
    "MDB": ["MongoDB"], "PANW": ["Palo Alto"],
    "ANET": ["Arista"], "SMCI": ["超微电脑", "Super Micro"],
    "MRVL": ["Marvell"], "ARM": ["Arm Holdings"],
    "SOUN": ["SoundHound"], "IONQ": ["IonQ"],
    "RGTI": ["Rigetti"], "APP": ["AppLovin"],
    "NOW": ["ServiceNow"], "TEAM": ["Atlassian"],
    "WDAY": ["Workday"], "ZM": ["Zoom"],
    "TTD": ["Trade Desk"], "ROKU": ["Roku"],
    "PINS": ["Pinterest"], "SNAP": ["Snapchat"],
    "HUBS": ["HubSpot"], "MNDY": ["Monday.com"],
    "OKTA": ["Okta"], "TWLO": ["Twilio"],
    "V": ["Visa"], "MA": ["万事达", "Mastercard"],
    "PYPL": ["PayPal", "贝宝"], "SQ": ["Block", "Square"],
    "SOFI": ["SoFi"], "COIN": ["Coinbase"],
    "HOOD": ["Robinhood"], "AFRM": ["Affirm"],
    "NU": ["Nu Holdings"], "GS": ["高盛", "Goldman"],
    "JPM": ["摩根大通", "JPMorgan"], "MS": ["摩根士丹利"],
    "BAC": ["美国银行"], "WFC": ["富国银行", "Wells Fargo"],
    "BRK.B": ["伯克希尔", "Berkshire", "巴菲特", "Buffett"],
    "SCHW": ["嘉信理财", "Schwab"], "AXP": ["美国运通"],
    "C": ["花旗", "Citigroup"],
    "BABA": ["阿里巴巴", "Alibaba", "阿里"],
    "JD": ["京东"], "PDD": ["拼多多", "Pinduoduo", "Temu"],
    "BIDU": ["百度", "Baidu"], "BILI": ["哔哩哔哩", "B站", "Bilibili"],
    "NIO": ["蔚来"], "XPEV": ["小鹏汽车", "XPeng"],
    "LI": ["理想汽车", "Li Auto"], "TCOM": ["携程", "Trip.com"],
    "TME": ["腾讯音乐"], "FUTU": ["富途"],
    "TIGR": ["老虎证券"], "TAL": ["好未来"],
    "EDU": ["新东方"], "MNSO": ["名创优品"],
    "IQ": ["爱奇艺"], "WB": ["微博"],
    "NTES": ["网易", "NetEase"], "BEKE": ["贝壳"],
    "WMT": ["沃尔玛", "Walmart"], "COST": ["Costco", "开市客"],
    "TGT": ["Target"], "SBUX": ["星巴克", "Starbucks"],
    "NKE": ["耐克", "Nike"], "LULU": ["Lululemon"],
    "DIS": ["迪士尼", "Disney"], "ABNB": ["Airbnb", "爱彼迎"],
    "UBER": ["Uber", "优步"], "LYFT": ["Lyft"],
    "DASH": ["DoorDash"], "CPNG": ["Coupang"],
    "SE": ["Shopee", "Sea Limited"], "SHOP": ["Shopify"],
    "MELI": ["MercadoLibre"], "DUOL": ["Duolingo", "多邻国"],
    "HIMS": ["Hims"], "CELH": ["Celsius"],
    "CMG": ["Chipotle"], "MCD": ["麦当劳", "McDonald"],
    "KO": ["可口可乐", "Coca-Cola"], "PEP": ["百事", "Pepsi"],
    "PG": ["宝洁", "Procter"], "MNST": ["怪物饮料"],
    "LLY": ["礼来", "Eli Lilly"], "UNH": ["联合健康", "UnitedHealth"],
    "JNJ": ["强生", "Johnson"], "PFE": ["辉瑞", "Pfizer"],
    "ABBV": ["艾伯维", "AbbVie"], "MRK": ["默沙东", "Merck"],
    "NVO": ["诺和诺德", "Novo Nordisk", "司美格鲁肽"],
    "BMY": ["百时美施贵宝"], "ISRG": ["直觉外科", "Intuitive Surgical"],
    "AMGN": ["安进", "Amgen"], "TMO": ["赛默飞", "Thermo Fisher"],
    "DHR": ["丹纳赫", "Danaher"],
    "XOM": ["埃克森美孚", "Exxon"], "CVX": ["雪佛龙", "Chevron"],
    "COP": ["康菲石油"], "OXY": ["西方石油", "Occidental"],
    "VST": ["Vistra"], "CEG": ["Constellation Energy"],
    "OKLO": ["Oklo"], "CCJ": ["Cameco"],
    "FSLR": ["First Solar"], "ENPH": ["Enphase"],
    "BA": ["波音", "Boeing"], "RTX": ["雷神", "Raytheon"],
    "LMT": ["洛克希德", "Lockheed"], "CAT": ["卡特彼勒", "Caterpillar"],
    "DE": ["迪尔", "John Deere"], "GE": ["通用电气"],
    "HON": ["霍尼韦尔", "Honeywell"], "UNP": ["联合太平洋"],
    "ASML": ["阿斯麦", "ASML"], "LRCX": ["拉姆研究", "Lam Research"],
    "AMAT": ["应用材料", "Applied Materials"], "KLAC": ["科磊", "KLA"],
    "TSM": ["台积电", "TSMC"],
    "SPOT": ["Spotify"], "RBLX": ["Roblox"], "RDDT": ["Reddit"],
    "SPY": ["标普500", "S&P 500", "标普指数"],
    "QQQ": ["纳指100", "纳斯达克100"],
    "ARKK": ["ARK基金", "木头姐", "Cathie Wood"],
    "SOXX": ["费城半导体"],
    "MSTR": ["MicroStrategy", "微策略"],
    "RIVN": ["Rivian"], "LCID": ["Lucid"],
    "GME": ["GameStop", "游戏驿站"],
    "RKLB": ["Rocket Lab"], "ACHR": ["Archer Aviation"],
    "JOBY": ["Joby Aviation"],
    "VIX": ["恐慌指数"],
    "BTC": ["比特币", "Bitcoin"],
    "FCX": ["自由港", "Freeport"], "NEM": ["纽蒙特", "Newmont"],
    "GOLD": ["巴里克", "Barrick Gold"],
    "CARR": ["Carrier"], "TT": ["Trane"],
    "ETN": ["Eaton", "伊顿"], "EMR": ["Emerson", "艾默生"],
    "SHW": ["宣伟", "Sherwin"], "ECL": ["Ecolab", "艺康"],
    "APD": ["空气产品"], "LIN": ["林德", "Linde"],
    "RACE": ["法拉利", "Ferrari"],
    "DPZ": ["达美乐", "Domino"],
    "IHG": ["洲际酒店", "InterContinental"],
    "MAR": ["万豪", "Marriott"], "HLT": ["希尔顿", "Hilton"],
    "BKNG": ["Booking"],
    "EXPE": ["Expedia"],
    "WYNN": ["永利", "Wynn"], "LVS": ["金沙"],
    "MGM": ["美高梅", "MGM"],
    "DXCM": ["DexCom"], "IDXX": ["IDEXX"],
    "CPRT": ["Copart"], "ODFL": ["Old Dominion"],
    "AXON": ["Axon"], "VEEV": ["Veeva"],
    "FTNT": ["Fortinet"], "GLOB": ["Globant"],
    "ACN": ["埃森哲", "Accenture"],
    "INTU": ["Intuit"],
    "SNPS": ["Synopsys", "新思科技"],
    "CDNS": ["Cadence", "铿腾"],
    "NXPI": ["恩智浦", "NXP"],
    "ON": ["安森美", "ON Semi"],
    "MCHP": ["微芯", "Microchip"],
    "ADI": ["亚德诺", "Analog Devices"],
    "MPWR": ["Monolithic Power"],
    "STZ": ["Constellation Brands"],
    "EL": ["雅诗兰黛", "Estee Lauder"],
    "RL": ["Ralph Lauren"],
    "TJX": ["TJX"],
    "DECK": ["Deckers"],
    "BIRK": ["Birkenstock"],
    "ONON": ["On Running", "昂跑"],
    "UAL": ["联合航空", "United Airlines"],
    "DAL": ["达美航空", "Delta Air"],
    "AAL": ["美国航空", "American Airlines"],
    "LUV": ["西南航空", "Southwest"],
    "TQQQ": ["三倍纳指"],
    "SOXL": ["三倍半导体"],
    "ETH": ["以太坊", "Ethereum"],
    "IBIT": ["比特币ETF"],
    "VIPS": ["唯品会"],
    "QFIN": ["奇富科技"],
    "DIDI": ["滴滴"],
    "GDS": ["万国数据"],
    "LKNCY": ["瑞幸"],
    "ZK": ["知乎"],
    "WOLF": ["Wolfspeed"],
}


def find_stock_mentions(text):
    if not text:
        return set()
    found = set()
    text_upper = text.upper()
    for ticker, aliases in US_STOCK_MAP.items():
        ticker_clean = ticker.replace(".", "")
        if len(ticker_clean) >= 2:
            patterns = [
                rf'\${re.escape(ticker)}\b',
                rf'(?<![A-Za-z0-9.]){re.escape(ticker_clean)}(?![A-Za-z0-9])',
            ]
            for pat in patterns:
                if re.search(pat, text_upper):
                    found.add(ticker)
                    break
        for alias in aliases:
            if alias in text or (alias.isascii() and alias.upper() in text_upper):
                found.add(ticker)
                break
    for t in re.findall(r'\$([A-Z]{2,5})\b', text_upper):
        found.add(t)
    return found


async def scrape_all_notes():
    print(f"Using cookies: {COOKIES_PATH}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=COOKIES_PATH,
            viewport={"width": 1280, "height": 900},
        )
        if os.path.exists(STEALTH_JS):
            await context.add_init_script(path=STEALTH_JS)

        page = await context.new_page()

        # Intercept API responses
        all_api_notes = []

        async def on_response(response):
            if "note/user/posted" in response.url and response.status == 200:
                try:
                    body = await response.json()
                    if body.get("code") == 0:
                        notes = body.get("data", {}).get("notes", [])
                        if notes:
                            all_api_notes.extend(notes)
                except Exception:
                    pass

        page.on("response", on_response)

        print("Loading note manager...")
        await page.goto(
            "https://creator.xiaohongshu.com/new/note-manager",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await asyncio.sleep(4)

        # Get total count
        page_text = await page.evaluate("() => document.body?.innerText?.substring(0, 300)")
        total_match = re.search(r'全部笔记\((\d+)\)', page_text)
        total_count = int(total_match.group(1)) if total_match else 0
        print(f"Account: Milton聊商业, Total notes: {total_count}")
        print(f"Initial API capture: {len(all_api_notes)} notes")

        # Find the scrollable content container
        # The note list is inside the main content area (right of sidebar)
        container_info = await page.evaluate("""
            () => {
                // Find divs that are scrollable and large enough to be the content area
                const candidates = [];
                const allDivs = document.querySelectorAll('div');
                for (const div of allDivs) {
                    if (div.scrollHeight > div.clientHeight + 50 &&
                        div.clientHeight > 300 &&
                        div.clientWidth > 500) {
                        candidates.push({
                            className: (div.className || '').substring(0, 100),
                            id: div.id || '',
                            scrollHeight: div.scrollHeight,
                            clientHeight: div.clientHeight,
                            clientWidth: div.clientWidth,
                            childCount: div.children.length,
                            tagPath: div.tagName,
                        });
                    }
                }
                return candidates;
            }
        """)
        print(f"\nScrollable containers found: {len(container_info)}")
        for c in container_info:
            print(f"  class={c['className'][:60]} size={c['clientWidth']}x{c['clientHeight']} scrollH={c['scrollHeight']} children={c['childCount']}")

        # Infinite scroll loop
        prev_count = len(all_api_notes)
        stale_rounds = 0
        max_stale = 10

        print(f"\nScrolling to load all notes...")
        for scroll_i in range(200):  # max 200 scroll attempts
            # Scroll all potential containers + window
            await page.evaluate("""
                () => {
                    // Scroll the window
                    window.scrollTo(0, document.body.scrollHeight);

                    // Scroll all scrollable divs
                    const allDivs = document.querySelectorAll('div');
                    for (const div of allDivs) {
                        if (div.scrollHeight > div.clientHeight + 50 &&
                            div.clientHeight > 300) {
                            div.scrollTop = div.scrollHeight;
                        }
                    }

                    // Also try scrolling the main/content element
                    const main = document.querySelector('main, [role="main"], [class*="content"], [class*="Content"]');
                    if (main && main.scrollHeight > main.clientHeight) {
                        main.scrollTop = main.scrollHeight;
                    }
                }
            """)

            await asyncio.sleep(1.5)

            current_count = len(all_api_notes)

            if current_count > prev_count:
                stale_rounds = 0
                print(f"  Scroll {scroll_i+1}: {current_count} notes (+{current_count - prev_count})")
                prev_count = current_count
            else:
                stale_rounds += 1

            if current_count >= total_count:
                print(f"  All {total_count} notes loaded!")
                break

            if stale_rounds >= max_stale:
                print(f"  No new notes after {max_stale} scrolls. Stopping at {current_count}.")
                break

        # Also try using keyboard End key to scroll
        if len(all_api_notes) < total_count * 0.5:
            print(f"\nScrolling method got only {len(all_api_notes)}/{total_count}.")
            print("Trying keyboard-based scrolling...")

            for i in range(100):
                await page.keyboard.press("End")
                await asyncio.sleep(1)
                if len(all_api_notes) > prev_count:
                    prev_count = len(all_api_notes)
                    stale_rounds = 0
                    print(f"  End key {i+1}: {len(all_api_notes)} notes")
                else:
                    stale_rounds += 1
                if stale_rounds >= 5 or len(all_api_notes) >= total_count:
                    break

        # Final: try mouse wheel scrolling on the content area
        if len(all_api_notes) < total_count * 0.5:
            print(f"\nTrying mouse wheel scrolling...")
            for i in range(200):
                await page.mouse.wheel(0, 1000)
                await asyncio.sleep(0.8)
                if len(all_api_notes) > prev_count:
                    prev_count = len(all_api_notes)
                    stale_rounds = 0
                    if i % 5 == 0:
                        print(f"  Wheel {i+1}: {len(all_api_notes)} notes")
                else:
                    stale_rounds += 1
                if stale_rounds >= 8 or len(all_api_notes) >= total_count:
                    break

        await browser.close()

    # ── Process ──────────────────────────────────────────────────────────────
    seen = set()
    unique_notes = []
    for note in all_api_notes:
        nid = note.get("id", "")
        if nid and nid not in seen:
            seen.add(nid)
            unique_notes.append(note)

    print(f"\n{'='*60}")
    print(f"Raw API notes: {len(all_api_notes)}")
    print(f"Unique notes: {len(unique_notes)}")

    parsed_notes = []
    for note in unique_notes:
        parsed_notes.append({
            "note_id": note.get("id", ""),
            "title": note.get("display_title", "") or "(无标题)",
            "type": note.get("type", ""),
            "status": note.get("tab_status", ""),
            "time": note.get("time", ""),
            "likes": note.get("likes", 0),
            "comments": note.get("comments_count", 0),
            "collects": note.get("collected_count", 0),
            "shares": note.get("shared_count", 0),
            "views": note.get("view_count", 0),
        })

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(parsed_notes, f, ensure_ascii=False, indent=2)
    print(f"Notes saved to {OUTPUT_PATH}")

    # ── Stock analysis ───────────────────────────────────────────────────────
    stock_notes = {}
    notes_with_stocks = []

    for note in parsed_notes:
        tickers = find_stock_mentions(note["title"])
        if tickers:
            notes_with_stocks.append({**note, "tickers_found": sorted(tickers)})
            for t in tickers:
                stock_notes.setdefault(t, []).append({
                    "note_id": note["note_id"],
                    "title": note["title"],
                    "time": note["time"],
                    "likes": note["likes"],
                    "collects": note["collects"],
                    "views": note["views"],
                })

    stock_summary = sorted(
        [{"ticker": t, "count": len(n), "notes": n} for t, n in stock_notes.items()],
        key=lambda x: -x["count"],
    )

    result = {
        "scraped_at": datetime.now().isoformat(),
        "account": "Milton聊商业",
        "total_notes_on_account": total_count,
        "total_notes_scraped": len(parsed_notes),
        "notes_mentioning_stocks": len(notes_with_stocks),
        "unique_tickers": len(stock_summary),
        "stock_summary": stock_summary,
        "notes_detail": notes_with_stocks,
    }

    with open(STOCK_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Stock analysis saved to {STOCK_OUTPUT_PATH}")

    print(f"\n{'='*60}")
    print(f"US STOCK MENTIONS - Milton聊商业")
    print(f"{'='*60}")
    print(f"Total notes: {total_count} | Scraped: {len(parsed_notes)} | With stocks: {len(notes_with_stocks)} | Unique tickers: {len(stock_summary)}")
    print(f"\n{'Ticker':<12} {'Count':<8} {'Sample Note'}")
    print(f"{'-'*12} {'-'*8} {'-'*50}")
    for item in stock_summary:
        sample = item["notes"][0]["title"][:50] if item["notes"] else ""
        print(f"{item['ticker']:<12} {item['count']:<8} {sample}")


if __name__ == "__main__":
    asyncio.run(scrape_all_notes())

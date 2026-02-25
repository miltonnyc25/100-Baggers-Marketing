#!/usr/bin/env python3
"""Build comprehensive ticker report from scraped XHS data."""
import json
from pathlib import Path

DIR = Path(__file__).parent

# Company info: ticker -> (full_name, one_line_description)
COMPANY_INFO = {
    "AAPL": ("Apple Inc.", "全球消费电子龙头，iPhone/Mac/服务生态构建全球最大市值公司"),
    "ACN": ("Accenture plc", "全球最大IT咨询与服务公司，AI工业化落地的核心推手"),
    "ADBE": ("Adobe Inc.", "创意与文档软件巨头，Photoshop/PDF标准制定者，AI驱动内容创作"),
    "ADI": ("Analog Devices Inc.", "模拟芯片龙头，工业/汽车/通信领域高精度信号处理专家"),
    "AMAT": ("Applied Materials Inc.", "全球最大半导体设备商，芯片制造的「军火供应商」"),
    "AMD": ("Advanced Micro Devices Inc.", "CPU/GPU双线挑战者，AI加速卡市场的英伟达最大竞争对手"),
    "AMGN": ("Amgen Inc.", "全球最大生物制药公司之一，减肥药赛道新玩家"),
    "AMZN": ("Amazon.com Inc.", "全球电商+云计算（AWS）双引擎，AI基础设施核心玩家"),
    "ANET": ("Arista Networks Inc.", "数据中心高速网络交换机龙头，AI算力集群的网络基石"),
    "APP": ("AppLovin Corp.", "移动广告与游戏平台，AI驱动的广告变现效率领先者"),
    "ARM": ("Arm Holdings plc", "全球移动芯片架构垄断者，95%智能手机CPU采用ARM架构"),
    "ASML": ("ASML Holding NV", "全球唯一EUV光刻机供应商，芯片制造最上游的绝对垄断"),
    "AVGO": ("Broadcom Inc.", "网络芯片与基础设施软件巨头，AI定制芯片的隐形冠军"),
    "AXP": ("American Express Co.", "高端信用卡与支付网络，服务高净值客户的金融品牌"),
    "BA": ("The Boeing Co.", "全球两大飞机制造商之一，1500亿债务下的航空工业支柱"),
    "BKNG": ("Booking Holdings Inc.", "全球最大在线旅游平台，负权益下的现金奶牛商业模式"),
    "BRK.B": ("Berkshire Hathaway Inc.", "巴菲特旗下多元化控股集团，保险+投资+实业的复合帝国"),
    "CARR": ("Carrier Global Corp.", "全球暖通空调与制冷系统龙头，楼宇自动化转型中"),
    "CAT": ("Caterpillar Inc.", "全球最大工程机械制造商，从卖设备到卖服务的转型先锋"),
    "CCJ": ("Cameco Corp.", "全球最大铀矿开采商之一，核电复兴的核心受益者"),
    "CDNS": ("Cadence Design Systems Inc.", "EDA芯片设计软件双寡头之一，芯片设计不可或缺的工具"),
    "CEG": ("Constellation Energy Corp.", "美国最大核电运营商，AI算力时代的稀缺清洁能源供应商"),
    "CMG": ("Chipotle Mexican Grill Inc.", "美国快休闲餐饮龙头，标准化墨西哥菜的连锁扩张模式"),
    "COIN": ("Coinbase Global Inc.", "美国最大合规加密货币交易所，加密经济的核心基础设施"),
    "COST": ("Costco Wholesale Corp.", "会员制仓储超市，极致低毛利+会员费的独特零售模式"),
    "CRM": ("Salesforce Inc.", "全球最大CRM云平台，企业级AI Agent的先行者"),
    "CRWD": ("CrowdStrike Holdings Inc.", "云原生网络安全龙头，端点防护与威胁情报平台"),
    "CSCO": ("Cisco Systems Inc.", "网络设备巨头，65%高毛利的企业网络基础设施供应商"),
    "CVX": ("Chevron Corp.", "全球第二大石油公司，逆势增产与并购扩张的能源巨头"),
    "DAL": ("Delta Air Lines Inc.", "美国三大航空之一，债务重压下的高盈利航空公司"),
    "DASH": ("DoorDash Inc.", "美国外卖配送平台龙头，从亏损到盈利的转折时刻"),
    "DDOG": ("Datadog Inc.", "云监控与可观测性平台，现金流远超利润的SaaS典范"),
    "DHR": ("Danaher Corp.", "生命科学与诊断工具平台型公司，并购整合的工业典范"),
    "DIS": ("The Walt Disney Co.", "全球娱乐帝国，主题乐园+流媒体+IP授权的多元变现"),
    "DPZ": ("Domino's Pizza Inc.", "全球最大披萨连锁，资不抵债却是现金流奶牛的轻资产模式"),
    "DUOL": ("Duolingo Inc.", "全球最大语言学习App，游戏化+AI驱动的教育增长飞轮"),
    "ETN": ("Eaton Corp. plc", "电力管理与工业自动化巨头，AI算力爆发下的电力基础设施受益者"),
    "EXPE": ("Expedia Group Inc.", "全球在线旅游平台，现金流强劲但获客成本承压"),
    "FCX": ("Freeport-McMoRan Inc.", "全球最大上市铜矿商，铜金双驱动的周期性资源巨头"),
    "GE": ("GE Aerospace", "航空发动机巨头，拆分后聚焦航空的工业传奇"),
    "GME": ("GameStop Corp.", "游戏零售商，散户运动标志性股票，转型比特币储备"),
    "GOOGL": ("Alphabet Inc.", "全球搜索与广告垄断者，AI竞赛中的全栈玩家"),
    "GS": ("The Goldman Sachs Group Inc.", "华尔街顶级投行，AI研究与资本市场的风向标"),
    "HIMS": ("Hims & Hers Health Inc.", "DTC远程医疗平台，借助「隐私病」赛道快速增长"),
    "HLT": ("Hilton Worldwide Holdings Inc.", "全球最大酒店管理集团之一，负权益下32% ROIC的轻资产印钞术"),
    "HOOD": ("Robinhood Markets Inc.", "零佣金证券交易平台，散户投资民主化的推动者"),
    "IBM": ("International Business Machines Corp.", "百年科技巨头，95亿AI订单驱动的企业级AI转型"),
    "IDXX": ("IDEXX Laboratories Inc.", "全球宠物诊断市场龙头，高毛利的动物健康检测平台"),
    "IHG": ("InterContinental Hotels Group plc", "全球最大酒店集团之一，负资产下544%回报的轻资产典范"),
    "INTC": ("Intel Corp.", "传统CPU霸主，代工转型中的半导体巨头"),
    "INTU": ("Intuit Inc.", "TurboTax/QuickBooks母公司，穿越周期的中小企业财税印钞机"),
    "ISRG": ("Intuitive Surgical Inc.", "达芬奇手术机器人垄断者，手术机器人赛道绝对龙头"),
    "JNJ": ("Johnson & Johnson", "全球最大医疗健康公司，剥离消费品后聚焦制药与医疗器械"),
    "KLAC": ("KLA Corp.", "半导体检测设备龙头，向台积电「收保护费」的61%毛利公司"),
    "KO": ("The Coca-Cola Co.", "全球饮料帝国，提价驱动利润狂飙的百年消费品牌"),
    "LIN": ("Linde plc", "全球最大工业气体公司，拒绝周期的稳定增长商业模式"),
    "LLY": ("Eli Lilly and Co.", "全球市值最高药企，GLP-1减肥药赛道的绝对王者"),
    "LRCX": ("Lam Research Corp.", "刻蚀与沉积设备龙头，AI芯片制造的关键设备供应商"),
    "LULU": ("Lululemon Athletica Inc.", "高端运动服饰品牌，瑜伽裤品类的定义者与统治者"),
    "LYFT": ("Lyft Inc.", "美国第二大网约车平台，会计魔法下的盈利假象"),
    "MAR": ("Marriott International Inc.", "全球最大酒店管理集团，负权益下的现金奶牛与轻资产博弈"),
    "MCD": ("McDonald's Corp.", "全球最大快餐连锁，负资产却年赚46%利润的特许经营帝国"),
    "MDB": ("MongoDB Inc.", "NoSQL数据库龙头，伪装成亏损企业的印钞机"),
    "META": ("Meta Platforms Inc.", "全球最大社交媒体集团，AI算力豪赌下的广告印钞机"),
    "MPWR": ("Monolithic Power Systems Inc.", "高性能电源管理芯片龙头，AI算力爆发下的库存博弈"),
    "MRK": ("Merck & Co. Inc.", "全球制药巨头，Keytruda免疫疗法王者的专利到期赛跑"),
    "MSFT": ("Microsoft Corp.", "全球软件与云计算巨头，Azure+AI双引擎的企业级生态"),
    "MU": ("Micron Technology Inc.", "全球三大存储芯片商之一，AI需求驱动HBM产能告急"),
    "NET": ("Cloudflare Inc.", "边缘云与网络安全平台，亏损之下现金流狂飙的增长型公司"),
    "NFLX": ("Netflix Inc.", "全球最大流媒体平台，从内容到广告帝国的商业模式进化"),
    "NIO": ("NIO Inc.", "中国高端电动汽车品牌，换电模式的先行者"),
    "NKE": ("NIKE Inc.", "全球最大运动品牌，批发渠道回归的战略调整期"),
    "NOW": ("ServiceNow Inc.", "企业级IT服务管理平台，60%溢价Pro版的AI变现逻辑"),
    "NVDA": ("NVIDIA Corp.", "全球AI芯片绝对霸主，GPU+CUDA生态构建AI算力垄断"),
    "NVO": ("Novo Nordisk A/S", "全球胰岛素与GLP-1药物龙头，减肥药市场双寡头之一"),
    "NXPI": ("NXP Semiconductors NV", "汽车芯片龙头，自动驾驶与电动化的核心供应商"),
    "OKLO": ("Oklo Inc.", "小型模块化核反应堆（SMR）开发商，AI核电的先锋赌注"),
    "ONON": ("On Holding AG", "瑞士高端跑鞋品牌，CloudTec技术驱动的高成长运动公司"),
    "ORCL": ("Oracle Corp.", "企业数据库与云基础设施巨头，负现金流豪赌AI算力"),
    "OXY": ("Occidental Petroleum Corp.", "美国石油生产商，巴菲特重仓的产量狂飙型能源公司"),
    "PANW": ("Palo Alto Networks Inc.", "网络安全平台化龙头，从产品到平台的战略转型"),
    "PEP": ("PepsiCo Inc.", "全球食品饮料巨头，比银行还牛的「金融帝国」型消费公司"),
    "PFE": ("Pfizer Inc.", "全球制药巨头，后疫情时代的成本重组与管线放量博弈"),
    "PG": ("The Procter & Gamble Co.", "全球最大日用消费品公司，涨价续命但销量承压"),
    "PLTR": ("Palantir Technologies Inc.", "政府+企业大数据分析平台，AI时代的利润炸裂与估值隐忧"),
    "QCOM": ("Qualcomm Inc.", "移动通信芯片龙头，AI推理数据中心的新赛道拓展者"),
    "RACE": ("Ferrari NV", "全球顶级超跑品牌，奢侈品属性的汽车制造商"),
    "RBLX": ("Roblox Corp.", "全球最大UGC游戏平台，亏损3亿却狂赚6亿现金的虚拟经济"),
    "RDDT": ("Reddit Inc.", "全球最大论坛社区，AI数据资产化的商业突围者"),
    "RGTI": ("Rigetti Computing Inc.", "量子计算硬件开发商，195万营收与6亿现金的早期赌注"),
    "RKLB": ("Rocket Lab USA Inc.", "小型运载火箭与航天器制造商，37%毛利的商业航天新星"),
    "ROKU": ("Roku Inc.", "美国最大流媒体硬件与平台，OTT广告的核心入口"),
    "RTX": ("RTX Corp.", "全球最大航空航天与防务公司，2680亿订单的交付大考"),
    "SBUX": ("Starbucks Corp.", "全球最大咖啡连锁，净利暴跌与中国变局下的艰难转身"),
    "SHOP": ("Shopify Inc.", "全球最大独立电商SaaS平台，现金流炸裂的中小商户赋能者"),
    "SMCI": ("Super Micro Computer Inc.", "AI服务器与液冷方案供应商，液冷红利下的争议公司"),
    "SOFI": ("SoFi Technologies Inc.", "数字银行与金融超级App，盈利翻正但股权稀释加速"),
    "SPOT": ("Spotify Technology SA", "全球最大音乐流媒体平台，暴赚11亿的流媒体印钞机"),
    "STZ": ("Constellation Brands Inc.", "啤酒与烈酒巨头（Modelo/Corona），巴菲特持仓的库存与回购博弈"),
    "TEAM": ("Atlassian Corp.", "企业协作软件巨头（Jira/Confluence），营收狂飙却深陷亏损"),
    "TJX": ("The TJX Companies Inc.", "全球最大折扣零售商，31%毛利创造57% ROE的效率之王"),
    "TMO": ("Thermo Fisher Scientific Inc.", "全球最大生命科学工具公司，AI重构与周期对抗的双面博弈"),
    "TSLA": ("Tesla Inc.", "全球电动车与AI机器人龙头，停产豪车豪赌AI的激进战略"),
    "TSM": ("Taiwan Semiconductor Manufacturing Co.", "全球最大芯片代工厂，2nm豪赌与AI算力的绝对基石"),
    "TXN": ("Texas Instruments Inc.", "模拟芯片龙头，稳定分红的半导体「老登股」"),
    "UBER": ("Uber Technologies Inc.", "全球最大网约车与配送平台，营收涨20%现金流凶猛"),
    "UNH": ("UnitedHealth Group Inc.", "美国最大医疗保险集团，千亿营收仅4%净利的规模帝国"),
    "V": ("Visa Inc.", "全球最大支付网络，交易量全面回升的支付基础设施垄断者"),
    "WDAY": ("Workday Inc.", "企业级HCM与财务云平台，从席位到算力的商业化突围"),
    "WMT": ("Walmart Inc.", "全球最大零售商，极致周转对抗高估值的零售帝国"),
    "XOM": ("Exxon Mobil Corp.", "全球最大上市石油公司，穿越周期平衡长短期投入的能源霸主"),
}

def main():
    # Load data
    with open(DIR / "xhs_stock_mentions.json", encoding="utf-8") as f:
        mentions = json.load(f)
    with open(DIR / "xhs_notes_raw.json", encoding="utf-8") as f:
        all_notes = json.load(f)

    # Build note lookup by id for full engagement data
    note_lookup = {n["note_id"]: n for n in all_notes}

    # Tickers to include (exclude BTC, VIX, SPY, ON)
    exclude = {"BTC", "VIX", "SPY", "ON"}

    # Build ticker data
    ticker_data = []
    for item in mentions["stock_summary"]:
        ticker = item["ticker"]
        if ticker in exclude:
            continue

        # Get full note data with comments and shares
        notes_full = []
        for note_ref in item["notes"]:
            nid = note_ref["note_id"]
            full = note_lookup.get(nid)
            if full:
                likes = full.get("likes", 0)
                comments = full.get("comments", 0)
                collects = full.get("collects", 0)
                shares = full.get("shares", 0)
                views = full.get("views", 0)
            else:
                likes = note_ref.get("likes", 0)
                comments = 0
                collects = note_ref.get("collects", 0)
                shares = 0
                views = note_ref.get("views", 0)

            engagement = likes + comments + collects + shares
            notes_full.append({
                "title": note_ref["title"],
                "time": note_ref["time"],
                "views": views,
                "likes": likes,
                "comments": comments,
                "collects": collects,
                "shares": shares,
                "engagement": engagement,
            })

        total_views = sum(n["views"] for n in notes_full)
        total_engagement = sum(n["engagement"] for n in notes_full)
        eng_rate = (total_engagement / total_views * 100) if total_views > 0 else 0

        info = COMPANY_INFO.get(ticker, (ticker, ""))

        ticker_data.append({
            "ticker": ticker,
            "company": info[0],
            "description": info[1],
            "count": len(notes_full),
            "notes": notes_full,
            "total_views": total_views,
            "total_engagement": total_engagement,
            "engagement_rate": eng_rate,
        })

    # Sort by count desc, then total_views desc
    ticker_data.sort(key=lambda x: (-x["count"], -x["total_views"]))

    # Write report
    lines = []
    for td in ticker_data:
        t = td["ticker"]
        lines.append(f"{'='*80}")
        lines.append(f"{t} | {td['company']} | 笔记数: {td['count']}")
        lines.append(f"简介: {td['description']}")
        lines.append(f"总览: 观看 {td['total_views']:,} | 互动 {td['total_engagement']:,} | 互动率 {td['engagement_rate']:.1f}%")
        lines.append(f"{'-'*80}")
        for i, n in enumerate(td["notes"], 1):
            eng_r = (n["engagement"] / n["views"] * 100) if n["views"] > 0 else 0
            lines.append(
                f"  {i}. {n['title']}"
            )
            lines.append(
                f"     {n['time']} | 观看 {n['views']:,} | "
                f"点赞 {n['likes']} 评论 {n['comments']} 收藏 {n['collects']} 转发 {n['shares']} | "
                f"互动 {n['engagement']} ({eng_r:.1f}%)"
            )
        lines.append("")

    # Summary header
    header = [
        f"Milton聊商业 小红书美股笔记分析",
        f"生成时间: {mentions['scraped_at'][:10]}",
        f"账户笔记总数: {mentions['total_notes_scraped']}",
        f"涉及美股笔记: {mentions['notes_mentioning_stocks']}",
        f"个股 Ticker 数: {len(ticker_data)}",
        f"",
        f"互动 = 点赞 + 评论 + 收藏 + 转发",
        f"互动率 = 互动 / 观看 × 100%",
        f"",
    ]

    with open(DIR / "all_tickers.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(header + lines))

    print(f"Report written: {len(ticker_data)} tickers")
    print(f"Output: {DIR / 'all_tickers.txt'}")


if __name__ == "__main__":
    main()

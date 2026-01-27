# Daily Newsletter Digest Skill

每日从 Gmail 提取 Grok 和 OpenAI 的新闻推送，整理并存档。

## 触发方式

- **Cron**: 每天 13:00 EST 自动执行
- **手动**: 用户说 "获取今日新闻" 或 "运行 daily-newsletter"

## 数据来源

| 来源 | 邮箱地址 | 内容类型 |
|------|----------|----------|
| Grok | noreply@x.ai | AI Dev Top 15 / 美股分析 Top 5 |
| OpenAI | noreply@tm.openai.com | 市场脉搏 / 板块热度 / 财报速递 |

## 存储位置

- **存档目录**: `~/clawd/newsletters/`
- **简版**: `YYYY-MM-DD.md` — 摘要版，便于快速浏览
- **完整版**: `YYYY-MM-DD-full.md` — 包含所有详细内容
- **同时发送**: 摘要推送给用户

---

## 执行流程

### Step 1: 获取邮件

```bash
# Grok 邮件
gog gmail messages search "from:noreply@x.ai newer_than:1d" --max 10 --account miltonnyc25@gmail.com --json

# OpenAI 邮件
gog gmail messages search "from:noreply@tm.openai.com newer_than:1d" --max 20 --account miltonnyc25@gmail.com --json
```

### Step 2: 获取邮件详情

对于每封邮件，获取完整内容：

```bash
gog gmail get <messageId> --account miltonnyc25@gmail.com
```

### Step 3: 提取链接并获取内容

从邮件 HTML 中提取关键链接：
- Grok: `https://grok.com/chat/...` 或 `https://grok.com/c/...`
- OpenAI: `https://chatgpt.com/c/...` 或 `https://chatgpt.com/g/...`

使用 `clawd` profile 浏览器（已登录 Grok 和 ChatGPT）获取完整内容：

```
browser action=open profile=clawd targetUrl=<link>
browser action=snapshot targetId=<id> profile=clawd
```

### Step 4: 补充缺失信息 ⚠️ 重要

**如果邮件只是通知类（如 "Baker Hughes earnings surprise"），必须主动用 web_fetch 获取实际数据：**

```bash
# 例：财报类
web_fetch url=https://www.reuters.com/markets/companies/BKR.O/

# 例：股票分析类
web_fetch url=https://seekingalpha.com/symbol/TICKER
```

**绝不允许出现占位符文字**，如：
- ❌ "具体内容需查看对应 ChatGPT 对话获取详细分析"
- ❌ "详见原文链接"

如果无法获取内容，标注 `⚠️ 获取失败` 并记录原因。

### Step 5: 整理并存档

1. 按下方格式规范整理成 Markdown
2. 保存简版到 `~/clawd/newsletters/YYYY-MM-DD.md`
3. 保存完整版到 `~/clawd/newsletters/YYYY-MM-DD-full.md`
4. 发送摘要给用户

### Step 6: 生成 NotebookLM Video Overview 🎬

完成文档生成后，提炼美股热点信息并生成视频摘要。

#### 6.1 提取美股热点内容

从完整版中提取最吸引人的美股相关信息，生成独立的 source 文件：

```bash
# 保存提炼后的美股热点
~/clawd/newsletters/YYYY-MM-DD-stocks-highlights.md
```

**提取内容包括：**
- Grok 美股分析 Top 5（完整内容）
- OpenAI 热点公司分析
- 财报速递（如有）
- 板块热度榜 + 逻辑判断
- Daily Market Pulse 核心观点

**提取原则：**
- 只保留美股相关内容（排除 AI Dev 技术类）
- 保留具体数据、ticker、催化剂
- 确保内容连贯、有洞察力

#### 6.2 创建 NotebookLM Notebook

```bash
# CLI 路径
NOTEBOOKLM=/Library/Frameworks/Python.framework/Versions/3.12/bin/notebooklm

# 创建当日 notebook
$NOTEBOOKLM create "美股日报 YYYY-MM-DD"

# 获取 notebook ID 并设为当前
$NOTEBOOKLM use <notebook_id>
```

#### 6.3 添加 Source

```bash
# 添加提炼后的美股热点文件
$NOTEBOOKLM source add ~/clawd/newsletters/YYYY-MM-DD-stocks-highlights.md
```

#### 6.4 生成 Video Overview

```bash
# 生成视频（可选样式：classic, whiteboard, kawaii, anime 等）
$NOTEBOOKLM generate video --style classic --wait

# 或使用 Python API
python3 << 'EOF'
import asyncio
from notebooklm import NotebookLMClient

async def generate_video(notebook_id: str, output_path: str):
    async with await NotebookLMClient.from_storage() as client:
        status = await client.artifacts.generate_video(
            notebook_id,
            style="classic",  # 可选: whiteboard, kawaii, anime
        )
        await client.artifacts.wait_for_completion(notebook_id, status.task_id)
        await client.artifacts.download_video(notebook_id, output_path)
        print(f"Video saved to {output_path}")

asyncio.run(generate_video("<notebook_id>", "~/clawd/newsletters/YYYY-MM-DD-video.mp4"))
EOF
```

#### 6.5 下载视频

```bash
# 下载到 newsletters 目录
$NOTEBOOKLM download video ~/clawd/newsletters/YYYY-MM-DD-video.mp4
```

#### 6.6 输出文件

| 文件 | 路径 | 说明 |
|------|------|------|
| 美股热点源文件 | `~/clawd/newsletters/YYYY-MM-DD-stocks-highlights.md` | NotebookLM source |
| Video Overview | `~/clawd/newsletters/YYYY-MM-DD-video.mp4` | 生成的视频摘要 |

---

## NotebookLM 配置

- **CLI 路径**: `/Library/Frameworks/Python.framework/Versions/3.12/bin/notebooklm`
- **认证**: `~/.notebooklm/storage_state.json`
- **首次登录**: 运行 `notebooklm login` 完成 Google 账户授权

### 首次设置

```bash
# 1. 登录（会打开浏览器）
/Library/Frameworks/Python.framework/Versions/3.12/bin/notebooklm login

# 2. 验证登录成功
/Library/Frameworks/Python.framework/Versions/3.12/bin/notebooklm list
```

---

## 输出格式规范

### 文件头（两版通用）

```markdown
# 每日新闻摘要 [完整版] - YYYY-MM-DD

> 生成时间: HH:MM EST
> 数据来源: Grok (noreply@x.ai) + OpenAI (noreply@tm.openai.com)

---
```

---

## 第一部分：Grok AI Dev Top 15

### 简版格式

```markdown
## 🤖 Grok AI Dev Top 15

**标题**: Daily AI Dev Top 15 is ready
**时间窗口**: YYYY-MM-DD ~ YYYY-MM-DD (GMT)

### 精选要点

**【#1】标题**
- 🔗 https://example.com/link
- 💡 一句话核心价值

**【#2】标题**
- 🔗 链接
- 💡 核心价值

[继续到 #10]

### 🎯 今日可抄作业清单
1. **项目名** - 一句话用途
2. **项目名** - 一句话用途
...
```

### 完整版格式

```markdown
# 🤖 第一部分：Grok AI Dev Top 15 - 完整内容

---

## 【#1】项目标题

🔗 主链接

### 完整内容

[详细描述项目是什么、解决什么问题]

### 快速开始

[安装命令、配置步骤]

### 代码示例

```language
[实际代码]
```

### 关键功能

- 功能1
- 功能2
...

---

## 【#2】项目标题
...
```

---

## 第二部分：Grok 美股分析 Top 5

### 简版格式

```markdown
## 📈 Grok 美股分析 Top 5

**标题**: US Stocks Long Insights Top 5
**时间窗口**: YYYY-MM-DD ~ YYYY-MM-DD (GMT)

### 1. 公司名 ($TICKER): 标题
- **核心观点**: 一句话总结
- **估值/关键数据**: 具体数字
- **催化剂**: 关键驱动因素
- 🔗 链接

### 2. ...
```

### 完整版格式

```markdown
# 📈 第二部分：Grok 美股分析 Top 5 - 完整内容

---

## 1. 公司名 ($TICKER): 完整标题

🔗 原文链接

### 完整内容

[完整分析，包括：]
- 商业模式
- 竞争优势
- 增长前景
- 财务数据
- 估值分析
- 风险提示

### 关键数据表

| 指标 | 数值 |
|------|------|
| 营收 | $XXB |
| 净利 | $XXB |
| ROE | XX% |
...

---

## 2. ...
```

---

## 第三部分：OpenAI 市场脉搏

### 简版格式

```markdown
## 📊 OpenAI 市场脉搏

### US Sector + Hot Tickers Radar
- **执行时间**: 每日 HH:MM ET
- **覆盖范围**: 
  - 板块热度榜（Top 5 + Bottom 3）
  - 全市场热点公司（8-12只）
  - 异常成交/波动雷达（6-10只）

### 财报速递（如有）

**$TICKER - 公司名**
- **业绩**: 关键数据
- **亮点**: 1-2句
- **催化剂**: 近期驱动

### 今日邮件汇总 (N封)
| 主题 | 状态 |
|------|------|
| 主题1 | ✅ 已提取 |
| 主题2 | ⏭️ 无变化 |
...
```

### 完整版格式

```markdown
# 📊 第三部分：OpenAI 市场脉搏 - 完整内容

> 数据来源：ChatGPT Tasks 定时任务输出
> 对话链接：https://chatgpt.com/c/...

---

## 📊 模块一｜板块热度榜 (Top5 + Bottom3)

**日期：YYYY-MM-DD (ET)**

| 排名 | 板块 | 热度 | 影响 | 置信度 |
|------|------|------|------|--------|
| 1 | 板块名 | 🔥🔥🔥 | 🎯 高 — 原因 | ✅ 高 |
| 2 | ... | 🔥🔥 | 🎯 中 — 原因 | ✅ 中 |
...

### 逻辑判断
[分析每个板块热度的原因，带来源链接]

---

## 🚀 模块二｜热点公司 (8–12)

### $TICKER – 公司名
🔥 热度: 🔥🔥🔥 | 🎯 影响: 高 | ✅ 置信度: 高

**驱动因素：** 详细描述
- 来源：[来源名](链接)

### $TICKER2 – 公司名
...

---

## 📈 模块三｜异常成交 / 波动

- **$TICKER** — 异常描述 → 关注点
...

---

## Daily Market Pulse（如有）

### 总览
[当日市场整体情况分析]

### 主线一：标题
[详细分析，带来源]

### 主线二：标题
...

### 下周看点
[日历事件、财报预告等]

---

## 财报详解（如有）

### $TICKER 财报解读

**时间**: Day, DD Mon YYYY
**来源**: [来源](链接)

#### 业绩亮点
- 关键数据1
- 关键数据2

#### 关键财务数据

| 指标 | 数值 | 同比 |
|------|------|------|
| 营收 | $XXB | +X% |
| 净利 | $XXB | +X% |
...

#### 近期催化剂
1. 催化剂1
2. 催化剂2

#### 投资要点
✅ **看多逻辑**: ...
⚠️ **风险**: ...
```

---

## 文件尾部

```markdown
---

# 📁 文件信息

- **完整版存档**: ~/clawd/newsletters/YYYY-MM-DD-full.md
- **简版存档**: ~/clawd/newsletters/YYYY-MM-DD.md
- **Grok 邮件数**: N
- **OpenAI 邮件数**: N
- **数据获取时间**: YYYY-MM-DD HH:MM UTC
```

---

## 错误处理

- **浏览器登录过期**: 通知用户手动登录一次
- **邮件为空**: 记录日志，跳过该部分
- **链接无法访问**: 用 web_fetch 尝试获取替代信息
- **财报/股票数据不完整**: 主动从 Reuters/SeekingAlpha 补充

## 质量检查清单 ✅

生成后必须检查：

- [ ] 所有部分都有实际内容（无占位符）
- [ ] 所有链接格式正确
- [ ] 财报数据包含具体数字
- [ ] 股票分析包含 ticker 符号
- [ ] 表格格式正确渲染
- [ ] 时间戳准确

---

## 配置

- **Gmail 账户**: `miltonnyc25@gmail.com`
- **浏览器 Profile**: `clawd`
- **时区**: `America/New_York`

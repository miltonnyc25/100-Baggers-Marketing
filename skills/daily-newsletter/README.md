# Daily Newsletter Skill

自动从 Gmail 提取 Grok 和 OpenAI 的每日新闻推送，生成完整的投资与 AI 技术日报。

## 文件结构

```
skills/daily-newsletter/
├── SKILL.md          # 技能定义（Clawdbot 读取）- 包含完整格式规范
└── README.md         # 本文件
```

## 输出文件

每天生成两个版本：

```
~/clawd/newsletters/
├── 2026-01-26.md          # 简版 - 摘要快速浏览
├── 2026-01-26-full.md     # 完整版 - 所有详细内容
├── 2026-01-27.md
├── 2026-01-27-full.md
└── ...
```

### 简版 vs 完整版

| 版本 | 内容 | 用途 |
|------|------|------|
| 简版 `.md` | 要点摘要、核心数据、作业清单 | 每日快速扫描 |
| 完整版 `-full.md` | 完整分析、代码示例、详细财务数据 | 深度研究 |

## 内容覆盖

### 🤖 第一部分：Grok AI Dev Top 15
- AI 开发工具、框架、SDK
- MCP 集成、Agent 架构
- 开源项目速递
- **输出**: 完整项目介绍 + 代码示例 + 作业清单

### 📈 第二部分：Grok 美股分析 Top 5
- Long 方向个股分析
- 估值、催化剂、风险
- **输出**: 完整投资论点 + 财务数据表

### 📊 第三部分：OpenAI 市场脉搏
- 板块热度榜 (Top 5 + Bottom 3)
- 热点公司 (8-12只)
- 异常成交/波动雷达
- 财报速递 (如 Baker Hughes 等)
- **输出**: 表格 + 深度分析 + 来源链接

## 质量要求 ⚠️

**绝不允许占位符内容！**

如果邮件只是通知（无完整内容），必须：
1. 主动用 `web_fetch` 获取实际数据
2. 从 Reuters/SeekingAlpha 等来源补充
3. 标注 `⚠️ 获取失败` 如果确实无法获取

## Cron 配置

已配置每天 13:00 EST 自动执行：
- Job ID: `daily-newsletter-digest`
- 执行时间: `0 13 * * * America/New_York`

## 手动运行

对 Clawdbot 说：
- "获取今日新闻"
- "运行 daily-newsletter"
- "生成今天的 newsletter"

## 查看历史

```bash
# 查看所有存档
ls ~/clawd/newsletters/

# 查看某天的完整版
cat ~/clawd/newsletters/2026-01-26-full.md

# 查看某天的简版
cat ~/clawd/newsletters/2026-01-26.md
```

## 依赖

- `gog` CLI (Gmail 访问)
- Clawdbot browser 工具 (页面抓取)
- 已登录的 `clawd` 浏览器 profile (Grok + ChatGPT)
- `web_fetch` (补充数据获取)

## 配置

- **Gmail 账户**: `miltonnyc25@gmail.com`
- **浏览器 Profile**: `clawd`
- **时区**: `America/New_York`

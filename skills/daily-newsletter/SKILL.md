# Daily Newsletter Digest Skill

每日从 Gmail 提取 Grok 和 OpenAI 的新闻推送，整理并存档。

## 触发方式

- **Cron**: 每天 13:00 EST 自动执行
- **手动**: 用户说 "获取今日新闻" 或 "运行 daily-newsletter"

## 数据来源

| 来源 | 邮箱地址 | 内容类型 |
|------|----------|----------|
| Grok | noreply@x.ai | AI Dev Top 15 / 美股分析 |
| OpenAI | noreply@tm.openai.com | 市场脉搏 / 热门股票 |

## 存储位置

- **存档目录**: `~/clawd/newsletters/`
- **文件命名**: `YYYY-MM-DD.md`
- **同时发送**: 摘要推送给用户

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

### Step 3: 提取链接

从邮件 HTML 中提取关键链接：
- Grok: `https://grok.com/chat/...` 或 `https://grok.com/c/...`
- OpenAI: `https://chatgpt.com/c/...` 或 `https://chatgpt.com/g/...`

### Step 4: 用浏览器获取内容

使用 `clawd` profile 浏览器（已登录 Grok 和 ChatGPT）：

```
browser action=open profile=clawd targetUrl=<link>
browser action=snapshot targetId=<id> profile=clawd
```

### Step 5: 整理并存档

1. 将内容整理成 Markdown 格式
2. 保存到 `~/clawd/newsletters/YYYY-MM-DD.md`
3. 发送摘要给用户

## 输出格式

```markdown
# 每日新闻摘要 - YYYY-MM-DD

## 🤖 Grok AI Dev Top 15
[提取的 AI 开发新闻...]

## 📈 Grok 美股分析
[提取的美股分析...]

## 📊 OpenAI 市场脉搏
[提取的市场更新...]

---
生成时间: HH:MM EST
```

## 错误处理

- **浏览器登录过期**: 通知用户手动登录一次
- **邮件为空**: 记录日志，跳过
- **链接无法访问**: 记录错误，继续下一个

## 配置

Gmail 账户: `miltonnyc25@gmail.com`
浏览器 Profile: `clawd`
时区: `America/New_York`

# Daily Newsletter Skill

自动从 Gmail 提取 Grok 和 OpenAI 的每日新闻推送。

## 文件结构

```
skills/daily-newsletter/
├── SKILL.md          # 技能定义（Clawdbot 读取）
├── fetch-emails.sh   # 邮件获取脚本
└── README.md         # 本文件
```

## 存储位置

提取的内容保存到：
```
~/clawd/newsletters/
├── 2026-01-26.md
├── 2026-01-27.md
└── ...
```

## 手动运行

```bash
# 1. 获取邮件
./skills/daily-newsletter/fetch-emails.sh /tmp

# 2. 查看结果
cat /tmp/grok_emails.json
cat /tmp/openai_emails.json
```

## Cron 配置

已配置每天 13:00 EST 自动执行：
- Job ID: `daily-newsletter-digest`
- 执行时间: `0 13 * * * America/New_York`

## 查看历史

```bash
# 查看所有存档
ls ~/clawd/newsletters/

# 查看某天的内容
cat ~/clawd/newsletters/2026-01-27.md
```

## 依赖

- `gog` CLI (Gmail 访问)
- `jq` (JSON 解析)
- Clawdbot browser 工具 (页面抓取)
- 已登录的 clawd 浏览器 profile (Grok + ChatGPT)

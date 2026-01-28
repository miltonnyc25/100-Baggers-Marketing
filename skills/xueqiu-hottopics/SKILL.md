# 雪球热门股票评论发布 Skill

## 概述

从每日 newsletter 提取热门股票，结合 100baggers.club 数据，生成雪球风格评论并发布到对应股票页面。

## 快速使用

```bash
# 发布所有热门股票评论
~/Downloads/add-caption/venv/bin/python ~/clawd/skills/xueqiu-hottopics/xueqiu_hottopics.py 2026-01-27

# 仅生成评论，不发布（预览）
~/Downloads/add-caption/venv/bin/python ~/clawd/skills/xueqiu-hottopics/xueqiu_hottopics.py 2026-01-27 --dry-run

# 只处理指定股票
~/Downloads/add-caption/venv/bin/python ~/clawd/skills/xueqiu-hottopics/xueqiu_hottopics.py 2026-01-27 --ticker AAPL
```

## 工作流程

```
1. 从 {date}-xhs-post.md 提取热门股票（ticker + 摘要）
2. 对每只股票，调用 100baggers.club API 获取详细数据
3. 使用 Gemini AI 生成雪球风格评论（300-500字）
4. 发布到 https://xueqiu.com/S/{TICKER} 页面
5. 每只股票间隔 30 秒，避免限流
```

## 前置条件

### 1. 环境变量

```bash
# Gemini API Key（生成评论用）
export GEMINI_API_KEY="your-gemini-api-key"

# 100baggers API Key（可选，获取详细数据用）
export INTERNAL_API_KEY="your-100baggers-api-key"
```

### 2. 雪球登录

首次使用需要登录雪球获取 cookie：

```bash
cd ~/Downloads/add-caption/social_uploader
python -c "
import asyncio
from xueqiu_uploader.main import get_xueqiu_cookie
asyncio.run(get_xueqiu_cookie('xueqiu_uploader/xueqiu_account.json'))
"
```

浏览器会打开，手动扫码登录后 cookie 会自动保存。

## 评论生成规则

生成的评论符合雪球用户讨论风格：

- **字数**：300-500字
- **风格**：像真人发帖，有个人观点，不说教，去AI味
- **内容**：
  - 直接切入主题，说明股票为什么值得关注
  - 结合数据分析，提出看法
  - 可以提出风险点或思考问题
- **结尾**：自动添加"数据参考了100baggers.club"

### Prompt 模板

评论生成使用以下 prompt（可在脚本中修改 `XUEQIU_COMMENT_PROMPT`）：

```
你是一个资深美股投资者，经常在雪球上和球友讨论股票...
```

## 输出示例

```
============================================================
🔥 雪球热门股票评论发布 - 2026-01-27
============================================================

[15:30:00] ℹ️  从 2026-01-27-xhs-post.md 提取股票
[15:30:00] ℹ️  提取到 5 只热门股票

============================================================
[15:30:00] ℹ️  处理股票: NVO (Novo Nordisk)
============================================================
[15:30:01] ℹ️  获取 NVO 的 100baggers 数据...
[15:30:03] ✅ 获取 NVO 数据成功
[15:30:04] ℹ️  为 NVO 生成雪球评论...
[15:30:08] ✅ 评论生成成功 (420 字)

--- 评论预览 ---
诺和诺德这波口服Wegovy的数据确实亮眼，首周1.8万张处方...
...
数据参考了100baggers.club
--- 预览结束 ---

[15:30:10] ✅ 成功发布到 https://xueqiu.com/S/NVO
```

## 参数说明

| 参数 | 说明 |
|------|------|
| `date` | 日期，格式 YYYY-MM-DD |
| `--dry-run` | 仅生成评论，不发布到雪球 |
| `--ticker`, `-t` | 只处理指定股票（如 AAPL） |

## 依赖

```bash
pip install google-generativeai requests playwright
```

或使用已有的 venv：

```bash
~/Downloads/add-caption/venv/bin/python xueqiu_hottopics.py ...
```

## 文件结构

```
skills/xueqiu-hottopics/
├── SKILL.md                 # 本文档
└── xueqiu_hottopics.py      # 主脚本
```

## 与其他 Skill 的关系

- **依赖 skill1**：使用 daily-newsletter 生成的 `{date}-xhs-post.md`
- **数据来源**：100baggers.club API
- **发布平台**：雪球 xueqiu.com

## 注意事项

1. **发布频率**：每只股票间隔 30 秒，避免被雪球限流
2. **内容合规**：生成的评论不包含具体买卖建议
3. **数据声明**：每篇评论结尾自动添加数据来源声明
4. **Cookie 有效期**：雪球 cookie 可能过期，需要重新登录

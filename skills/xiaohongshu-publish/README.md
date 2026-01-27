# 小红书美股日报发布 Skill

将每日美股新闻自动生成小红书发布内容。

## 功能

- 🎨 **封面图生成** — 统一视觉风格，每日自动生成
- 📝 **标题优化** — 提取最吸引眼球的热点
- 📋 **描述生成** — 结构化内容 + 热门标签
- 🎬 **视频附带** — NotebookLM 生成的 Video Overview

## 输出文件

```
~/clawd/newsletters/
├── 2026-01-26-xhs-cover.png    # 封面图
├── 2026-01-26-xhs-post.md      # 发布内容
└── 2026-01-26-video.mp4        # 视频
```

## 使用方法

**前置条件**: 先运行 `daily-newsletter` skill 生成内容

```
# 对 Clawdbot 说
发布到小红书
xiaohongshu publish
生成今天的小红书内容
```

## 封面设计

**视觉风格**:
- 深蓝渐变背景
- 金色 + 白色文字
- 统一布局模板

**尺寸**: 1242 x 1660 px (3:4 竖版)

## 依赖

- `daily-newsletter` skill
- Canvas 工具
- NotebookLM (视频)

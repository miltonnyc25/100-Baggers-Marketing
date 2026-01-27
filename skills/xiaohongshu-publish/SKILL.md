# 小红书美股日报发布 Skill

将每日美股新闻摘要发布到小红书，包含封面图、标题、描述和视频。

## 触发方式

- **手动**: 用户说 "发布到小红书" 或 "xiaohongshu publish"
- **依赖**: 需要先完成 `daily-newsletter` skill 生成 newsletter 和 video

## 输入文件

| 文件 | 来源 | 用途 |
|------|------|------|
| `YYYY-MM-DD-stocks-highlights.md` | daily-newsletter | 内容提取 |
| `YYYY-MM-DD-video.mp4` | NotebookLM | 发布视频 |

## 输出文件

```
~/clawd/newsletters/
├── YYYY-MM-DD-xhs-cover.png      # 封面图
├── YYYY-MM-DD-xhs-post.md        # 发布内容（标题+描述）
└── YYYY-MM-DD-video.mp4          # 视频（来自 NotebookLM）
```

---

## 执行流程

### Step 1: 生成封面图 🎨

使用 Canvas 或 AI 图像生成工具创建封面图。

#### 封面设计规范

**尺寸**: 1242 x 1660 px (3:4 竖版) 或 1242 x 930 px (4:3 横版)

**统一视觉风格**:
```
背景: 深蓝渐变 (#0a1628 → #1a365d)
主色调: 金色 (#FFD700) + 白色 (#FFFFFF)
字体: 思源黑体 / SF Pro (粗体)
图标: 📈 💰 🔥 等 emoji 点缀
```

**布局模板**:
```
┌─────────────────────────────┐
│  📊 美股日报                 │ ← 顶部固定标识
│  2026.01.26                 │ ← 日期
├─────────────────────────────┤
│                             │
│   🔥 今日最热               │ ← 主标题区
│   [热门标的 1]              │
│   [热门标的 2]              │
│   [热门标的 3]              │
│                             │
├─────────────────────────────┤
│  💡 每日投资洞察             │ ← 底部 slogan
└─────────────────────────────┘
```

#### 生成方式

**方式 1: Canvas HTML 渲染**
```javascript
// 使用 canvas action=present 渲染 HTML 模板
// 然后 canvas action=snapshot 截图
```

**方式 2: 模板 + 文字替换**
```bash
# 基础模板存放位置
~/clawd/skills/xiaohongshu-publish/templates/cover-base.html
```

### Step 2: 生成标题 📝

从当日热点中提取最吸引眼球的标题。

**标题规范**:
- 长度: 15-25 字
- 必须包含: emoji + 数据/亮点
- 格式: `[emoji] 核心信息 | 补充信息`

**标题模板**:
```
🔥 $IRDM 被低估75%！全球唯一卫星垄断者
📈 ASML 5个月翻倍！AI芯片龙头还能追吗
💰 黄金突破$5000！白银冲上$100 硬资产时代来了
🚀 Baker Hughes财报炸裂！天然气设备需求爆发
```

**生成逻辑**:
1. 读取 `stocks-highlights.md`
2. 提取最有话题性的 1-2 个标的
3. 结合关键数据生成标题

### Step 3: 生成描述 📋

**描述规范**:
- 长度: 200-500 字
- 结构: 开头金句 + 3-5 个要点 + 结尾互动
- 必须包含: 热门标签

**描述模板**:
```markdown
[开头金句 - 制造紧迫感/好奇心]

📊 今日美股热点：

1️⃣ [标的1] - [一句话亮点]
2️⃣ [标的2] - [一句话亮点]  
3️⃣ [标的3] - [一句话亮点]

💡 关键洞察：
[最重要的市场观点]

🎯 明日关注：
[即将到来的催化剂/事件]

---
👆 点击视频看完整分析

#美股 #投资 #股票 #财经 #[相关标的ticker]
```

### Step 4: 组装发布内容

将标题和描述保存到 `YYYY-MM-DD-xhs-post.md`:

```markdown
# 小红书发布内容 - YYYY-MM-DD

## 标题
[生成的标题]

## 描述
[生成的描述]

## 封面图
~/clawd/newsletters/YYYY-MM-DD-xhs-cover.png

## 视频
~/clawd/newsletters/YYYY-MM-DD-video.mp4

## 标签
#美股 #投资 #股票 #财经 #IRDM #ASML #Baker Hughes
```

### Step 5: 发布到小红书 (可选)

**手动发布**: 复制内容到小红书 App

**自动发布** (需要配置):
- 使用浏览器自动化上传
- 需要小红书账号登录态

---

## 封面图 HTML 模板

```html
<!DOCTYPE html>
<html>
<head>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      width: 1242px;
      height: 1660px;
      background: linear-gradient(135deg, #0a1628 0%, #1a365d 100%);
      font-family: -apple-system, "SF Pro Display", "PingFang SC", sans-serif;
      color: white;
      padding: 80px;
      display: flex;
      flex-direction: column;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 60px;
    }
    .logo {
      font-size: 48px;
      font-weight: 700;
      color: #FFD700;
    }
    .date {
      font-size: 36px;
      color: rgba(255,255,255,0.7);
    }
    .main {
      flex: 1;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }
    .section-title {
      font-size: 42px;
      color: #FFD700;
      margin-bottom: 40px;
    }
    .hot-item {
      font-size: 56px;
      font-weight: 700;
      margin-bottom: 30px;
      line-height: 1.4;
    }
    .hot-item .ticker {
      color: #FFD700;
    }
    .hot-item .highlight {
      color: #4ADE80;
    }
    .footer {
      text-align: center;
      padding-top: 60px;
      border-top: 2px solid rgba(255,255,255,0.2);
    }
    .slogan {
      font-size: 36px;
      color: rgba(255,255,255,0.8);
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="logo">📊 美股日报</div>
    <div class="date">{{DATE}}</div>
  </div>
  
  <div class="main">
    <div class="section-title">🔥 今日最热</div>
    <div class="hot-item">
      <span class="ticker">${{TICKER1}}</span> {{TITLE1}}
    </div>
    <div class="hot-item">
      <span class="ticker">${{TICKER2}}</span> {{TITLE2}}
    </div>
    <div class="hot-item">
      <span class="ticker">${{TICKER3}}</span> {{TITLE3}}
    </div>
  </div>
  
  <div class="footer">
    <div class="slogan">💡 每日投资洞察 · 抓住财富密码</div>
  </div>
</body>
</html>
```

---

## 配置

- **输出目录**: `~/clawd/newsletters/`
- **模板目录**: `~/clawd/skills/xiaohongshu-publish/templates/`
- **封面尺寸**: 1242 x 1660 px (竖版)

## 依赖

- `daily-newsletter` skill (内容来源)
- Canvas 工具 (封面生成)
- NotebookLM video (视频来源)

# 小红书视频发布 Skill

## 概述
处理 NotebookLM 生成的视频，添加中英双语字幕和 Logo 水印，发布到小红书。

---

## 🚀 推荐方式：使用 Python 脚本发布

**最可靠的发布方式是使用专门的 Python 脚本：**

```bash
# 使用 venv 环境运行
/Users/xuemeizhao/Downloads/add-caption/venv/bin/python \
  ~/clawd/skills/xiaohongshu-publish/xhs_publisher.py \
  ~/clawd/newsletters/YYYY-MM-DD-video-with-subs.mp4 \
  ~/clawd/newsletters/YYYY-MM-DD-cover-xhs.jpg \
  ~/clawd/newsletters/YYYY-MM-DD-xhs-post.md
```

**脚本特性：**
- ✅ 自动注入 stealth.min.js 反检测
- ✅ 自动上传预生成的封面（3:4 比例）
- ✅ 自动读取 xhs-post.md 填充正文
- ✅ 自动处理 Shepherd 新手引导弹窗
- ✅ 多种发布按钮点击方法（直接/JS/React）
- ✅ 自动保存和加载 cookies
- ✅ 6 次重试机制

**参数说明：**
| 参数 | 说明 |
|------|------|
| video_path | 带字幕的视频文件 |
| cover_path | **预生成的封面图** (YYYY-MM-DD-cover-xhs.jpg) |
| post_md_path | **文案文件** (YYYY-MM-DD-xhs-post.md) |
| --headless | 可选，无头模式（不显示浏览器） |

---

## ⚠️ 重要规则（必读）

1. **不要重复生成视频！** 已生成过 Video Overview 的笔记本，直接下载即可，生成一次太慢了
2. **必须保留原视频！** 先保存原视频文件，然后再添加字幕生成新版本
3. **已生成视频的下载方式**: 在 NotebookLM 页面点击视频的 **三个点图标 → Download**
4. **封面必须是 3:4 比例！** 使用脚本专门生成，**禁止从视频截取**
5. **发布时设为"公开可见"！** 直接公开发布
6. **观点归属必须明确！** 高估/低估是文章观点，不是我们的观点
7. **不给投资建议！** 我们只做信息整理，不做买卖推荐

---

## ⚠️ 内容合规规则（小红书必读）

### 1. 敏感话题（必须删除） 🚫

| 类别 | 敏感话题 |
|------|----------|
| **地缘政治** | 台海、台湾、中美脱钩、制裁、贸易战、芯片禁令 |
| **政治敏感** | 香港、西藏、新疆、国家领导人 |
| **军事相关** | 军工股涉及中国威胁论、南海、军事冲突 |

**如果视频中包含这些内容，必须在字幕/描述中删除或用中性词替换！**

### 2. 观点归属规则 📝

**关于高估/低估、目标价等表述：**

| ❌ 禁止 | ✅ 正确 |
|--------|--------|
| 该股被低估 75% | **据分析文章**，该股被低估 75% |
| 目标价 $150 | **原文给出的**目标价为 $150 |
| 建议买入 | **文章观点**看多该股 |

### 3. 标题/描述规范

**标题格式（固定）：**
```
美股热点速递 | YYYY.MM.DD
```

**示例：**
- ✅ `美股热点速递 | 2026.01.27`
- ✅ `美股热点速递 | 2026.01.28`
- ❌ `IRDM低估75%快买！`（禁止投资建议）
- ❌ `据分析NVO减肥药龙头`（不要用其他格式）

**描述必须包含免责声明：**
```
⚠️ 免责声明：本视频所有观点均来自原始分析文章，不代表本账号立场。
我们不对任何股票做高估/低估判断，也不提供投资建议。投资有风险，请谨慎决策。
```

### 4. 封面文字规范

封面上如果有"低估 XX%"等文字，前面加上"据分析"或用问号：
- ✅ `据分析：低估 75%`
- ✅ `低估 75%？`
- ❌ `低估 75%！`（显得像我们的观点）

## 完整工作流程

### 1. 下载 NotebookLM 视频
```
⚠️ 先检查是否已存在 Video Overview！

如果已存在：
1. 点击视频右上角的 **三个点图标（⋮）**
2. 选择 **Download** 下载

如果不存在才生成：
1. 点击 Video Overview 生成视频
2. 等待生成完成（5-15分钟）
3. 点击 More → Download 下载 webm 文件

无论哪种方式，**必须保存原始视频到 ~/clawd/newsletters/YYYY-MM-DD-video.webm**
```

### 2. 转换视频格式
```bash
# webm 转 mp4
ffmpeg -i input.webm -c:v libx264 -c:a aac output.mp4
```

### 3. 裁剪视频（去掉末尾 2.5s NotebookLM 水印）
```bash
# 获取视频时长
duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 input.mp4)

# 裁剪
ffmpeg -y -i input.mp4 -t $(echo "$duration - 2.5" | bc) -c copy trimmed.mp4
```

### 4. 语音转文字（Groq Whisper）
```bash
curl -X POST "https://api.groq.com/openai/v1/audio/transcriptions" \
  -H "Authorization: Bearer $GROQ_API_KEY" \
  -F file="@trimmed.mp4" \
  -F model="whisper-large-v3-turbo" \
  -F response_format="verbose_json" \
  -F language="en"
```

### 5. 翻译为中文（Google Translate）
```python
from deep_translator import GoogleTranslator
translator = GoogleTranslator(source='en', target='zh-CN')
chinese = translator.translate(english_text)
```

### 6. 生成中英双语 SRT 字幕

#### ⚠️ 字幕分行规则（重要！）
参考 `/Users/xuemeizhao/Downloads/add-caption/video_processor.py`:
- **中文字幕**: 每行最多 **15 个字符**
- **英文字幕**: 每行最多 **10 个单词**
- 分割优先位置: 逗号、顿号、空格、"的"、"了"、连词（and/or/but）

```python
# 中文分行
def split_chinese(text, max_length=15):
    break_chars = ['，', '、', ' ', '的', '了']
    # 在 max_length 附近找断点

# 英文分行
def split_english(text, max_words=10):
    break_punctuation = [',', ';', ':', ' and ', ' or ', ' but ']
    # 在 max_words 附近找断点
```

#### SRT 格式示例
```
1
00:00:00,000 --> 00:00:05,000
English text here
中文翻译在这里
```

### 7. 烧录字幕 + Logo 水印
```bash
LOGO="/Users/xuemeizhao/Downloads/add-caption/assets/100bagersclub_logo.png"
SRT="video_bilingual.srt"

ffmpeg -y \
  -i input.mp4 \
  -i "$LOGO" \
  -filter_complex "[1:v]scale=-1:40[wm];[0:v][wm]overlay=W-w-15:H-h-15[v];[v]subtitles=${SRT}:charenc=UTF-8:force_style='FontName=Noto Sans CJK SC,FontSize=24,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,BorderStyle=3,Outline=2,Shadow=1,Bold=1'[outv]" \
  -map "[outv]" \
  -map 0:a \
  -c:a copy \
  output.mp4
```

### 8. 生成封面图（⚠️ 必须专门生成！）

**⚠️ 重要规则：**
- **封面必须使用脚本专门生成，禁止从视频截取！**
- **比例必须是 3:4**（竖版，小红书推荐格式）
- **风格要统一**，保持品牌一致性

#### 封面规格
| 属性 | 要求 |
|------|------|
| **比例** | **3:4**（竖版） |
| **尺寸** | 1080 x 1440 px 或 1242 x 1660 px |
| **格式** | JPG |
| **风格** | **金色模板（cover3-gold）** - 深色背景 + 金色边框/高亮 + 绿色股票代码 |
| **内容** | 日期 + "✨ 今日热点分析 ✨" + Top 3 股票卡片 |
| **文件名** | **YYYY-MM-DD-cover-xhs.jpg** |

#### 封面模板参考
![金色模板](covers-2026-01-27/cover3-gold.jpg)

**模板样式要点：**
- 顶部：黄色方块 + "美股日报" + 日期
- 标题："✨ 今日热点分析 ✨"（金色）
- 三个股票卡片（带金色边框）：
  - 序号（01/02/03）+ 股票代码（绿色）
  - 标题（白色粗体）
  - 高亮标签（带 emoji）
- 底部："💡 每日投资洞察 · 信息整理" + 免责声明

#### 生成方法

**方法 1: 使用 Python 脚本（推荐）**
```python
from generate_cover import generate_cover

items = [
    {'ticker': 'IRDM', 'title': '全球唯一卫星网络垄断者', 'highlight': '📉 低估 75%'},
    {'ticker': 'ASML', 'title': 'EUV光刻机龙头', 'highlight': '📈 5个月翻倍'},
    {'ticker': 'GOLD', 'title': '黄金历史性突破', 'highlight': '💰 突破 $5000'},
]

cover_path = generate_cover('~/clawd/newsletters', '2026-01-26', items)
```

**方法 2: 命令行**
```bash
python ~/clawd/skills/xiaohongshu-publish/generate_cover.py \
  ~/clawd/newsletters 2026-01-26
```

**方法 3: 浏览器渲染 HTML 模板**
```bash
# 1. 编辑 HTML 模板
open ~/clawd/skills/xiaohongshu-publish/templates/cover.html

# 2. 用浏览器打开，设置视口为 1080x1440 或 1242x1660
# 3. 截图保存为 JPG
```

#### 输出文件
- `YYYY-MM-DD-cover-xhs.jpg` - 封面图片（3:4 比例，金色模板）

#### 封面上传到小红书

小红书的封面上传 input 默认隐藏，需要特殊处理：

```javascript
// 1. 点击 "设置封面" 按钮打开对话框

// 2. 修改封面比例为 3:4
// 点击"封面比例"下拉框 → 选择 "3:4"

// 3. 点击 "上传图片" 按钮上传封面
// 或：让隐藏的 input 可见后用 upload action

// 4. 点击"确定"保存封面
```

**上传成功标志**：看到 "封面效果评估通过，未发现封面质量问题"

### 9. 生成发布文案 xhs-post.md（⚠️ 必须生成！）

**⚠️ 这一步是发布的前置条件！必须在发布前完成！**

根据当日股票摘要（`YYYY-MM-DD-stocks-highlights.md`）生成小红书发布文案。

#### 文案格式模板

```markdown
📈 美股热点速递 | YYYY.MM.DD

今日X大热股速览 👇

1️⃣ [公司名] $[股票代码] 🔥🔥🔥
[一句话概括]
• [要点1]
• [要点2]
• [要点3（如有）]

2️⃣ [公司名] $[股票代码] 🔥🔥
[一句话概括]
• [要点1]
• [要点2]

...（更多股票）

⚠️ 免责声明：以上观点均来自 Grok/OpenAI 原始分析，不构成投资建议！投资有风险，请自行研究决策。

---
#美股 #股票 #投资理财 #[相关标签] #每日复盘
```

#### 生成步骤

```bash
# 1. 读取股票摘要
cat ~/clawd/newsletters/YYYY-MM-DD-stocks-highlights.md

# 2. 根据摘要提取关键信息，生成文案
# 3. 保存到 xhs-post.md
```

#### 示例输出

```markdown
📈 美股热点速递 | 2026.01.27

今日5大热股速览 👇

1️⃣ Novo Nordisk $NVO 🔥🔥🔥
减肥药龙头财报前瞻
• 口服 Wegovy 首发破 1.8 万张处方！
• 美国产能 2026 年中翻倍
• 分析师：12-16 月潜在 52% 上涨空间

2️⃣ Apple $AAPL 🔥🔥🔥
iPhone 需求强劲 + 财报周
• S&P 500 目标 7000 点
• iPhone 预期出货 84-90M 台
• 历史规律：类似时期平均涨 17%

...

⚠️ 免责声明：以上观点均来自 Grok/OpenAI 原始分析，不构成投资建议！投资有风险，请自行研究决策。

---
#美股 #股票 #投资理财 #减肥药 #NVO #Apple #苹果 #AI #科技股 #每日复盘
```

#### 输出文件
- `YYYY-MM-DD-xhs-post.md` - 小红书发布文案（**发布脚本会读取此文件！**）

#### 规则要点
1. **🔥 火焰数量**：最重要的 3 个 🔥🔥🔥，次重要 2 个 🔥🔥，普通 1 个 🔥
2. **要点精炼**：每个要点 ≤ 20 字
3. **股票代码**：使用 $ 前缀（如 $NVO）
4. **免责声明**：必须包含！
5. **话题标签**：包含相关股票代码和主题

### 10. 发布到小红书
```
1. 打开 https://creator.xiaohongshu.com/publish/publish
2. 上传处理后的视频（YYYY-MM-DD-video-with-subs.mp4）
3. **上传封面图！** 
   - 点击"设置封面" → 选择比例 3:4 → "上传图片"
   - 选择 YYYY-MM-DD-cover-xhs.jpg（金色模板）
   - 点击"确定"
4. 填写标题：**美股热点速递 | YYYY.MM.DD**（固定格式！）
5. 填写正文描述（含免责声明）
6. 设置可见范围为"公开可见"
7. 点击发布
```

---

## 🤖 浏览器自动化发布指南（Clawdbot）

### ⚠️ 强制规则（每次发布必须遵守！）

1. **封面图必须使用预生成的封面！**
   - 文件：`~/clawd/newsletters/YYYY-MM-DD-cover-xhs.jpg`
   - **禁止跳过封面上传步骤！**
   - **禁止使用视频截图作为封面！**

2. **正文内容必须使用 xhs-post.md！**
   - 文件：`~/clawd/newsletters/YYYY-MM-DD-xhs-post.md`
   - **必须读取此文件内容并填入正文！**
   - **禁止自行编写正文内容！**

3. **必须使用 stealth 反检测脚本！**
   - 脚本：`/Users/xuemeizhao/Downloads/add-caption/social_uploader/utils/stealth.min.js`
   - **在每次 browser.open 后立即注入！**

---

### 反机器人检测配置（⚠️ 必须执行！）

小红书有反自动化检测，必须注入 stealth 脚本绕过：

**方法 1: 使用精简版 stealth（推荐，代码较短）**

直接用 browser evaluate 注入：
```javascript
browser.act(action="act", request={
  kind: "evaluate",
  fn: `
(function() {
  // 隐藏 webdriver 标记
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  
  // 模拟 Chrome runtime
  window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: { isInstalled: false }
  };
  
  // 伪装 navigator
  Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
  Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN','zh','en'] });
  
  // 隐藏自动化痕迹
  const origQuery = navigator.permissions.query;
  navigator.permissions.query = (p) => p.name === 'notifications' 
    ? Promise.resolve({state: Notification.permission}) : origQuery(p);
  
  console.log('[Stealth] Applied');
})();
  `
})
```

**方法 2: 使用完整版 stealth.min.js（更全面）**

```bash
# 文件位置
/Users/xuemeizhao/Downloads/add-caption/social_uploader/utils/stealth.min.js

# 由于文件较大(180KB)，需要通过 exec 读取后用 browser evaluate 注入
```

**Stealth 脚本提供的保护：**
| 技术 | 作用 |
|------|------|
| navigator.webdriver | 隐藏自动化标记 |
| chrome.app 模拟 | 模拟真实 Chrome 的 window.chrome.app |
| chrome.runtime 模拟 | 模拟 Chrome 扩展运行时 API |
| navigator.plugins | 伪装插件列表 |
| navigator.languages | 伪装语言设置 |
| permissions.query | 修复权限查询行为 |

---

### 成功经验总结

#### 1. 视频上传
```javascript
// 视频上传 input 的 selector
selector: 'input[type="file"][accept*=".mp4"]'
// 或直接用 button ref
ref: "Choose File" button

// 使用 browser upload action
browser.upload(ref=视频按钮ref, paths=[视频路径])
```

#### 2. 封面上传（⚠️ 必须执行！）

**⚠️ 必须使用预生成的封面文件：`YYYY-MM-DD-cover-xhs.jpg`**

**问题：** 小红书的封面上传 input 默认是隐藏的 (display: none)

**解决方案：**
```javascript
// 步骤 1: 点击"设置封面"按钮打开对话框
browser.act(click, ref="设置封面")

// 步骤 2: 选择比例 3:4
browser.act(click, ref="封面比例下拉框")  // 显示 "4:3"
browser.act(click, ref="3:4选项")

// 步骤 3: 点击"上传图片"按钮，让隐藏的 input 变可见
browser.act(click, ref="上传图片")

// 步骤 4: 用 JavaScript 强制让 input 可见
browser.evaluate(() => {
  const imgInput = document.querySelector('input[type="file"][accept*="image"]');
  if (imgInput) {
    imgInput.style.display = 'block';
    imgInput.style.opacity = '1';
    imgInput.style.position = 'relative';
    imgInput.style.zIndex = '9999';
  }
})

// 步骤 5: 找到 "Choose File" 按钮的 ref，用它上传
// ⚠️ 必须使用预生成的封面：~/clawd/newsletters/YYYY-MM-DD-cover-xhs.jpg
browser.upload(ref="Choose File按钮ref", paths=["/Users/xuemeizhao/clawd/newsletters/YYYY-MM-DD-cover-xhs.jpg"])

// 步骤 6: 等待 3 秒让图片加载
sleep 3

// 步骤 7: 点击"确定"保存封面
browser.act(click, ref="确定")
```

**成功标志：**
- 看到封面预览显示金色模板
- 显示 "封面效果评估通过，未发现封面质量问题"

#### 3. 标题设置
```javascript
// 标题固定格式：美股热点速递 | YYYY.MM.DD
browser.evaluate(() => {
  const input = document.querySelector('input[placeholder*="标题"]');
  if (input) {
    input.value = '美股热点速递 | 2026.01.27';  // 替换为实际日期
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }
})
```

#### 4. 正文设置（⚠️ 必须使用 xhs-post.md！）

**⚠️ 必须读取并使用 `~/clawd/newsletters/YYYY-MM-DD-xhs-post.md` 的内容！**

```javascript
// 步骤 1: 先用 read 工具读取 xhs-post.md 内容
// read("/Users/xuemeizhao/clawd/newsletters/2026-01-27-xhs-post.md")

// 步骤 2: 将读取的内容填入正文
browser.evaluate(() => {
  const textarea = document.querySelector('.ql-editor') || 
                   document.querySelector('[contenteditable="true"]') ||
                   document.querySelector('textarea[placeholder*="描述"]');
  if (textarea) {
    // 使用 xhs-post.md 的完整内容（不要自己编写！）
    const content = `📈 美股热点速递 | 2026.01.27

今日5大热股速览 👇

1️⃣ Novo Nordisk $NVO 🔥🔥🔥
...
（完整内容来自 xhs-post.md）
`;
    
    if (textarea.tagName === 'TEXTAREA') {
      textarea.value = content;
    } else {
      textarea.innerHTML = content.replace(/\n/g, '<br>');
    }
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  }
})
```

**禁止行为：**
- ❌ 自己编写正文内容
- ❌ 只填写部分内容
- ❌ 跳过正文填写步骤

#### 5. 发布按钮（多种方法尝试）

**方法 1: 直接点击（stealth 注入后）**
```javascript
browser.act(click, ref="发布按钮ref")
```

**方法 2: 模拟真实鼠标事件**
```javascript
browser.evaluate(() => {
  const btn = Array.from(document.querySelectorAll('button'))
    .find(b => b.textContent.includes('发布'));
  if (btn) {
    const rect = btn.getBoundingClientRect();
    ['mousedown', 'mouseup', 'click'].forEach(type => {
      btn.dispatchEvent(new MouseEvent(type, {
        bubbles: true,
        cancelable: true,
        view: window,
        clientX: rect.left + rect.width / 2,
        clientY: rect.top + rect.height / 2
      }));
    });
  }
})
```

**方法 3: 触发 React 内部事件**
```javascript
browser.evaluate(() => {
  const btn = document.querySelector('button.css-k3lmfk, button.publishBtn, button[class*="publish"]') ||
              Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('发布'));
  if (btn) {
    // 找 React fiber
    const key = Object.keys(btn).find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'));
    if (key) {
      const fiber = btn[key];
      const onClick = fiber.memoizedProps?.onClick || fiber.pendingProps?.onClick;
      if (onClick) onClick({stopPropagation: ()=>{}, preventDefault: ()=>{}});
    } else {
      btn.click();
    }
  }
})
```

**方法 4: 键盘提交**
```javascript
// 尝试 Enter 键提交
browser.act(action="act", request={kind: "press", key: "Enter"})
```

**如果以上方法都失败，最后手段：手动点击**
- 打开浏览器窗口让用户手动点击发布按钮

---

### 完整自动化流程（必须严格遵守！）

```
# 准备阶段
0. 读取 xhs-post.md 内容备用
   read("/Users/xuemeizhao/clawd/newsletters/YYYY-MM-DD-xhs-post.md")

# 启动浏览器
1. browser.start(profile="clawd")
2. browser.open("https://creator.xiaohongshu.com/publish/publish")

# 注入反检测脚本（⚠️ 关键步骤！）
3. browser.evaluate(注入 stealth.min.js 内容)

# 上传视频
4. browser.upload(视频) - 等待上传完成

# 上传封面（⚠️ 必须执行！使用预生成的封面！）
5. browser.act(click, "设置封面")
6. browser.act(click, "封面比例") → 选择 "3:4"
7. browser.evaluate(让封面input可见)
8. browser.upload(paths=["/Users/xuemeizhao/clawd/newsletters/YYYY-MM-DD-cover-xhs.jpg"])
9. sleep(3)
10. browser.act(click, "确定")

# 填写标题（固定格式）
11. browser.evaluate(设置标题 "美股热点速递 | YYYY.MM.DD")

# 填写正文（⚠️ 必须使用 xhs-post.md 的内容！）
12. browser.evaluate(填入 xhs-post.md 的完整内容)

# 发布
13. browser.act(click, "发布")
```

### 检查清单（每次发布前确认）

- [ ] stealth.min.js 已注入？
- [ ] 封面使用的是 YYYY-MM-DD-cover-xhs.jpg？
- [ ] 正文内容来自 YYYY-MM-DD-xhs-post.md？
- [ ] 标题格式正确（美股热点速递 | YYYY.MM.DD）？

### 注意事项
- **stealth 脚本必须在页面加载后立即注入**
- 封面上传的 input 是隐藏的，必须用 JavaScript 让它可见
- 比例选择器点击后会出现下拉菜单，需要再次点击选择
- 上传成功后等待 3 秒让图片加载完成

---

## 🎯 快速发布命令（复制即用）

```bash
# 2026-01-27 发布示例
/Users/xuemeizhao/Downloads/add-caption/venv/bin/python \
  ~/clawd/skills/xiaohongshu-publish/xhs_publisher.py \
  ~/clawd/newsletters/2026-01-27-video-with-subs.mp4 \
  ~/clawd/newsletters/2026-01-27-cover-xhs.jpg \
  ~/clawd/newsletters/2026-01-27-xhs-post.md

# 通用模板（替换 YYYY-MM-DD）
/Users/xuemeizhao/Downloads/add-caption/venv/bin/python \
  ~/clawd/skills/xiaohongshu-publish/xhs_publisher.py \
  ~/clawd/newsletters/YYYY-MM-DD-video-with-subs.mp4 \
  ~/clawd/newsletters/YYYY-MM-DD-cover-xhs.jpg \
  ~/clawd/newsletters/YYYY-MM-DD-xhs-post.md
```

## 脚本文件说明

| 文件 | 说明 |
|------|------|
| `xhs_publisher.py` | **主发布脚本**（推荐使用） |
| `inject_stealth.js` | 精简版 stealth 反检测代码 |
| `generate_cover.py` | 封面生成脚本 |
| `cookies/xhs_account.json` | 自动保存的登录状态 |

## 依赖说明

脚本使用 add-caption 的 venv 环境，已包含所需依赖：
- playwright (浏览器自动化)
- stealth.min.js (反机器人检测)

## 文件命名规范

```
~/clawd/newsletters/
├── YYYY-MM-DD-video.webm          # 原始 NotebookLM 视频（必须保存！）
├── YYYY-MM-DD-video.mp4           # 转换后的 mp4
├── YYYY-MM-DD-video_english.srt   # 英文字幕
├── YYYY-MM-DD-video_bilingual.srt # 中英双语字幕
├── YYYY-MM-DD-video-with-subs.mp4 # 最终视频（带字幕+Logo）
├── YYYY-MM-DD-cover-xhs.jpg       # 封面图片 ⭐（金色模板）
└── YYYY-MM-DD-xhs-post.md         # 发布内容文案
```

## 完整工作流程清单

```
□ 1. 下载 NotebookLM 视频（三个点图标 → Download，不要重复生成！）
□ 2. 保存原始视频到 newsletters/
□ 3. 转换 webm → mp4
□ 4. 裁剪末尾 2.5s
□ 5. 语音转文字（Groq Whisper）
□ 6. 翻译为中文
□ 7. 生成 SRT 字幕（中文≤15字符，英文≤10单词）
□ 8. 烧录字幕 + Logo 水印
□ 9. 生成封面图（金色模板！保存为 YYYY-MM-DD-cover-xhs.jpg）
□ 10. 生成发布文案（保存为 YYYY-MM-DD-xhs-post.md）⭐ 关键步骤！
□ 11. 发布到小红书（使用 xhs_publisher.py 脚本）
```

## 依赖

### ffmpeg（必须带 libass 支持）
```bash
# 安装带字幕支持的 ffmpeg
brew tap homebrew-ffmpeg/ffmpeg
brew install homebrew-ffmpeg/ffmpeg/ffmpeg
```

### Python 依赖
```bash
pip install groq deep-translator
```

### 资源文件
- Logo: `/Users/xuemeizhao/Downloads/add-caption/assets/100bagersclub_logo.png`

## 处理脚本

完整处理脚本位于：
`~/clawd/skills/xiaohongshu-publish/process_notebooklm.py`

### 使用方法
```bash
/Users/xuemeizhao/Downloads/add-caption/venv/bin/python \
  ~/clawd/skills/xiaohongshu-publish/process_notebooklm.py \
  <input_video> \
  <output_dir>
```

## 注意事项

1. **必须保存原始视频**：在处理前先备份原始 webm/mp4 文件
2. **字幕样式**：使用 Noto Sans CJK SC 字体，白色文字黑色描边
3. **Logo 位置**：右下角，距边缘 15px
4. **可见范围**：设为"公开可见"直接发布
5. **封面比例**：**必须是 3:4**，使用脚本生成，不能从视频截取

## Groq API

- **API Key**: 在 TOOLS.md 中配置
- **模型**: whisper-large-v3-turbo
- **价格**: $0.04/小时（比 OpenAI 便宜 9x）

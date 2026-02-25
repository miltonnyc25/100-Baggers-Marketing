# 100Baggers Report Marketing System

Report → Content Extraction → Platform Content Generation → Publishing pipeline
for 100Baggers.club deep research reports.

## Repository Structure

```
100-Baggers-Marketing/
├── CLAUDE.md                      # This file
├── engine/                        # Content extraction engine
│   ├── config.py                  # Paths, API URLs, ticker list
│   ├── report_schema.py           # ReportData dataclass
│   ├── content_strategist.py      # Shared angle selection + 30K curation
│   ├── prompts/                   # Unified prompt templates
│   │   ├── angle_recommend.md     # Angle recommendation prompt
│   │   └── content_curation.md    # 30K document curation prompt
│   ├── segment_schema.py          # SegmentData dataclass
│   ├── segment_splitter.py        # chapters → 3-5 themed segments
│   ├── segment_generator.py       # segment → mini-ReportData → platform generator
│   ├── markdown_parser.py         # Primary: .md report parser
│   └── report_parser.py           # Fallback: HTML parser
│
├── platforms/                     # Per-platform content generators
│   ├── xueqiu/                    # 雪球 — long-form analysis posts
│   ├── xiaohongshu/               # 小红书 — slide decks + captions
│   ├── twitter/                   # X/Twitter — English long-form posts
│   └── youtube/                   # YouTube — video scripts + descriptions
│   (each contains: generate.py, publish.py, prompt.md, template.md, config.json, archive/)
│
├── orchestrate.py                 # CLI: one-command cross-platform pipeline
│
├── webapp/                        # Content review + publishing web UI
│   ├── app.py                     # Flask app (python webapp/app.py)
│   ├── state.py                   # Session JSON persistence
│   ├── notebooklm.py              # Per-segment video generation
│   ├── templates/                 # Jinja2 templates (Pico CSS + HTMX)
│   ├── static/                    # CSS + JS
│   └── sessions/                  # Session JSON files (gitignored)
│
├── marketing/                     # Editorial pipeline + analytics
│   ├── CLAUDE.md                  # Marketing guidelines
│   ├── config.json                # Platform config
│   ├── ideas/                     # backlog + pipeline
│   └── analytics/                 # Performance tracking
│
└── newsletters/                   # Daily newsletter digests
```

## Quick Start

```bash
# List available report tickers
python orchestrate.py --list

# Generate content for all platforms (dry-run)
python orchestrate.py SMCI

# Generate only for Xueqiu
python orchestrate.py SMCI --platforms xueqiu

# Generate + publish (live)
python orchestrate.py SMCI --publish

# Batch: all tickers, all platforms
python orchestrate.py --all
```

## Web Review UI

```bash
# Install Flask (only new dependency)
pip install flask

# Start the review server
python webapp/app.py

# Open http://localhost:5000
# 1. Select ticker + platform → creates segmented session
# 2. Review & edit each segment inline
# 3. Generate NotebookLM videos per segment
# 4. Approve segments → publish (dry-run first)
```

## Architecture

### Data Flow

```
InvestView_v0/public/reports/{ticker}/*.md
         │
         ▼
    engine/ (parse → ReportData)
         │
    ┌────┼────┬────────┐
    ▼    ▼    ▼        ▼
 xueqiu  xhs  twitter  youtube   ← platforms/*/generate.py
    │    │    │        │
    ▼    ▼    ▼        ▼
 archive/  (content files)
    │    │    │        │
    ▼    ▼    ▼        ▼
 publish   publish  publish  publish  ← platforms/*/publish.py
    │    │    │        │
    ▼    ▼    ▼        ▼
 clawd-workspace skills (building blocks)
```

### Shared Content Strategist (engine/content_strategist.py)

Unified angle selection + 30K document curation pipeline shared across platforms.

```
Full Report (~200-800K chars)
        │
   preprocess_markdown()          ← strip noise, cap at 800K
        │
   recommend_angles()             ← Gemini selects best angles
        │                            (with platform-specific additions)
   curate_content(30K)            ← Gemini curates focused document
        │
   ┌────┼──────────┐
   ▼    ▼          ▼
 雪球   小红书     NotebookLM
```

| Downstream | 30K Role | Final Output |
|------------|----------|-------------|
| Xueqiu Writer | Intermediate — Writer condenses 30K → 6-8K post | 6,000-8,000 chars |
| Xiaohongshu Slides | Intermediate — Gemini extracts data points for 5 slides | ~2,000 chars (slides + caption) |
| NotebookLM Video | Direct source material — single-speaker explainer from 30K doc | 30K (the curated doc itself) |

**Fallback behavior**: If curation fails (API error, empty result), each platform
falls back to its existing method:
- Xueqiu → raw chapter extraction via `extract_chapters()`
- Xiaohongshu → `executive_summary[:2000]` + `key_findings` + `financial_snapshot`
- Video → error raised to webapp

### Segmented Flow (Web UI)

```
ReportData (engine)
    │
    ▼
segment_splitter.py → 3-5 SegmentData per platform
    │
    ▼
segment_generator.py → mini-ReportData → existing generators
    │
    ▼
webapp/app.py → review, edit, approve in browser
    │
    ├── notebooklm.py → per-segment video generation
    └── publish → approved segments to platforms
```

### Building Blocks (External — DO NOT copy into this repo)

Publishing infrastructure lives in the **clawd-workspace** repo (`~/clawd/skills/`).
Platform generators call these as building blocks via subprocess or imports.

| Building Block | Location | Used By |
|---------------|----------|---------|
| XHS publisher | `~/clawd/skills/xiaohongshu-publish/` | platforms/xiaohongshu/ |
| XHS slides | `~/clawd/skills/xiaohongshu-slides/` | platforms/xiaohongshu/ |
| Xueqiu publisher | `~/clawd/skills/xueqiu-hottopics/` | platforms/xueqiu/ |
| X/Twitter publisher | `~/clawd/skills/x-hottopics/` | platforms/twitter/ |
| YouTube publisher | `~/clawd/skills/youtube-daily-news/` | platforms/youtube/ |
| Earnings video pipeline | `~/clawd/skills/earnings-video/` | platforms/youtube/ |
| Cover generator | `~/clawd/skills/superamy-cover/` | platforms/xiaohongshu/ |
| YouTube OAuth | `~/clawd/skills/youtube-auth/` | platforms/youtube/ |
| Social uploaders | `~/Downloads/add-caption/social_uploader/` | all platforms |

### Shared Infrastructure

| Component | Location |
|-----------|----------|
| Python venv | `~/Downloads/add-caption/venv/` |
| Stealth JS | `~/Downloads/add-caption/social_uploader/utils/stealth.min.js` |
| Logo | `~/Downloads/add-caption/assets/100bagersclub_logo.png` |
| XHS cookies | `~/clawd/skills/xiaohongshu-publish/cookies/` |
| X cookies | `~/Downloads/add-caption/social_uploader/x_uploader/x_account.json` |
| Xueqiu cookies | `~/Downloads/add-caption/social_uploader/xueqiu_uploader/xueqiu_account.json` |
| YouTube OAuth | `~/clawd/skills/youtube-auth/youtube_oauth.txt` |
| Report source | `~/Downloads/InvestView_v0/public/reports/` |

## Content Rules

- Never fabricate data — all numbers must trace back to source reports
- Never include investment advice or price targets
- Always disclose AI-generated nature where platform requires it
- Each platform has its own compliance rules in `platforms/*/config.json`

# 100 Baggers Marketing

## Project Overview

Marketing content generation and distribution system for 100Baggers.club deep research reports. Covers ideation, content creation, multi-platform publishing, analytics tracking, and iterative improvement.

## Report Source

All marketing content is derived from deep research reports located at:
```
~/Downloads/InvestView_v0/public/reports/{ticker}/index.html
```

Production site: https://www.100baggers.club/reports

## Workflow

```
ideas/backlog.md → ideas/pipeline.md → ideas/drafts/ → published/{platform}/ → analytics/ → insights.md → backlog.md
```

1. **Ideation**: New ideas go to `ideas/backlog.md`, prioritized ideas move to `pipeline.md`
2. **Production**: Drafts created in `ideas/drafts/`, using `templates/` for platform format
3. **Publishing**: Final content archived in `published/{platform}/{date}-{topic}/`
4. **Analytics**: Performance data collected in `analytics/snapshots/`, reviewed in `analytics/reports/`
5. **Improvement**: Learnings accumulated in `analytics/insights.md`, feed back into new ideas

## Platform Guidelines

### Xueqiu (雪球)
- Audience: Chinese retail investors, value-oriented
- Format: Long-form analysis posts (2000-5000 chars), with charts/tables
- Tone: Professional, data-driven, conversational
- Key: Actionable insights, contrarian angles, specific numbers

### Xiaohongshu (小红书)
- Audience: Younger Chinese investors, lifestyle-oriented
- Format: Visual cards (image + short text), 500-1000 chars
- Tone: Approachable, visual-first, educational
- Key: Eye-catching cover image, numbered takeaways, simple language

### Twitter/X
- Audience: Global investors, tech-savvy
- Format: Threads (5-15 tweets), with charts
- Tone: Concise, punchy, data-forward
- Language: English
- Key: Strong hook tweet, one insight per tweet, end with CTA

### YouTube
- Audience: Mixed, seeking deeper understanding
- Format: Video scripts (5-15 min), with visual cues
- Tone: Educational, storytelling
- Key: Hook in first 30s, clear structure, visual variety

## Content Principles

1. **Extract, don't summarize** — Pull specific unique insights from reports, not generic overviews
2. **Platform-native** — Each platform version is a standalone piece, not a cross-post
3. **Data-backed** — Every claim needs a number or source from the report
4. **Contrarian angles** — Lead with what most investors get wrong
5. **CTA to full report** — Always link back to the full report on 100baggers.club

## File Conventions

### Published Content Structure
```
published/{platform}/{YYYY-MM-DD}-{topic}/
  ├── content.md      # Final published text
  ├── assets/         # Images, charts, thumbnails
  └── meta.json       # Publish time, URL, tags, status
```

### meta.json Schema
```json
{
  "ticker": "SMCI",
  "platform": "xueqiu",
  "publishedAt": "2026-02-23T10:00:00+08:00",
  "url": "https://xueqiu.com/...",
  "tags": ["SMCI", "AI服务器", "深度研报"],
  "status": "published",
  "notes": ""
}
```

### Analytics Review Naming
- Weekly: `analytics/reports/YYYY-WNN-review.md`
- Monthly: `analytics/reports/YYYY-MM-review.md`

## Skills Reuse (CRITICAL)

This repo contains verified, battle-tested skills and components in `skills/` for publishing to each platform. **You MUST reuse these existing solutions instead of writing new ones from scratch.**

### Available Skills

| Skill | Path | Purpose |
|-------|------|---------|
| **xiaohongshu-publish** | `skills/xiaohongshu-publish/` | Video publishing to Xiaohongshu (cover generation, stealth injection, auto-upload) |
| **xiaohongshu-slides** | `skills/xiaohongshu-slides/` | Multi-image slide deck publishing to Xiaohongshu |
| **xueqiu-hottopics** | `skills/xueqiu-hottopics/` | Stock comment generation & publishing to Xueqiu |
| **youtube-auth** | `skills/youtube-auth/` | YouTube OAuth credential management |
| **youtube-daily-news** | `skills/youtube-daily-news/` | Video uploading to YouTube via API |
| **daily-newsletter** | `skills/daily-newsletter/` | Email digest extraction & NotebookLM video generation |

### Reuse Rules

1. **Always check `skills/` first** — Before building any publishing workflow, read the relevant skill's `SKILL.md` to understand what's already built.
2. **Share underlying components** — Even if you don't use a full skill end-to-end, reuse its components:
   - Cover generation → `skills/xiaohongshu-publish/generate_cover.py`
   - Stealth anti-detection → `skills/xiaohongshu-publish/inject_stealth.js`
   - XHS auto-publisher → `skills/xiaohongshu-publish/xhs_publisher.py`
   - XHS slides publisher → `skills/xiaohongshu-slides/xhs_slides_publisher.py`
   - Xueqiu comment generator → `skills/xueqiu-hottopics/xueqiu_hottopics.py`
   - YouTube uploader → `skills/youtube-daily-news/youtube_publisher.py`
   - YouTube OAuth → `skills/youtube-auth/youtube_auth.py`
   - Email fetching → `skills/daily-newsletter/fetch-emails.sh`
3. **Single source of truth** — When updating a component (e.g., stealth script, cover template, content format), update it in `skills/` so all workflows benefit from the change.
4. **Extend, don't duplicate** — If a new use case needs slight modifications, extend the existing script with parameters or configuration rather than copying and modifying it.
5. **New skills go to `skills/`** — Any new platform automation or reusable workflow must be added as a skill with its own `SKILL.md`.

### Shared Infrastructure

| Component | Location | Used By |
|-----------|----------|---------|
| Python venv | `~/Downloads/add-caption/venv/` | All Python scripts |
| Stealth JS | `~/Downloads/add-caption/social_uploader/utils/stealth.min.js` | XHS publisher |
| Logo | `~/Downloads/add-caption/assets/100bagersclub_logo.png` | Cover generation, video watermark |
| XHS cookies | `skills/xiaohongshu-publish/cookies/` | XHS publisher, slides publisher |
| YouTube OAuth | `skills/youtube-auth/youtube_oauth.txt` | YouTube publisher |

## Rules

- Never fabricate data — all numbers must trace back to source reports
- Never include investment advice or price targets in marketing content
- Always disclose AI-generated nature where platform requires it
- Track every published piece in the corresponding platform folder
- Review analytics weekly, record insights immediately
- **Reuse existing skills and components** — never start from scratch when a solution exists in `skills/`

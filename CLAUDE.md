# clawd-workspace

Workspace for 100Baggers.club automation: content marketing, platform publishing, and daily workflows.

## Repository Structure

```
clawd-workspace/
├── skills/            # Shared infrastructure — verified publishing tools
├── marketing/         # Content marketing — ideation, publishing, analytics
└── newsletters/       # Daily newsletter digests
```

- **`skills/`** is the tool layer — reusable, battle-tested scripts for each platform
- **`marketing/`** and **`newsletters/`** are business layers that consume skills

## Skills Reuse (CRITICAL)

**Always use existing skills and their components. Never start from scratch when a solution exists in `skills/`.**

### Available Skills

| Skill | Path | Purpose |
|-------|------|---------|
| **xiaohongshu-publish** | `skills/xiaohongshu-publish/` | Video publishing to Xiaohongshu (cover gen, stealth, auto-upload) |
| **xiaohongshu-slides** | `skills/xiaohongshu-slides/` | Multi-image slide deck publishing to Xiaohongshu |
| **xueqiu-hottopics** | `skills/xueqiu-hottopics/` | Stock comment generation & publishing to Xueqiu |
| **youtube-auth** | `skills/youtube-auth/` | YouTube OAuth credential management |
| **youtube-daily-news** | `skills/youtube-daily-news/` | Video uploading to YouTube via API |
| **daily-newsletter** | `skills/daily-newsletter/` | Email digest extraction & NotebookLM video generation |

### Reuse Rules

1. **Check `skills/` first** — Before building any workflow, read the relevant `SKILL.md`.
2. **Share components** — Reuse existing scripts even if you don't use a full skill end-to-end:
   - Cover generation → `skills/xiaohongshu-publish/generate_cover.py`
   - Stealth anti-detection → `skills/xiaohongshu-publish/inject_stealth.js`
   - XHS publisher → `skills/xiaohongshu-publish/xhs_publisher.py`
   - XHS slides → `skills/xiaohongshu-slides/xhs_slides_publisher.py`
   - Xueqiu comments → `skills/xueqiu-hottopics/xueqiu_hottopics.py`
   - YouTube uploader → `skills/youtube-daily-news/youtube_publisher.py`
   - YouTube OAuth → `skills/youtube-auth/youtube_auth.py`
   - Email fetching → `skills/daily-newsletter/fetch-emails.sh`
3. **Single source of truth** — Update components in `skills/`, all consumers benefit.
4. **Extend, don't duplicate** — Add parameters/config to existing scripts rather than copying.
5. **New tools → `skills/`** — Any new platform automation must be added as a skill with its own `SKILL.md`.

### Shared Infrastructure

| Component | Location |
|-----------|----------|
| Python venv | `~/Downloads/add-caption/venv/` |
| Stealth JS | `~/Downloads/add-caption/social_uploader/utils/stealth.min.js` |
| Logo | `~/Downloads/add-caption/assets/100bagersclub_logo.png` |
| XHS cookies | `skills/xiaohongshu-publish/cookies/` |
| YouTube OAuth | `skills/youtube-auth/youtube_oauth.txt` |

## Content Rules

- Never fabricate data — all numbers must trace back to source
- Never include investment advice or price targets
- Always disclose AI-generated nature where platform requires it
- Reuse existing skills and components — never start from scratch

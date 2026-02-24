# 100 Baggers Marketing

Editorial pipeline and analytics for 100Baggers.club deep research reports.

## Report Source

All content is derived from deep research reports located at:
```
~/Downloads/InvestView_v0/public/reports/{ticker}/
```

Production site: https://www.100baggers.club/reports

## Workflow

```
ideas/backlog.md → ideas/pipeline.md → platforms/*/generate.py → platforms/*/archive/ → analytics/
```

1. **Ideation**: New ideas go to `ideas/backlog.md`, prioritized ideas move to `pipeline.md`
2. **Generation**: `python orchestrate.py TICKER` generates content for all platforms
3. **Review**: Generated content saved in `platforms/*/archive/{ticker}/` for review
4. **Publishing**: `python orchestrate.py TICKER --publish` to go live
5. **Analytics**: Performance data tracked in `analytics/`

## Platform Guidelines

### Xueqiu (雪球)
- Audience: Chinese retail investors, value-oriented
- Format: Long-form analysis (2000-5000 chars), with data tables
- Tone: Professional, data-driven, contrarian angles
- Generator: `platforms/xueqiu/generate.py`

### Xiaohongshu (小红书)
- Audience: Younger Chinese investors, lifestyle-oriented
- Format: 5 visual slides + 500-1000 char caption
- Tone: Approachable, educational, visual-first
- Generator: `platforms/xiaohongshu/generate.py`

### Twitter/X
- Audience: Global investors, tech-savvy
- Format: Single long-form post (300-500 words)
- Tone: Conversational, data-forward, English only
- Generator: `platforms/twitter/generate.py`

### YouTube
- Audience: Mixed, seeking deeper understanding
- Format: Content brief for NotebookLM (800-2000 words) + short description (~100 words)
- Tone: Educational, analytical
- Generator: `platforms/youtube/generate.py`

## Content Principles

1. **Extract, don't summarize** — Pull specific unique insights, not generic overviews
2. **Platform-native** — Each version is standalone, not a cross-post
3. **Data-backed** — Every claim needs a number from the report
4. **Contrarian angles** — Lead with what most investors get wrong
5. **CTA to full report** — Always link back to 100baggers.club

## Rules

- Never fabricate data — all numbers must trace back to source reports
- Never include investment advice or price targets in marketing content
- Always disclose AI-generated nature where platform requires it
- Review generated content before publishing — AI output needs human QA

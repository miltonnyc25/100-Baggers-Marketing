# Xiaohongshu (小红书) — Slide Decks + Captions

## Pipeline

```
Raw Report (ReportData from engine)
        |
  Gemini AI (prompt.md)
  - Generates: title (<=20 chars), 5 slides, caption (500-1000 chars)
  - Compliance: sensitive topic filter, attribution prefix, disclaimer
        |
  Evaluate Loop (up to 3 rounds)
        |
  Output: Markdown file with title, slides, caption, hashtags
```

**Fallback**: Template-based generation when AI is unavailable.

## Output Files

```
archive/{ticker}/
  {ticker}_xiaohongshu.md   # Title + slides + caption
```

## CLI

```bash
# Generate via orchestrator
python orchestrate.py PLTR --platforms xiaohongshu
```

## Key Files

| File | Purpose |
|------|---------|
| `generate.py` | Main generator (AI + template fallback) |
| `prompt.md` | Gemini prompt template |
| `config.json` | Platform config (char limits, hashtags, compliance) |
| `publish.py` | Publish to Xiaohongshu via browser automation |
| `render_slides.py` | Render slides to images |
| `templates/` | Slide templates |

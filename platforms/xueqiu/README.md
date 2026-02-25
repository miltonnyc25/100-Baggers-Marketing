# Xueqiu (雪球) — Long-Form Analysis Posts

## Pipeline

```
Raw Report (.md/.html, 50K-500K chars)
        |
  Stage 1: Strategist (Gemini)
  - Reads full report
  - Selects 1-3 post angles with max "cognitive delta"
  - Picks specific chapters + chart recommendations
        |
  Stage 2: Writer (Gemini, per post)
  - Receives strategist-selected chapters + directives
  - Writes post following prompt.md (30+ data points, probability framework)
        |
  Evaluate Loop (up to 5 rounds)
  - Gemini evaluator scores quality, compliance, data density
  - Rewrite instructions on failure
        |
  Content Filter
  - Strips Mermaid/code blocks, price targets, markdown formatting
        |
  Output: 6000-8000 char Chinese post(s)
```

**Fallback chain**: two-stage → single-stage (if strategist fails) → template (if no API key).

## Output Files

```
archive/{ticker}/
  {TICKER}-xueqiu-{date}.html   # Rich text (with copy-to-clipboard command)
  {TICKER}-xueqiu-{date}.txt    # Plain text
  strategy.json                  # Strategist decisions (angles, chapters, charts)
  chart-*.png                    # Chart screenshots (if available)
```

## CLI

```bash
# Generate for a ticker (primary two-stage path)
python platforms/xueqiu/generate.py pltr --save

# Force single-stage (skip strategist)
python platforms/xueqiu/generate.py pltr --save --single

# Copy to clipboard (macOS)
python platforms/xueqiu/generate.py pltr --save --copy
```

## Key Files

| File | Purpose |
|------|---------|
| `generate.py` | Main generator (strategist + writer + eval loop) |
| `prompt.md` | Writer prompt template |
| `strategist_prompt.md` | Strategist prompt (angle selection, chapter mapping) |
| `template.md` | Template fallback (no API needed) |
| `config.json` | Platform config (char limits, compliance rules) |
| `publish.py` | Publish to Xueqiu via browser automation |

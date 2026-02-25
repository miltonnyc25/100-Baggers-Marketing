# X/Twitter — English Long & Short Posts

## Pipeline

```
Xueqiu archive/{ticker}/*.html (already generated Chinese post)
        |
  strip_html_to_text()
        |
  Long Post: Translate Chinese → English (Gemini)
  - Faithful translation via long_prompt.md
  - Preserves all data points, arguments, analytical framework
  - Evaluate loop (word count + AI-word check + Gemini evaluator)
  - Output: 1500-2500 words
        |
  Short Post: Distill from English long post (Gemini)
  - Selects most attention-grabbing insight from long post
  - Writes in punchy fintwit voice via short_prompt.md
  - Evaluate loop (word count + AI-word check + Gemini evaluator)
  - Output: 200-300 words
```

**Dependency**: Xueqiu must be generated first. If no Xueqiu output exists, falls back to legacy raw-report path (prompt.md).

## Output Files

```
archive/{ticker}/
  {TICKER}-twitter-long-{date}.html    # Long post (rich text with copy command)
  {TICKER}-twitter-long-{date}.txt     # Long post (plain text)
  {TICKER}-twitter-short-{date}.html   # Short post (rich text)
  {TICKER}-twitter-short-{date}.txt    # Short post (plain text)
```

## CLI

```bash
# Generate both long + short posts
python platforms/twitter/generate.py pltr --save

# Long post only
python platforms/twitter/generate.py pltr --save --long-only

# Short post only (still generates long first as intermediate)
python platforms/twitter/generate.py pltr --save --short-only

# Copy long post to clipboard (macOS)
python platforms/twitter/generate.py pltr --save --copy

# Force legacy path (raw report, no Xueqiu dependency)
python platforms/twitter/generate.py pltr --save --legacy
```

## Key Files

| File | Purpose |
|------|---------|
| `generate.py` | Main generator (translate + distill + eval loop) |
| `long_prompt.md` | Translation prompt (Chinese → English) |
| `short_prompt.md` | Distillation prompt (long post → short post) |
| `prompt.md` | Legacy fallback prompt (raw report → single post) |
| `config.json` | Platform config (word limits, compliance rules) |
| `publish.py` | Publish to X via browser automation |

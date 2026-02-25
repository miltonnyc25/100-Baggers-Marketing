# YouTube — Video Scripts + Descriptions

## Pipeline

```
Raw Report (ReportData from engine)
        |
  Gemini AI (prompt.md)
  - Generates: title, description, video script, tags, timestamps
  - Script length: 5-15 minutes
  - Compliance: disclaimer, attribution
        |
  Evaluate Loop (up to 3 rounds)
        |
  Output: Directory with script, description, metadata files
```

Note: This generator only produces scripts. Video rendering is a separate step handled by external tools.

## Output Files

```
archive/{ticker}/
  script.md        # Video script
  description.md   # YouTube description
  metadata.json    # Title, tags, timestamps
```

## CLI

```bash
# Generate via orchestrator
python orchestrate.py PLTR --platforms youtube

# Direct CLI
python platforms/youtube/generate.py PLTR
```

## Key Files

| File | Purpose |
|------|---------|
| `generate.py` | Main generator (AI + eval loop) |
| `prompt.md` | Gemini prompt template |
| `config.json` | Platform config (script length, compliance) |
| `publish.py` | Publish to YouTube via OAuth |

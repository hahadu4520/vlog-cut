---
name: video-asset-index
description: Use when the user has a folder of raw video clips and needs them indexed for narration-driven cutting — probes metadata, samples 3 keyframes per clip, builds one horizontal contact sheet per clip, and emits assets_index.json. Triggers on "整理素材 / 看素材 / 给素材打标 / build asset index". Two modes: deterministic-only (default — Claude reads the sheets and fills tags) or --describe api (calls Anthropic vision to auto-tag).
---

# video-asset-index

## What this does

For every clip in a source folder:

1. `ffprobe` → width, height, duration, fps, rotation, orientation
2. Extract 3 keyframes (at 1/4, 2/4, 3/4 of the clip)
3. Stack the 3 frames horizontally into one contact sheet (`sheets/<stem>.jpg`) — so Claude can review one whole clip per Read tool call
4. Optionally: call Anthropic vision API to auto-fill `scene` / `description` / `tags` / `usable`
5. Emit `assets_index.json` matching `shared/schemas/assets_index.schema.json`

## When to use

Trigger when the user:
- has a folder of source clips that need cataloguing before cutting
- says "看一下素材 / 整理素材库 / 给视频打标签 / index my clips"
- is about to plan a timeline and Claude needs `assets_index.json` to choose shots from

Skip when:
- an `assets_index.json` already exists and the user doesn't want to re-index (use `--force` only if they ask)
- the user just wants to look at one clip — use `ffprobe` directly

## How to call

```bash
# Default: probe + frames + sheets only. Claude fills tags by hand.
vlog-cut-index --src /path/to/clips --out /path/to/project_dir

# With Claude vision auto-tagging:
vlog-cut-index --src /path/to/clips --out /path/to/project_dir --describe api
```

Optional:
- `--model claude-sonnet-4-5` — vision model (or set `VISION_MODEL` env)
- `--workers 4` — vision API concurrency
- `--force` — ignore cached records and rerun
- `--frame-width 480` / `--sheet-width 400` — frame sizes

The default mode does NOT call any API and is free / offline. Vision auto-tagging is opt-in.

## Outputs

```
<out>/
├── frames/
│   ├── clip_a_f0.jpg  clip_a_f1.jpg  clip_a_f2.jpg
│   └── clip_b_f0.jpg  ...
├── sheets/
│   ├── clip_a.jpg     ← 3 frames stacked horizontally
│   └── clip_b.jpg
└── assets_index.json
```

## How Claude should fill tags (default mode, no API)

After this skill runs:

1. Read `assets_index.json` — see which clips lack `scene` / `tags`
2. For each one, Read its `<out>/sheets/<stem>.jpg` — that's all 3 keyframes in one image
3. Add `scene` (≤20 chars), `description` (≤60 chars), `tags`, `usable`, optionally `chapters` and `highlight`
4. Save back to `assets_index.json`

The schema is in `shared/schemas/assets_index.schema.json`. Stick to it — `narration-cut` reads these fields.

## Idempotency / resume

If `assets_index.json` already exists, records keyed by `file` are reused. Only clips missing from the index (or with an `error`) are re-processed. Pass `--force` to re-do everything. Frames and sheets are cached on disk — they're only re-extracted if missing.

## Checkpoint (when called from vlog-cut-pipeline)

After this skill returns + Claude finishes any tagging pass, **stop and ask the user to spot-check**: are clips marked `usable: false` actually unusable? Do the `chapters` (section ids) match the script? This is the cheap moment to fix tagging mistakes — getting it wrong here means bad shot picks in the timeline.

## Dependencies

- `ffmpeg` / `ffprobe` on PATH
- `anthropic` Python SDK only when `--describe api` is used (`pip install anthropic`)
- `ANTHROPIC_API_KEY` env var only when `--describe api` is used

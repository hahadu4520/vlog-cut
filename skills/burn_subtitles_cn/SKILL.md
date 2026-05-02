---
name: burn-subtitles-cn
description: Use when the user wants Chinese subtitles burned into a finished rough cut. Three CLIs — split (timing.json → paged subs_pages.json), build (subs_pages.json → ASS), burn (mp4 + ASS → mp4 with hard-burnt subs). Triggers on "加字幕 / 烧字幕 / burn subtitles / add Chinese subs". Designed for ≤12-char per-page Chinese subtitles with punctuation-priority line breaks.
---

# burn-subtitles-cn

Three CLIs, used in sequence. Each is fine to call alone too.

| step | CLI | input | output |
|------|-----|-------|--------|
| split | `vlog-cut-subs-split`  | `timing.json` | `subs_pages.json` |
| build | `vlog-cut-subs-build`  | `subs_pages.json` | `subtitles.ass` |
| burn  | `vlog-cut-subs-burn`   | mp4 + .ass | `<name>_subs.mp4` |

## When to use

Trigger on:
- "加字幕 / 烧字幕 / 把字幕烧上去 / 出带字幕的版本"
- "burn subtitles / add Chinese subs / hard-coded subs"
- the user has a finished rough_cut.mp4 + the timing.json that produced it

Skip when:
- the user wants soft subs they can toggle in players → just hand them the .ass + mp4 separately (use `subs-build` only, skip `subs-burn`)
- the language isn't Chinese — the splitting heuristic (≤12 chars, Chinese punctuation priority) is tuned for CJK

## Step 1 — split (paginate)

```bash
vlog-cut-subs-split \
  --timing  <project_dir>/timing.json \
  --out     <project_dir>/subs_pages.json \
  --max-chars 12
```

Algorithm: greedy scan from the start of each line, find the strongest available break point (`。！？；——` → `，、：` → space) within the next N chars; otherwise hard-cut at N. Each page strips leading/trailing punctuation. Page durations are interpolated from the line's `start`/`end` by character-count fraction.

Optional:
- `--max-chars 12` — characters per page (default 12, fits comfortably on 1080p with size 56 font)
- `--keep-together <path>` — file with whitespace-separated 2-char bigrams that must NOT split across pages (e.g. proper nouns). One file per project.
- `--script <path>` — script.json with sections containing punctuated `lines[]`. For each timing line whose `section` matches, the splitter replaces the timing's text with the script's punctuated version (joined by `，`). Timestamps are unchanged. **Use this when timing.json came from `align-narration`** — whisper's Chinese transcription strips punctuation, so without `--script` the splitter has no soft-break anchors and is forced into hard-cuts every 12 chars (e.g. "AI" + "时代码"). With `--script`, it can break at commas / periods you wrote.

The output matches `shared/schemas/subs_pages.schema.json`.

### text-source rule of thumb

- driven from `tts-from-script` → timing.json already has the script's punctuated text → no `--script` needed
- driven from `align-narration` → timing.json has whisper's no-punct text → **always pass `--script`** to recover splits at natural break points

If a section in timing.json doesn't match anything in `--script`, the splitter prints a WARN and keeps the original text for that section.

## Step 2 — build (paged JSON → ASS)

```bash
vlog-cut-subs-build \
  --pages <project_dir>/subs_pages.json \
  --out   <project_dir>/subtitles.ass
```

Optional style flags (sensible defaults match a 1080p vlog):
- `--size 1920x1080`
- `--font "LXGW WenKai"` — open-source 楷体 with a hand-written feel, looks more personal than the macOS default 宋体 (Songti SC). Install via `brew install --cask font-lxgw-wenkai` (see README's font section for the full set we recommend).
- `--font-size 56`
- `--margin-v 80` — distance from bottom in px
- `--outline 2` — black outline around the white text
- `--shadow 1.5`
- `--fade-ms 80` — per-page fade-in/out (0 = no fade)

For vertical 9:16 video, drop `--size 1080x1920 --font-size 64 --margin-v 200`.

### Recommended fonts

All four ship as Homebrew casks — `brew install --cask <name>` and pass the family name to `--font`:

| Family name (`--font`)  | Cask | Style |
|---|---|---|
| `LXGW WenKai`           | `font-lxgw-wenkai`         | hand-written 楷体 — gentle, personal (default) |
| `LXGW Marker Gothic`    | `font-lxgw-marker-gothic`  | marker-pen handwriting — friendly, casual |
| `Smiley Sans`           | `font-smiley-sans`         | rounded oblique — modern, media-style |
| `Ma Shan Zheng`         | `font-ma-shan-zheng`       | brush calligraphy — artistic but heavier to read |

If `--font` names a family libass can't find, it falls back to whatever fontconfig picks — usually a system Sans. Pass the family name (left column) exactly, including the space.

### --video (recommended): auto-detect letterbox + auto-fit font

When the underlying video has letterbox/pillarbox black bars (e.g. portrait
clips inside a 1920x1080 horizontal canvas), subtitles by default span the
full canvas width and their tails spill into the bars — reads as "missing
characters" to viewers who focus on the inner content.

**Just pass `--video <mp4>`.** Build will:

1. Run ffmpeg `cropdetect` on the video to find the narrowest content
   rectangle across all frames
2. Apply an 18% **title-safe** padding (default `--safe-ratio 0.82`, matching
   the broadcast convention — tight margins look cramped even when text
   technically doesn't overflow)
3. Auto-shrink `--font-size` so every subtitle page fits inside that budget
4. If anything still overflows after fitting, print a `WARN` with the
   offending pages

This is the recommended path. No manual safe-width math.

```bash
vlog-cut-subs-build \
  --pages   <out>/subs_pages.json \
  --video   <out>/rough_cut.mp4 \
  --out     <out>/subtitles.ass
```

### Manual overrides

- `--safe-width <px>` — explicit width budget. Overrides cropdetect AND
  bypasses `--safe-ratio` (use this exact pixel count). Use when `--video`
  isn't around or cropdetect picks a wrong rectangle.
- `--safe-ratio <0..1>` — fraction of detected content width subtitles may
  occupy (default 0.82). Lower for more breathing room (e.g. 0.7), higher
  if content edges are forgiving (e.g. 0.95). Only applies to cropdetect-
  derived widths — `--safe-width` is taken literally.
- `--no-auto-fit` — only WARN about overflow, don't auto-shrink. Useful if
  you want to manually decide between lowering font-size vs. lowering
  `--max-chars` in `subs-split`.

### How the heuristic works

The text-width estimator inside build assumes Chinese chars ≈ 1.0 ×
font-size, ASCII ≈ 0.55 × font-size. libass does the actual layout — the
heuristic is a leading indicator, not a precise measurement. The 5%
auto-margin on top of cropdetect's content width accounts for slight
underestimation. If you still see overflow in the rendered mp4 that the
build-time warning didn't catch, pass `--safe-width` ~10% lower than the
detected content width.

## Step 3 — burn (composite onto video)

```bash
vlog-cut-subs-burn \
  --video <project_dir>/rough_cut.mp4 \
  --subs  <project_dir>/subtitles.ass \
  --out   <project_dir>/rough_cut_subs.mp4
```

Optional:
- `--crf 20` — x264 quality (lower = better quality, larger file)
- `--preset veryfast` — speed/quality tradeoff (see ffmpeg docs)

Audio is stream-copied (no re-encode). Video is re-encoded once with the subtitles burned into the pixels — there's no toggle-off in players.

## Iteration workflow

If the user wants to adjust subtitle text (typos, line breaks):
1. Edit `subs_pages.json` directly (it's a JSON list with per-page text).
2. Re-run `subs-build` (instant — pure text op).
3. Re-run `subs-burn` (slow — full re-encode).

If the user wants different style (font / size / position):
1. Skip `subs-split`, skip `subs-pages.json` edits.
2. Re-run `subs-build` with new style flags.
3. Re-run `subs-burn`.

## Checkpoint (when called from vlog-cut-pipeline)

After `subs-build` (before `subs-burn`), **stop and ask the user to spot-check `subs_pages.json`**. Common issues:
- punctuation-aware splitter cut a proper noun in two ("阿勒" + "泰") → add it to a `--keep-together` file and re-split
- a page is awkwardly long (one big line ran past 12 chars on a punct-free stretch) → bump `--max-chars` or break the source `timing.json` line

After `subs-burn`, **stop and ask the user to watch the mp4** (checkpoint 4 in the pipeline becomes "subs preview approved", which is `state.checkpoints.subs_preview_approved`).

## Why this is its own skill (not part of narration-cut)

- runs after the rough cut is approved, so it's gated behind a separate user decision ("do you want subtitles at all?")
- has its own iteration loop (style tweaks don't require re-rendering the video timeline)
- if the user has an existing mp4 + timing.json from elsewhere, this skill works standalone

## Dependencies

- `ffmpeg` / `ffprobe` on PATH (libass-enabled build, which Homebrew's `ffmpeg` is by default)
- A Chinese font installed for `--font`. Default is `LXGW WenKai`; install with `brew install --cask font-lxgw-wenkai`. See "Recommended fonts" above for alternatives. Without a matching font, libass falls back to whatever fontconfig picks (usually system Sans) — usable but not pretty.
- no Python deps beyond stdlib

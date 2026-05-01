---
name: narration-cut
description: Use when narration audio (timing.json + narration.wav) and an indexed asset pool (assets_index.json) exist, and the user wants a rough cut. Three sub-tools — plan (draft a timeline), validate (check it before render), render (cut + concat + mux into mp4). Triggers on "对齐镜头 / 排时间线 / 出粗剪 / cut to narration / build timeline". Plan is a deterministic baseline; Claude usually rewrites timeline.json by hand before render.
---

# narration-cut

Three CLIs, used in sequence. Each is also fine to call alone.

| step | CLI | what it does |
|------|-----|--------------|
| plan | `vlog-cut-plan` | timing + assets → draft timeline.json (algorithmic) |
| validate | `vlog-cut-validate` | structural + temporal sanity check on timeline.json |
| render | `vlog-cut-render` | timeline + narration → rough_cut.mp4 |

## When to use

Trigger on:
- "对齐镜头 / 排时间线 / 出粗剪"
- "cut to narration / build timeline / render the rough cut"
- the user has both `timing.json` and `assets_index.json` and wants a video

Skip when:
- either timing or assets index is missing — go back to `tts-from-script` or `video-asset-index`
- the user wants subtitles only — that's `burn-subtitles-cn` (v0.2)

## Step 1 — plan (draft a timeline)

```bash
vlog-cut-plan \
  --timing  <out>/timing.json \
  --assets  <out>/assets_index.json \
  --out     <out>/timeline.json \
  --size    1920x1080 \
  --fps     30
```

The algorithm scores clips by `chapters` match, tag overlap with the section, `highlight` bonus, and a "already used" penalty for variety. It's a starting point, not a final answer.

**The expected workflow is**: Claude reads `timeline.json`, opens the relevant `sheets/<stem>.jpg` for any shot it's unsure about, then **rewrites timeline.json by hand** to swap in better picks. This is a checkpoint — don't render until the user has signed off.

## Step 2 — validate (before you render)

```bash
vlog-cut-validate \
  --timeline <out>/timeline.json \
  --src      <clips_folder> \
  --timing   <out>/timing.json   # optional but recommended
```

Catches:
- missing source clips
- `in + dur` exceeding source duration
- shots not covering line audio (video would end first)
- duplicate / mismatched line ids

Exit code: 0 = clean, 1 = warnings only, 2 = errors. Don't render on exit 2.

## Step 3 — render (make the mp4)

```bash
vlog-cut-render \
  --timeline  <out>/timeline.json \
  --timing    <out>/timing.json \
  --src       <clips_folder> \
  --narration <out>/narration.wav \
  --out       <out> \
  --name      rough_cut.mp4
```

Optional:
- `--size 1920x1080` — override timeline.size
- `--fps 30` — override timeline.fps
- `--name xxx.mp4` — output filename

Outputs:
```
<out>/
├── segs/        ← per-shot mp4 (cached on rerun)
├── video_silent.mp4
└── rough_cut.mp4
```

The render absorbs gap silences into the *last shot of each line*: if the source has room, `dur` is extended; otherwise the last frame is held (`tpad`). Result: the video stays populated through every silence.

## Idempotency

`segs/<idx>_<lid>_<stem>.mp4` is reused if it exists. To force a re-render of a single shot, delete that file. To force the whole video, delete `segs/`.

## Checkpoint (when called from vlog-cut-pipeline)

Two checkpoints land in this skill:

1. **after plan** — `timeline_drafted` → ask the user to approve the picks (or let Claude refine first, then approve)
2. **after render** — `rough_cut_rendered` → ask the user to watch `rough_cut.mp4`

Don't proceed until both are approved.

## Dependencies

- `ffmpeg` / `ffprobe` on PATH
- no Python deps beyond stdlib

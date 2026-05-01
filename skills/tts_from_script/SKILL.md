---
name: tts-from-script
description: Use when the user has a narration script (script.json) and needs voiceover audio plus per-line timing data — synthesizes each line with edge-tts, probes durations, and writes timing.json + a merged narration.wav. Triggers on "做配音 / TTS / 文案配音 / 生成口播". Skip when the user already has their own narration audio (then use align-narration instead, planned for v0.4).
---

# tts-from-script

## What this does

Turns a `script.json` (see `shared/schemas/script.schema.json`) into:

- `<out>/tts/<id>.mp3` — one MP3 per line, id = `<section_id>_<line_idx:02>`
- `<out>/timing.json` — Timing data (per-line `start` / `end` / `duration`, plus `total_duration`)
- `<out>/narration.wav` — single merged audio track with line / section silences inserted

The Timing JSON is the contract every downstream skill reads.

## When to use

Trigger when the user:
- has finished writing the narration and wants voiceover
- says "make TTS / 配音 / 口播 / 生成 narration"
- needs a `timing.json` to feed into `narration-cut` or future `burn-subtitles-cn`

Do NOT use when:
- the user already has their own recorded voiceover — that path is `align-narration` (v0.4, not yet built)
- the user only wants to test a voice — point them at `edge-tts --list-voices` directly

## How to call

```bash
vlog-cut-tts --script /path/to/script.json --out /path/to/project_dir
```

Optional:
- `--gap-line 0.25` — override per-line silence
- `--gap-section 0.6` — override per-section silence

Defaults come from the script file (`gap_line_sec`, `gap_section_sec`), then fall back to 0.25 / 0.6.

## Inputs (script.json)

```json
{
  "voice": "zh-CN-XiaoyiNeural",
  "rate": "-5%",
  "gap_line_sec": 0.25,
  "gap_section_sec": 0.6,
  "sections": [
    { "id": "intro", "title": "引子", "lines": ["第一句。", "第二句。"] },
    { "id": "body",  "title": "正片", "lines": ["第三句。"] }
  ]
}
```

## Outputs

```
<out>/
├── tts/
│   ├── intro_00.mp3
│   ├── intro_01.mp3
│   └── body_00.mp3
├── timing.json
└── narration.wav
```

`timing.json` matches `shared/schemas/timing.schema.json`. Each line carries `start`/`end` measured against the merged narration, so downstream tools can align cuts without re-probing.

## Checkpoint (when called from vlog-cut-pipeline)

After this skill returns, **stop and ask the user to listen to `narration.wav`**. Common reasons to re-run:

- voice / rate sounds wrong → edit `script.json`, rerun
- a line has a wrong word or weird pronunciation → edit that line's text, rerun (cached MP3s only re-synth for changed lines if the file is missing — to force a re-synth, delete that one MP3)

Mark `state.checkpoints.narration_approved = true` before continuing.

## Idempotency

If an MP3 already exists for a given line id, it is reused (no re-synth). Delete the file to force regeneration. `timing.json` and `narration.wav` are always rewritten.

## Dependencies

- `edge-tts` (Python, listed in `pyproject.toml`)
- `ffmpeg` / `ffprobe` on PATH (used to probe durations and build the merged WAV)

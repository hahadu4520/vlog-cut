---
name: align-narration
description: Use when the user has their OWN narration audio (m4a/mp3/wav) and needs the same timing.json + narration.wav that tts-from-script would emit. Calls whisper to transcribe, then groups segments into one line per section (using each section's optional `head_text` anchor in script.json). Triggers on "我自己录了配音 / 自带口播 / align my narration / 我有现成的录音". This is the v0.4 alternative to tts-from-script.
---

# align-narration

## What this does

Takes a user-recorded narration audio file and produces:

- `<out>/narration.wav` — the audio re-encoded to canonical mono 24kHz PCM WAV (same format `tts-from-script` emits, so `narration-cut.render` doesn't have to special-case)
- `<out>/timing.json` — Timing data (per-line `start` / `end` / `duration` + `total_duration`), matching `shared/schemas/timing.schema.json`
- `<out>/whisper/<stem>.json` — raw whisper output, cached for reruns

## When to use

Trigger when the user says:
- "我自己录了配音" / "我有现成的口播" / "用我自己录的"
- "align my narration" / "I already have audio"
- they drop an `.m4a` / `.mp3` / `.wav` into the project folder instead of asking for TTS

Skip when:
- the user wants TTS — that's `tts-from-script`
- the user only wants a transcript (no timing alignment) — call `whisper` directly

## How to call

**Minimum-friction (no script):**
```bash
vlog-cut-align --audio /path/to/口播.m4a --out /path/to/project_dir
```
Produces a single line `narration_00` covering the whole audio. The downstream timeline plan/render then chooses shots for that one giant line. Works but loses per-section structure.

**With section alignment (recommended):**
```bash
vlog-cut-align \
  --audio /path/to/口播.m4a \
  --script /path/to/script.json \
  --out /path/to/project_dir
```

The `script.json` must include, for each section, a `head_text` field — the first few characters of that section as actually spoken. align uses `head_text` to find each section's start in the recording.

```json
{
  "voice": "user-recorded",
  "rate": "+0%",
  "sections": [
    { "id": "intro",  "title": "钩子",   "head_text": "AI越好用",    "lines": [...] },
    { "id": "scene",  "title": "场景",   "head_text": "写代码",       "lines": [...] },
    { "id": "reason", "title": "道理",   "head_text": "对着屏幕",     "lines": [...] },
    { "id": "outro",  "title": "收尾",   "head_text": "散步当正经事", "lines": [...] }
  ]
}
```

If a section is missing `head_text`, align falls back to equal-fraction splitting (audio_dur × section_idx / n_sections) and prints a warning. Iterate by adding anchors as you review the output.

## Optional flags

- `--engine whisperx` — use word-level forced alignment (more accurate). Falls back to `whisper` with a warning if whisperx not installed.
- `--model large-v3-turbo` — whisper model (default; for Chinese, large-v3-turbo is the sweet spot for speed × quality)
- `--language Chinese` — whisper `--language` (default Chinese)

## Caching

`<out>/whisper/<audio_stem>.json` is cached. If you re-run with the same audio (e.g. to retry section grouping with a different `script.json`), whisper isn't called again. To force re-transcription, delete that file.

`narration.wav` is also cached — delete it to re-encode.

## Checkpoint (when called from vlog-cut-pipeline)

After this skill returns, **stop and ask the user to spot-check `timing.json`**. Common issues:

- a section's `head_text` failed to match → that section's start is wrong → review the WARN lines align printed
- whisper misheard a word → the `text` field looks wrong, but the timestamps are still usable; only fix if you'll burn subtitles later
- audio has a long opening gap before the first word → first line's `start > 0` is fine

Mark `state.checkpoints.narration_approved = true` once the user confirms.

## How it differs from tts-from-script

| | tts-from-script | align-narration |
|---|---|---|
| input | text in script.json | recorded audio (any format) |
| output | per-line MP3s + merged WAV + timing | single canonical WAV + timing |
| line granularity | every script line gets its own MP3+timestamps | one timing line per section (coarser) |
| iteration cost | edit script line, delete that MP3, rerun (only that line re-synths) | edit head_text or re-record audio, rerun (whisper cached) |
| voice control | edge-tts voices/rates | whatever you sound like |

## Dependencies

- `ffmpeg` / `ffprobe` on PATH (re-encode audio, probe duration)
- `whisper` CLI on PATH (`pip install openai-whisper` — adds ~3GB of PyTorch + a one-time model download)
- optional: `whisperx` for word-level alignment

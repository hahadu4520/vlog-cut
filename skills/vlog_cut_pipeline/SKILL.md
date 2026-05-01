---
name: vlog-cut-pipeline
description: Use when the user wants to take a script + a folder of raw clips all the way to a finished rough cut. Orchestrates tts-from-script → video-asset-index → narration-cut (plan / validate / render), with FOUR mandatory human-review checkpoints between stages. Triggers on "做视频 / 剪个视频 / 把这段文案做成视频 / make a video from this script". Do NOT bypass the checkpoints — Claude pauses, the user approves, then the next stage runs. State is tracked in <project_dir>/.vlog-cut/state.json.
---

# vlog-cut-pipeline

Top-level orchestration. **Stop and ask for approval at every checkpoint** — that's the whole point of this pipeline.

## When to use

The user gives you:
- a narration script (text or `script.json`)
- a folder of raw video clips
- a project directory to put outputs in

…and wants a rough-cut mp4 at the end.

If they only need *one* stage, call the underlying skill directly instead.

## High-level flow

```
script.json ── tts-from-script ──▶ timing.json + narration.wav
                                              │
                            🔴 CHECKPOINT 1 — listen to narration.wav
                                              │
clips/      ── video-asset-index ──▶ assets_index.json + sheets/
                                              │
                            🔴 CHECKPOINT 2 — spot-check tags & usable
                                              │
        narration-cut.plan  ──────▶ timeline.json (draft)
        Claude refines by reading sheets ──▶ timeline.json (final)
        narration-cut.validate ─▶ exit 0 required
                                              │
                            🔴 CHECKPOINT 3 — review timeline.json
                                              │
        narration-cut.render  ────▶ rough_cut.mp4
                                              │
                            🔴 CHECKPOINT 4 — watch rough_cut.mp4
                                              │
                                            done
```

## State file

Maintain `<project_dir>/.vlog-cut/state.json` matching `shared/schemas/state.schema.json`. Update `stage`, `outputs.*` paths, and `checkpoints.*` flags as you go. Read it at every entry to know where to resume.

Initial state when starting fresh:

```json
{
  "project_dir": "<abs path>",
  "stage": "init",
  "outputs": {},
  "checkpoints": {
    "narration_approved": false,
    "timeline_approved": false,
    "rough_cut_approved": false,
    "subs_preview_approved": false
  },
  "settings": {
    "narration_source": "tts",
    "voice": "zh-CN-XiaoyiNeural",
    "rate": "-5%",
    "output_aspect": "16:9",
    "output_size": "1920x1080",
    "fps": 30,
    "want_subtitles": false
  }
}
```

## Step-by-step

### Stage A — narration  (stage `init` → `narration_ready`)

1. If user gave plain text, help them write `<project_dir>/script.json` (validate against `shared/schemas/script.schema.json`).
2. Run:
   ```bash
   vlog-cut-tts --script <project_dir>/script.json --out <project_dir>
   ```
3. Update state: `stage=narration_ready`, `outputs.timing=<project_dir>/timing.json`, `outputs.narration=<project_dir>/narration.wav`.

### 🔴 Checkpoint 1 — narration approved

**STOP.** Tell the user the narration is ready at `<project_dir>/narration.wav` and the timing is in `timing.json`. Ask them to listen and approve, OR to tell you which line(s) need re-synthesis.

If they want changes:
- edit the line(s) in `script.json`
- delete the corresponding `tts/<id>.mp3` files
- rerun `vlog-cut-tts`

Only when they say "approved" do you set `checkpoints.narration_approved=true` and continue.

### Stage B — asset index  (stage `narration_ready` → `assets_indexed`)

1. Confirm with the user where the source clips live (e.g. `<project_dir>/clips/` or an external folder).
2. Run:
   ```bash
   vlog-cut-index --src <clips_folder> --out <project_dir>
   # add --describe api ONLY if the user asks for auto-tagging
   ```
3. If `--describe api` was not used: open `assets_index.json` and for each clip, Read its `<project_dir>/sheets/<stem>.jpg` and fill in `scene` / `description` / `tags` / `usable` / optionally `chapters` and `highlight`.
4. Update state: `stage=assets_indexed`, `outputs.assets_index=<project_dir>/assets_index.json`.

### 🔴 Checkpoint 2 — tags spot-checked

**STOP.** Show the user a brief summary: how many clips, how many marked `usable: false` (and why), distribution across `chapters`. Ask them to spot-check the index.

If they want changes, edit `assets_index.json` directly. Don't continue until they approve.

### Stage C — timeline  (stage `assets_indexed` → `timeline_reviewed`)

1. Run the deterministic baseline:
   ```bash
   vlog-cut-plan \
     --timing  <project_dir>/timing.json \
     --assets  <project_dir>/assets_index.json \
     --out     <project_dir>/timeline.json \
     --size    <output_size>  --fps <fps>
   ```
2. **Refine.** Read `timeline.json`. For any line where the picked shots look weak (low score, repeated clip, odd `why`), open `sheets/<stem>.jpg` for candidate alternatives and rewrite that line's `shots` array. Keep `sum(shots.dur) >= line.duration` so audio doesn't outrun video.
3. Validate:
   ```bash
   vlog-cut-validate \
     --timeline <project_dir>/timeline.json \
     --src      <clips_folder> \
     --timing   <project_dir>/timing.json
   ```
   Must exit 0. Fix and re-validate until clean. (Exit 1 = warnings — usable but show the warnings to the user.)
4. Update state: `stage=timeline_drafted`, `outputs.timeline=<project_dir>/timeline.json`.

### 🔴 Checkpoint 3 — timeline approved

**STOP.** Summarize the timeline for the user (lines × shots, any reused clips, any tpad freeze-frames the renderer will need). Ask them to read `timeline.json` and approve, or call out lines they want different.

When approved, set `checkpoints.timeline_approved=true`, `stage=timeline_reviewed`.

### Stage D — render  (stage `timeline_reviewed` → `rough_cut_rendered`)

1. Run:
   ```bash
   vlog-cut-render \
     --timeline  <project_dir>/timeline.json \
     --timing    <project_dir>/timing.json \
     --src       <clips_folder> \
     --narration <project_dir>/narration.wav \
     --out       <project_dir> \
     --name      rough_cut.mp4
   ```
2. Update state: `stage=rough_cut_rendered`, `outputs.rough_cut=<project_dir>/rough_cut.mp4`.

### 🔴 Checkpoint 4 — rough cut approved

**STOP.** Tell the user where the file is, mention the duration / size from the final probe. Ask them to watch and approve.

If they want changes: most fixes happen by editing `timeline.json` and re-running render (segs are cached — only changed shots re-encode). Bigger fixes (wrong narration line, mistagged clip) loop back to earlier stages.

When approved, set `checkpoints.rough_cut_approved=true`, `stage=rough_cut_approved` → `done`.

(Subtitles are v0.2 — `burn-subtitles-cn` will hook in here when ready.)

## Resuming

If state.json already exists, **read it first** and resume from `stage`. Don't redo earlier stages unless the user explicitly asks ("redo TTS", "re-index").

## Hard rules

- **Never skip a checkpoint** to "save time". The user signing off is the contract.
- **Never claim a stage succeeded** without the corresponding output file existing. Verify with `ls` / `Read`.
- **All paths configurable.** No hardcoded absolute paths anywhere — always derive from `project_dir` + `clips_folder`.
- **Don't auto-render after plan.** Always pause for the timeline review checkpoint, even if validate exits clean.

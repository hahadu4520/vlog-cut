# Known issues — bugs found via real-world dogfooding

Recorded as I hit them. Each entry: what broke, when, what we did this time, what
the proper fix looks like.

## Summary

| # | Bug | Found via | Status | Regression test |
|---|---|---|---|---|
| 1 | `render.py` `-t` capped tpad freeze frames | smoke test (synthetic fixture) | ✅ fixed | `test_gap_absorbed_by_freeze_when_source_too_short` |
| 2 | `tts.py` `gap=0` deadlocked ffmpeg concat | smoke test (zero-gap test) | ✅ fixed | `test_cli_overrides_gaps` |
| 3 | Pipeline can't ingest user-supplied narration | dogfooding 散步 vlog | ✅ fixed (v0.4 `align-narration` skill landed early) | 9 tests in `tests/test_align_narration.py` |
| 4 | Should detect local whisper before asking | dogfooding 散步 vlog | ⚠️ behavioral lesson (no code change yet) | — |
| 5 | `render.py` concat broke with relative `--out` | dogfooding 散步 vlog | ✅ fixed | `test_render_works_with_relative_paths` |
| 6 | `render.py` seg cache key didn't include `in/dur` | dogfooding 散步 vlog (audio felt truncated) | ✅ fixed | `test_cache_invalidates_when_dur_changes` |
| 7 | Render didn't warn when audio length ≠ video_total | dogfooding 散步 vlog (root cause of perceived "audio truncation") | ✅ fixed | `test_render_warns_on_audio_video_mismatch` |
| 8 | Whisper transcription errors (`AI时代码`) burned straight into subtitles | dogfooding subtitled 散步 vlog | ✅ fixed (`subs-split --script`) | `test_split_with_script_replaces_text` |
| 9 | Subtitle pages hard-cut mid-word (no punctuation in whisper text) | same | ✅ fixed (same `--script` flag) | `test_split_with_script_uses_punct_for_better_breaks` |
| 10 | Subtitle text overflows letterboxed video's content area, looks like "missing chars" | same | ✅ fixed (`subs-build --safe-width [--auto-fit]`) | `test_build_safe_width_*` ×4 |

**Score**: 10 bugs found, 9 fixed in code, 1 behavioral guidance (probe-before-asking).

**Cross-cutting lessons**:
1. **Synthetic smoke tests lie.** Tests 1 & 2 were caught only because I hand-wrote a freeze-path test and a zero-gap test. Tests 5 & 6 slipped past 41 passing tests because every test used `tmp_path` (absolute) and rendered exactly once (no iteration). The test harness needs to model realistic user friction: relative paths, multiple iterations, optional deps that may or may not be present.
2. **Cache keys must hash every input that affects output.** Shortcut keys (`lid+idx+stem`) silently produce stale outputs. Rule: if changing X changes file content, X belongs in the key.
3. **`-shortest` hides upstream bugs.** It silently truncates instead of erroring. The mux step now warns when audio and video lengths disagree (bug #7).
4. **Optional dependencies should be probed, not asked about.** "Do you want me to install whisper?" is the wrong default when whisper is already on PATH.

---

## 1 — render.py `-t` capped tpad freeze frames

**Found while:** writing the smoke test suite, specifically the test where a shot already consumes the entire source clip and the gap must be filled with a held last-frame freeze.

**What broke:** the renderer placed `-t shot.dur` AFTER `-i source.mp4` but BEFORE the output filename. ffmpeg interprets that as an OUTPUT duration cap. The `tpad=stop_mode=clone:stop_duration=0.25` was correctly added to the filter chain, but `-t 1.0` truncated the output to 1.0s before tpad's frozen frames could be emitted. Result: the seg was 1.0s, not the expected 1.25s.

**Why the original 02-Cut code never tripped this:** every shot in that project's render had a source clip longer than the shot, so the freeze branch was never taken.

**Fix:** [skills/narration_cut/render.py:97](../skills/narration_cut/render.py:97) — `out_t = float(shot["dur"]) + pad_extra` so the cap accommodates the freeze.

**Regression test:** `test_gap_absorbed_by_freeze_when_source_too_short` in [tests/test_narration_cut_render.py](../tests/test_narration_cut_render.py).

**Lesson:** synthetic test data needs to exercise the corner that real test data never hits — the freeze code path was dead in the original use case but live in the new harness.

---

## 2 — tts.py `gap=0` deadlocked ffmpeg concat

**Found while:** the same smoke test suite. `test_cli_overrides_gaps` overrode `--gap-line 0.0 --gap-section 0.0` to verify the no-silence path. ffmpeg hung indefinitely.

**What broke:** `_build_merged()` always inserted a silence segment between consecutive lines. When the gap was 0, it generated `ffmpeg -f lavfi -t 0.0 -i anullsrc=...` for each silence — a 0-duration lavfi input emits no frames. The concat filter waits forever for that input to produce something. Tests had to be killed manually.

**Fix:** [skills/tts_from_script/tts.py:43](../skills/tts_from_script/tts.py:43) — skip the silence input when `gap > 1e-3`.

**Regression test:** `test_cli_overrides_gaps` (now finishes in <1s instead of hanging).

**Lesson:** zero is a real value at the boundary of any range parameter. Defensive code paths around lavfi inputs need a "skip if duration ≈ 0" guard.

---

## 3 — Pipeline can't ingest user-supplied narration

**Found while:** dogfooding the "AI 时代多散步" 50-second vlog. User had recorded their own narration (`口播.m4a`) and dropped it in the source folder.

**What broke:** the only way the pipeline gets `timing.json` is via `vlog-cut-tts`, which synthesizes audio AND emits per-line timestamps in one pass. There's no "I already have audio, please align it" path.

**Workaround used:** ran `whisper` on the m4a manually, parsed the segment-level JSON into a `timing.json` matching `shared/schemas/timing.schema.json`, then proceeded with `narration-cut` as normal. Helper script left behind at [proj/sanbu/build_timing_from_whisper.py](../proj/sanbu/build_timing_from_whisper.py) for reference.

**Status: ✅ fixed.** Built `skills/align_narration/` immediately after v0.1 tag. CLI `vlog-cut-align`. Same Timing schema as tts-from-script so `narration-cut.render` works unchanged. Section grouping done by per-section `head_text` anchors in `script.json` (the first few characters of that section as actually spoken). 9 regression tests in [tests/test_align_narration.py](../tests/test_align_narration.py); end-to-end validation by re-running the 散步 vlog through it (gave the same 5-section timing.json the manual helper had produced).

**Bonus fix:** align-narration probes the audio file's true duration (via ffprobe) and uses THAT as `total_duration`, rather than whisper's last-segment end. This automatically dodges bug #7 for user-supplied audio: even when whisper trims a silent tail, the timing carries the full audio length so `-shortest` won't truncate.

**Out of scope for this fix:** auto-detecting whether the audio matches the script (whisper hallucinations, missing lines). That's a checkpoint-1 review problem — show the user the alignment diff. whisperx (word-level forced alignment) is also still a future enhancement; current implementation falls back to plain whisper.

---

## 4 — Should detect local whisper before asking the user

**Found while:** same session as #3. When the timing-vs-narration gap came up, I asked the user "do you want me to install whisper or do it manually" without first checking whether `whisper` was already on PATH (it was, at `/opt/homebrew/bin/whisper`).

**Why this matters:** every "do you want me to install X" prompt is friction. If X is already installed, asking is just noise.

**Proper fix:**
- in `vlog-cut-pipeline/SKILL.md`, when any stage needs an optional dep, the rule should be:
  1. probe with `which <cmd>` / try-import
  2. if present, use it
  3. only ask if absent AND there's a real install cost
- generalise to other optional deps: `anthropic` SDK for vision tagging, `whisperx` vs `whisper`, future `ffprobe` plugin filters
- once `align-narration` skill exists, its SKILL.md should run this probe in its own preamble so the pipeline doesn't have to know

**Bonus headache from this dogfood session:** the local `medium.pt` model file was corrupted (SHA256 mismatch on load), which I only discovered after waiting two minutes for it to load. The fallback `large-v3-turbo.pt` worked. A robust skill should: (a) probe model integrity if possible, (b) catch the SHA error and either auto-redownload or fall back to a smaller model with a warning.

---

## 5 — render concat broke when --out was a relative path

**Found while:** rendering the 散步 vlog. `vlog-cut-render --out proj/sanbu` crashed at the concat step. All 18 segs encoded fine, but `ffmpeg -f concat` failed with "no such file" for each seg path.

**Root cause:** `_concat()` in `narration_cut/render.py` wrote relative paths into `concat_list.txt`. ffmpeg's concat demuxer resolves those paths against the **list file's directory**, not the cwd of ffmpeg. So a path like `proj/sanbu/segs/000.mp4` written into a list file at `proj/sanbu/concat_list.txt` gets resolved to `proj/sanbu/proj/sanbu/segs/000.mp4` — nonexistent.

**Worse:** the existing test suite never caught this because every test passed absolute paths via `tmp_path`. The bug only triggers when the user types a relative `--out`, which is the natural shell ergonomic.

**Fix:** [skills/narration_cut/render.py:118](../skills/narration_cut/render.py:118) — call `s.resolve()` before writing each path, so the list file always contains absolute paths.

**Regression test:** [tests/test_narration_cut_render.py::test_render_works_with_relative_paths](../tests/test_narration_cut_render.py) chdir's to an unrelated dir and passes every path as `../...` relative.

**Lesson:** anything where a path is "written down somewhere then re-resolved later" silently changes meaning depending on cwd. Audit candidates: `assets_index.json`'s `file` field, `timing.json`'s `file` field — both are relative to a containing dir that may change.

---

## 6 — render seg cache key didn't include in/dur

**Found while:** rendering v3 of the 散步 vlog. User noticed audio felt truncated. Investigation: source audio 55.40s, mp4 only 52.57s — almost 3 seconds gone. Root cause turned out to be **two bugs stacking** (this one and bug #7).

**What broke:** `_render_segments()` named segs `{idx:03d}_{lid}_{stem}.mp4` — no `in` / `dur` in the filename. When the user iterates on the timeline (changing a shot's window without changing the file or shuffling shots), the old cached cut still wins and the new dur is silently ignored.

In v1, `IMG_2127` had `dur=2.6s`; v3 changed it to `dur=3.5s`. The 2.6s seg from v1 was reused. Per-section video came out 0.9s short of what timing said it should be — and then bug #7 turned that into truncated audio.

**Fix:** [skills/narration_cut/render.py:75](../skills/narration_cut/render.py:75) — seg filename now includes the `in-dur` (and `-pXXX` for tpad freeze) so cache invalidates on any window edit.

**Regression test:** [tests/test_narration_cut_render.py::test_cache_invalidates_when_dur_changes](../tests/test_narration_cut_render.py) renders with `dur=2.0`, then re-renders the SAME line/idx/file with `dur=3.0`, asserts final mp4 is ~3s.

**Lessons:**
- Cache keys must hash all inputs that affect the output. "lid + idx + stem" was an undertested shortcut; `in/dur/pad` directly determine pixel content and must be in the key.
- Real-world iteration is the test the synthetic suite missed. The smoke tests render once — they never exercised "edit timeline, re-render, check output reflects edit." That's a gap worth filling for any future content pipeline skill.

---

## 7 — render didn't warn when audio length ≠ video_total

**Found while:** same session as #6. After fixing the cache bug, I realized the user's perception of "audio truncated" wasn't only about the 0.9s lost to bug #6 — there was also a **silent 1.94s loss at the end of every render** because:

- whisper's last segment ended at 53.46s (it stopped recognizing once "都是正经事" finished pronouncing)
- but the actual audio file was 55.40s long (1.94s of breath/tail after the last word)
- `timing.json.total_duration` was 53.46s
- render built a 53.46s video
- mux used `-shortest` → audio truncated to match the 53.46s video

The renderer never told the user the audio file was longer than `video_total`. The fix needs to **surface the discrepancy** so the user can decide: extend `outro.end` to include the tail, or trim the audio file.

**Fix:** [skills/narration_cut/render.py](../skills/narration_cut/render.py) — added an `_audio_video_check()` step before mux that probes the audio file's actual duration and prints a warning if it differs from `video_total` by more than 0.3s.

**Regression test:** [tests/test_narration_cut_render.py::test_render_warns_on_audio_video_mismatch](../tests/test_narration_cut_render.py) creates a narration WAV that's 1.5s longer than the timeline says, renders, asserts the warning lands in stderr.

**Lesson:** `-shortest` is a silent-truncation hazard. Any muxer that combines two streams with potentially different lengths should explicitly compare them and warn (or refuse) when they disagree past tolerance.

---

## 8 — whisper recognition errors burned into subtitles

**Found while:** dogfooding the subtitled 散步 vlog. The visible subtitle "AI时代码" is whisper's mis-hearing of "AI时代，能让脑子..."  ("代" + "能" → "代码"). With `subs-split` consuming `timing.json.text` directly (which came from `align-narration` → whisper), every recognition error gets baked into the burnt-in subtitles.

**Root cause:** `align-narration` faithfully copies whisper's transcription into `timing.json.text` so the rest of the pipeline has *something* to display. But the user-authored, correct version of the text lives in `script.json.sections[*].lines[]`. The subtitle layer was reading from the wrong source.

**Fix:** [skills/burn_subtitles_cn/split.py:121](../skills/burn_subtitles_cn/split.py:121) — `vlog-cut-subs-split --script <script.json>` substitutes the script's punctuated `lines[]` (joined by `，`) for each timing line whose `section` matches. Timestamps stay; text comes from the user-authored version.

**Regression test:** `test_split_with_script_replaces_text` in [tests/test_burn_subtitles_cn.py](../tests/test_burn_subtitles_cn.py).

**Lesson:** when there are two sources of truth for the same content (whisper output AND user-authored script), default to the user-authored one for anything user-visible. Whisper's text is for *alignment*, not *display*.

---

## 9 — subtitle pages hard-cut mid-word

**Found while:** same session as #8. Pages like "事现在下楼单纯就是想走一" / "走" — the splitter's punctuation-priority algorithm had no commas/periods to anchor on (whisper drops punctuation in Chinese), so it fell back to hard-cuts every 12 chars. "想走一走" got split as "想走一" + "走".

**Root cause:** same as #8 — `subs-split` consumed whisper's no-punct text. The splitter's algorithm is fine; the input was missing the signals it needed.

**Fix:** same as #8. The script-substituted text *has* punctuation (the user wrote it that way), so the existing splitter algorithm now finds soft breaks at every comma and period.

**Regression test:** `test_split_with_script_uses_punct_for_better_breaks` confirms split output differs (and is better) when `--script` is supplied.

---

## 10 — subtitle text overflows letterboxed video's content area

**Found while:** same session, after fixing #8 and #9. The user reported "字幕宽度超出画面" + "有一些漏掉的字". Frame inspection: at font_size=56 with 12 chars per page, the rendered text ≈ 670px wide, but the inner content of pillarboxed portrait clips is only ~608px wide. The subtitle's last chars trail into the black bars on either side, where the viewer's eye doesn't track them — reads as "missing characters".

**Root cause:** `subs-build` rendered to PlayResX = full canvas width (1920) without any awareness of where the actual video content lives. There was no overflow check at all — fully a build-time failure that only manifested visually, after a full burn.

**First-pass fix (rejected):** added `--safe-width <px>` + `--auto-fit` flags. Both manual / opt-in. The user had to compute the inner content width by hand, remember to pass both flags, and the **default behavior didn't change** — so the original bug recurred whenever those flags were forgotten. User feedback was sharp and right: "这种不是一个很好直接判断的事情吗，你去计算下画面宽度，然后用代码约束好字幕长度，不行啊".

**Real fix:** [skills/burn_subtitles_cn/build.py:14](../skills/burn_subtitles_cn/build.py:14)
- new flag `--video <mp4>` — when given, build auto-probes the video's content rectangle via ffmpeg `cropdetect`, applies a title-safe padding, and auto-fits font-size to keep every page inside that budget
- auto-fit is now the default — `--no-auto-fit` opts out (warn only)
- `--safe-width <px>` kept as a manual override for cases where cropdetect picks the wrong rectangle
- pipeline SKILL.md Stage E now mandates `--video` on every subs-build call

**Second-pass fix (after user feedback):** initial implementation used a 5% safety margin. User pointed out that subtitles were "pressed against the content edges" — technically not overflowing, but visually claustrophobic. Loosened default to 18% (broadcast title-safe convention; subtitles get 82% of the detected content width). Made the ratio configurable via `--safe-ratio` so users can tighten or loosen per-project. Bumped sanbu vlog from font-size 48 → 41 with the new default; visual breathing room significantly improved.

**Regression tests** (6):
- `test_build_video_auto_detects_letterbox` — synthetic pillarboxed mp4 → font-size drops automatically without any width flags
- `test_build_video_no_letterbox_no_change` — full-frame mp4 → font-size stays
- `test_build_video_missing_returns_2`
- `test_build_safe_width_auto_fits_by_default` — manual `--safe-width` still triggers auto-fit (no opt-in needed)
- `test_build_no_auto_fit_only_warns` — explicit opt-out path still works
- `test_build_safe_width_only_warns_for_real_overflows` — multi-page input under no-auto-fit only flags real overflows

**Lessons:**
- "Add a flag to opt into the safe behavior" is not a fix — it's a future bug. Default behavior must be the safe one; the dangerous one is the opt-in.
- When a tool has the information it needs (the video file is *right there*), make the tool gather what it needs autonomously instead of asking the user to compute and pass it. The user shouldn't need to know what "9:16 inside 16:9" means in pixels.
- The right unit of correctness is "user types the obvious command and gets the right output," not "user types the right command and gets the right output."

**Future:** when v0.3 adds rotation handling, the cropdetect call may need to account for rotated source frames. Currently fine because `narration-cut.render` already normalises rotation before encoding segs.

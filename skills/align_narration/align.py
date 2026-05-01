"""align-narration: align user-recorded narration audio against a script,
producing the same timing.json + narration.wav that tts-from-script emits.

Two modes:
  --script <script.json>   : use sections (with optional `head_text`) to build
                              one timing line per section
  (no script)              : emit one big "narration_00" line covering the
                              entire audio — minimum-friction onboarding

Engine: subprocess to local `whisper` (OpenAI). whisperx is preferred for
word-level alignment but optional; if `--engine whisperx` is passed but not
installed, we fall back to whisper with a warning.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from shared import ffmpeg_helpers as ff


DEFAULT_MODEL = "large-v3-turbo"
DEFAULT_LANG = "Chinese"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run_whisper(audio: Path, out_dir: Path, model: str, language: str) -> Path:
    """Invoke whisper CLI, return the path to its <stem>.json output."""
    if not _have("whisper"):
        raise RuntimeError(
            "whisper CLI not found on PATH. Install with `pip install openai-whisper`."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  running whisper ({model}, {language})...", flush=True)
    cmd = [
        "whisper", str(audio),
        "--language", language,
        "--model", model,
        "--output_format", "json",
        "--output_dir", str(out_dir),
        "--verbose", "False",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"whisper failed (exit {r.returncode}):\n{r.stderr[-2000:]}"
        )
    json_path = out_dir / f"{audio.stem}.json"
    if not json_path.exists():
        raise RuntimeError(f"whisper did not write expected output {json_path}")
    return json_path


def _to_wav(audio_in: Path, wav_out: Path) -> None:
    """Re-encode the user's audio to canonical mono 24kHz PCM WAV — same
    format `tts-from-script` emits, so render's mux step gets a predictable
    stream regardless of what the user dropped in."""
    wav_out.parent.mkdir(parents=True, exist_ok=True)
    if wav_out.exists() and wav_out.stat().st_size > 0:
        return
    ff.run([
        "ffmpeg", "-y",
        "-i", str(audio_in),
        "-ac", "1",
        "-ar", "24000",
        "-c:a", "pcm_s16le",
        str(wav_out),
    ])


def _segments_to_lines_no_script(segments: list[dict],
                                  audio_file: str) -> list[dict]:
    """No script supplied → fold the entire transcription into one line."""
    if not segments:
        return []
    text = "".join(s["text"] for s in segments).strip()
    return [{
        "id": "narration_00",
        "section": "narration",
        "section_title": "Narration",
        "text": text,
        "file": audio_file,
        "duration": round(segments[-1]["end"] - segments[0]["start"], 3),
        "start": round(segments[0]["start"], 3),
        "end": round(segments[-1]["end"], 3),
    }]


def _segments_to_lines_with_script(segments: list[dict], script: dict,
                                    audio_file: str,
                                    audio_duration: float) -> list[dict]:
    """Group whisper segments into one line per script section.

    Strategy: each section in script.json may carry a `head_text` field — the
    first few characters of that section as recorded. We scan whisper segments
    in order, finding the first segment whose text contains a section's
    head_text. That segment's start becomes the section's start. The section
    extends until the next section starts (or, for the last section, until the
    actual audio end — NOT just the last whisper segment, because whisper drops
    silent tails).

    If a section has no `head_text`, we fall back to taking section_idx /
    n_sections of the audio as that section's start point — crude but it never
    leaves a section unassigned. The user can iterate by adding head_text
    anchors as they review the output."""
    sections = script.get("sections", [])
    if not sections:
        return _segments_to_lines_no_script(segments, audio_file)

    # locate each section's start time in the audio
    section_starts: list[float] = []
    cursor_seg = 0
    for sec_idx, sec in enumerate(sections):
        head = (sec.get("head_text") or "").strip()
        start_t: float | None = None
        if head:
            for i in range(cursor_seg, len(segments)):
                if head in segments[i]["text"]:
                    start_t = segments[i]["start"]
                    cursor_seg = i + 1
                    break
        if start_t is None:
            # fallback: equal-fraction split
            start_t = audio_duration * sec_idx / max(1, len(sections))
            print(
                f"  WARN: section '{sec['id']}' has no `head_text` match; "
                f"falling back to {start_t:.2f}s (equal-fraction split)",
                file=sys.stderr,
            )
        section_starts.append(start_t)

    # build one line per section
    lines: list[dict] = []
    for i, sec in enumerate(sections):
        start = section_starts[i]
        end = section_starts[i + 1] if i + 1 < len(sections) else audio_duration
        # collect every whisper segment whose midpoint is in [start, end)
        text_parts = []
        for seg in segments:
            mid = (seg["start"] + seg["end"]) / 2
            if start <= mid < end:
                text_parts.append(seg["text"])
        text = "".join(text_parts).strip()
        line = {
            "id": f"{sec['id']}_00",
            "section": sec["id"],
            "text": text,
            "file": audio_file,
            "duration": round(end - start, 3),
            "start": round(start, 3),
            "end": round(end, 3),
        }
        if "title" in sec:
            line["section_title"] = sec["title"]
        lines.append(line)
    return lines


def _run(audio: Path, out_dir: Path, script_path: Path | None,
         engine: str, model: str, language: str) -> dict:
    if engine == "whisperx" and not _have("whisperx"):
        print("  WARN: whisperx not installed; falling back to whisper",
              file=sys.stderr)
        engine = "whisper"

    # Step 1: transcribe (cached per audio stem in <out>/whisper/)
    whisper_dir = out_dir / "whisper"
    json_path = whisper_dir / f"{audio.stem}.json"
    if json_path.exists():
        print(f"  using cached whisper output: {json_path}")
    else:
        if engine == "whisper":
            json_path = _run_whisper(audio, whisper_dir, model, language)
        else:
            # whisperx future hook — for now treat same as whisper
            json_path = _run_whisper(audio, whisper_dir, model, language)

    # Step 2: probe true audio duration (whisper's last segment trims silence)
    audio_dur = ff.duration(audio)

    # Step 3: convert segments → timing lines
    data = json.loads(json_path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])
    last_end = segments[-1]["end"] if segments else 0.0
    print(f"  {len(segments)} whisper segments, "
          f"{last_end:.2f}s recognized / {audio_dur:.2f}s audio")

    # Step 4: re-encode audio to canonical narration.wav
    wav_out = out_dir / "narration.wav"
    _to_wav(audio, wav_out)
    audio_file_field = wav_out.name

    if script_path is not None:
        script = json.loads(script_path.read_text(encoding="utf-8"))
        lines = _segments_to_lines_with_script(segments, script,
                                                audio_file_field, audio_dur)
    else:
        lines = _segments_to_lines_no_script(segments, audio_file_field)
        if lines:
            # extend the lone line to the true audio end if whisper trimmed it
            lines[0]["end"] = round(audio_dur, 3)
            lines[0]["duration"] = round(audio_dur - lines[0]["start"], 3)

    timing = {
        "voice": "user-recorded",
        "rate": "+0%",
        "total_duration": round(audio_dur, 3),
        "lines": lines,
    }
    return timing


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vlog-cut-align",
                                description=__doc__.splitlines()[0])
    p.add_argument("--audio", required=True, type=Path,
                   help="user-recorded narration (m4a/mp3/wav/etc.)")
    p.add_argument("--out", required=True, type=Path, help="project directory")
    p.add_argument("--script", type=Path, default=None,
                   help="optional script.json with sections (and per-section `head_text`)")
    p.add_argument("--engine", choices=["whisper", "whisperx"], default="whisper",
                   help="alignment engine (whisperx falls back to whisper if missing)")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"whisper model (default {DEFAULT_MODEL})")
    p.add_argument("--language", default=DEFAULT_LANG,
                   help=f"whisper --language (default {DEFAULT_LANG})")
    args = p.parse_args(argv)

    if not args.audio.exists():
        print(f"audio not found: {args.audio}", file=sys.stderr)
        return 2
    if args.script is not None and not args.script.exists():
        print(f"script not found: {args.script}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)

    timing = _run(args.audio, args.out, args.script,
                  args.engine, args.model, args.language)

    timing_path = args.out / "timing.json"
    timing_path.write_text(json.dumps(timing, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"\nWrote {timing_path}")
    print(f"Wrote {args.out / 'narration.wav'}")
    print(f"Total duration: {timing['total_duration']:.2f}s "
          f"({timing['total_duration']/60:.2f} min) / "
          f"{len(timing['lines'])} line(s)")
    for ln in timing["lines"]:
        print(f"  {ln['id']:14s} [{ln['start']:6.2f} → {ln['end']:6.2f}]  "
              f"{ln['text'][:40]}{'...' if len(ln['text'])>40 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(cli())

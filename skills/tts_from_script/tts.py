"""tts-from-script: script.json -> per-line TTS clips + timing.json + merged narration.wav.

Reads a Script (see shared/schemas/script.schema.json), synthesizes each line with
edge-tts, probes durations, and emits:

  <out>/tts/<id>.mp3        per-line audio
  <out>/timing.json         Timing (see shared/schemas/timing.schema.json)
  <out>/narration.wav       merged track with line / section gaps
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import edge_tts

from shared import ffmpeg_helpers as ff


DEFAULT_GAP_LINE = 0.25
DEFAULT_GAP_SECTION = 0.6
SAMPLE_RATE = 24000


async def _synth(voice: str, rate: str, text: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    await edge_tts.Communicate(text, voice=voice, rate=rate).save(str(out))


def _build_merged(timing: dict, root: Path, out_wav: Path,
                  gap_line: float, gap_section: float) -> None:
    plan: list[tuple[str, object]] = []
    last_section: str | None = None
    for entry in timing["lines"]:
        if last_section is not None:
            gap = gap_section if entry["section"] != last_section else gap_line
            # ffmpeg's lavfi anullsrc with -t 0 produces no output and stalls
            # the concat filter. Skip the silence input entirely when the gap
            # is zero (or smaller than one audio sample).
            if gap > 1e-3:
                plan.append(("silence", gap))
        plan.append(("audio", entry["file"]))
        last_section = entry["section"]

    cmd = ["ffmpeg", "-y"]
    for kind, val in plan:
        if kind == "audio":
            cmd += ["-i", str(root / val)]
        else:
            cmd += ["-f", "lavfi", "-t", f"{val}",
                    "-i", f"anullsrc=channel_layout=mono:sample_rate={SAMPLE_RATE}"]

    n = len(plan)
    parts = [f"[{i}:a]aformat=sample_rates={SAMPLE_RATE}:channel_layouts=mono[a{i}]"
             for i in range(n)]
    parts.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]")
    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", "[out]",
        "-c:a", "pcm_s16le",
        str(out_wav),
    ]
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    ff.run(cmd)


async def _run(script_path: Path, out_dir: Path,
               gap_line: float | None, gap_section: float | None) -> dict:
    cfg = json.loads(script_path.read_text(encoding="utf-8"))
    voice = cfg["voice"]
    rate = cfg["rate"]
    gap_line = gap_line if gap_line is not None else cfg.get("gap_line_sec", DEFAULT_GAP_LINE)
    gap_section = gap_section if gap_section is not None else cfg.get("gap_section_sec", DEFAULT_GAP_SECTION)

    tts_dir = out_dir / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)

    timing: dict = {"voice": voice, "rate": rate, "lines": []}
    cursor = 0.0
    last_section: str | None = None

    for sec in cfg["sections"]:
        for line_idx, text in enumerate(sec["lines"]):
            fid = f"{sec['id']}_{line_idx:02d}"
            mp3 = tts_dir / f"{fid}.mp3"
            print(f"[{fid}] {text[:30]}...", flush=True)
            if not mp3.exists() or mp3.stat().st_size == 0:
                await _synth(voice, rate, text, mp3)
            dur = ff.duration(mp3)
            if last_section is not None:
                cursor += gap_section if sec["id"] != last_section else gap_line
            entry = {
                "id": fid,
                "section": sec["id"],
                "text": text,
                "file": str(mp3.relative_to(out_dir)),
                "duration": round(dur, 3),
                "start": round(cursor, 3),
                "end": round(cursor + dur, 3),
            }
            if "title" in sec:
                entry["section_title"] = sec["title"]
            timing["lines"].append(entry)
            cursor += dur
            last_section = sec["id"]

    timing["total_duration"] = round(cursor, 3)
    timing_path = out_dir / "timing.json"
    timing_path.write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nTotal duration: {cursor:.2f}s ({cursor/60:.2f} min)")
    print(f"Wrote {timing_path}")

    narration = out_dir / "narration.wav"
    print("Merging narration...", flush=True)
    _build_merged(timing, out_dir, narration, gap_line, gap_section)
    print(f"Wrote {narration}")
    return timing


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vlog-cut-tts", description=__doc__.splitlines()[0])
    p.add_argument("--script", required=True, type=Path, help="path to script.json")
    p.add_argument("--out", required=True, type=Path, help="output directory")
    p.add_argument("--gap-line", type=float, default=None,
                   help=f"silence between lines (default from script or {DEFAULT_GAP_LINE})")
    p.add_argument("--gap-section", type=float, default=None,
                   help=f"silence between sections (default from script or {DEFAULT_GAP_SECTION})")
    args = p.parse_args(argv)

    if not args.script.exists():
        print(f"script not found: {args.script}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    asyncio.run(_run(args.script, args.out, args.gap_line, args.gap_section))
    return 0


if __name__ == "__main__":
    sys.exit(cli())

"""narration-cut render: realize timeline.json into a final mp4.

Steps:
  1. For each shot, cut the source clip to the shot's [in, in+dur] window,
     normalize to <size>@<fps>, strip audio. Write to <out>/segs/<idx>_<lid>_<stem>.mp4
  2. The narration has gaps between lines (gap_line) and sections (gap_section).
     The LAST shot of each line absorbs that gap so the video covers the silence.
     If the source clip has room, we extend `dur`; otherwise we tpad-freeze the
     last frame to fill the difference.
  3. concat all segments (stream copy) into <out>/video_silent.mp4.
  4. mux narration.wav onto the silent video → <out>/<final_name>.mp4

Reads timing.json (for per-line gap lengths) and timeline.json (for shots).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from shared import ffmpeg_helpers as ff


DEFAULT_FINAL = "rough_cut.mp4"


def _src_duration(src_dir: Path, name: str, cache: dict[str, float]) -> float:
    if name not in cache:
        cache[name] = ff.duration(src_dir / name)
    return cache[name]


def _video_dur_per_line(timing: dict) -> dict[str, float]:
    """For each line, the video must cover from this line's start to the next line's
    start (so silences between lines stay visually populated)."""
    lines = timing["lines"]
    starts = {l["id"]: l["start"] for l in lines}
    total = timing["total_duration"]
    ids = [l["id"] for l in lines]
    next_start = {ids[i]: starts[ids[i + 1]] for i in range(len(ids) - 1)}
    next_start[ids[-1]] = total
    return {lid: next_start[lid] - starts[lid] for lid in ids}


def _render_segments(timeline: dict, timing: dict, src_dir: Path, segs_dir: Path,
                     w: int, h: int, fps: int) -> list[Path]:
    segs_dir.mkdir(parents=True, exist_ok=True)
    line_video_dur = _video_dur_per_line(timing)
    src_cache: dict[str, float] = {}

    plan: list[tuple[Path, dict, str]] = []
    idx = 0
    for line in timeline["lines"]:
        lid = line["id"]
        target = line_video_dur.get(lid, line["duration"])
        shot_sum = sum(s["dur"] for s in line["shots"])
        extra = target - shot_sum
        for j, shot in enumerate(line["shots"]):
            adjusted = dict(shot)
            if j == len(line["shots"]) - 1 and extra > 0:
                src_d = _src_duration(src_dir, shot["file"], src_cache)
                room = src_d - shot["in"] - shot["dur"]
                add = min(extra, max(0.0, room))
                adjusted["dur"] = shot["dur"] + add
                adjusted["pad"] = max(0.0, extra - add)
            stem = Path(shot["file"]).stem
            # Cache key MUST include in/dur/pad — otherwise editing a shot's
            # window (without changing file/lid/idx) silently reuses the old
            # cut. Hit this on the 散步 vlog: a v1 IMG_2127 clip with dur=2.6
            # got reused after v3 changed it to dur=3.5, so the section was
            # 0.9s short and audio got truncated by -shortest.
            sig = f"{shot['in']:.3f}-{adjusted['dur']:.3f}"
            if adjusted.get("pad", 0) > 0.01:
                sig += f"-p{adjusted['pad']:.3f}"
            seg = segs_dir / f"{idx:03d}_{lid}_{stem}_{sig}.mp4"
            plan.append((seg, adjusted, lid))
            idx += 1

    total = len(plan)
    out_paths: list[Path] = []
    for i, (seg, shot, lid) in enumerate(plan, 1):
        out_paths.append(seg)
        if seg.exists() and seg.stat().st_size > 0:
            print(f"[{i}/{total}] {seg.name} (cached)")
            continue

        src = src_dir / shot["file"]
        pad_extra = shot.get("pad", 0.0)
        vf_parts = [
            f"scale={w}:{h}:force_original_aspect_ratio=decrease",
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black",
            f"fps={fps}",
            "setsar=1",
        ]
        if pad_extra > 0.01:
            vf_parts.append(f"tpad=stop_mode=clone:stop_duration={pad_extra:.3f}")
        # ffmpeg's `-t` after `-i` caps OUTPUT duration. We need to include the
        # freeze padding in that cap, otherwise tpad's frozen frames get truncated.
        out_t = float(shot["dur"]) + pad_extra
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{float(shot['in']):.3f}",
            "-i", str(src),
            "-t", f"{out_t:.3f}",
            "-vf", ",".join(vf_parts),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-an",
            "-movflags", "+faststart",
            str(seg),
        ]
        info = f"{float(shot['dur']):.2f}s"
        if pad_extra > 0.01:
            info += f" +{pad_extra:.2f}s freeze"
        print(f"[{i}/{total}] {seg.name} ({info})")
        ff.run(cmd)
    return out_paths


def _concat(segs: list[Path], out_dir: Path, silent_path: Path) -> None:
    list_file = out_dir / "concat_list.txt"
    # ffmpeg's concat demuxer resolves relative paths against the LIST FILE's
    # directory, not the cwd of ffmpeg. Always emit absolute paths to avoid
    # silent breakage when the user invokes us with a relative --out.
    with list_file.open("w", encoding="utf-8") as f:
        for s in segs:
            f.write(f"file '{s.resolve().as_posix()}'\n")
    print(f"\nConcat → {silent_path}")
    ff.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(silent_path),
    ])


AUDIO_VIDEO_TOLERANCE = 0.3


def _audio_video_check(narration: Path, video_total: float) -> None:
    """Warn (but don't fail) when narration audio length disagrees with the
    expected video length. ffmpeg's `-shortest` will silently truncate the
    longer stream; surfacing the gap lets the user catch a stale timing.json
    or a too-long recording before they wonder why the audio cuts off."""
    try:
        audio_dur = ff.duration(narration)
    except Exception as e:
        print(f"WARN: could not probe narration duration ({e}); skipping check",
              file=sys.stderr)
        return
    diff = audio_dur - video_total
    if abs(diff) <= AUDIO_VIDEO_TOLERANCE:
        return
    if diff > 0:
        print(
            f"WARN: narration audio is {audio_dur:.2f}s but video_total is "
            f"{video_total:.2f}s — the trailing {diff:.2f}s of audio will be "
            f"truncated by ffmpeg -shortest. Extend the last line's `end` in "
            f"timing.json to cover the full audio, or trim the audio file.",
            file=sys.stderr,
        )
    else:
        print(
            f"WARN: video_total is {video_total:.2f}s but narration audio is "
            f"only {audio_dur:.2f}s — the trailing {-diff:.2f}s of video will "
            f"play with no sound (then -shortest will cut it). Trim "
            f"timing.json or supply a longer narration.",
            file=sys.stderr,
        )


def _mux(silent: Path, narration: Path, final: Path) -> None:
    print(f"Mux narration → {final}")
    ff.run([
        "ffmpeg", "-y",
        "-i", str(silent),
        "-i", str(narration),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(final),
    ])


def _parse_size(s: str) -> tuple[int, int]:
    if "x" not in s:
        raise argparse.ArgumentTypeError(f"size must look like 1920x1080, got {s!r}")
    w, h = s.lower().split("x", 1)
    return int(w), int(h)


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vlog-cut-render", description=__doc__.splitlines()[0])
    p.add_argument("--timeline", required=True, type=Path)
    p.add_argument("--timing", required=True, type=Path)
    p.add_argument("--src", required=True, type=Path,
                   help="folder containing source clips referenced in timeline")
    p.add_argument("--narration", required=True, type=Path, help="merged narration audio")
    p.add_argument("--out", required=True, type=Path, help="output directory")
    p.add_argument("--name", default=DEFAULT_FINAL,
                   help=f"final mp4 filename (default {DEFAULT_FINAL})")
    p.add_argument("--size", default=None,
                   help="WxH, e.g. 1920x1080 (default: read from timeline.size)")
    p.add_argument("--fps", type=int, default=None,
                   help="output fps (default: read from timeline.fps)")
    args = p.parse_args(argv)

    for label, path in [("timeline", args.timeline), ("timing", args.timing),
                        ("narration", args.narration)]:
        if not path.exists():
            print(f"{label} not found: {path}", file=sys.stderr)
            return 2
    if not args.src.is_dir():
        print(f"src not a directory: {args.src}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)

    timeline = json.loads(args.timeline.read_text(encoding="utf-8"))
    timing = json.loads(args.timing.read_text(encoding="utf-8"))

    size_str = args.size or timeline.get("size") or "1920x1080"
    w, h = _parse_size(size_str)
    fps = args.fps or int(timeline.get("fps", 30))

    segs_dir = args.out / "segs"
    silent = args.out / "video_silent.mp4"
    final = args.out / args.name

    segs = _render_segments(timeline, timing, args.src, segs_dir, w, h, fps)
    _concat(segs, args.out, silent)
    _audio_video_check(args.narration, float(timeline["video_total"]))
    _mux(silent, args.narration, final)

    # Final probe
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name",
        "-of", "default=nw=1",
        str(final),
    ]).decode()
    print("\n=== FINAL ===")
    print(out)
    print(f"Output: {final}")
    return 0


if __name__ == "__main__":
    sys.exit(cli())

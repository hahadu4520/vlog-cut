"""burn-subtitles-cn burn: hard-burn an .ass subtitle file onto a video.

Uses ffmpeg's libass via the `subtitles` filter. Subtitles are part of the
output's pixels — no soft-sub track to toggle off.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from shared import ffmpeg_helpers as ff


def _escape_subs_path(p: Path) -> str:
    """The ffmpeg `subtitles=` filter takes a path inside a filtergraph
    expression, where `:`, `\\`, `[`, `]`, `'`, `,` are all special. The safe
    pattern on macOS / Linux is to wrap the absolute path in single quotes
    and escape any single quotes in the path itself."""
    abs_p = str(p.resolve())
    # libass expects forward slashes even on Windows; on POSIX this is a no-op
    abs_p = abs_p.replace("\\", "/")
    # escape : (drive letters etc.) and ' for the filtergraph
    abs_p = abs_p.replace(":", r"\:").replace("'", r"\'")
    return abs_p


def burn(video: Path, subs: Path, out: Path, *, crf: int = 20,
         preset: str = "veryfast") -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    vf = f"subtitles='{_escape_subs_path(subs)}'"
    ff.run([
        "ffmpeg", "-y",
        "-i", str(video),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(out),
    ])


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vlog-cut-subs-burn",
                                description=__doc__.splitlines()[0])
    p.add_argument("--video", required=True, type=Path,
                   help="source video (typically rough_cut.mp4)")
    p.add_argument("--subs",  required=True, type=Path,
                   help=".ass subtitle file from vlog-cut-subs-build")
    p.add_argument("--out",   required=True, type=Path,
                   help="output mp4 path (subtitles burned in)")
    p.add_argument("--crf",   type=int, default=20,
                   help="x264 CRF (lower = better quality, default 20)")
    p.add_argument("--preset", default="veryfast",
                   help="x264 preset (default veryfast)")
    args = p.parse_args(argv)

    if not args.video.exists():
        print(f"video not found: {args.video}", file=sys.stderr)
        return 2
    if not args.subs.exists():
        print(f"subs not found: {args.subs}", file=sys.stderr)
        return 2

    print(f"Burning {args.subs.name} → {args.out}")
    burn(args.video, args.subs, args.out, crf=args.crf, preset=args.preset)

    info = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size",
        "-show_entries", "stream=width,height,codec_name",
        "-of", "default=nw=1",
        str(args.out),
    ]).decode()
    print("\n=== FINAL ===")
    print(info)
    print(f"Output: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(cli())

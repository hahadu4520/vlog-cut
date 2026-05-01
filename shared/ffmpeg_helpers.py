"""Thin wrappers over ffmpeg/ffprobe used by all skills."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def probe(path: Path) -> dict:
    """Return {width, height, duration, fps, rotation} for a video file."""
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-show_entries", "stream_side_data=rotation",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ])
    data = json.loads(out)
    s = data["streams"][0]
    fmt = data["format"]
    num, den = s["r_frame_rate"].split("/")
    fps = float(num) / float(den) if float(den) else 0.0

    rotation = None
    for sd in s.get("side_data_list", []):
        if "rotation" in sd:
            rotation = int(sd["rotation"])
            break

    return {
        "width": s["width"],
        "height": s["height"],
        "duration": float(fmt["duration"]),
        "fps": round(fps, 2),
        "rotation": rotation,
    }


def duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1",
        str(path),
    ])
    return float(out.strip())


def run(cmd: list, quiet: bool = True) -> None:
    """Run an ffmpeg command, raising on failure."""
    kwargs = {}
    if quiet:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    r = subprocess.run(cmd, **kwargs)
    if r.returncode != 0:
        # rerun verbosely so the user sees what broke
        subprocess.run(cmd)
        raise RuntimeError(f"ffmpeg failed: {' '.join(str(c) for c in cmd[:5])} ...")


def extract_frame(video: Path, timestamp: float, out: Path, scale_w: int = 480) -> None:
    """Extract one frame at `timestamp` seconds, scaled to width=scale_w."""
    out.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-ss", f"{timestamp:.2f}",
        "-i", str(video),
        "-frames:v", "1",
        "-vf", f"scale={scale_w}:-2",
        "-q:v", "5",
        str(out),
    ])


def hstack_frames(frames: list[Path], out: Path, each_w: int = 400) -> None:
    """Combine N frames horizontally into one image (contact sheet)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    n = len(frames)
    cmd = ["ffmpeg", "-y"]
    for f in frames:
        cmd += ["-i", str(f)]
    parts = [f"[{i}:v]scale={each_w}:-1[t{i}]" for i in range(n)]
    concat = "".join(f"[t{i}]" for i in range(n))
    parts.append(f"{concat}hstack=inputs={n}[out]")
    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", "[out]",
        "-q:v", "5",
        str(out),
    ]
    run(cmd)

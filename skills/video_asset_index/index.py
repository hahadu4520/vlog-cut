"""video-asset-index: scan a folder of video clips, probe metadata, sample keyframes,
build per-clip contact sheets, and emit assets_index.json.

Two modes:
  --describe off (default): metadata + sheets only. Claude reads the sheets via the
                            Read tool and writes scene/description/tags/usable into
                            the index by hand.
  --describe api          : call the Anthropic API to auto-fill scene/description/tags.

Output matches shared/schemas/assets_index.schema.json.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from shared import ffmpeg_helpers as ff


N_FRAMES = 3
DEFAULT_SHEET_WIDTH = 400  # per frame, in the contact sheet
DEFAULT_FRAME_WIDTH = 480  # per extracted keyframe
SUPPORTED_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}


def _orientation(w: int, h: int) -> str:
    if w > h:
        return "landscape"
    if h > w:
        return "portrait"
    return "square"


def _sample_frames(video: Path, duration: float, n: int,
                   out_dir: Path, scale_w: int) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    times = [duration * (i + 1) / (n + 1) for i in range(n)]
    out_paths: list[Path] = []
    for i, t in enumerate(times):
        fp = out_dir / f"{video.stem}_f{i}.jpg"
        if not fp.exists() or fp.stat().st_size == 0:
            ff.extract_frame(video, t, fp, scale_w=scale_w)
        out_paths.append(fp)
    return out_paths


def _probe_record(video: Path, frames_dir: Path,
                  frame_w: int) -> dict:
    """Deterministic part: probe + extract frames. Returns one record."""
    meta = ff.probe(video)
    rec: dict = {
        "file": video.name,
        "duration": round(meta["duration"], 3),
        "width": meta["width"],
        "height": meta["height"],
        "fps": meta["fps"],
        "rotation": meta["rotation"],
        "orientation": _orientation(meta["width"], meta["height"]),
    }
    _sample_frames(video, meta["duration"], N_FRAMES, frames_dir, frame_w)
    return rec


def _build_sheet(video_stem: str, frames_dir: Path, sheets_dir: Path,
                 each_w: int) -> Path:
    sheets_dir.mkdir(parents=True, exist_ok=True)
    out = sheets_dir / f"{video_stem}.jpg"
    if out.exists() and out.stat().st_size > 0:
        return out
    frames = sorted(frames_dir.glob(f"{video_stem}_f*.jpg"))
    if not frames:
        raise RuntimeError(f"no frames for {video_stem}")
    ff.hstack_frames(frames, out, each_w=each_w)
    return out


# ---------- optional: Claude vision auto-tagging ----------

VISION_PROMPT = """你正在整理一个短视频的素材库。下面是一段视频的 3 张关键帧（按时间顺序：开头/中间/结尾）。

请返回 **严格的 JSON**（不要带 markdown 代码块），字段如下：

{
  "scene": "一句话场景概括（中文，<=20字）",
  "description": "更详细的画面描述（中文，<=60字，提到地貌/物体/人/动作）",
  "tags": ["1-6 个简短中文标签"],
  "usable": true,
  "highlight": false,
  "reason": ""
}

usable=false 时，reason 写明原因（抖动/糊/截屏/无关）。
highlight=true 表示这段是"封面级"的精彩镜头。
"""


def _encode_image(path: Path) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.standard_b64encode(path.read_bytes()).decode("ascii"),
        },
    }


def _describe_via_api(client, model: str, frames: list[Path]) -> dict:
    content: list = [_encode_image(fp) for fp in frames]
    content.append({"type": "text", "text": VISION_PROMPT})
    resp = client.messages.create(
        model=model,
        max_tokens=600,
        messages=[{"role": "user", "content": content}],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


# ---------- main pipeline ----------

def _list_videos(src: Path) -> list[Path]:
    return sorted(p for p in src.iterdir()
                  if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS)


def _load_existing(index_path: Path) -> dict[str, dict]:
    if not index_path.exists():
        return {}
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return {r["file"]: r for r in data if isinstance(r, dict) and "file" in r}
    except Exception:
        return {}


def _save_index(index_path: Path, records: list[dict]) -> None:
    records_sorted = sorted(records, key=lambda r: r["file"])
    index_path.write_text(
        json.dumps(records_sorted, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _run(src: Path, out_dir: Path, describe: str, model: str,
         workers: int, force: bool, frame_w: int, sheet_w: int) -> None:
    frames_dir = out_dir / "frames"
    sheets_dir = out_dir / "sheets"
    index_path = out_dir / "assets_index.json"

    videos = _list_videos(src)
    if not videos:
        print(f"no videos found in {src}", file=sys.stderr)
        return
    print(f"Found {len(videos)} clips in {src}")

    existing = {} if force else _load_existing(index_path)
    records: list[dict] = []
    todo: list[Path] = []

    for v in videos:
        prev = existing.get(v.name)
        if prev and not prev.get("error"):
            records.append(prev)
        else:
            todo.append(v)

    print(f"To process: {len(todo)} (cached: {len(videos) - len(todo)})")

    # Step 1: deterministic — probe + frames + sheet
    for i, v in enumerate(todo, 1):
        try:
            rec = _probe_record(v, frames_dir, frame_w)
            _build_sheet(v.stem, frames_dir, sheets_dir, sheet_w)
            records.append(rec)
            print(f"[{i}/{len(todo)}] {v.name} probed ({rec['duration']:.1f}s, "
                  f"{rec['width']}x{rec['height']}, {rec['orientation']})")
        except Exception as e:  # keep going on a single bad clip
            records.append({"file": v.name, "error": str(e), "usable": False})
            print(f"[{i}/{len(todo)}] {v.name} FAILED: {e}", file=sys.stderr)
        _save_index(index_path, records)

    # Step 2: optional — vision tagging
    if describe == "api" and todo:
        try:
            import anthropic  # noqa: WPS433
        except ImportError:
            print("anthropic SDK not installed; skipping --describe api", file=sys.stderr)
            return

        client = anthropic.Anthropic()
        rec_by_file = {r["file"]: r for r in records}

        def _describe_one(video: Path) -> tuple[str, dict | Exception]:
            try:
                frames = sorted(frames_dir.glob(f"{video.stem}_f*.jpg"))
                desc = _describe_via_api(client, model, frames)
                return video.name, desc
            except Exception as e:
                return video.name, e

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_describe_one, v): v for v in todo}
            done = 0
            for fut in as_completed(futures):
                name, result = fut.result()
                done += 1
                if isinstance(result, Exception):
                    rec_by_file[name].setdefault("error", str(result))
                    print(f"[{done}/{len(todo)}] {name} describe FAILED: {result}",
                          file=sys.stderr)
                else:
                    rec_by_file[name].update(result)
                    print(f"[{done}/{len(todo)}] {name} → {result.get('scene', '?')}")
                _save_index(index_path, list(rec_by_file.values()))

    print(f"\nWrote {index_path}")
    print(f"Sheets at {sheets_dir} (one .jpg per clip — review with the Read tool)")


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vlog-cut-index", description=__doc__.splitlines()[0])
    p.add_argument("--src", required=True, type=Path, help="source folder of clips")
    p.add_argument("--out", required=True, type=Path, help="output directory")
    p.add_argument("--describe", choices=["off", "api"], default="off",
                   help="off = metadata+sheets only (default); api = also call Anthropic vision")
    p.add_argument("--model", default=os.environ.get("VISION_MODEL", "claude-sonnet-4-5"),
                   help="vision model id (only used when --describe api)")
    p.add_argument("--workers", type=int, default=4, help="vision API concurrency")
    p.add_argument("--force", action="store_true", help="ignore cached records and rerun")
    p.add_argument("--frame-width", type=int, default=DEFAULT_FRAME_WIDTH,
                   help="extracted keyframe width (px)")
    p.add_argument("--sheet-width", type=int, default=DEFAULT_SHEET_WIDTH,
                   help="per-frame width inside contact sheet (px)")
    args = p.parse_args(argv)

    if not args.src.is_dir():
        print(f"src not a directory: {args.src}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)

    _run(args.src, args.out, args.describe, args.model, args.workers,
         args.force, args.frame_width, args.sheet_width)
    return 0


if __name__ == "__main__":
    sys.exit(cli())

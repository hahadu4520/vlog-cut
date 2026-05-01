"""narration-cut plan: deterministic baseline shot allocator.

Reads timing.json + assets_index.json, emits a draft timeline.json (matching
shared/schemas/timeline.schema.json). The algorithm is intentionally simple — it
exists so a non-LLM run still produces *something*. In a normal pipeline, Claude
will read this draft, swap shots around, and rewrite the file before validate/render.

Algorithm per line:
  1. Score every usable clip by:
       + section/chapter match  (+5)
       + tag overlap with section/title  (+1 per match)
       + highlight bonus  (+2)
       - already-used penalty  (-3 per prior use, encourages variety)
  2. Pick top clips greedily until covered_dur >= line.duration.
  3. Each shot trims the clip starting at `in=0.0` for `dur=min(remaining, clip.duration)`.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


DEFAULT_FPS = 30
DEFAULT_SIZE = "1920x1080"
MIN_SHOT = 1.2     # don't make shots shorter than this if we can help it
MAX_SHOT = 6.0     # cap a single shot at this length


def _is_usable(clip: dict) -> bool:
    u = clip.get("usable", True)
    if u is False:
        return False
    return True  # True or "marginal"


def _score(clip: dict, section: str, title: str, used: Counter[str]) -> float:
    s = 0.0
    chapters = clip.get("chapters") or []
    if section in chapters:
        s += 5
    tags = [t.lower() for t in (clip.get("tags") or [])]
    haystack = (section + " " + title).lower()
    for t in tags:
        if t and t in haystack:
            s += 1
    if clip.get("highlight"):
        s += 2
    if clip.get("usable") == "marginal":
        s -= 1
    s -= 3 * used[clip["file"]]
    return s


def _pick_shots(line: dict, clips: list[dict], used: Counter[str],
                title_by_section: dict[str, str]) -> list[dict]:
    target = line["duration"]
    section = line.get("section", "")
    title = title_by_section.get(section, "")

    pool = sorted(
        ((c, _score(c, section, title, used)) for c in clips if _is_usable(c)),
        key=lambda t: t[1],
        reverse=True,
    )

    shots: list[dict] = []
    remaining = target
    for clip, score in pool:
        if remaining <= 0.05:
            break
        cap = min(MAX_SHOT, float(clip.get("duration", MAX_SHOT)))
        # take MIN_SHOT (or remaining if smaller), bounded by cap
        take = min(cap, max(MIN_SHOT, remaining))
        if take > remaining:
            take = remaining
        if take < 0.4:
            continue
        shots.append({
            "file": clip["file"],
            "in": 0.0,
            "dur": round(take, 3),
            "why": f"score={score:.1f} {clip.get('scene','')}".strip(),
        })
        used[clip["file"]] += 1
        remaining -= take

    if not shots and pool:
        # fall back: at least put one shot
        clip, score = pool[0]
        shots.append({
            "file": clip["file"],
            "in": 0.0,
            "dur": round(min(target, float(clip.get("duration", target))), 3),
            "why": f"fallback score={score:.1f}",
        })
        used[clip["file"]] += 1

    return shots


def _run(timing: dict, assets: list[dict], size: str, fps: int) -> dict:
    title_by_section: dict[str, str] = {}
    for ln in timing["lines"]:
        sec = ln.get("section", "")
        if sec and sec not in title_by_section:
            title_by_section[sec] = ln.get("section_title", "")

    used: Counter[str] = Counter()
    out_lines = []
    for ln in timing["lines"]:
        shots = _pick_shots(ln, assets, used, title_by_section)
        out_lines.append({
            "id": ln["id"],
            "text": ln["text"],
            "duration": ln["duration"],
            "shots": shots,
        })

    return {
        "video_total": timing["total_duration"],
        "fps": fps,
        "size": size,
        "notes": "draft from narration-cut.plan; review before rendering",
        "lines": out_lines,
    }


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vlog-cut-plan", description=__doc__.splitlines()[0])
    p.add_argument("--timing", required=True, type=Path, help="path to timing.json")
    p.add_argument("--assets", required=True, type=Path, help="path to assets_index.json")
    p.add_argument("--out", required=True, type=Path, help="path to timeline.json (will be written)")
    p.add_argument("--size", default=DEFAULT_SIZE, help=f"output size, default {DEFAULT_SIZE}")
    p.add_argument("--fps", type=int, default=DEFAULT_FPS, help=f"output fps, default {DEFAULT_FPS}")
    args = p.parse_args(argv)

    if not args.timing.exists():
        print(f"timing not found: {args.timing}", file=sys.stderr)
        return 2
    if not args.assets.exists():
        print(f"assets index not found: {args.assets}", file=sys.stderr)
        return 2

    timing = json.loads(args.timing.read_text(encoding="utf-8"))
    assets = json.loads(args.assets.read_text(encoding="utf-8"))
    if not isinstance(assets, list):
        print("assets_index.json must be a JSON array", file=sys.stderr)
        return 2

    timeline = _run(timing, assets, args.size, args.fps)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    n_shots = sum(len(l["shots"]) for l in timeline["lines"])
    print(f"Wrote {args.out}: {len(timeline['lines'])} lines, {n_shots} shots")
    return 0


if __name__ == "__main__":
    sys.exit(cli())

"""narration-cut validate: structural + temporal sanity check on timeline.json.

Checks:
  - timeline.json conforms to shared/schemas/timeline.schema.json (light structural check)
  - every shot.file exists in the source folder
  - shot.in + shot.dur <= source clip duration (probed)
  - sum(shots.dur) per line >= line.duration (else audio will outrun video)
  - sum of line.duration roughly matches video_total
  - line ids match timing.json (if --timing supplied)

Exits 0 on clean, 1 on warnings only, 2 on errors.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from shared import ffmpeg_helpers as ff


REQUIRED_TOP = {"video_total", "fps", "size", "lines"}
REQUIRED_LINE = {"id", "text", "duration", "shots"}
REQUIRED_SHOT = {"file", "in", "dur"}
EPS_LINE = 0.05      # tolerance for "shots cover line" check
EPS_TOTAL = 0.5      # tolerance for video_total vs sum(line.duration)


def _ok(msg: str) -> None:
    print(f"  ok   {msg}")


def _warn(msg: str, warnings: list[str]) -> None:
    warnings.append(msg)
    print(f"  WARN {msg}", file=sys.stderr)


def _err(msg: str, errors: list[str]) -> None:
    errors.append(msg)
    print(f"  ERR  {msg}", file=sys.stderr)


def _validate(timeline: dict, src: Path, timing: dict | None,
              errors: list[str], warnings: list[str]) -> None:
    # structural
    missing = REQUIRED_TOP - set(timeline)
    if missing:
        _err(f"top-level missing keys: {sorted(missing)}", errors)
        return
    lines = timeline["lines"]
    if not isinstance(lines, list) or not lines:
        _err("`lines` must be a non-empty array", errors)
        return

    # source-duration cache
    src_dur: dict[str, float] = {}

    def _src(name: str) -> float | None:
        if name not in src_dur:
            p = src / name
            if not p.exists():
                return None
            try:
                src_dur[name] = ff.duration(p)
            except Exception as e:  # broken file
                _err(f"could not probe {name}: {e}", errors)
                src_dur[name] = -1.0
        return src_dur[name] if src_dur[name] >= 0 else None

    # per-line checks
    sum_line_dur = 0.0
    seen_ids: set[str] = set()
    for i, ln in enumerate(lines):
        m = REQUIRED_LINE - set(ln)
        if m:
            _err(f"line[{i}] missing keys: {sorted(m)}", errors)
            continue
        lid = ln["id"]
        if lid in seen_ids:
            _err(f"duplicate line id: {lid}", errors)
        seen_ids.add(lid)
        ldur = float(ln["duration"])
        sum_line_dur += ldur

        if not isinstance(ln["shots"], list) or not ln["shots"]:
            _err(f"line {lid}: empty shots", errors)
            continue

        shot_sum = 0.0
        for j, sh in enumerate(ln["shots"]):
            sm = REQUIRED_SHOT - set(sh)
            if sm:
                _err(f"line {lid} shot[{j}] missing: {sorted(sm)}", errors)
                continue
            f = sh["file"]
            sin = float(sh["in"])
            sdur = float(sh["dur"])
            if sin < 0 or sdur <= 0:
                _err(f"line {lid} shot[{j}]: bad in={sin} dur={sdur}", errors)
                continue
            sd = _src(f)
            if sd is None:
                _err(f"line {lid} shot[{j}]: source missing → {f}", errors)
            elif sin + sdur > sd + 0.05:
                _err(f"line {lid} shot[{j}]: in+dur ({sin+sdur:.2f}) exceeds "
                     f"source {f} ({sd:.2f})", errors)
            shot_sum += sdur

        if shot_sum + EPS_LINE < ldur:
            _warn(f"line {lid}: shots cover {shot_sum:.2f}s but audio is "
                  f"{ldur:.2f}s (video will end before audio)", warnings)

    if abs(sum_line_dur - float(timeline["video_total"])) > EPS_TOTAL:
        _warn(f"sum of line.duration={sum_line_dur:.2f} but video_total="
              f"{timeline['video_total']:.2f}", warnings)

    if timing is not None:
        timing_ids = {l["id"] for l in timing["lines"]}
        if seen_ids != timing_ids:
            extra = seen_ids - timing_ids
            missing = timing_ids - seen_ids
            if extra:
                _err(f"timeline has line ids not in timing: {sorted(extra)}", errors)
            if missing:
                _err(f"timing has line ids not in timeline: {sorted(missing)}", errors)


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vlog-cut-validate", description=__doc__.splitlines()[0])
    p.add_argument("--timeline", required=True, type=Path)
    p.add_argument("--src", required=True, type=Path,
                   help="folder containing the source clips referenced in timeline")
    p.add_argument("--timing", type=Path, default=None,
                   help="optional: timing.json to cross-check line ids")
    args = p.parse_args(argv)

    if not args.timeline.exists():
        print(f"timeline not found: {args.timeline}", file=sys.stderr)
        return 2
    if not args.src.is_dir():
        print(f"src not a directory: {args.src}", file=sys.stderr)
        return 2

    timeline = json.loads(args.timeline.read_text(encoding="utf-8"))
    timing = None
    if args.timing is not None:
        if not args.timing.exists():
            print(f"timing not found: {args.timing}", file=sys.stderr)
            return 2
        timing = json.loads(args.timing.read_text(encoding="utf-8"))

    print(f"Validating {args.timeline}")
    print(f"  src: {args.src}")
    errors: list[str] = []
    warnings: list[str] = []
    _validate(timeline, args.src, timing, errors, warnings)

    print()
    print(f"errors: {len(errors)}  warnings: {len(warnings)}")
    if errors:
        return 2
    if warnings:
        return 1
    print("clean.")
    return 0


if __name__ == "__main__":
    sys.exit(cli())

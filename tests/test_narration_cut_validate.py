"""narration-cut.validate tests — exit codes 0/1/2 across error/warning conditions."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from skills.narration_cut import validate as val_mod


def _good_timeline(timing_two_lines):
    return {
        "video_total": timing_two_lines["total_duration"],
        "fps": 30,
        "size": "1920x1080",
        "lines": [
            {
                "id": "intro_00", "text": "第一句。", "duration": 2.5,
                "shots": [{"file": "a.mp4", "in": 0.0, "dur": 2.75}],
            },
            {
                "id": "intro_01", "text": "第二句。", "duration": 2.7,
                "shots": [{"file": "b.mp4", "in": 0.0, "dur": 3.25}],
            },
        ],
    }


def test_clean_returns_0(tmp_path, write_json, clip_pool, timing_two_lines):
    tl = _good_timeline(timing_two_lines)
    # bump video_total to match line.duration sum exactly so no warning fires
    tl["video_total"] = round(sum(l["duration"] for l in tl["lines"]), 3)
    tl_p = write_json(tmp_path / "timeline.json", tl)
    rc = val_mod.cli(["--timeline", str(tl_p), "--src", str(clip_pool)])
    assert rc == 0


def test_warning_when_video_total_mismatch(tmp_path, write_json, clip_pool, timing_two_lines):
    tl = _good_timeline(timing_two_lines)  # video_total=6.0, sum=5.2 → warning
    tl_p = write_json(tmp_path / "timeline.json", tl)
    rc = val_mod.cli(["--timeline", str(tl_p), "--src", str(clip_pool)])
    assert rc == 1


def test_warning_when_shots_underrun_line(tmp_path, write_json, clip_pool, timing_two_lines):
    tl = _good_timeline(timing_two_lines)
    tl["video_total"] = sum(l["duration"] for l in tl["lines"])
    tl["lines"][0]["shots"][0]["dur"] = 0.5  # way less than line.duration=2.5
    tl_p = write_json(tmp_path / "timeline.json", tl)
    rc = val_mod.cli(["--timeline", str(tl_p), "--src", str(clip_pool)])
    assert rc == 1


def test_error_when_source_missing(tmp_path, write_json, clip_pool, timing_two_lines):
    tl = _good_timeline(timing_two_lines)
    tl["lines"][0]["shots"][0]["file"] = "missing.mp4"
    tl_p = write_json(tmp_path / "timeline.json", tl)
    rc = val_mod.cli(["--timeline", str(tl_p), "--src", str(clip_pool)])
    assert rc == 2


def test_error_when_in_dur_exceeds_source(tmp_path, write_json, clip_pool, timing_two_lines):
    tl = _good_timeline(timing_two_lines)
    tl["lines"][0]["shots"][0]["in"] = 100.0  # way past clip end
    tl_p = write_json(tmp_path / "timeline.json", tl)
    rc = val_mod.cli(["--timeline", str(tl_p), "--src", str(clip_pool)])
    assert rc == 2


def test_error_on_missing_top_keys(tmp_path, write_json, clip_pool):
    tl = {"lines": []}  # missing video_total / fps / size + empty lines
    tl_p = write_json(tmp_path / "timeline.json", tl)
    rc = val_mod.cli(["--timeline", str(tl_p), "--src", str(clip_pool)])
    assert rc == 2


def test_error_on_duplicate_line_ids(tmp_path, write_json, clip_pool, timing_two_lines):
    tl = _good_timeline(timing_two_lines)
    tl["video_total"] = sum(l["duration"] for l in tl["lines"])
    tl["lines"][1]["id"] = tl["lines"][0]["id"]  # duplicate
    tl_p = write_json(tmp_path / "timeline.json", tl)
    rc = val_mod.cli(["--timeline", str(tl_p), "--src", str(clip_pool)])
    assert rc == 2


def test_error_on_empty_shots(tmp_path, write_json, clip_pool, timing_two_lines):
    tl = _good_timeline(timing_two_lines)
    tl["video_total"] = sum(l["duration"] for l in tl["lines"])
    tl["lines"][0]["shots"] = []
    tl_p = write_json(tmp_path / "timeline.json", tl)
    rc = val_mod.cli(["--timeline", str(tl_p), "--src", str(clip_pool)])
    assert rc == 2


def test_timing_id_mismatch_is_error(tmp_path, write_json, clip_pool, timing_two_lines):
    tl = _good_timeline(timing_two_lines)
    tl["video_total"] = sum(l["duration"] for l in tl["lines"])
    timing = deepcopy(timing_two_lines)
    timing["lines"][0]["id"] = "different_id"  # mismatch
    timing_p = write_json(tmp_path / "timing.json", timing)
    tl_p = write_json(tmp_path / "timeline.json", tl)
    rc = val_mod.cli([
        "--timeline", str(tl_p),
        "--src", str(clip_pool),
        "--timing", str(timing_p),
    ])
    assert rc == 2


def test_missing_files_return_2(tmp_path):
    rc = val_mod.cli(["--timeline", str(tmp_path / "nope.json"),
                      "--src", str(tmp_path)])
    assert rc == 2

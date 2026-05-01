"""narration-cut.plan tests — algorithm behavior on small fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skills.narration_cut import plan as plan_mod


def _run(tmp_path, write_json, timing, assets):
    timing_p = write_json(tmp_path / "timing.json", timing)
    assets_p = write_json(tmp_path / "assets.json", assets)
    out_p = tmp_path / "timeline.json"
    rc = plan_mod.cli([
        "--timing", str(timing_p),
        "--assets", str(assets_p),
        "--out", str(out_p),
        "--size", "1280x720",
        "--fps", "24",
    ])
    assert rc == 0
    return json.loads(out_p.read_text(encoding="utf-8"))


def test_basic_shape(tmp_path, write_json, timing_two_lines, assets_three):
    tl = _run(tmp_path, write_json, timing_two_lines, assets_three)
    assert tl["video_total"] == timing_two_lines["total_duration"]
    assert tl["fps"] == 24
    assert tl["size"] == "1280x720"
    assert len(tl["lines"]) == len(timing_two_lines["lines"])
    for ln in tl["lines"]:
        assert ln["shots"], "every line should get at least one shot"
        for s in ln["shots"]:
            assert s["dur"] > 0
            assert s["in"] >= 0
            assert "file" in s


def test_unusable_clips_excluded(tmp_path, write_json, timing_two_lines, assets_three):
    tl = _run(tmp_path, write_json, timing_two_lines, assets_three)
    used_files = {s["file"] for ln in tl["lines"] for s in ln["shots"]}
    assert "c.mp4" not in used_files, "usable=false clips must not be picked"


def test_chapter_match_outscores_no_match(tmp_path, write_json, timing_two_lines):
    """A clip that lists the section in chapters should beat a clip that doesn't."""
    assets = [
        {"file": "match.mp4", "duration": 5.0, "width": 1920, "height": 1080,
         "fps": 30, "rotation": None, "orientation": "landscape",
         "chapters": ["intro"], "tags": [], "usable": True},
        {"file": "nomatch.mp4", "duration": 5.0, "width": 1920, "height": 1080,
         "fps": 30, "rotation": None, "orientation": "landscape",
         "chapters": ["other"], "tags": [], "usable": True},
    ]
    # Single-line timing so we don't trigger the "already used" penalty
    timing = {
        "voice": "v", "rate": "+0%", "total_duration": 2.0,
        "lines": [{"id": "intro_00", "section": "intro", "section_title": "引子",
                   "text": "x", "file": "tts/intro_00.mp3",
                   "duration": 2.0, "start": 0.0, "end": 2.0}],
    }
    tl = _run(tmp_path, write_json, timing, assets)
    assert tl["lines"][0]["shots"][0]["file"] == "match.mp4"


def test_highlight_bonus(tmp_path, write_json):
    """All-else-equal, highlight=True wins."""
    assets = [
        {"file": "plain.mp4", "duration": 3.0, "width": 1920, "height": 1080,
         "fps": 30, "rotation": None, "orientation": "landscape",
         "chapters": ["intro"], "tags": [], "usable": True},
        {"file": "hero.mp4", "duration": 3.0, "width": 1920, "height": 1080,
         "fps": 30, "rotation": None, "orientation": "landscape",
         "chapters": ["intro"], "tags": [], "usable": True, "highlight": True},
    ]
    timing = {
        "voice": "v", "rate": "+0%", "total_duration": 2.0,
        "lines": [{"id": "intro_00", "section": "intro", "section_title": "引子",
                   "text": "x", "file": "tts/intro_00.mp3",
                   "duration": 2.0, "start": 0.0, "end": 2.0}],
    }
    tl = _run(tmp_path, write_json, timing, assets)
    assert tl["lines"][0]["shots"][0]["file"] == "hero.mp4"


def test_already_used_penalty_encourages_variety(tmp_path, write_json):
    """Across many lines, the planner should rotate clips when alternatives exist
    with comparable score."""
    # Two equally-tagged clips, both chapter-matched. Score gap is just the highlight,
    # so once 'a' is used twice, 'b' should beat it.
    assets = [
        {"file": "a.mp4", "duration": 5.0, "width": 1920, "height": 1080,
         "fps": 30, "rotation": None, "orientation": "landscape",
         "chapters": ["s"], "tags": [], "usable": True, "highlight": True},
        {"file": "b.mp4", "duration": 5.0, "width": 1920, "height": 1080,
         "fps": 30, "rotation": None, "orientation": "landscape",
         "chapters": ["s"], "tags": [], "usable": True},
    ]
    lines = []
    cursor = 0.0
    for i in range(4):
        lines.append({
            "id": f"s_{i:02d}", "section": "s", "section_title": "S",
            "text": "x", "file": f"tts/s_{i:02d}.mp3",
            "duration": 1.5, "start": cursor, "end": cursor + 1.5,
        })
        cursor += 1.75
    timing = {"voice": "v", "rate": "+0%", "total_duration": cursor, "lines": lines}
    tl = _run(tmp_path, write_json, timing, assets)
    files = [ln["shots"][0]["file"] for ln in tl["lines"]]
    # both clips should appear at least once
    assert "a.mp4" in files
    assert "b.mp4" in files


def test_shots_cover_line_duration(tmp_path, write_json, timing_two_lines, assets_three):
    """sum(shots.dur) per line must >= line.duration so audio doesn't outrun video."""
    tl = _run(tmp_path, write_json, timing_two_lines, assets_three)
    for ln in tl["lines"]:
        shot_sum = sum(s["dur"] for s in ln["shots"])
        # plan emits shots clamped to [MIN_SHOT, MAX_SHOT]; a single-line ≤ MAX_SHOT
        # and ≥ MIN_SHOT or = remaining → coverage should be exact-ish.
        assert shot_sum >= ln["duration"] - 0.05


def test_missing_inputs_return_2(tmp_path):
    rc = plan_mod.cli(["--timing", str(tmp_path / "nope.json"),
                       "--assets", str(tmp_path / "nope2.json"),
                       "--out", str(tmp_path / "out.json")])
    assert rc == 2

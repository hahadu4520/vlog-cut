"""Integration: index → plan → validate → render, end to end with real ffmpeg.

Skips TTS (mocked elsewhere) — we feed in a hand-built timing.json + narration.wav.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared import ffmpeg_helpers as ff
from skills.video_asset_index import index as idx_mod
from skills.narration_cut import plan as plan_mod
from skills.narration_cut import validate as val_mod
from skills.narration_cut import render as render_mod


def test_full_pipeline(tmp_path, clip_pool, timing_two_lines, write_json,
                      make_silent_audio_factory):
    project = tmp_path / "proj"
    project.mkdir()

    # Stage A — narration: pretend tts already ran
    timing_p = write_json(project / "timing.json", timing_two_lines)
    narration = make_silent_audio_factory(project / "narration.wav",
                                          duration=timing_two_lines["total_duration"])

    # Stage B — index
    rc = idx_mod.cli(["--src", str(clip_pool), "--out", str(project)])
    assert rc == 0
    idx = json.loads((project / "assets_index.json").read_text(encoding="utf-8"))
    # add chapters/usable so plan can pick them
    for rec in idx:
        rec["chapters"] = ["intro"]
        rec["usable"] = True
    write_json(project / "assets_index.json", idx)

    # Stage C — plan + validate
    rc = plan_mod.cli([
        "--timing", str(project / "timing.json"),
        "--assets", str(project / "assets_index.json"),
        "--out", str(project / "timeline.json"),
        "--size", "640x360", "--fps", "30",
    ])
    assert rc == 0

    rc = val_mod.cli([
        "--timeline", str(project / "timeline.json"),
        "--src", str(clip_pool),
        "--timing", str(project / "timing.json"),
    ])
    # exit 1 acceptable (warning about video_total > sum line.duration is expected,
    # since narration has gaps the planner doesn't account for)
    assert rc in (0, 1)

    # Stage D — render
    rc = render_mod.cli([
        "--timeline", str(project / "timeline.json"),
        "--timing", str(project / "timing.json"),
        "--src", str(clip_pool),
        "--narration", str(narration),
        "--out", str(project),
        "--name", "rough_cut.mp4",
    ])
    assert rc == 0

    final = project / "rough_cut.mp4"
    assert final.exists() and final.stat().st_size > 0
    info = ff.probe(final)
    # Final should match narration duration within a frame or two
    assert abs(info["duration"] - timing_two_lines["total_duration"]) < 0.2

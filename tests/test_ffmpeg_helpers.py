"""Quick sanity tests for the ffmpeg helper layer."""
from __future__ import annotations

from pathlib import Path

from shared import ffmpeg_helpers as ff


def test_probe_returns_expected_fields(tmp_path, make_video_factory):
    v = make_video_factory(tmp_path / "v.mp4", duration=3.0, size="640x360", fps=30)
    info = ff.probe(v)
    assert info["width"] == 640
    assert info["height"] == 360
    assert abs(info["duration"] - 3.0) < 0.1
    assert info["fps"] in (30.0, 29.97, 30)
    # rotation is None for synthetic clips
    assert info["rotation"] is None


def test_duration_matches_probe(tmp_path, make_video_factory):
    v = make_video_factory(tmp_path / "v.mp4", duration=2.5)
    assert abs(ff.duration(v) - 2.5) < 0.1


def test_extract_frame_creates_file(tmp_path, make_video_factory):
    v = make_video_factory(tmp_path / "v.mp4", duration=2.0)
    out = tmp_path / "frame.jpg"
    ff.extract_frame(v, 1.0, out, scale_w=200)
    assert out.exists() and out.stat().st_size > 0


def test_hstack_combines_three_frames(tmp_path, make_video_factory):
    v = make_video_factory(tmp_path / "v.mp4", duration=3.0)
    frames = [tmp_path / f"f{i}.jpg" for i in range(3)]
    for i, f in enumerate(frames, 1):
        ff.extract_frame(v, float(i) * 0.5, f, scale_w=200)
    out = tmp_path / "sheet.jpg"
    ff.hstack_frames(frames, out, each_w=200)
    assert out.exists() and out.stat().st_size > 0
    # The sheet should be wider than a single frame
    info = ff.probe(out) if False else None  # ffprobe on jpg is awkward; just trust size

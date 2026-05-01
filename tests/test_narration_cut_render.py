"""narration-cut.render tests — verify segment cutting, gap absorption, tpad freeze, mux."""
from __future__ import annotations

from pathlib import Path

import pytest

from shared import ffmpeg_helpers as ff
from skills.narration_cut import render as render_mod


def _build_inputs(tmp_path, write_json, timing, timeline,
                  make_video, make_audio, *, clip_dur=4.0):
    src = tmp_path / "clips"
    files = {s["file"] for ln in timeline["lines"] for s in ln["shots"]}
    for f in files:
        make_video(src / f, duration=clip_dur)
    narration = make_audio(tmp_path / "narration.wav",
                           duration=timing["total_duration"])
    timing_p = write_json(tmp_path / "timing.json", timing)
    tl_p = write_json(tmp_path / "timeline.json", timeline)
    return src, narration, timing_p, tl_p


def test_render_produces_final_mp4(tmp_path, write_json,
                                    make_video_factory, make_silent_audio_factory):
    timing = {
        "voice": "v", "rate": "+0%", "total_duration": 4.0,
        "lines": [
            {"id": "a_00", "section": "a", "section_title": "A",
             "text": "x", "file": "tts/a_00.mp3",
             "duration": 2.0, "start": 0.0, "end": 2.0},
            {"id": "a_01", "section": "a", "section_title": "A",
             "text": "y", "file": "tts/a_01.mp3",
             "duration": 1.5, "start": 2.25, "end": 3.75},
        ],
    }
    timeline = {
        "video_total": 4.0, "fps": 30, "size": "640x360",
        "lines": [
            {"id": "a_00", "text": "x", "duration": 2.0,
             "shots": [{"file": "a.mp4", "in": 0.0, "dur": 2.0}]},
            {"id": "a_01", "text": "y", "duration": 1.5,
             "shots": [{"file": "b.mp4", "in": 0.0, "dur": 1.5}]},
        ],
    }
    src, narration, timing_p, tl_p = _build_inputs(
        tmp_path, write_json, timing, timeline,
        make_video_factory, make_silent_audio_factory)
    out = tmp_path / "out"
    rc = render_mod.cli([
        "--timeline", str(tl_p),
        "--timing", str(timing_p),
        "--src", str(src),
        "--narration", str(narration),
        "--out", str(out),
        "--name", "rough.mp4",
    ])
    assert rc == 0
    final = out / "rough.mp4"
    assert final.exists() and final.stat().st_size > 0
    info = ff.probe(final)
    assert info["width"] == 640
    assert info["height"] == 360
    assert abs(info["duration"] - timing["total_duration"]) < 0.15


def test_size_overrides_timeline(tmp_path, write_json,
                                  make_video_factory, make_silent_audio_factory):
    timing = {
        "voice": "v", "rate": "+0%", "total_duration": 2.0,
        "lines": [{"id": "a_00", "section": "a", "section_title": "A",
                   "text": "x", "file": "tts/a_00.mp3",
                   "duration": 2.0, "start": 0.0, "end": 2.0}],
    }
    timeline = {
        "video_total": 2.0, "fps": 30, "size": "640x360",
        "lines": [{"id": "a_00", "text": "x", "duration": 2.0,
                   "shots": [{"file": "a.mp4", "in": 0.0, "dur": 2.0}]}],
    }
    src, narration, timing_p, tl_p = _build_inputs(
        tmp_path, write_json, timing, timeline,
        make_video_factory, make_silent_audio_factory)
    out = tmp_path / "out"
    render_mod.cli([
        "--timeline", str(tl_p), "--timing", str(timing_p),
        "--src", str(src), "--narration", str(narration),
        "--out", str(out), "--size", "1280x720",
    ])
    info = ff.probe(out / render_mod.DEFAULT_FINAL)
    assert info["width"] == 1280
    assert info["height"] == 720


def test_gap_absorbed_by_extending_last_shot(tmp_path, write_json,
                                              make_video_factory,
                                              make_silent_audio_factory):
    """When the last shot has source room, gap is added to its dur (no freeze)."""
    timing = {
        "voice": "v", "rate": "+0%", "total_duration": 5.0,
        "lines": [
            {"id": "a_00", "section": "a", "section_title": "A",
             "text": "x", "file": "tts/a_00.mp3",
             "duration": 2.0, "start": 0.0, "end": 2.0},
            # second line starts at 2.25 → 0.25s gap to absorb
            {"id": "a_01", "section": "a", "section_title": "A",
             "text": "y", "file": "tts/a_01.mp3",
             "duration": 2.5, "start": 2.25, "end": 4.75},
        ],
    }
    timeline = {
        "video_total": 5.0, "fps": 30, "size": "640x360",
        "lines": [
            {"id": "a_00", "text": "x", "duration": 2.0,
             "shots": [{"file": "a.mp4", "in": 0.0, "dur": 2.0}]},
            {"id": "a_01", "text": "y", "duration": 2.5,
             "shots": [{"file": "b.mp4", "in": 0.0, "dur": 2.5}]},
        ],
    }
    src, narration, timing_p, tl_p = _build_inputs(
        tmp_path, write_json, timing, timeline,
        make_video_factory, make_silent_audio_factory, clip_dur=4.0)
    out = tmp_path / "out"
    render_mod.cli([
        "--timeline", str(tl_p), "--timing", str(timing_p),
        "--src", str(src), "--narration", str(narration), "--out", str(out),
    ])
    seg0 = next((out / "segs").glob("000_*.mp4"))
    seg1 = next((out / "segs").glob("001_*.mp4"))
    # First seg = line.dur (2.0) + gap absorbed (0.25) = 2.25s
    assert abs(ff.duration(seg0) - 2.25) < 0.1
    # Last seg = line.dur (2.5) + trailing extension to fill total
    # Total video must == narration total (5.0) → seg1 = 5.0 - 2.25 = 2.75
    assert abs(ff.duration(seg1) - 2.75) < 0.1


def test_gap_absorbed_by_freeze_when_source_too_short(tmp_path, write_json,
                                                       make_video_factory,
                                                       make_silent_audio_factory):
    """If the source can't extend, the renderer should tpad-freeze instead."""
    timing = {
        "voice": "v", "rate": "+0%", "total_duration": 3.0,
        "lines": [
            {"id": "a_00", "section": "a", "section_title": "A",
             "text": "x", "file": "tts/a_00.mp3",
             "duration": 1.0, "start": 0.0, "end": 1.0},
            {"id": "a_01", "section": "a", "section_title": "A",
             "text": "y", "file": "tts/a_01.mp3",
             "duration": 1.5, "start": 1.25, "end": 2.75},
        ],
    }
    timeline = {
        "video_total": 3.0, "fps": 30, "size": "640x360",
        "lines": [
            # shot already consumes the entire 1.0s source — gap of 0.25 must freeze
            {"id": "a_00", "text": "x", "duration": 1.0,
             "shots": [{"file": "a.mp4", "in": 0.0, "dur": 1.0}]},
            {"id": "a_01", "text": "y", "duration": 1.5,
             "shots": [{"file": "b.mp4", "in": 0.0, "dur": 1.5}]},
        ],
    }
    src = tmp_path / "clips"
    make_video_factory(src / "a.mp4", duration=1.0)  # exactly the shot length
    make_video_factory(src / "b.mp4", duration=2.0)  # has room for trailing
    narration = make_silent_audio_factory(tmp_path / "narration.wav", duration=3.0)
    timing_p = write_json(tmp_path / "timing.json", timing)
    tl_p = write_json(tmp_path / "timeline.json", timeline)

    out = tmp_path / "out"
    rc = render_mod.cli([
        "--timeline", str(tl_p), "--timing", str(timing_p),
        "--src", str(src), "--narration", str(narration), "--out", str(out),
    ])
    assert rc == 0
    seg0 = next((out / "segs").glob("000_*.mp4"))
    # seg0 must cover line.dur + gap (1.0 + 0.25 = 1.25) via freeze
    assert abs(ff.duration(seg0) - 1.25) < 0.15


def test_segs_are_cached(tmp_path, write_json,
                          make_video_factory, make_silent_audio_factory):
    timing = {
        "voice": "v", "rate": "+0%", "total_duration": 2.0,
        "lines": [{"id": "a_00", "section": "a", "section_title": "A",
                   "text": "x", "file": "tts/a_00.mp3",
                   "duration": 2.0, "start": 0.0, "end": 2.0}],
    }
    timeline = {
        "video_total": 2.0, "fps": 30, "size": "640x360",
        "lines": [{"id": "a_00", "text": "x", "duration": 2.0,
                   "shots": [{"file": "a.mp4", "in": 0.0, "dur": 2.0}]}],
    }
    src, narration, timing_p, tl_p = _build_inputs(
        tmp_path, write_json, timing, timeline,
        make_video_factory, make_silent_audio_factory)
    out = tmp_path / "out"
    render_mod.cli([
        "--timeline", str(tl_p), "--timing", str(timing_p),
        "--src", str(src), "--narration", str(narration), "--out", str(out),
    ])
    seg = next((out / "segs").glob("000_*.mp4"))
    mtime = seg.stat().st_mtime

    render_mod.cli([
        "--timeline", str(tl_p), "--timing", str(timing_p),
        "--src", str(src), "--narration", str(narration), "--out", str(out),
    ])
    assert seg.stat().st_mtime == mtime, "cached seg should not re-encode"


def test_cache_invalidates_when_dur_changes(tmp_path, write_json,
                                              make_video_factory,
                                              make_silent_audio_factory):
    """Regression: editing a shot's `dur` (without changing file/lid/idx) must
    NOT reuse the prior cut. Hit on the 散步 vlog: an old shot dur=2.6 silently
    survived a timeline edit that asked for dur=3.5, leaving the section short
    and the audio truncated by -shortest at mux time."""
    timing = {
        "voice": "v", "rate": "+0%", "total_duration": 3.0,
        "lines": [{"id": "a_00", "section": "a", "section_title": "A",
                   "text": "x", "file": "tts/a_00.mp3",
                   "duration": 3.0, "start": 0.0, "end": 3.0}],
    }
    src = tmp_path / "clips"
    make_video_factory(src / "a.mp4", duration=5.0)
    narration = make_silent_audio_factory(tmp_path / "narration.wav", duration=3.0)
    timing_p = write_json(tmp_path / "timing.json", timing)
    out = tmp_path / "out"

    # First render with dur=2.0
    tl_v1 = {
        "video_total": 3.0, "fps": 30, "size": "640x360",
        "lines": [{"id": "a_00", "text": "x", "duration": 3.0,
                   "shots": [{"file": "a.mp4", "in": 0.0, "dur": 2.0}]}],
    }
    tl_p = write_json(tmp_path / "timeline.json", tl_v1)
    render_mod.cli(["--timeline", str(tl_p), "--timing", str(timing_p),
                    "--src", str(src), "--narration", str(narration),
                    "--out", str(out)])
    final_v1 = ff.duration(out / render_mod.DEFAULT_FINAL)

    # Now bump dur to 3.0 and re-render — output must be ~3s, not the cached 2s
    tl_v2 = {
        "video_total": 3.0, "fps": 30, "size": "640x360",
        "lines": [{"id": "a_00", "text": "x", "duration": 3.0,
                   "shots": [{"file": "a.mp4", "in": 0.0, "dur": 3.0}]}],
    }
    write_json(tmp_path / "timeline.json", tl_v2)
    # Wipe stitched outputs but KEEP segs/ — that's the cache we're testing
    (out / "video_silent.mp4").unlink(missing_ok=True)
    (out / render_mod.DEFAULT_FINAL).unlink(missing_ok=True)
    (out / "concat_list.txt").unlink(missing_ok=True)
    render_mod.cli(["--timeline", str(tl_p), "--timing", str(timing_p),
                    "--src", str(src), "--narration", str(narration),
                    "--out", str(out)])
    final_v2 = ff.duration(out / render_mod.DEFAULT_FINAL)

    # v2 should be a full 3s, not the 2s that v1's cached seg would've given us
    assert abs(final_v2 - 3.0) < 0.15, \
        f"cache should have invalidated; got {final_v2:.2f}s (was {final_v1:.2f}s in v1)"


def test_render_works_with_relative_paths(tmp_path, write_json, monkeypatch,
                                            make_video_factory,
                                            make_silent_audio_factory):
    """Regression: ffmpeg's concat demuxer resolves relative paths against the
    list-file directory, not cwd. Render must emit absolute paths in the list."""
    timing = {
        "voice": "v", "rate": "+0%", "total_duration": 2.0,
        "lines": [{"id": "a_00", "section": "a", "section_title": "A",
                   "text": "x", "file": "tts/a_00.mp3",
                   "duration": 2.0, "start": 0.0, "end": 2.0}],
    }
    timeline = {
        "video_total": 2.0, "fps": 30, "size": "640x360",
        "lines": [{"id": "a_00", "text": "x", "duration": 2.0,
                   "shots": [{"file": "a.mp4", "in": 0.0, "dur": 2.0}]}],
    }
    src, narration, timing_p, tl_p = _build_inputs(
        tmp_path, write_json, timing, timeline,
        make_video_factory, make_silent_audio_factory)
    out = tmp_path / "out"

    # Run from a totally unrelated cwd, with --out relative to that cwd.
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    rel_out = Path("..") / "out"
    rel_tl = Path("..") / tl_p.relative_to(tmp_path)
    rel_timing = Path("..") / timing_p.relative_to(tmp_path)
    rel_src = Path("..") / src.relative_to(tmp_path)
    rel_narr = Path("..") / narration.relative_to(tmp_path)

    rc = render_mod.cli([
        "--timeline", str(rel_tl),
        "--timing", str(rel_timing),
        "--src", str(rel_src),
        "--narration", str(rel_narr),
        "--out", str(rel_out),
    ])
    assert rc == 0
    final = out / render_mod.DEFAULT_FINAL
    assert final.exists() and final.stat().st_size > 0


def test_render_warns_on_audio_video_mismatch(tmp_path, write_json, capsys,
                                                make_video_factory,
                                                make_silent_audio_factory):
    """Regression: audio that's noticeably longer than video_total should
    trigger a stderr warning before mux silently truncates it via -shortest."""
    timing = {
        "voice": "v", "rate": "+0%", "total_duration": 2.0,
        "lines": [{"id": "a_00", "section": "a", "section_title": "A",
                   "text": "x", "file": "tts/a_00.mp3",
                   "duration": 2.0, "start": 0.0, "end": 2.0}],
    }
    timeline = {
        "video_total": 2.0, "fps": 30, "size": "640x360",
        "lines": [{"id": "a_00", "text": "x", "duration": 2.0,
                   "shots": [{"file": "a.mp4", "in": 0.0, "dur": 2.0}]}],
    }
    src = tmp_path / "clips"
    make_video_factory(src / "a.mp4", duration=4.0)
    # narration is 1.5s LONGER than the video timeline says
    narration = make_silent_audio_factory(tmp_path / "narration.wav", duration=3.5)
    timing_p = write_json(tmp_path / "timing.json", timing)
    tl_p = write_json(tmp_path / "timeline.json", timeline)
    out = tmp_path / "out"

    rc = render_mod.cli([
        "--timeline", str(tl_p), "--timing", str(timing_p),
        "--src", str(src), "--narration", str(narration),
        "--out", str(out),
    ])
    assert rc == 0
    captured = capsys.readouterr()
    # The warning should mention both durations and the truncation risk
    assert "WARN" in captured.err
    assert "truncat" in captured.err.lower()


def test_render_no_warning_when_lengths_match(tmp_path, write_json, capsys,
                                                make_video_factory,
                                                make_silent_audio_factory):
    """Regression complement: don't be a noisy warner when lengths agree."""
    timing = {
        "voice": "v", "rate": "+0%", "total_duration": 2.0,
        "lines": [{"id": "a_00", "section": "a", "section_title": "A",
                   "text": "x", "file": "tts/a_00.mp3",
                   "duration": 2.0, "start": 0.0, "end": 2.0}],
    }
    timeline = {
        "video_total": 2.0, "fps": 30, "size": "640x360",
        "lines": [{"id": "a_00", "text": "x", "duration": 2.0,
                   "shots": [{"file": "a.mp4", "in": 0.0, "dur": 2.0}]}],
    }
    src, narration, timing_p, tl_p = _build_inputs(
        tmp_path, write_json, timing, timeline,
        make_video_factory, make_silent_audio_factory)
    out = tmp_path / "out"
    render_mod.cli([
        "--timeline", str(tl_p), "--timing", str(timing_p),
        "--src", str(src), "--narration", str(narration),
        "--out", str(out),
    ])
    captured = capsys.readouterr()
    assert "WARN" not in captured.err


def test_missing_inputs_return_2(tmp_path):
    rc = render_mod.cli([
        "--timeline", str(tmp_path / "nope.json"),
        "--timing", str(tmp_path / "nope2.json"),
        "--src", str(tmp_path),
        "--narration", str(tmp_path / "nope.wav"),
        "--out", str(tmp_path / "out"),
    ])
    assert rc == 2


def test_size_parser_rejects_bad_input():
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        render_mod._parse_size("not-a-size")

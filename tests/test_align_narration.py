"""align-narration tests.

The whisper subprocess is mocked: instead of running the real CLI we write a
canned segment-level JSON to the expected output path. Audio re-encoding (the
ffmpeg part) runs for real against tiny lavfi-generated audio.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from skills.align_narration import align as align_mod


# A canned whisper output for a 4-section recording.
def _canned_whisper(out_dir: Path, stem: str, segments: list[dict]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{stem}.json"
    p.write_text(json.dumps({
        "language": "Chinese",
        "segments": segments,
    }, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def mock_whisper(monkeypatch):
    """Replace _run_whisper with a function that writes a canned JSON.

    Tests inject the canned segment list via the `segments` attribute on the
    fixture before calling cli().
    """
    state: dict = {"segments": []}

    def fake(audio: Path, out_dir: Path, model: str, language: str) -> Path:
        return _canned_whisper(out_dir, audio.stem, state["segments"])

    monkeypatch.setattr(align_mod, "_run_whisper", fake)
    monkeypatch.setattr(align_mod, "_have", lambda c: True)
    return state


# ---------- helpers ----------

def _make_audio(path: Path, duration: float) -> Path:
    """Generate a silent m4a of given duration via ffmpeg lavfi."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=mono:sample_rate=24000",
        "-t", f"{duration}",
        "-c:a", "aac",
        str(path),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return path


# ---------- tests ----------

def test_no_script_emits_single_line(tmp_path, mock_whisper):
    audio = _make_audio(tmp_path / "rec.m4a", duration=6.0)
    mock_whisper["segments"] = [
        {"start": 0.5, "end": 3.0, "text": "前半段"},
        {"start": 3.0, "end": 5.5, "text": "后半段"},
    ]
    out = tmp_path / "out"
    rc = align_mod.cli(["--audio", str(audio), "--out", str(out)])
    assert rc == 0

    timing = json.loads((out / "timing.json").read_text(encoding="utf-8"))
    assert len(timing["lines"]) == 1
    ln = timing["lines"][0]
    assert ln["id"] == "narration_00"
    assert ln["section"] == "narration"
    assert ln["text"] == "前半段后半段"
    # Should extend to the true audio end (6.0s), not just last segment end (5.5s)
    assert abs(ln["end"] - 6.0) < 0.1
    assert abs(timing["total_duration"] - 6.0) < 0.1


def test_with_script_groups_by_head_text(tmp_path, mock_whisper):
    audio = _make_audio(tmp_path / "rec.m4a", duration=12.0)
    mock_whisper["segments"] = [
        {"start": 0.0, "end": 2.5, "text": "AI越好用我越想出门"},
        {"start": 2.5, "end": 5.0, "text": "下楼是去办事"},
        {"start": 5.0, "end": 8.0, "text": "写代码崩溃的时候"},
        {"start": 8.0, "end": 10.0, "text": "出门遛十分钟"},
        {"start": 10.0, "end": 11.5, "text": "回来就通了"},
    ]
    script = {
        "voice": "user-recorded", "rate": "+0%",
        "sections": [
            {"id": "intro", "title": "钩子", "head_text": "AI越好用",
             "lines": ["AI越好用我越想出门散步", "下楼是去办事"]},
            {"id": "scene", "title": "场景", "head_text": "写代码",
             "lines": ["写代码崩溃...", "出门遛...", "回来就通了"]},
        ],
    }
    script_p = tmp_path / "script.json"
    script_p.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

    out = tmp_path / "out"
    rc = align_mod.cli(["--audio", str(audio), "--out", str(out),
                        "--script", str(script_p)])
    assert rc == 0

    timing = json.loads((out / "timing.json").read_text(encoding="utf-8"))
    assert len(timing["lines"]) == 2
    intro, scene = timing["lines"]

    assert intro["id"] == "intro_00"
    assert intro["section"] == "intro"
    assert intro["section_title"] == "钩子"
    assert intro["start"] == 0.0
    assert intro["end"] == 5.0          # = scene.start
    assert "AI越好用" in intro["text"]
    assert "下楼" in intro["text"]

    assert scene["id"] == "scene_00"
    assert scene["start"] == 5.0
    # scene's end is the true audio duration (12.0), not last segment end
    assert abs(scene["end"] - 12.0) < 0.1
    assert "写代码" in scene["text"]
    assert "通了" in scene["text"]


def test_missing_head_text_falls_back_to_equal_split(tmp_path, mock_whisper, capsys):
    audio = _make_audio(tmp_path / "rec.m4a", duration=10.0)
    mock_whisper["segments"] = [
        {"start": 0.0, "end": 5.0, "text": "前半"},
        {"start": 5.0, "end": 9.5, "text": "后半"},
    ]
    script = {
        "voice": "u", "rate": "+0%",
        "sections": [
            {"id": "a", "head_text": "前半", "lines": ["前半"]},
            {"id": "b", "lines": ["后半"]},  # NO head_text → must fall back
        ],
    }
    script_p = tmp_path / "script.json"
    script_p.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "out"

    rc = align_mod.cli(["--audio", str(audio), "--out", str(out),
                        "--script", str(script_p)])
    assert rc == 0

    captured = capsys.readouterr()
    assert "WARN" in captured.err
    assert "head_text" in captured.err

    timing = json.loads((out / "timing.json").read_text(encoding="utf-8"))
    assert len(timing["lines"]) == 2
    # second section start = 10.0 * 1/2 = 5.0 (equal split fallback)
    assert abs(timing["lines"][1]["start"] - 5.0) < 0.1


def test_writes_canonical_narration_wav(tmp_path, mock_whisper):
    audio = _make_audio(tmp_path / "rec.m4a", duration=3.0)
    mock_whisper["segments"] = [{"start": 0.0, "end": 2.5, "text": "x"}]
    out = tmp_path / "out"

    align_mod.cli(["--audio", str(audio), "--out", str(out)])

    wav = out / "narration.wav"
    assert wav.exists() and wav.stat().st_size > 0

    # Probe: should be mono 24kHz PCM
    import subprocess as sp
    info = sp.check_output([
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels",
        "-of", "json",
        str(wav),
    ])
    s = json.loads(info)["streams"][0]
    assert s["codec_name"] == "pcm_s16le"
    assert int(s["sample_rate"]) == 24000
    assert s["channels"] == 1


def test_caches_whisper_output(tmp_path, mock_whisper, capsys):
    audio = _make_audio(tmp_path / "rec.m4a", duration=4.0)
    mock_whisper["segments"] = [{"start": 0.0, "end": 3.5, "text": "hi"}]
    out = tmp_path / "out"

    # First run — calls (mocked) whisper
    align_mod.cli(["--audio", str(audio), "--out", str(out)])
    captured1 = capsys.readouterr()
    assert "running whisper" in captured1.out or "running whisper" in captured1.err \
        or "cached" not in captured1.out

    # Second run — should hit cache
    align_mod.cli(["--audio", str(audio), "--out", str(out)])
    captured2 = capsys.readouterr()
    assert "cached" in captured2.out


def test_empty_segments_emit_no_lines(tmp_path, mock_whisper):
    audio = _make_audio(tmp_path / "rec.m4a", duration=2.0)
    mock_whisper["segments"] = []
    out = tmp_path / "out"
    rc = align_mod.cli(["--audio", str(audio), "--out", str(out)])
    assert rc == 0
    timing = json.loads((out / "timing.json").read_text(encoding="utf-8"))
    assert timing["lines"] == []


def test_missing_audio_returns_2(tmp_path, mock_whisper):
    rc = align_mod.cli([
        "--audio", str(tmp_path / "nope.m4a"),
        "--out", str(tmp_path / "out"),
    ])
    assert rc == 2


def test_missing_script_returns_2(tmp_path, mock_whisper):
    audio = _make_audio(tmp_path / "rec.m4a", duration=2.0)
    rc = align_mod.cli([
        "--audio", str(audio),
        "--out", str(tmp_path / "out"),
        "--script", str(tmp_path / "nope.json"),
    ])
    assert rc == 2


def test_compatible_with_render_pipeline(tmp_path, mock_whisper, write_json,
                                          make_video_factory):
    """End-to-end: align-narration's output feeds into narration-cut.render
    without any glue code. Same Timing schema means the rest of the pipeline
    doesn't care that audio came from a recording vs. TTS."""
    from skills.narration_cut import render as render_mod

    # Step 1: align fake audio
    audio = _make_audio(tmp_path / "rec.m4a", duration=6.0)
    mock_whisper["segments"] = [
        {"start": 0.0, "end": 3.0, "text": "first"},
        {"start": 3.0, "end": 5.5, "text": "second"},
    ]
    proj = tmp_path / "proj"
    align_mod.cli(["--audio", str(audio), "--out", str(proj)])

    # Step 2: hand-build a one-shot timeline pointing at one source clip
    clips = tmp_path / "clips"
    make_video_factory(clips / "a.mp4", duration=8.0)
    timeline = {
        "video_total": 6.0, "fps": 30, "size": "640x360",
        "lines": [{
            "id": "narration_00",
            "text": "first second",
            "duration": 6.0,
            "shots": [{"file": "a.mp4", "in": 0.0, "dur": 6.0}],
        }],
    }
    tl_p = write_json(proj / "timeline.json", timeline)

    # Step 3: render using align's outputs
    rc = render_mod.cli([
        "--timeline", str(tl_p),
        "--timing", str(proj / "timing.json"),
        "--src", str(clips),
        "--narration", str(proj / "narration.wav"),
        "--out", str(proj),
    ])
    assert rc == 0
    final = proj / render_mod.DEFAULT_FINAL
    assert final.exists() and final.stat().st_size > 0

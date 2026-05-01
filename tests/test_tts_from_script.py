"""tts-from-script tests.

Edge-TTS synthesis is mocked: instead of calling the network we generate a tiny
silent MP3 of a deterministic length, so the merge / timing logic gets exercised
end-to-end with real ffmpeg.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from skills.tts_from_script import tts as tts_mod


# Map (section, line_idx) → desired duration. Lets each test pick durations.
_DURATIONS: dict[str, float] = {}


async def _fake_synth(voice, rate, text, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    # the fid is encoded in the filename: <section>_<idx>.mp3
    key = out.stem
    dur = _DURATIONS.get(key, 1.0)
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=mono:sample_rate=24000",
        "-t", f"{dur}",
        "-c:a", "libmp3lame", "-q:a", "9",
        str(out),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.fixture(autouse=True)
def patch_synth(monkeypatch):
    monkeypatch.setattr(tts_mod, "_synth", _fake_synth)
    _DURATIONS.clear()
    yield
    _DURATIONS.clear()


def _write_script(path: Path) -> Path:
    path.write_text(json.dumps({
        "voice": "zh-CN-XiaoyiNeural",
        "rate": "+0%",
        "gap_line_sec": 0.25,
        "gap_section_sec": 0.6,
        "sections": [
            {"id": "intro", "title": "引子", "lines": ["第一句。", "第二句。"]},
            {"id": "body",  "title": "正片", "lines": ["第三句。"]},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    return path


def test_emits_timing_and_narration(tmp_path):
    script = _write_script(tmp_path / "script.json")
    _DURATIONS.update({
        "intro_00": 1.0,
        "intro_01": 1.5,
        "body_00":  2.0,
    })
    rc = tts_mod.cli(["--script", str(script), "--out", str(tmp_path)])
    assert rc == 0

    timing_path = tmp_path / "timing.json"
    narration = tmp_path / "narration.wav"
    assert timing_path.exists() and narration.exists()

    data = json.loads(timing_path.read_text(encoding="utf-8"))
    assert data["voice"] == "zh-CN-XiaoyiNeural"
    assert data["rate"] == "+0%"
    assert len(data["lines"]) == 3

    # Per-line durations are within ffmpeg/lame quantization tolerance
    expected_dur = [1.0, 1.5, 2.0]
    for ln, d in zip(data["lines"], expected_dur):
        assert abs(ln["duration"] - d) < 0.15

    # start/end consistent with cumulative cursor + gaps
    # cursor: 0 → +1.0 line, +0.25 gap, +1.5 line, +0.6 section gap, +2.0 line
    # => starts 0.0, 1.25, 3.35    (allow tolerance for mp3 quantization)
    starts = [ln["start"] for ln in data["lines"]]
    assert abs(starts[0] - 0.0) < 0.05
    assert abs(starts[1] - (data["lines"][0]["end"] + 0.25)) < 0.01
    assert abs(starts[2] - (data["lines"][1]["end"] + 0.6)) < 0.01

    # total_duration ≈ last line end
    assert abs(data["total_duration"] - data["lines"][-1]["end"]) < 0.01


def test_files_are_relative_to_out(tmp_path):
    script = _write_script(tmp_path / "script.json")
    _DURATIONS.update({"intro_00": 0.8, "intro_01": 0.8, "body_00": 0.8})
    tts_mod.cli(["--script", str(script), "--out", str(tmp_path)])
    timing = json.loads((tmp_path / "timing.json").read_text(encoding="utf-8"))
    for ln in timing["lines"]:
        assert ln["file"].startswith("tts/")
        assert (tmp_path / ln["file"]).exists()


def test_caches_existing_mp3s(tmp_path):
    script = _write_script(tmp_path / "script.json")
    _DURATIONS.update({"intro_00": 1.0, "intro_01": 1.0, "body_00": 1.0})
    tts_mod.cli(["--script", str(script), "--out", str(tmp_path)])

    # Tamper with one MP3 — cached path should NOT re-synth (overwrite)
    intro_00 = tmp_path / "tts" / "intro_00.mp3"
    sentinel = intro_00.read_bytes()
    intro_00.write_bytes(sentinel + b"")  # noop but we'll check mtime
    mtime = intro_00.stat().st_mtime

    # Re-run; existing files should be reused
    tts_mod.cli(["--script", str(script), "--out", str(tmp_path)])
    assert intro_00.stat().st_mtime == mtime, "cached MP3 should not be regenerated"


def test_cli_overrides_gaps(tmp_path):
    script = _write_script(tmp_path / "script.json")
    _DURATIONS.update({"intro_00": 1.0, "intro_01": 1.0, "body_00": 1.0})
    tts_mod.cli([
        "--script", str(script),
        "--out", str(tmp_path),
        "--gap-line", "0.0",
        "--gap-section", "0.0",
    ])
    timing = json.loads((tmp_path / "timing.json").read_text(encoding="utf-8"))
    starts = [ln["start"] for ln in timing["lines"]]
    # zero gaps → each start = previous end
    for i in range(1, len(starts)):
        assert abs(starts[i] - timing["lines"][i - 1]["end"]) < 0.01


def test_missing_script_returns_2(tmp_path, capsys):
    rc = tts_mod.cli(["--script", str(tmp_path / "nope.json"),
                      "--out", str(tmp_path)])
    assert rc == 2

"""Shared pytest fixtures.

Tests rely on real ffmpeg/ffprobe. We synthesize tiny lavfi videos and audio so
the suite is hermetic — no checked-in binary fixtures, no network.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _ff_run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:6])}\n{r.stderr.decode()}")


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# Skip the entire suite if ffmpeg / ffprobe missing — every skill needs them.
collect_ignore_glob: list[str] = []


def pytest_configure(config):
    if not _have("ffmpeg") or not _have("ffprobe"):
        pytest.exit("ffmpeg and ffprobe required on PATH for the test suite.", 1)


def make_video(path: Path, *, duration: float = 4.0,
               size: str = "320x180", fps: int = 30,
               color: str = "black") -> Path:
    """Generate a tiny lavfi h264 mp4 of given duration."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ff_run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={color}:s={size}:d={duration}:r={fps}",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-t", f"{duration}",
        str(path),
    ])
    return path


def make_silent_audio(path: Path, *, duration: float = 6.0,
                      sample_rate: int = 24000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ff_run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=mono:sample_rate={sample_rate}",
        "-t", f"{duration}",
        "-c:a", "pcm_s16le",
        str(path),
    ])
    return path


@pytest.fixture
def make_video_factory():
    return make_video


@pytest.fixture
def make_silent_audio_factory():
    return make_silent_audio


@pytest.fixture
def clip_pool(tmp_path):
    """A folder with three clips of varying durations."""
    src = tmp_path / "clips"
    make_video(src / "a.mp4", duration=4.0)
    make_video(src / "b.mp4", duration=5.0)
    make_video(src / "c.mp4", duration=3.0)
    return src


@pytest.fixture
def timing_two_lines():
    """A canonical 2-line timing structure (intro section, with one inter-line gap)."""
    return {
        "voice": "zh-CN-XiaoyiNeural",
        "rate": "-5%",
        "total_duration": 6.0,
        "lines": [
            {
                "id": "intro_00", "section": "intro", "section_title": "引子",
                "text": "第一句。", "file": "tts/intro_00.mp3",
                "duration": 2.5, "start": 0.0, "end": 2.5,
            },
            {
                "id": "intro_01", "section": "intro", "section_title": "引子",
                "text": "第二句。", "file": "tts/intro_01.mp3",
                "duration": 2.7, "start": 2.75, "end": 5.45,
            },
        ],
    }


@pytest.fixture
def assets_three(tmp_path):
    """A canonical 3-clip assets index (matches the `clip_pool` filenames)."""
    return [
        {
            "file": "a.mp4", "duration": 4.0,
            "width": 1920, "height": 1080, "fps": 30,
            "rotation": None, "orientation": "landscape",
            "scene": "山脉远眺", "tags": ["intro", "山脉"],
            "chapters": ["intro"], "usable": True, "highlight": True,
        },
        {
            "file": "b.mp4", "duration": 5.0,
            "width": 1920, "height": 1080, "fps": 30,
            "rotation": None, "orientation": "landscape",
            "scene": "草甸", "tags": ["草甸"],
            "chapters": ["intro"], "usable": True,
        },
        {
            "file": "c.mp4", "duration": 3.0,
            "width": 1920, "height": 1080, "fps": 30,
            "rotation": None, "orientation": "landscape",
            "scene": "糊镜头", "tags": [],
            "usable": False, "reason": "shake",
        },
    ]


@pytest.fixture
def write_json():
    def _writer(path: Path, data) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path
    return _writer

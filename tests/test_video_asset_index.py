"""video-asset-index tests — deterministic mode only (no API)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skills.video_asset_index import index as idx_mod


def test_indexes_clip_pool(tmp_path, clip_pool):
    out = tmp_path / "out"
    rc = idx_mod.cli(["--src", str(clip_pool), "--out", str(out)])
    assert rc == 0

    index_path = out / "assets_index.json"
    data = json.loads(index_path.read_text(encoding="utf-8"))
    files = sorted(r["file"] for r in data)
    assert files == ["a.mp4", "b.mp4", "c.mp4"]

    for rec in data:
        assert "duration" in rec and rec["duration"] > 0
        assert rec["width"] == 320
        assert rec["height"] == 180
        assert rec["orientation"] == "landscape"
        # default mode does NOT auto-fill scene/tags
        assert "scene" not in rec
        assert "tags" not in rec


def test_creates_frames_and_sheets(tmp_path, clip_pool):
    out = tmp_path / "out"
    idx_mod.cli(["--src", str(clip_pool), "--out", str(out)])

    for stem in ("a", "b", "c"):
        for i in range(3):
            assert (out / "frames" / f"{stem}_f{i}.jpg").exists()
        sheet = out / "sheets" / f"{stem}.jpg"
        assert sheet.exists() and sheet.stat().st_size > 500


def test_resume_keeps_existing_records(tmp_path, clip_pool):
    out = tmp_path / "out"
    idx_mod.cli(["--src", str(clip_pool), "--out", str(out)])

    # Hand-edit one record (simulate user / Claude tagging it)
    index_path = out / "assets_index.json"
    data = json.loads(index_path.read_text(encoding="utf-8"))
    for rec in data:
        if rec["file"] == "a.mp4":
            rec["scene"] = "山脉"
            rec["tags"] = ["intro"]
            rec["usable"] = True
    index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                          encoding="utf-8")

    # Re-run — the hand edits must survive
    idx_mod.cli(["--src", str(clip_pool), "--out", str(out)])
    data2 = json.loads(index_path.read_text(encoding="utf-8"))
    a = next(r for r in data2 if r["file"] == "a.mp4")
    assert a.get("scene") == "山脉"
    assert a.get("tags") == ["intro"]


def test_force_reprocesses_everything(tmp_path, clip_pool):
    out = tmp_path / "out"
    idx_mod.cli(["--src", str(clip_pool), "--out", str(out)])

    # Hand-edit
    index_path = out / "assets_index.json"
    data = json.loads(index_path.read_text(encoding="utf-8"))
    for rec in data:
        rec["scene"] = "MARK"
    index_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    idx_mod.cli(["--src", str(clip_pool), "--out", str(out), "--force"])
    data2 = json.loads(index_path.read_text(encoding="utf-8"))
    for rec in data2:
        assert "scene" not in rec  # force wipes user edits


def test_orientation_portrait(tmp_path, make_video_factory):
    src = tmp_path / "clips"
    make_video_factory(src / "tall.mp4", duration=2.0, size="180x320")
    out = tmp_path / "out"
    idx_mod.cli(["--src", str(src), "--out", str(out)])
    data = json.loads((out / "assets_index.json").read_text(encoding="utf-8"))
    assert data[0]["orientation"] == "portrait"


def test_supported_extensions_only(tmp_path, make_video_factory):
    src = tmp_path / "clips"
    make_video_factory(src / "ok.mp4", duration=1.5)
    (src / "ignore.txt").write_text("hi")
    out = tmp_path / "out"
    idx_mod.cli(["--src", str(src), "--out", str(out)])
    data = json.loads((out / "assets_index.json").read_text(encoding="utf-8"))
    assert [r["file"] for r in data] == ["ok.mp4"]


def test_bad_src_returns_2(tmp_path):
    rc = idx_mod.cli(["--src", str(tmp_path / "nope"), "--out", str(tmp_path / "out")])
    assert rc == 2

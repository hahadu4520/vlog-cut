#!/usr/bin/env bash
# Check + install vlog-cut runtime dependencies.
# - Required: ffmpeg, ffprobe, python3, edge-tts (Python pkg)
# - Optional: whisper (only for align-narration), 4 Chinese fonts (for subtitles)

set -e

ok=true

check_cmd() {
    local name="$1"
    local cmd="$2"
    if command -v "$cmd" >/dev/null 2>&1; then
        printf "  ✓ %-22s (%s)\n" "$name" "$($cmd -version 2>/dev/null | head -1 || echo present)"
    else
        printf "  ✗ %-22s NOT FOUND\n" "$name"
        ok=false
    fi
}

check_pip_pkg() {
    local pkg="$1"
    local mod="$2"
    if python3 -c "import $mod" 2>/dev/null; then
        printf "  ✓ %s\n" "$pkg"
    else
        printf "  ✗ %s NOT INSTALLED  (pip install %s)\n" "$pkg" "$pkg"
        ok=false
    fi
}

check_font() {
    local family="$1"
    local cask="$2"
    if fc-list 2>/dev/null | grep -qi "$family"; then
        printf "  ✓ %-30s (installed)\n" "$family"
    else
        printf "  ⚠ %-30s not installed → brew install --cask %s\n" "$family" "$cask"
    fi
}


echo "=== Required system tools ==="
check_cmd ffmpeg   ffmpeg
check_cmd ffprobe  ffprobe
check_cmd python3  python3

echo ""
echo "=== Required Python packages ==="
check_pip_pkg edge-tts edge_tts

echo ""
echo "=== Optional: align-narration (user-recorded audio path) ==="
if command -v whisper >/dev/null 2>&1; then
    printf "  ✓ %-22s (%s)\n" whisper "$(whisper --help 2>&1 | head -1 | tr -d '\n')"
else
    printf "  ⚠ %-22s NOT INSTALLED   (pip install openai-whisper)\n" whisper
    printf "    └─ Skip if you only use TTS (vlog-cut-tts), not user audio (vlog-cut-align).\n"
fi

echo ""
echo "=== Optional: Chinese subtitle fonts ==="
if ! command -v fc-list >/dev/null 2>&1; then
    printf "  ⚠ fc-list missing — can't probe font installation\n"
    printf "    Install fontconfig (brew install fontconfig) to enable font checks.\n"
else
    check_font "LXGW WenKai"        font-lxgw-wenkai
    check_font "LXGW Marker Gothic" font-lxgw-marker-gothic
    check_font "Smiley Sans"        font-smiley-sans
    check_font "Ma Shan Zheng"      font-ma-shan-zheng
fi

echo ""
echo "=== Project ==="
if python3 -c "import skills" 2>/dev/null; then
    printf "  ✓ vlog-cut package importable\n"
    if command -v vlog-cut-render >/dev/null 2>&1; then
        printf "  ✓ CLI entry points on PATH\n"
    else
        printf "  ⚠ CLI entry points not on PATH — run: pip install -e .\n"
    fi
else
    printf "  ⚠ vlog-cut package not installed — run: pip install -e .\n"
fi

echo ""
if $ok; then
    echo "✅ All required dependencies present."
    echo ""
    echo "Next: pip install -e . (if you haven't), then talk to Claude Code:"
    echo "  > 我有口播和素材，帮我做成视频"
else
    echo "❌ Missing required dependencies above. Install them, then re-run."
    exit 1
fi

#!/usr/bin/env bash
# Check that vlog-cut runtime dependencies are available.
set -e

ok=true

check() {
    local name="$1"
    local cmd="$2"
    if command -v "$cmd" >/dev/null 2>&1; then
        printf "  ✓ %-12s (%s)\n" "$name" "$($cmd -version 2>/dev/null | head -1 || echo present)"
    else
        printf "  ✗ %-12s NOT FOUND\n" "$name"
        ok=false
    fi
}

echo "Checking required tools:"
check ffmpeg ffmpeg
check ffprobe ffprobe
check python3 python3

echo ""
echo "Checking Python packages:"
for pkg in edge_tts; do
    if python3 -c "import $pkg" 2>/dev/null; then
        printf "  ✓ %s\n" "$pkg"
    else
        printf "  ✗ %s NOT INSTALLED  (pip install %s)\n" "$pkg" "${pkg/_/-}"
        ok=false
    fi
done

echo ""
if $ok; then
    echo "All dependencies present. Run: pip install -e ."
else
    echo "Missing dependencies above. Install them, then re-run."
    exit 1
fi

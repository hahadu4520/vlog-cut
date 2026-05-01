"""burn-subtitles-cn build: subs_pages.json → ASS subtitle file.

ASS (Advanced SubStation Alpha) is what ffmpeg's libass burns onto video.
Style is configurable via CLI (font, size, outline, position, fade).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DEFAULT_FONT      = "Songti SC"
DEFAULT_FONT_SIZE = 56
DEFAULT_W, DEFAULT_H = 1920, 1080
DEFAULT_MARGIN_V  = 80     # px from bottom
DEFAULT_OUTLINE   = 2
DEFAULT_SHADOW    = 1.5
DEFAULT_FADE_MS   = 80     # fade-in / fade-out duration

# ASS color = &HBBGGRR (alpha first byte; 00 = opaque, FF = transparent)
WHITE     = "&H00FFFFFF"
BLACK     = "&H00000000"
SHADOW_C  = "&H80000000"   # 50% alpha black drop shadow


def _t(seconds: float) -> str:
    """Format seconds as ASS time h:mm:ss.cs"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(pages_doc: list[dict], *,
              w: int, h: int, font: str, font_size: int,
              margin_v: int, outline: int, shadow: float,
              fade_ms: int) -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{WHITE},{WHITE},{BLACK},{SHADOW_C},-1,0,0,0,100,100,2,0,1,{outline},{shadow},2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    fade = f"{{\\fad({fade_ms},{fade_ms})}}" if fade_ms > 0 else ""
    events: list[str] = []
    for line in pages_doc:
        for p in line["pages"]:
            text = (p["text"] or "").replace("\n", "\\N")
            if not text:
                continue   # skip empty pages (don't emit blank dialogue)
            events.append(
                f"Dialogue: 0,{_t(p['start'])},{_t(p['end'])},Default,,0,0,0,,{fade}{text}"
            )
    return header + "\n".join(events) + "\n"


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vlog-cut-subs-build",
                                description=__doc__.splitlines()[0])
    p.add_argument("--pages", required=True, type=Path,
                   help="subs_pages.json from vlog-cut-subs-split")
    p.add_argument("--out",   required=True, type=Path,
                   help="output .ass path")
    p.add_argument("--size",  default=f"{DEFAULT_W}x{DEFAULT_H}",
                   help=f"WxH for PlayRes (default {DEFAULT_W}x{DEFAULT_H})")
    p.add_argument("--font",  default=DEFAULT_FONT,
                   help=f"font name (default '{DEFAULT_FONT}')")
    p.add_argument("--font-size", type=int, default=DEFAULT_FONT_SIZE,
                   help=f"font size (default {DEFAULT_FONT_SIZE})")
    p.add_argument("--margin-v", type=int, default=DEFAULT_MARGIN_V,
                   help=f"distance from bottom in px (default {DEFAULT_MARGIN_V})")
    p.add_argument("--outline", type=int, default=DEFAULT_OUTLINE,
                   help=f"black outline width (default {DEFAULT_OUTLINE})")
    p.add_argument("--shadow", type=float, default=DEFAULT_SHADOW,
                   help=f"shadow depth (default {DEFAULT_SHADOW})")
    p.add_argument("--fade-ms", type=int, default=DEFAULT_FADE_MS,
                   help=f"per-page fade-in/out in ms (default {DEFAULT_FADE_MS}, 0 = off)")
    args = p.parse_args(argv)

    if not args.pages.exists():
        print(f"pages not found: {args.pages}", file=sys.stderr)
        return 2
    if "x" not in args.size:
        print(f"--size must be WxH, got {args.size!r}", file=sys.stderr)
        return 2
    w, h = (int(x) for x in args.size.lower().split("x", 1))

    pages_doc = json.loads(args.pages.read_text(encoding="utf-8"))
    ass = build_ass(pages_doc,
                    w=w, h=h,
                    font=args.font, font_size=args.font_size,
                    margin_v=args.margin_v,
                    outline=args.outline, shadow=args.shadow,
                    fade_ms=args.fade_ms)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(ass, encoding="utf-8")
    n_pages = sum(len(l["pages"]) for l in pages_doc)
    print(f"Wrote {args.out} ({n_pages} subtitle events)")
    return 0


if __name__ == "__main__":
    sys.exit(cli())

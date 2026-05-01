"""burn-subtitles-cn split: split each timing line into pages of ≤N chars.

Algorithm: greedy scan from the start of the line, find the strongest available
break point (hard punct → soft punct → whitespace) within the next N chars,
otherwise cut at exactly N chars. After splitting, strip leading and trailing
punctuation from each page so no page begins or ends with a comma.

Each page's start/end is interpolated from the source line's start/end by
character-count fraction (so a longer page stays on screen longer).

Output matches shared/schemas/subs_pages.schema.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DEFAULT_MAX_CHARS = 12

# Priority break chars (high → low)
HARD_BREAKS  = "。！？；——"
SOFT_BREAKS  = "，、："
LIGHT_BREAKS = " "

LEADING_PUNCT  = "，、：；。！？——「」『』""''… "
TRAILING_PUNCT = "，、：；。！？「」『』""''… "


def _find_cut(text: str, max_chars: int,
              keep_together: set[str]) -> int:
    """Return the cut point (index where the next page starts) for a text
    that's already known to be longer than max_chars."""
    window_end = min(max_chars, len(text))
    best = -1
    for prio in (HARD_BREAKS, SOFT_BREAKS, LIGHT_BREAKS):
        for i in range(window_end - 1, 0, -1):
            if text[i] in prio:
                best = i + 1
                break
        if best > 0:
            break
    if best <= 0:
        best = max_chars
    # Don't split across a keep-together bigram.
    if 0 < best < len(text):
        pair = text[best - 1] + text[best]
        if pair in keep_together:
            best -= 1
    if best <= 0:
        best = max_chars
    return best


def split_line(text: str, max_chars: int,
               keep_together: set[str] | None = None) -> list[str]:
    """Greedy split on punctuation priority; clean up leading/trailing punct."""
    keep_together = keep_together or set()
    text = text.strip()
    pages: list[str] = []
    while text:
        if len(text) <= max_chars:
            pages.append(text)
            break
        cut = _find_cut(text, max_chars, keep_together)
        page = text[:cut].rstrip().rstrip("，、 ")
        pages.append(page)
        text = text[cut:].lstrip()

    # post-pass: strip leading/trailing punct on every page; drop orphan "—"
    cleaned: list[str] = []
    for p in pages:
        while p and p[0] in LEADING_PUNCT:
            p = p[1:]
        if p.endswith("—") and not p.endswith("——"):
            p = p.rstrip("—")
        while p and p[-1] in TRAILING_PUNCT:
            p = p[:-1]
        if p:
            cleaned.append(p)
    return cleaned


def _build_pages_for_line(line: dict, max_chars: int,
                          keep_together: set[str]) -> dict:
    text = line["text"]
    pages = split_line(text, max_chars, keep_together)
    n = len(pages)
    if n == 0:
        # degenerate: empty line → emit one empty page covering the full duration
        # (so render still has timing parity)
        pages = [""]
        n = 1
    # Distribute time by character count (longer pages stay on screen longer).
    weights = [max(1, len(p)) for p in pages]
    total_w = sum(weights)
    line_dur = float(line["end"]) - float(line["start"])

    page_records: list[dict] = []
    cursor = float(line["start"])
    for i, (p, w) in enumerate(zip(pages, weights)):
        per = line_dur * (w / total_w)
        start = cursor
        end = cursor + per if i < n - 1 else float(line["end"])
        page_records.append({
            "page": i + 1,
            "of":   n,
            "text": p,
            "chars": len(p),
            "start": round(start, 3),
            "end":   round(end, 3),
            "dur":   round(end - start, 3),
        })
        cursor = end

    return {"id": line["id"], "text": text, "pages": page_records}


def _read_keep_together(path: Path | None) -> set[str]:
    if path is None:
        return set()
    if not path.exists():
        raise FileNotFoundError(f"keep-together file not found: {path}")
    return set(path.read_text(encoding="utf-8").split())


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vlog-cut-subs-split",
                                description=__doc__.splitlines()[0])
    p.add_argument("--timing", required=True, type=Path)
    p.add_argument("--out",    required=True, type=Path,
                   help="output subs_pages.json path")
    p.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS,
                   help=f"max characters per subtitle page (default {DEFAULT_MAX_CHARS})")
    p.add_argument("--keep-together", type=Path, default=None,
                   help="optional file with whitespace-separated 2-char "
                        "bigrams that must NOT split across pages")
    args = p.parse_args(argv)

    if not args.timing.exists():
        print(f"timing not found: {args.timing}", file=sys.stderr)
        return 2

    timing = json.loads(args.timing.read_text(encoding="utf-8"))
    keep_together = _read_keep_together(args.keep_together)

    out_records: list[dict] = []
    for line in timing["lines"]:
        out_records.append(_build_pages_for_line(line, args.max_chars,
                                                  keep_together))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_records, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    n_pages = sum(len(r["pages"]) for r in out_records)
    print(f"Wrote {args.out}: {len(out_records)} lines → {n_pages} pages "
          f"(max {args.max_chars} chars/page)")
    return 0


if __name__ == "__main__":
    sys.exit(cli())

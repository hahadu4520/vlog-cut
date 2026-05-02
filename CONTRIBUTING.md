# Contributing to vlog-cut

Issues, PRs, ideas — all welcome.

## Setup for development

```bash
git clone <this repo>
cd vlog-cut
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest

# system deps
brew install ffmpeg
# optional: pip install openai-whisper  (only if working on align-narration)
```

Run `bash install.sh` to verify everything's wired.

## Run the test suite

```bash
.venv/bin/pytest                          # all 89 tests, ~15s
.venv/bin/pytest tests/test_render*.py    # one file
.venv/bin/pytest -k "test_split" -v       # by name
```

Tests synthesize their own video / audio fixtures via ffmpeg lavfi — no
checked-in binaries, no network. Whisper and edge-tts are mocked. If a test
fails, it's almost certainly a real bug, not environment drift.

## Project layout

```
skills/<skill_name>/         # one directory per skill
  SKILL.md                   # what Claude reads to know how to use it
  __init__.py                # empty marker
  <module>.py                # CLI(s) + library functions

shared/
  schemas/*.json             # the data contracts between skills
  ffmpeg_helpers.py          # thin wrappers shared across skills

tests/
  conftest.py                # pytest fixtures (sample mp4 generator, etc.)
  test_<skill>.py            # one test file per skill

docs/
  known-issues.md            # bug retrospective
  tutorials/                 # user-facing tutorials
```

Skills are Python packages (underscore-named because hyphens can't be
imported). The SKILL.md `name:` field is the public hyphen-separated
name (`vlog-cut-pipeline` etc.) that Claude Code uses.

## Adding a new skill

1. Create `skills/<skill_name>/` with `__init__.py`, your `<module>.py`, and `SKILL.md`.
2. SKILL.md frontmatter:
   ```yaml
   ---
   name: vlog-cut-<skill-name>
   description: One-sentence trigger description that tells Claude when to invoke this.
   ---
   ```
3. Register CLI entry in `pyproject.toml` `[project.scripts]`.
4. If you produce data consumed by another skill, add a JSON schema in `shared/schemas/`.
5. Write tests in `tests/test_<skill_name>.py`. Cover:
   - happy path (CLI exits 0, produces expected files)
   - exit code 2 on missing/invalid inputs
   - any caching behavior
   - edge cases that have already burned us once (see `docs/known-issues.md`)

## Coding style

- **Default to no comments.** Only add a comment if WHY is non-obvious (a
  hidden constraint, a workaround for a specific bug). Don't restate WHAT
  the code does.
- Keep skill modules small and focused. If a single CLI starts doing 3
  unrelated things, split it.
- Errors at boundaries get user-readable messages on stderr + exit code.
  Internal invariants are asserts.
- Prefer `argparse` for CLIs (not click / typer) — keeps deps minimal.

## Reporting bugs

Open an issue with:

1. Which stage broke (A=narration / B=index / C=timeline / D=render / E=subtitles)
2. The full command line + stderr
3. `<project_dir>/.vlog-cut/state.json` contents if it exists
4. ffmpeg / Python / macOS versions

Check [docs/known-issues.md](docs/known-issues.md) first — we documented 10
bugs from real-world dogfooding, your symptom may match.

## PR checklist

Before opening a PR:

- [ ] `.venv/bin/pytest` passes (89/89 expected; if you added a feature,
      add tests for it)
- [ ] If you fixed a bug, added a regression test that would have caught it
- [ ] `bash install.sh` still passes
- [ ] If you added a CLI flag or changed a default, updated the relevant
      `SKILL.md` so Claude knows about it
- [ ] If your change affects users, updated `README.md` or `docs/tutorials/quick-start.md`
- [ ] If your change is non-trivial, added a `docs/known-issues.md` entry
      with the bug story (this is how we keep the lessons)

## License

By contributing you agree your contributions are licensed under MIT.

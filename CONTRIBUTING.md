# Contributing

Thanks for helping. Small, focused pull requests are easiest to review.

## Layout

- `skills/tbd-board/` is the skill. Everything in it is installed into users' agents, so keep it small.
  - `SKILL.md` and `references/` are written in [ASD-STE100 Simplified Technical English](https://www.asd-ste100.org/): short sentences, one instruction per sentence, active voice.
  - `scripts/board.py` is the helper: Python 3.8+, standard library only.
  - `assets/board-template.html` is the board page: one file, no external requests, no build step.
- `tests/` holds the tests. `examples/hearth/` is the demo board. `docs/media/` holds the icon and the screenshots. `tools/` makes them.

## Checks

Run these before you open a pull request:

```bash
python3 -m unittest discover -s tests -v
```

```bash
node tests/browser_check.mjs
```

```bash
python3 skills/tbd-board/scripts/board.py check --board examples/hearth/board.html
```

The browser check needs Node 22+ and Google Chrome (set `CHROME_PATH` if Chrome is not in the usual place).

## Rules

- Keep one version string: `.claude-plugin/plugin.json`, `plugin.json`, `board.py`, the template's `generator` meta tag, and the top entry of `CHANGELOG.md`. A test fails when they differ.
- Do not add symlinks. Codex drops them when it copies a plugin.
- `SKILL.md` uses only the six Agent Skills frontmatter fields, so it also works as a claude.ai upload.
- A change to the page or the data format needs a test, and the page must still pass the browser check at 360 px wide, with storage blocked, and in both themes.
- Use only the fictional Hearth data in examples and screenshots.

## Media

```bash
python3 tools/make_icons.py
```

```bash
node tools/make_media.mjs
```

The first command writes the icon SVGs. The second rebuilds the demo board, the card images, the screenshots, the GIF (needs `ffmpeg`), and the icon PNGs.

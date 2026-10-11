# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-11

### Added

- The `tbd-board` skill: when to ask the user and when to decide alone, how to write a good card, and how to read and record pasted answers.
- The board page: one self-contained HTML file that works offline from `file://`, in light and dark mode, and on a phone. Tap an option to answer, "Decide later", search and filters, progress, drafts kept in the browser, and "Copy all answers" with a header that names the board and its revision.
- The helper `board.py` (Python 3.8+, no packages): `init`, `ask`, `answer`, `close`, `auto`, `list`, `check`, and `upgrade`. It writes the board and the decision log together, atomically.
- The add-only decision log with "Supersedes" links, and the "Decided for you" list.
- Install support for Claude Code, Codex, GitHub Copilot, VS Code, Cursor, Gemini CLI, and other agents that read Agent Skills.
- The Hearth demo board (a fictional app), screenshots, and the TBoarD icon.

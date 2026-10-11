# Install tests

Each test installed the skill from a clean local export of this repository (only the tracked files), in an empty test folder. "Prompt" is what the agent was asked after the install.

| Agent | Version | Route | Prompt | Result | Date |
| --- | --- | --- | --- | --- | --- |
| Claude Code | 2.1.284 | `claude plugin marketplace add <local export>`, then `claude plugin install tbd-board@camerash` | "Set up a decision board here." (Haiku) | Pass. The agent loaded the skill and ran `init`; `check` passes. `claude plugin validate --strict` passes for both manifests. | 2026-10-11 |
| Claude Code | 2.1.284 | Same project | A pasted answer block: one answer with a condition, one unknown card ID (Sonnet) | Pass. The agent recorded D-001 with the condition and asked about the unknown ID. | 2026-10-11 |
| Claude Code | 2.1.284 | Same project | The same paste test (Haiku) | First fail: Haiku did not load the skill for a paste in a new session, and recorded nothing. A reordered skill description did not help. Pass after the change: the answer block now ends with "(Agent: record these answers with the tbd-board skill.)". Haiku then recorded the answer and reported the unknown ID. | 2026-10-11 |
| Codex CLI | 0.160.0 | `codex plugin marketplace add <local export>`, then `codex plugin add tbd-board@camerash` | "Set up a decision board here." | Pass. The agent loaded the skill, ran `init` and `check`, and asked about the project rules with a card. | 2026-10-11 |
| Codex CLI | 0.160.0 | `npx skills@1.7.2 add <local export> -a codex -a cursor -a claude-code --copy -y` (project scope) | "Set up a TBD board for this project." | Pass. The skills CLI copied the skill to `.agents/skills/` and `.claude/skills/`; the agent used it. | 2026-10-11 |
| Codex CLI | 0.160.0 | Same project, after the test above | A pasted answer block: one answer with a condition, one unknown card ID | Pass. The agent recorded D-001 with the condition, set the card to answered, did the work, and reported the unknown ID without a record. `check` passes. | 2026-10-11 |
| skills CLI | 1.7.2 | `npx skills add <local export> --list` | none | Pass. It finds 1 skill. | 2026-10-11 |
| Agent Skills validator | skills-ref 0.1.1 | `agentskills validate skills/tbd-board` | none | Pass. | 2026-10-11 |

Not tested (not installed on the test machine): GitHub Copilot CLI, VS Code, Cursor, Gemini CLI, Antigravity CLI, Windsurf, OpenCode, Amp, Goose, Roo Code, Kiro, Pi, Cline. The README marks them "Not yet".

## Known risks

From the install survey, checked on 2026-10-11:

1. **Root `plugin.json` next to `.claude-plugin/`.** Tested: Codex reads the root Agent Plugins manifest and installs the skill; Claude Code reads `.claude-plugin/` and installs the skill. Both work with the two manifests in place.
2. **Cline paths.** The docs say `.cline/skills/`; some installers write `.agents/skills/`. Not tested.
3. **Goose user path** (`~/.config/goose/skills/`). Not confirmed. The README uses the skills CLI route.
4. **Antigravity CLI with the Agent Plugins `$schema` key.** Not tested.
5. **Copilot direct repository installs.** The docs and other projects disagree. The README uses the marketplace route.

## Repeat a test

```bash
claude plugin marketplace add Camerash/tbd-board
```

```bash
claude plugin install tbd-board@camerash
```

Then, in an empty folder, ask the agent "Set up a decision board here." and run `board.py check` on the result. Remove the test install afterwards (`claude plugin uninstall tbd-board@camerash`, then `claude plugin marketplace remove camerash`).

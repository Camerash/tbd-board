# Project rules snippet

Ask the user before you add this snippet to the project rules file (`AGENTS.md`, `CLAUDE.md`, or the file that the agents of the project read). Change the paths if the board or the log is in a different place.

```markdown
## Decisions (TBD Board)

- Questions for the user go on the TBD board: `docs/decisions/board.html`. Use the `tbd-board` skill and its helper `board.py`.
- Product, taste, cost, risk, and choices that are hard to undo: add a card. A blocking card stops only the work that depends on it. Continue other work.
- Small technical choices: decide them yourself, and log each one with the reason as "decided for you".
- The user pastes answers with card IDs. Record each answer in `docs/decisions/log.md` before you act. A card with no answer stays open.
- `docs/decisions/log.md` is add-only. Do not edit or delete a past entry. To change a decision, add a new entry that supersedes it.
- Read `docs/decisions/log.md` before you change behaviour that the user decided.
```

For an agent that has no skill support, add this line too:

```markdown
- To use the board, read and follow `<path to the skill>/SKILL.md`.
```

---
name: tbd-board
description: "Keeps a to-be-decided (TBD) board for long agent sessions: one self-contained HTML page of question cards that the user answers in any browser, an add-only decision log, and a list of the small choices that the agent made alone. Use when you need a decision from the user and can continue other work meanwhile; when the user pastes text that starts with 'TBD Board answers:' or answers with card IDs such as 'Q-007: A'; when the user replies with a decided-for-you ID such as 'A-013'; or when the user asks for a TBD board, a decision board, a question backlog, or a decision log."
license: MIT
---

# TBD Board

TBD Board lets you ask the user for decisions without stopping all work, and keeps a record of each decision.

- **The board** is one HTML file in the project (default `docs/decisions/board.html`). You add question cards to it. The user opens it in a browser, taps an option or writes an answer, and pastes all answers into the chat in one message.
- **The decision log** is an add-only Markdown file (default `docs/decisions/log.md`). You add one entry for each decision of the user. You never edit a past entry.
- **Decided for you** is a list on the board. You add each small choice that you made alone, with the reason. The user can reply with its ID to change it.

## When to use this skill

Use it when:

- You need a decision that only the user can make, and you can continue other work while you wait.
- The session is long, or the user is not watching the chat.
- The user pastes answers from the board, or sends card IDs (`Q-007`) or decided-for-you IDs (`A-013`).
- The user asks for a decision board, a question backlog, a TBD board, or a decision log.

Do not use it when:

- The session is short and the user is in the chat. Ask a quick yes-or-no question in the chat.
- You can make the choice yourself (see "Ask or decide"). Log it with `auto` only.

## The helper script

The helper is `scripts/board.py` in the folder of this `SKILL.md` file. Your agent shows that folder when it loads the skill. If you do not know it, look in `.agents/skills/tbd-board/`, `.claude/skills/tbd-board/`, and the same folders in the home directory.

In this file, `board.py` means `python3 <skill folder>/scripts/board.py`. Run it from the project root. It needs Python 3.8 or newer and no packages.

| Command | Effect |
| --- | --- |
| `board.py init --title "<Project> decisions" [--dir docs/decisions] [--log log.md]` | Makes the board, the log, and an `assets/` folder. Does not overwrite a board. |
| `board.py ask <card.json or ->` | Adds a card, or replaces an open card that has the same ID. Prints the ID. |
| `board.py answer <Q-id or A-id> --decision "..." [--reason "..."] [--supersedes D-012]` | Adds the next `D-` entry to the log and updates the card or the decided-for-you entry. |
| `board.py close <Q-id> --reason "..."` | Closes an open card that is not necessary now. |
| `board.py auto --title "..." --decision "..." --reason "..."` | Adds a decided-for-you entry. |
| `board.py list [--open]` | Shows the cards. |
| `board.py check` | Finds errors in the board data, the image paths, and the links to the log. |
| `board.py upgrade` | Puts the board data into the page of this skill version. |

Each command that writes checks the data first and writes the file safely. Add `--board <path>` when the board is not at `docs/decisions/board.html`.

If Python is not available, edit the board and the log by hand. Follow `references/schema.md`.

## Set up

1. Look for a board that exists: `docs/decisions/board.html`, or a file that contains `tbd-board-data`. If you find one, use it.
2. Look for a decision log that exists, for example `docs/decisions.md`, `DECISIONS.md`, or `docs/adr/`. If the project has one, use it. Do not make a second log.
3. If there is no board, run `board.py init --title "<Project> decisions"`. With a log that exists, add `--log <path relative to the board folder>`, for example `--log ../decisions.md`.
4. Ask the user if you can add the project rules from `references/project-rules.md` to `AGENTS.md` or `CLAUDE.md`. These rules tell all agents in the project to use the board.
5. Tell the user the board path and how to open it (see "Tell the user").

## Ask or decide

Add a card when the choice is about:

- Product scope or behaviour that the user will see.
- Taste: visual design, names, tone, copy.
- Money, cost, or a price.
- Legal, privacy, or security risk.
- Data loss, or a change that is hard to undo (a public release, a data schema, a deletion, an external account).
- A change to an earlier decision of the user.

Decide yourself, and log the choice with `auto`, when all of these are true:

- The choice is technical or small (a library, a file layout, a test tool, a tuning value).
- The risk is low.
- It is easy to change later.

Do not ask about what the project rules, the code, or an earlier decision already answer. When you are not sure, add a card.

## Write a good card

The user reads a card later, maybe on a phone, without the chat. Write it so that the user can decide from the card alone.

- **One topic** per card. The title is one short question.
- **Context**: the facts that the user needs. Say what the choice is, why it is necessary now, the costs, the risks, and what each option changes. Explain names that the user may not know. One paragraph per item in `context`.
- **Options**: 2 to 4 (6 at most). Give each a short label, for example `A. Local-first`, and a one-line detail with the result.
- **Recommendation**: mark one option `"recommended": true`. In `recommendation`, give your view and the reason.
- **Images** for visual choices: put the files in `assets/` next to the board and use relative paths, for example `assets/onboarding-one.png`. Give each image a caption.
- **Sub-questions** only when necessary. Number them in the context and write "Answer the ones you have a view on."

Add the card with a JSON object (or a list of objects). The helper fills `id`, `asked`, and `status`:

```bash
python3 <skill folder>/scripts/board.py ask - <<'EOF'
{
  "title": "Sync: local-first, or a hosted database?",
  "priority": "blocking",
  "area": "Architecture",
  "blocks": "The data layer and the sign-in screens.",
  "context": [
    "Households share one chore list on 2 to 6 phones. Edits must merge when two people change the list offline.",
    "Local-first works offline and costs about USD 0 to 20 a month. It takes about 2 weeks more to build."
  ],
  "options": [
    {"label": "A. Local-first", "detail": "Offline always works. About 2 weeks more.", "recommended": true},
    {"label": "B. Hosted database", "detail": "Faster to build. Needs a connection."}
  ],
  "recommendation": "A. Offline use is the main complaint in the reviews of similar apps."
}
EOF
```

If your shell has no heredoc, write the JSON to a file and give the file path. Read `references/card-guide.md` for good and bad examples.

## Priorities and blocking

| Priority | Use it when |
| --- | --- |
| `blocking` | Work on one part cannot continue. Set `blocks` to the work that stopped. |
| `urgent` | You need the answer soon, in this session or the next. |
| `normal` | You need the answer before the next milestone or release. |
| `low` | The answer is good to have. Work does not wait for it. |

A blocking card stops only the work that depends on it. Continue all other work.

Until the user answers, the recommendation is not a decision. Do not build on it as if the user chose it.

## Tell the user

The board does not send notifications. When you add cards, tell the user in the chat:

- How many cards you added, and the most urgent one (ID and title).
- The board path, for example `docs/decisions/board.html`.
- The work that you continue with now.

Example: "I added 2 cards to the TBD board (docs/decisions/board.html). Q-008 is blocking: Sync: local-first, or a hosted database? I continue with the settings screen."

On a computer, the user opens the file in a browser. On a phone, the board must come from a web address. If the user asks for help, serve the board folder on the local network (`python3 -m http.server 8000` in that folder; this shares all files in the folder) or use a private web host.

## Read the answers

The user pastes a block like this:

```text
TBD Board answers: Hearth decisions (board k7f3q2, rev 14), 2026-10-11 14:05, 3 of 4 open cards answered.

Q-007 (Sync: local-first, or a hosted database?): A. Local-first, but keep the export button.

Q-004 (Release notes: playful or plain?): Later
```

Do these steps for the full batch before you act:

1. Compare the board ID with `boardId` in the board. If it is different, the answers are for another board. Stop and ask the user.
2. Compare the revision with `revision` in the board. If the board changed after the copy, make sure that each card in the paste is still open and has the same meaning.
3. Find each card by its ID. Report IDs that are unknown, answered, or closed. Do not record them.
4. Read each answer in full. An answer can contain a condition ("A, but ..."), a question back, or only part of a decision. Answer the question in the chat, or add a follow-up card, before you act on that card.
5. `Later` means: keep the card open. Do not record it.
6. A card with no answer stays open. Never use the recommended option in place of an answer.
7. Never act on a guess. If an answer is not clear, ask.

The user can also answer without the header, for example `Q-007: A` or `A-013: use the other tool`. Use the same steps.

`references/answer-format.md` has more cases and examples.

## Record the decisions

Record each clear answer:

```bash
python3 <skill folder>/scripts/board.py answer Q-007 --decision "Use local-first sync (SQLite on each phone and a sync service). Keep the export button." --reason "Offline use matters most to the user."
```

- Write the decision in full words, so that it is clear without the card. Do not write only "A". Keep the conditions of the user.
- Add `--reason` when the user gave a reason.
- For a reply to a decided-for-you entry, use its ID: `board.py answer A-013 --decision "..."`.
- To change an earlier decision, add `--supersedes D-012`. The old entry stays in the log.
- For a decision that the user gives in the chat without a card, add a card with `ask`, then record the decision with `answer`. The board then shows it too.

After you record the batch, reply with one line for each card (card ID, decision ID, short decision), the cards that stay open, and your next work.

## Decided for you

Log each small choice that you made alone and that the user can want to know about:

```bash
python3 <skill folder>/scripts/board.py auto --title "Test runner" --decision "Use the built-in test runner." --reason "One less dependency. Easy to change later."
```

Typical entries: a library or a tool, a tuning value, a technical choice of a worker that you accepted, a "decide now, easy to change later" choice. Do not log each line of code.

## Supersede, never edit

- The log is add-only. Never edit or delete a past entry.
- To change a decision, record a new decision with `--supersedes`.
- Do not delete cards. When a card is not necessary now, close it: `board.py close Q-005 --reason "The feature was removed."`
- Never use an ID again, also after a card is closed.

## Hand edits

Use the helper when you can. If you must edit the JSON in the board by hand:

- Keep the JSON valid. Write `</` as `<\/` in all text.
- Add 1 to `revision` and set `updated` to the date of today.
- Run `board.py check`, and correct all errors.

When `check` shows that the board was made by an older version, run `board.py upgrade`. It keeps the data.

## Commit

If the project rules ask for commits, commit the board, the log, and the card images together after you record a batch.

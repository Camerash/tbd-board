# The answer block, and how to read it

## Format

"Copy all answers" on the board makes this text:

```text
TBD Board answers: Hearth decisions (board k7f3q2, rev 14), 2026-10-11 14:05, 3 of 4 open cards answered.

Q-007 (Sync: local-first, or a hosted database?): A. Local-first, but keep the export button.

Q-006 (Onboarding: three short screens, or one screen?): One screen.

Q-004 (Release notes: playful or plain?): Later

(Agent: record these answers with the tbd-board skill.)
```

- **Line 1, the header:** the board title, the board ID (`boardId`), the data revision (`revision`), the local time of the copy, and the progress (answered open cards of all open cards).
- **Then one paragraph for each answered open card:** `<card ID> (<card title>): <answer>`. A blank line separates the cards. An answer can have line breaks, but no blank lines.
- The order is the order of the Open section: blocking, urgent, normal, low, then by ID.
- Cards with no answer are not in the block.
- **The last line** tells an agent that has not loaded this skill what to do with the paste. It is not an answer.
- "Copy this answer" on one card makes the same block with only that card.
- A tap on an option puts the option label at the start of the answer. The user can add words after it.

## Steps

1. **Board ID.** If the ID is not the `boardId` of the board, the answers are for another board. Stop and ask the user which board they mean.
2. **Revision.** If the revision is lower than `revision` in the board, the board changed after the copy. Make sure that each card in the paste is still open and has the same meaning. If a card changed in a way that changes the answer, ask the user.
3. **IDs.** Find each card. Report IDs that are unknown, answered, or closed. Do not record them.
4. **Each answer.** Read it in full. Find the decision, the conditions, the reason, and any question back.
5. **Act after the batch.** Record all clear answers. Then plan the work once, with all decisions together.

## Cases

| The answer | What to do |
| --- | --- |
| `A. Local-first` (only a label) | Record the option: its label and its detail, in full words. |
| `A. Local-first, but keep the export button.` | Record the option and the condition. |
| `A. Local-first, I think` | Record it. "I think" is not a question. |
| `A or C. What does C cost us later?` | Do not record. Answer the question in the chat, or add a follow-up card. |
| `Let's talk about this.` | Do not record. Keep the card open. Tell the user that you wait. |
| `Later` | Keep the card open. Do not record. |
| An answer to only some sub-questions | Record the answered parts. Keep the card open, or add a follow-up card for the rest. |
| No answer for a card | The card stays open. Never use the recommended option in its place. |
| `A-013: use the other tool` | A change to a decided-for-you entry. Record it with `board.py answer A-013 --decision "..."`. |
| `D-012 is wrong now; one reminder a week` | Record a new decision with `--supersedes D-012`. Use `answer` on the card that D-012 answered. |
| An answer that is not clear | Ask. Never act on a guess. |

## Without the header

The user can answer in the chat without the board, for example:

```text
Q-007: A
Q-005 - kettle, but make it orange
```

Use the same steps. Skip the board ID and revision checks.

## Your reply after the batch

Give one line for each card, then the open cards, then your next work:

```text
Recorded:
- Q-007 -> D-013: local-first sync; keep the export button.
- Q-006 -> D-014: one onboarding screen, invite button first.
Still open: Q-004 (you chose Later), Q-005 (no answer).
Next: I start the local database layer.
```

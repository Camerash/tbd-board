# How to write a good card

The user reads cards later, often in a batch, sometimes on a phone. The user did not see your work. A good card lets the user decide in less than a minute, with no other source.

## Checklist

- [ ] One topic. The title is one short question.
- [ ] The context says what the choice is, why it is necessary now, and what each option changes.
- [ ] Each name, file, or term that the user may not know has a short explanation.
- [ ] 2 to 4 options (6 at most). Each label is short and starts with a letter (`A.`, `B.`) when the order helps.
- [ ] Each option has a one-line detail: the result, the cost, or the risk.
- [ ] One option is recommended, and `recommendation` gives the reason.
- [ ] `blocks` names the stopped work, only when the priority is `blocking`.
- [ ] Visual choices have images with captions.
- [ ] Nothing in the card depends on the chat.

## A bad card and a good card

The examples use "Hearth", a fictional household-chores app.

### Bad

```json
{
  "title": "Sync?",
  "priority": "blocking",
  "context": ["Need to pick the sync approach per our discussion. See the PR."],
  "options": [
    {"label": "CRDT"},
    {"label": "Server"}
  ],
  "recommendation": "CRDT"
}
```

Problems:

- The title is not a question that the user can answer alone.
- The context refers to the chat and a pull request. The user must search for the facts.
- "CRDT" is jargon. The user does not know what it changes.
- The options have no result, cost, or risk.
- The recommendation has no reason.
- The card is blocking, but `blocks` does not say which work stopped.

### Good

```json
{
  "title": "Sync: local-first, or a hosted database?",
  "priority": "blocking",
  "area": "Architecture",
  "blocks": "The data layer and the sign-in screens.",
  "context": [
    "Households share one chore list on 2 to 6 phones. Edits must merge when two people change the list offline.",
    "Local-first (a database on each phone, plus a sync service that merges the edits) works offline and costs about USD 0 to 20 a month. It takes about 2 weeks more to build.",
    "A hosted database is faster to build, but the app shows a spinner with no connection, and the cost grows with each household."
  ],
  "options": [
    {"label": "A. Local-first", "detail": "Offline always works. About 2 weeks more.", "recommended": true},
    {"label": "B. Hosted database", "detail": "Faster to build. Needs a connection."},
    {"label": "C. Hosted now, local-first in 2.0", "detail": "Ship sooner; a data migration later."}
  ],
  "recommendation": "A. Offline use is the main complaint in the reviews of the apps we compared, and a later migration costs more than the 2 weeks."
}
```

## Options

- Give real alternatives. Do not add a weak option only to make the recommended one look good.
- Include "do nothing now" or "later" only when it is a real choice with a known result.
- Keep labels short. The user taps a label, and the label goes into the answer.
- Labels must be different in each card. Do not start one label with the full text of another label.

## Sub-questions

Put one topic on each card. Answers to cards with many sub-questions come back partial.

When some small questions belong together, use one card:

1. Number the questions in the context: "1. ...", "2. ...".
2. Write: "Answer the ones you have a view on."
3. Use no options, or options only for the main question.
4. When the user answers only some questions, record those. Keep the card open, or add a follow-up card for the rest.

## Images

- Use images for visual choices: layouts, icons, colours, charts, screenshots.
- Put the files in the `assets/` folder next to the board. Use relative paths, for example `assets/icon-kettle.png`.
- Give each image a caption that names the option.
- Keep each image small (less than about 300 KB). The page shows 150 px thumbnails. A click opens the full image.

## Priority

| Priority | Examples |
| --- | --- |
| `blocking` | The data model, when you cannot write the data layer without it. A legal question before a public release. |
| `urgent` | The onboarding flow, when you build the first screens next. |
| `normal` | The app icon. The name of a setting. |
| `low` | The tone of the release notes. A nice-to-have feature for a later version. |

## Ask or decide: examples

| Choice | Ask or decide | Why |
| --- | --- | --- |
| Local-first sync or a hosted database | Ask | Product behaviour, cost, hard to change |
| The app icon | Ask | Taste |
| The test runner | Decide, log with `auto` | Technical, easy to change |
| A linter preset | Decide, log with `auto` | Technical, low risk |
| Delete the old user data after the migration | Ask | Data loss |
| The price of the paid plan | Ask | Money |
| The name of an internal function | Decide, do not log | Too small to log |
| A change to the D-012 reminder rule | Ask | Changes an earlier decision of the user |

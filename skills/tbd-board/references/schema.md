# Board data schema (schema 1)

The board is one HTML file. The data is JSON in this element:

```html
<script type="application/json" id="tbd-board-data">
{ ... }
</script>
```

All other parts of the file are the renderer. Do not change them. `board.py upgrade` replaces the renderer and keeps the data.

## Rules for the JSON text

- The JSON must be valid. A comma after the last item is an error.
- Write `</` as `<\/` in all text, so that a text cannot end the script element. Write `<!--` as `<!--`. The helper does this for you.
- Keep the opening tag exactly as shown above. It must occur one time only.

## Top level

```json
{
  "schema": 1,
  "boardId": "k7f3q2",
  "revision": 14,
  "title": "Hearth decisions",
  "updated": "2026-10-11",
  "log": "log.md",
  "questions": [],
  "autodecided": []
}
```

| Field | Type | Rule |
| --- | --- | --- |
| `schema` | integer | `1`. |
| `boardId` | string | 6 to 12 characters, `a-z` and `0-9`. `init` makes it. Do not change it. The page uses it to keep the drafts of this board apart from other boards. |
| `revision` | integer | 0 or more. Add 1 at each change. The answer block contains it, so you can see if the answers are for an older version of the board. |
| `title` | string | Not empty. Shown as the page title. |
| `updated` | string | The date of the last change, `YYYY-MM-DD`. |
| `log` | string | Optional. The path of the decision log, relative to the board file. Default `log.md`. |
| `questions` | array | The cards. |
| `autodecided` | array | The decided-for-you entries, newest first. |

## Card

```json
{
  "id": "Q-007",
  "title": "Sync: local-first, or a hosted database?",
  "priority": "blocking",
  "status": "open",
  "area": "Architecture",
  "asked": "2026-10-11",
  "blocks": "The data layer and the sign-in screens.",
  "context": ["Paragraph one.", "Paragraph two."],
  "images": [{ "src": "assets/sync.png", "caption": "The two designs" }],
  "options": [
    { "label": "A. Local-first", "detail": "Offline always works. About 2 weeks more.", "recommended": true },
    { "label": "B. Hosted database", "detail": "Faster to build. Needs a connection." }
  ],
  "recommendation": "A. Offline use is the main complaint in the reviews.",
  "decision": ""
}
```

| Field | Type | Rule |
| --- | --- | --- |
| `id` | string | `Q-` and 3 or more digits. Unique. Never used again. |
| `title` | string | Required. One short question. |
| `priority` | string | `blocking`, `urgent`, `normal`, or `low`. |
| `status` | string | `open`, `answered`, or `closed`. |
| `area` | string | Optional. Free text. The page makes a filter chip for each area. |
| `asked` | string | The date of the card, `YYYY-MM-DD`. |
| `blocks` | string | Optional. The work that stopped. Empty when the card does not block work. |
| `context` | array of strings | One paragraph per item. |
| `images` | array | Optional. Each item: `src` and `caption`. See "Image addresses". |
| `options` | array | 0 to 6 items. Each item: `label` (required, unique in the card), `detail` (optional), `recommended` (optional, `true` or `false`). At most one option has `recommended: true`. |
| `recommendation` | string | Optional. Your view and the reason. |
| `decision` | string | Empty while the card is `open`. When `answered`: `D-<number>: <short decision>`. When `closed`: the reason. |

## Decided-for-you entry

```json
{ "id": "A-014", "date": "2026-10-11", "title": "Date formats", "decision": "Use the platform Intl API.", "reason": "No new dependency.", "changed": "" }
```

| Field | Type | Rule |
| --- | --- | --- |
| `id` | string | `A-` and 3 or more digits. Unique. |
| `date` | string | `YYYY-MM-DD`. |
| `title`, `decision`, `reason` | string | Required, not empty. |
| `changed` | string | Optional. Empty, or `D-<number>: <text>` when the user changed the entry. `board.py answer A-014` sets it. |

## Image addresses

An image `src` is allowed when it is one of these:

- An address that starts with `https://`.
- A relative path from the board file, for example `assets/onboarding-one.png`. It must not start with `/` or `\`, must not contain `\`, and must not start with a scheme such as `javascript:`, `data:`, `http:`, or `file:`.

Control characters and spaces at the start or the end are not allowed. `board.py check` also makes sure that each relative image file exists.

## The decision log

The log is Markdown. It starts with a short header that states the rules. Each entry is one line:

```markdown
- **D-013** — 2026-10-11 — Supersedes D-012. Use push notifications, asked after the first chore. Reason: Reminders bring people back. Answers Q-003. Source: user.
```

- `Supersedes ...` only when the entry replaces an earlier decision.
- `Reason: ...` only when there is a reason.
- `Answers Q-xxx.` for a card, or `Changes A-xxx.` for a decided-for-you entry.
- Add entries at the end only. Do not edit or delete an entry.

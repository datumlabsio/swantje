---
name: glossary
description: Manage the Swantje domain glossary — add, edit, view, or remove term definitions that the assistant uses to resolve client-specific and non-English terminology without asking the user each time
---

# Swantje Glossary

Manage `.swantje/glossary.json` in the current working directory.

## What the glossary is

A lightweight term store that maps client-specific or non-English words to their technical meaning, table, and field. The assistant reads it at startup (Step 0) so it can resolve unfamiliar terms without stopping to ask.

Good candidates: role names ("closer", "planner"), status codes ("live afspraak", "getekende offerte"), Dutch or other-language field names, business-specific metric definitions.

Not needed: standard SQL terms, common English words, connector names.

## Commands

The user can invoke this skill in several ways. Detect their intent and act:

---

### View — "show glossary", "what terms do you know?"

Read `.swantje/glossary.json` and display as a table:

| Term | Meaning | Field | Table |
|------|---------|-------|-------|
| closer | Sales rep who signed the deal | closer_id | quotes |
| … | … | … | … |

If empty: "Glossary is empty — use `/swantje:glossary add` or just ask me a question with an unknown term and I'll prompt you."

---

### Add — "add term X", "define X as Y", "remember that X means Y"

1. Parse the term and definition from the user's message.
2. Ask for field name and table if not provided (or mark as `null` if genuinely unknown).
3. Write to `.swantje/glossary.json`. Create the file if absent:
   ```json
   { "terms": {} }
   ```
4. Confirm: `Added "X" → glossary.`
5. Offer to commit: "Want me to commit `.swantje/glossary.json` to the repo so the team shares it?"

**Entry schema:**
```json
"<term>": {
  "meaning": "<plain English definition>",
  "field": "<snake_case column name or null>",
  "table": "<table name or null>",
  "added": "<YYYY-MM-DD>"
}
```

---

### Edit — "update X", "change the definition of X"

Read existing entry, show it, apply the user's change, write back.

---

### Remove — "remove X", "forget X"

Confirm before deleting: "Remove `X` from the glossary?" Then delete and confirm.

---

### Seed — "seed the glossary", "add common terms"

Ask the user to list terms their team uses that might be unfamiliar. Collect them interactively (up to 20 at a time), then write all in one go.

Useful prompt to offer: "What words do you use in your business that might be Dutch, jargon, or have a non-obvious technical mapping?"

---

### Export / Share — "share the glossary", "push to GitHub"

If GitHub connector is enabled, offer to commit and push `.swantje/glossary.json` to the connected repo.

If not, tell the user: "Add `.swantje/glossary.json` to your repo — it has no secrets and the whole team benefits. Unlike `config.json`, this one is safe to commit."

---

### Remote glossary (optional)

If `config.json` contains a `glossary.remote_url`, the assistant fetches from that URL at startup instead of (or in addition to) the local file. This lets a team maintain a shared glossary in a GitHub raw URL, Notion export, or any public endpoint returning the same JSON schema.

To configure:
```json
"glossary": {
  "remote_url": "https://raw.githubusercontent.com/your-org/your-repo/main/.swantje/glossary.json",
  "local_override": true
}
```

`local_override: true` means local entries take precedence over remote ones for the same term.

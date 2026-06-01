---
name: connect-hex
description: Connect Hex to Swantje — verifies hex CLI auth, captures workspace context, and enables the analyst and engineer agents to create and run Hex notebooks directly
---

# Hex Connector

Guide the user through connecting their Hex workspace.

## Step 1 — Check hex CLI is installed

```bash
hex --version
```

If not found, tell the user to install it:
```bash
npm install -g @hex-tech/hex-cli
# or
brew install hex-tech/tap/hex
```

## Step 2 — Check authentication

```bash
hex auth status
```

If not authenticated, guide them through login:
```bash
hex auth login
```

This opens a browser-based OAuth flow. Wait for confirmation that login succeeded, then re-run `hex auth status` to confirm.

## Step 3 — Discover workspace context

Once authenticated, collect workspace info:

```bash
# Get available data connections (important for analyst agent)
hex connection list --json
```

Show the user their data connections and ask: "Which connection(s) should the analyst use by default?" Note the connection IDs.

```bash
# List existing projects for context
hex project list --json -n 5
```

## What to collect

**Non-secret (write to `.swantje/config.json`):**
- `workspace_url` — e.g. `https://app.hex.tech/your-org` (ask user or extract from `hex auth status`)
- `default_connection_id` — the data connection to use for SQL cells by default (from step 3)
- `default_connection_name` — human-readable name for display

No secrets needed — hex CLI manages auth via its own profile system.

## Write the config

Read `.swantje/config.json` and update `connectors.hex`:

```json
"hex": {
  "enabled": true,
  "workspace_url": "<value>",
  "default_connection_id": "<value>",
  "default_connection_name": "<value>"
}
```

## Confirm

Tell the user Hex is now connected. The analyst agent can now:
- Create Hex notebooks directly from natural language questions
- Run SQL and Python cells against their connected warehouse
- Open notebooks in the browser automatically

The engineer agent can now:
- Scaffold Hex projects for pipeline outputs
- Create analysis notebooks alongside dlt/dbt work

Suggest they try: `/swantje:analyst` and ask something like "Show me the top 10 customers by revenue this month"

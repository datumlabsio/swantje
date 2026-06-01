---
name: connect-clickhouse
description: Connect a ClickHouse instance to Swantje — collects host/database config and guides env var setup for credentials
---

# ClickHouse Connector

Guide the user through connecting their ClickHouse instance.

## What to collect

Ask the user for each of these. Mark which are required:

**Non-secret (write to `.swantje/config.json`):**
- `host` (required) — e.g. `abc123.us-east.clickhouse.cloud`
- `port` (default: `8443` for HTTPS, `8123` for HTTP)
- `database` (required) — default database name
- `username` (required) — usually `default`
- `secure` (default: `true`) — whether to use HTTPS/TLS

**Secret (env vars only, never written to files):**
- `CLICKHOUSE_PASSWORD` — the password for the username above

## Env var guidance

Tell the user to set:
```bash
export CLICKHOUSE_PASSWORD="your-password-here"
```

Suggest they add it to their shell profile (`~/.zshrc` or `~/.bashrc`) or a `.env` file (gitignored) for persistence.

## Write the config

Once you have the values, read `.swantje/config.json` and update the `connectors.clickhouse` block:

```json
"clickhouse": {
  "enabled": true,
  "host": "<value>",
  "port": <value>,
  "database": "<value>",
  "username": "<value>",
  "secure": true
}
```

Write the updated config back to `.swantje/config.json`.

## Verify

[STUB — v0.0.1] Tell the user that connection verification is not yet implemented. They can test manually with:

```bash
curl "https://<host>:<port>/?query=SELECT+1" \
  -u "<username>:$CLICKHOUSE_PASSWORD"
```

## Confirm

Tell the user ClickHouse is now configured in Swantje and they can use `/swantje:analyst` to query it.

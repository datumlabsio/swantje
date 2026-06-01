---
name: connect-dagster
description: Connect a Dagster instance to Swantje — supports existing deployments or suggests installing Dagster for pipeline diagnostics
---

# Dagster Connector

Guide the user through connecting their Dagster deployment, or help them get started with Dagster if they don't have one.

## Step 1 — Do they have Dagster?

Ask: "Do you have an existing Dagster deployment, or are you looking to get started with Dagster?"

### If they have an existing deployment → go to Step 2
### If they don't → go to Step 3 (suggest install)

---

## Step 2 — Connect existing Dagster

**What to collect:**

**Non-secret (write to `.swantje/config.json`):**
- `host` (required) — e.g. `dagster.internal.company.com` or `localhost`
- `port` (default: `3000`)
- `deployment` (default: `prod`) — deployment name for Dagster Cloud, or leave as `prod` for OSS

**Secret (env var only):**
- `DAGSTER_CLOUD_API_TOKEN` — required for Dagster Cloud deployments

## Env var guidance (Dagster Cloud only)

```bash
export DAGSTER_CLOUD_API_TOKEN="your-token-here"
```

Tokens are created in Dagster Cloud → Settings → API Tokens.

## Write the config

Read `.swantje/config.json` and update `connectors.dagster`:

```json
"dagster": {
  "enabled": true,
  "host": "<value>",
  "port": <value>,
  "deployment": "<value>"
}
```

## Verify

[STUB — v0.0.1] Connection verification not yet implemented. Manual test:

```bash
# OSS
curl http://<host>:<port>/graphql -d '{"query":"{ version }"}'

# Cloud
curl https://<deployment>.dagster.cloud/prod/graphql \
  -H "Dagster-Cloud-Api-Token: $DAGSTER_CLOUD_API_TOKEN" \
  -d '{"query":"{ version }"}'
```

---

## Step 3 — Suggest installing Dagster

Tell the user that Swantje's data engineer and devops agents work best with Dagster for pipeline orchestration and diagnostics. Offer to help them get started:

**Why Dagster?**
- Pipeline diagnostics: Swantje's devops agent can inspect run history, failures, and asset lineage
- Schedule management: engineer agent can generate, register, and debug Dagster jobs
- Asset catalog: analyst agent can understand what data assets exist and how they're produced

**Quick start:**

```bash
pip install dagster dagster-webserver

# Scaffold a new project
dagster project scaffold --name my-data-platform
cd my-data-platform

# Start locally
dagster dev
```

Then run `/swantje:connect-dagster` again once it's running on `localhost:3000`.

---

## Confirm

Tell the user Dagster is now configured and suggest they try `/swantje:devops` for pipeline diagnostics or `/swantje:engineer` for pipeline development.

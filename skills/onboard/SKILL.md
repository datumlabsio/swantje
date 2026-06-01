---
name: onboard
description: Swantje onboarding wizard — connect your data stack (ClickHouse, BigQuery, Dagster, dlt, GitHub, dbt) and set up the three agents
---

# Swantje Onboarding

Welcome the user to Swantje and guide them through connecting their data stack.

## Step 1 — Check for existing config

Look for `.swantje/config.json` in the current working directory.

- If it exists, read it and show which connectors are already enabled.
- If it doesn't exist, tell the user you'll create it now. Copy `config.template.json` from the plugin root to `.swantje/config.json`. If `config.template.json` is not accessible, write the config manually using the structure below.

## Step 2 — Ask which connectors to set up

Present this menu and ask the user to select which ones they want to connect now (they can skip any):

```
Data Warehouses / Databases:
  [ ] ClickHouse
  [ ] BigQuery

Orchestration:
  [ ] Dagster

Data Pipelines:
  [ ] dlt (data load tool)

Source Control:
  [ ] GitHub

Transformations:
  [ ] dbt
```

Tell them they can always run `/swantje:connect-<name>` later to add more.

## Step 3 — Run selected connectors

For each connector the user selected, invoke the corresponding skill:
- ClickHouse → tell them to run `/swantje:connect-clickhouse`
- BigQuery → `/swantje:connect-bigquery`
- Dagster → `/swantje:connect-dagster`
- dlt → `/swantje:connect-dlt`
- GitHub → `/swantje:connect-github`
- dbt → `/swantje:connect-dbt`

Walk through them one by one in this session if the user wants — just invoke each skill inline.

## Step 4 — Introduce the agents

Once at least one connector is set up, introduce the three agents:

```
/swantje:analyst   — query your data warehouse, explore schemas, run analytics
/swantje:engineer  — build pipelines, write dlt/dbt code, manage Dagster jobs
/swantje:devops    — diagnose infrastructure, review Dagster health, manage deployments
```

## Step 5 — Final check

Show a summary of what's connected. Remind the user to add `.swantje/config.json` to `.gitignore` if it contains any non-public values.

## Config structure (for reference)

`.swantje/config.json` — non-secret config lives here. Secrets go in env vars.

```json
{
  "version": "0.0.1",
  "connectors": {
    "clickhouse": { "enabled": false, "host": null, ... },
    "bigquery": { "enabled": false, "project_id": null, ... },
    ...
  }
}
```

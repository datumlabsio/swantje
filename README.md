# Swantje

Data platform copilot for Claude Code. Connect your data stack and get a single assistant that handles analytics, pipeline engineering, and devops.

## What it does

Swantje connects to your existing tools — ClickHouse, BigQuery, Dagster, dlt, dbt, GitHub, Hex — and gives you one assistant that understands your environment. Query data, build pipelines, diagnose failures — no switching agents, no re-explaining your setup.

## Install

```
/plugin marketplace add datumlabsio/swantje
/plugin install swantje@datumlabs
```

Then run the onboarding wizard:

```
/swantje:onboard
```

## Assistant

### `/swantje:assistant`
One agent for everything:
- **Analytics** — query your warehouse, explore schemas, explain data. When Hex is connected, creates and runs notebooks directly.
- **Engineering** — build dlt pipelines, generate Dagster assets, write dbt models. Reads your existing code before generating.
- **DevOps** — diagnose failures, review Dagster health, audit configs. Gives you root cause, not just the error.

## Connectors

| Command | What it connects |
|---|---|
| `/swantje:connect-clickhouse` | ClickHouse database |
| `/swantje:connect-bigquery` | Google BigQuery |
| `/swantje:connect-hex` | Hex notebooks — unlocks direct query execution |
| `/swantje:connect-dagster` | Dagster orchestration |
| `/swantje:connect-dlt` | dlt pipeline directory |
| `/swantje:connect-github` | GitHub org and repos |
| `/swantje:connect-dbt` | dbt project |

Connection config is stored in `.swantje/config.json` in your project. Secrets stay in env vars — never written to files.

## Requirements

- Claude Code v2.1.0+
- At least one connector configured (run `/swantje:onboard` to get started)

## Version

`0.3.0` — Unified assistant. Single agent replaces analyst, engineer, and devops.

## Made by

[DatumLabs](https://datumlabs.io) · [dev@datumlabs.io](mailto:dev@datumlabs.io)

# Swantje

Data platform copilot for Claude Code. Connect your data stack and get three specialized agents that understand your environment.

## What it does

Swantje connects to your existing tools — ClickHouse, BigQuery, Dagster, dlt, dbt, GitHub — and gives you agents that can query your data, build pipelines, and diagnose infrastructure without needing to re-explain your setup every time.

## Install

```
/plugin marketplace add datumlabsio/swantje
/plugin install swantje@datumlabs
```

Then run the onboarding wizard:

```
/swantje:onboard
```

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

Connection config is stored in `.swantje/config.json` in your project. Secrets (passwords, tokens) stay in env vars — never written to files.

## Agents

### `/swantje:analyst`
Queries your connected data warehouse, explores schemas, and explains data. Knows your dbt models so it can answer questions about where data comes from. **When Hex is connected, creates and runs notebooks directly** — no copy-pasting queries.

### `/swantje:engineer`
Builds and maintains pipelines. Generates dlt sources, Dagster assets, and dbt models. Reads your existing code before generating anything so it matches your conventions.

### `/swantje:devops`
Diagnoses pipeline failures, reviews Dagster deployment health, and audits infrastructure configs. Point it at an error and it explains the root cause.

## Requirements

- Claude Code v2.1.0+
- At least one connector configured (run `/swantje:onboard` to get started)

## Version

`0.1.0` — Hex integration. Analyst agent now creates and runs notebooks directly when Hex is connected.

## Made by

[DatumLabs](https://datumlabs.io) · [dev@datumlabs.io](mailto:dev@datumlabs.io)

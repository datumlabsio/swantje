---
name: connect-dlt
description: Connect a dlt (data load tool) project to Swantje — points to pipeline directory so the engineer agent can read, run, and generate dlt pipelines
---

# dlt Connector

Guide the user through connecting their dlt project.

## What is dlt?

If the user seems unfamiliar: dlt (data load tool) is a Python library for building data pipelines. Swantje's engineer agent uses it to generate new pipelines and understand existing ones.

## Step 1 — Do they have a dlt project?

Ask: "Do you have an existing dlt pipeline directory, or are you starting from scratch?"

### If they have one → collect the directory path
### If they're starting fresh → offer to scaffold one after setup

## What to collect

**Non-secret (write to `.swantje/config.json`):**
- `pipeline_dir` (required) — path to the root of their dlt project, relative to project root or absolute. E.g. `./pipelines` or `/home/user/data-pipelines`

No secrets needed at the connector level — dlt pipelines manage their own credentials via `secrets.toml` or env vars, which the engineer agent will help configure per-pipeline.

## Write the config

Read `.swantje/config.json` and update `connectors.dlt`:

```json
"dlt": {
  "enabled": true,
  "pipeline_dir": "<value>"
}
```

## Verify

[STUB — v0.0.1] Basic check — look for `pipeline_dir` and confirm it exists and contains Python files:

```bash
ls <pipeline_dir>/*.py 2>/dev/null || echo "No Python files found"
```

If the directory doesn't exist, offer to create it.

## Scaffold new dlt project (if starting fresh)

```bash
pip install dlt

mkdir -p pipelines
cd pipelines

# Start a new pipeline (interactive)
dlt init <source> <destination>
# e.g.: dlt init github bigquery
```

Tell the user to run `/swantje:connect-dlt` again once they have a directory.

## Confirm

Tell the user dlt is connected and they can use `/swantje:engineer` to build or modify pipelines.

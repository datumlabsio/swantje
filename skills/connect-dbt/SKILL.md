---
name: connect-dbt
description: Connect a dbt project to Swantje — project dir, profiles, and target so the engineer and analyst agents understand your transformation layer
---

# dbt Connector

Guide the user through connecting their dbt project.

## What to collect

**Non-secret (write to `.swantje/config.json`):**
- `project_dir` (required) — path to the dbt project (where `dbt_project.yml` lives), e.g. `./transform` or `/home/user/analytics/transform`
- `profiles_dir` (optional) — path to `profiles.yml`. Defaults to `~/.dbt/`
- `target` (default: `dev`) — dbt target to use

No secrets at the connector level — dbt credentials live in `profiles.yml` which the user already manages.

## Step 1 — Find the dbt project

Ask for `project_dir`. Verify `dbt_project.yml` exists there:

```bash
ls <project_dir>/dbt_project.yml
```

If not found, help them locate it or confirm it's a valid dbt project.

## Step 2 — Confirm profiles

Ask if their `profiles.yml` is in the default location (`~/.dbt/profiles.yml`) or elsewhere. If elsewhere, collect the path.

## Step 3 — Confirm target

Ask which target to use. Common values: `dev`, `prod`, `staging`. Default to `dev`.

## Write the config

Read `.swantje/config.json` and update `connectors.dbt`:

```json
"dbt": {
  "enabled": true,
  "project_dir": "<value>",
  "profiles_dir": "<value or null>",
  "target": "<value>"
}
```

## Verify

[STUB — v0.0.1] Verification not yet implemented. Manual test:

```bash
cd <project_dir> && dbt debug --target <target>
```

## Confirm

Tell the user dbt is connected. Agents now understand the transformation layer:
- `/swantje:analyst` — can reference dbt models when answering questions about data
- `/swantje:engineer` — can generate, refactor, and test dbt models in the project

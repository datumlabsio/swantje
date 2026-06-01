---
name: connect-bigquery
description: Connect a BigQuery project to Swantje — collects project/dataset config and guides service account credential setup
---

# BigQuery Connector

Guide the user through connecting their BigQuery project.

## What to collect

**Non-secret (write to `.swantje/config.json`):**
- `project_id` (required) — GCP project ID, e.g. `my-company-dwh`
- `dataset` (optional) — default dataset to query against
- `location` (default: `US`) — dataset region

**Secret (env var only):**
- `GOOGLE_APPLICATION_CREDENTIALS` — path to a service account JSON key file

## Credential guidance

Two options — present both:

**Option A — Service account key (recommended for local dev):**
1. Go to GCP Console → IAM → Service Accounts
2. Create or select a service account with `BigQuery Data Viewer` + `BigQuery Job User` roles
3. Download a JSON key
4. Set the env var:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
   ```

**Option B — Application Default Credentials (recommended for CI/cloud):**
```bash
gcloud auth application-default login
```
No env var needed when ADC is set up.

## Write the config

Read `.swantje/config.json` and update `connectors.bigquery`:

```json
"bigquery": {
  "enabled": true,
  "project_id": "<value>",
  "dataset": "<value or null>",
  "location": "<value>"
}
```

## Verify

[STUB — v0.0.1] Connection verification not yet implemented. Manual test:

```bash
bq query --project_id=<project_id> 'SELECT 1'
```

## Confirm

Tell the user BigQuery is now configured and they can use `/swantje:analyst` to query it.

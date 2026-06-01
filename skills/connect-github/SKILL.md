---
name: connect-github
description: Connect GitHub repos to Swantje — org, repo list, and token setup so agents can read code, issues, and PRs
---

# GitHub Connector

Guide the user through connecting their GitHub organization and repositories.

## What to collect

**Non-secret (write to `.swantje/config.json`):**
- `org` (required) — GitHub organization name, e.g. `datumlabs`
- `repos` (optional) — list of specific repos to focus on, e.g. `["data-platform", "analytics"]`. Leave empty for all repos in the org.

**Secret (env var only):**
- `GITHUB_TOKEN` — a GitHub personal access token or fine-grained token

## Token guidance

**Minimum required scopes:**
- `repo` (read access to code, issues, PRs)
- `read:org` (read org membership)

**Create a token:**
1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Set repository access to the repos you want Swantje to see
3. Permissions: `Contents: Read`, `Issues: Read`, `Pull requests: Read`, `Metadata: Read`

```bash
export GITHUB_TOKEN="github_pat_..."
```

## Write the config

Read `.swantje/config.json` and update `connectors.github`:

```json
"github": {
  "enabled": true,
  "org": "<value>",
  "repos": ["<repo1>", "<repo2>"]
}
```

If the user provides no specific repos, write `"repos": []` (means all org repos).

## Verify

[STUB — v0.0.1] Verification not yet implemented. Manual test:

```bash
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/orgs/<org>/repos?per_page=1
```

## Confirm

Tell the user GitHub is connected. Agents can now reference their codebase context:
- `/swantje:engineer` — understands repo structure, can suggest PRs, generate code that fits conventions
- `/swantje:devops` — can read CI/CD configs, action workflows, infrastructure code

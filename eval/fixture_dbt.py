#!/usr/bin/env python3
"""
Build the Westwise dbt eval fixture.

Reads the westwise-dbt project from the filesystem (no live ClickHouse required
for the schema layer) and optionally queries ClickHouse for model row counts.

Outputs eval/fixtures/dbt.json with:
  - context_turn: full dbt project context (models, sources, lineage, SQL excerpts)
  - ground_truth: model row counts from analytics_prod (if --schema-only not set)
  - grounded_cases: 6 eval cases testing dbt capabilities

Usage:
    python3 eval/fixture_dbt.py                  # full build (live row counts)
    python3 eval/fixture_dbt.py --schema-only     # filesystem only, no ClickHouse
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURE_PATH = FIXTURE_DIR / "dbt.json"
WESTWISE_DBT = Path.home() / "dev" / "westwise-dbt" / "westwise_analytics"
WESTWISE_INTERNAL = Path.home() / "dev" / "westwise-internal"
METADATA_CACHE = WESTWISE_INTERNAL / "data" / "metadata_raw.json"
ENV_FILE = WESTWISE_INTERNAL / ".env"

# Key intermediate model SQL files to excerpt in context
KEY_MODEL_EXCERPTS = [
    ("sales", "int_sales__deals_legacy_cleansed.sql"),
    ("sales", "int_sales__agent_performance.sql"),
    ("core_metrics", "int_ww_daily.sql"),
]

# Ground-truth queries for model row counts (analytics_prod)
GROUND_TRUTH_QUERIES = [
    {
        "id": "deals_legacy_rows",
        "label": "Row count: int_sales__deals_legacy_cleansed",
        "sql": "SELECT count() FROM analytics_prod.int_sales__deals_legacy_cleansed",
    },
    {
        "id": "agent_perf_rows",
        "label": "Row count: int_sales__agent_performance",
        "sql": "SELECT count() FROM analytics_prod.int_sales__agent_performance",
    },
    {
        "id": "deal_stages",
        "label": "Distinct deal stages in int_sales__deals_legacy_cleansed",
        "sql": "SELECT groupArray(DISTINCT stage) FROM analytics_prod.int_sales__deals_legacy_cleansed WHERE stage IS NOT NULL",
    },
    {
        "id": "ww_daily_rows",
        "label": "Row count: int_ww_daily (if materialized)",
        "sql": "SELECT count() FROM analytics_prod.int_ww_daily",
    },
]


def load_env():
    if not ENV_FILE.exists():
        return
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'").strip()
            os.environ[key.strip()] = val


def get_connection():
    try:
        from clickhouse_driver import Client
    except ImportError:
        print("pip install clickhouse-driver", file=sys.stderr)
        sys.exit(1)
    secure = os.environ.get("CLICKHOUSE_SECURE", "true").lower() in ("true", "1", "yes")
    return Client(
        host=os.environ["CLICKHOUSE_HOST"],
        port=int(os.environ.get("CLICKHOUSE_PORT", "9440")),
        user=os.environ["CLICKHOUSE_USER"],
        password=os.environ["CLICKHOUSE_PASSWORD"],
        database=os.environ.get("CLICKHOUSE_DATABASE", "default"),
        secure=secure,
    )


def run_query(client, sql):
    result = client.execute(sql, with_column_types=True)
    rows, col_types = result
    col_names = [c[0] for c in col_types]
    return [dict(zip(col_names, row)) for row in rows]


def enumerate_models(models_dir: Path) -> dict[str, list[str]]:
    """Walk models/ and return {layer/domain: [model_name, ...]}."""
    out: dict[str, list[str]] = {}
    for sql_file in sorted(models_dir.rglob("*.sql")):
        rel = sql_file.relative_to(models_dir)
        parts = rel.parts
        if len(parts) == 1:
            key = "root"
        else:
            key = "/".join(parts[:-1])
        out.setdefault(key, []).append(sql_file.stem)
    return out


def enumerate_sources(sources_dir: Path) -> list[str]:
    """Return list of source YAML filenames."""
    if not sources_dir.exists():
        return []
    return sorted(f.stem for f in sources_dir.glob("*.yml"))


def read_sql_excerpt(layer: str, filename: str, max_lines: int = 25) -> str:
    path = WESTWISE_DBT / "models" / "intermediate" / layer / filename
    if not path.exists():
        return ""
    lines = path.read_text().splitlines()[:max_lines]
    return "\n".join(lines)


def get_row_counts_from_cache(meta: dict) -> dict[str, int | None]:
    return {t["name"]: t.get("total_rows") for t in meta["tables"] if t.get("database") == "analytics_prod"}


def build_context(models: dict, sources: list, row_counts: dict, ground_truth: list) -> str:
    lines = [
        "dbt project: westwise  |  profile: westwise → ClickHouse analytics_prod",
        f"Total models: {sum(len(v) for v in models.values())}  |  Sources: {len(sources)} YAML files",
        "",
        "## Model inventory by domain",
    ]

    # Group by top-level layer
    by_layer: dict[str, dict] = {}
    for path_key, model_names in models.items():
        parts = path_key.split("/")
        layer = parts[0] if parts[0] != "root" else "root"
        domain = parts[1] if len(parts) > 1 else ""
        by_layer.setdefault(layer, {}).setdefault(domain, []).extend(model_names)

    for layer in ["intermediate", "staging", "semantic", "root"]:
        if layer not in by_layer:
            continue
        lines.append(f"\n### {layer}/")
        for domain, names in sorted(by_layer[layer].items()):
            lines.append(f"  {domain or '(root)'}:")
            for name in sorted(names)[:12]:
                rc = row_counts.get(name)
                rc_str = f" ({rc:,} rows)" if rc else ""
                lines.append(f"    • {name}{rc_str}")
            if len(names) > 12:
                lines.append(f"    … +{len(names)-12} more")

    lines += [
        "",
        "## Source systems (13 YAML definitions)",
        "  Zoho CRM (legacy + latest), Zoho Voice (legacy), GA4 (westwise + accident-group),",
        "  Google Ads, Facebook Ads, CallRail, Zoho Books, Google Sheets,",
        "  billing (GCP, ClickHouse, Langfuse, Decodo)",
        "",
        "## Key lineage paths",
        "  stg_zoho_crm__deals_legacy",
        "    → int_sales__deals_legacy_cleansed",
        "      → int_sales__deals_legacy_cleansed_stream_v (+ streaming branch)",
        "        → int_ww_daily",
        "  stg_callrails__calls",
        "    → int_voice_calls__callrails_streaming_v",
        "      → int_sales__affiliate_performance",
        "  stg_google_ads__campaigns",
        "    → int_google_ads__campaigns_v",
        "      → int_marketing__cpc_lhp → int_ww_daily",
        "",
        "## ClickHouse-specific patterns in use",
        "  FINAL clause (ReplacingMergeTree dedup)",
        "  merge() function (wildcard GA4 tables)",
        "  toTimeZone(toDateTime64(...), 'America/Los_Angeles')",
        "  JSONExtractString(), JSONExtractArrayRaw(), arrayFirst()",
        "  ROW_NUMBER() OVER (PARTITION BY id ORDER BY modified_time DESC)",
        "  toDate(), toDateTime64(), assumeNotNull(), nullIf()",
    ]

    # Append verified row counts from ground truth
    if ground_truth:
        lines += ["", "## Verified model row counts"]
        for gt in ground_truth:
            if gt.get("value") is not None:
                lines.append(f"  {gt['label']}: {gt['value']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Build Westwise dbt eval fixture")
    parser.add_argument("--schema-only", action="store_true", help="Skip live ClickHouse queries")
    args = parser.parse_args()

    load_env()

    models_dir = WESTWISE_DBT / "models"
    if not models_dir.exists():
        print(f"dbt project not found at {WESTWISE_DBT}", file=sys.stderr)
        sys.exit(1)

    print("Enumerating dbt models…", end=" ", flush=True)
    models = enumerate_models(models_dir)
    total = sum(len(v) for v in models.values())
    print(f"{total} models")

    print("Reading source definitions…", end=" ", flush=True)
    sources = enumerate_sources(models_dir / "staging" / "sources")
    print(f"{len(sources)} source files")

    print("Loading row counts from metadata cache…", end=" ", flush=True)
    if not METADATA_CACHE.exists():
        print("WARNING: metadata cache not found, row counts will be missing")
        row_counts = {}
    else:
        meta = json.loads(METADATA_CACHE.read_text())
        row_counts = get_row_counts_from_cache(meta)
        print(f"{len(row_counts)} tables")

    # Live ground-truth queries
    ground_truth = []
    if not args.schema_only:
        print("Running ground-truth queries against ClickHouse…")
        try:
            client = get_connection()
            for q in GROUND_TRUTH_QUERIES:
                print(f"  {q['id']}… ", end="", flush=True)
                try:
                    rows = run_query(client, q["sql"])
                    val = list(rows[0].values())[0] if rows else None
                    if isinstance(val, (list, tuple)):
                        val = sorted(str(v) for v in val)
                    ground_truth.append({**q, "value": val})
                    print(val if not isinstance(val, list) else f"{len(val)} stages")
                except Exception as e:
                    print(f"ERROR: {e}")
                    ground_truth.append({**q, "value": None, "error": str(e)})
        except Exception as e:
            print(f"Connection failed: {e}", file=sys.stderr)
            print("Use --schema-only to build without live queries.", file=sys.stderr)
            sys.exit(1)
    else:
        print("Skipping live queries (--schema-only)")

    context_content = build_context(models, sources, row_counts, ground_truth)

    # Pull deal_stages from ground truth for the test case rubric
    deal_stages = []
    for gt in ground_truth:
        if gt["id"] == "deal_stages" and isinstance(gt.get("value"), list):
            deal_stages = gt["value"]

    fixture = {
        "name": "dbt",
        "description": "Westwise dbt project — 102 models, 13 sources, ClickHouse target",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "dbt_project_path": str(WESTWISE_DBT),
        "model_count": total,
        "source_count": len(sources),
        "context_turn": {
            "role": "assistant",
            "content": (
                "Config loaded from `.swantje/config.json`:\n\n"
                "```json\n"
                '{\n  "connectors": {\n'
                '    "clickhouse": {\n'
                '      "enabled": true,\n'
                '      "host": "wh43usg2hz.us-central1.gcp.clickhouse.cloud",\n'
                '      "database": "analytics_prod"\n'
                "    },\n"
                '    "dbt": {\n'
                '      "enabled": true,\n'
                '      "project_dir": "~/dev/westwise-dbt/westwise_analytics",\n'
                '      "profiles_dir": "~/.dbt",\n'
                '      "target": "prod"\n'
                "    }\n  }\n}\n"
                "```\n\n"
                + context_content
                + "\n\nReady."
            ),
        },
        "ground_truth": ground_truth,
        "grounded_cases": [
            {
                "id": "dbt-refactor-001",
                "customer": "dbt",
                "category": "config_change",
                "language": "en",
                "prompt": "Refactor int_sales__deals_legacy_cleansed to use incremental materialization",
                "ground_truth_id": None,
                "rubric": {
                    "shows_config_block": "Shows the dbt config block change (materialized='incremental')",
                    "adds_where_clause": "Adds an incremental WHERE clause filtering on modified_time or created_time",
                    "no_full_rewrite": "Does not rewrite the entire model SQL — surgical change only",
                    "immediate": "Executes immediately, no confirmation ask",
                },
                "must_have": ["incremental", "modified_time"],
                "must_not_have": ["Should I", "Are you sure", "Do you want"],
            },
            {
                "id": "dbt-test-001",
                "customer": "dbt",
                "category": "config_change",
                "language": "en",
                "prompt": "Add a not_null and accepted_values test for the stage column in int_sales__deals_legacy_cleansed",
                "ground_truth_id": "deal_stages",
                "note": "accepted_values list should include the real stage values from ground truth",
                "rubric": {
                    "generates_yaml": "Generates a dbt schema YAML test block, not Python or SQL",
                    "not_null_test": "Includes a not_null test for the stage column",
                    "accepted_values_test": "Includes an accepted_values test with real stage names",
                    "correct_model_name": "References int_sales__deals_legacy_cleansed correctly",
                },
                "must_have": ["not_null", "accepted_values", "stage"],
                "must_not_have": [],
            },
            {
                "id": "dbt-diagnostic-001",
                "customer": "dbt",
                "category": "diagnostic",
                "language": "en",
                "prompt": "My dbt run fails: Database Error in model int_sales__deals_legacy_cleansed — Table `westwise.stg_zoho_crm__deals_legacy` doesn't exist",
                "ground_truth_id": None,
                "rubric": {
                    "hypothesis_first": "States most likely cause first (ref() target not built, wrong schema, spelling)",
                    "evidence_section": "Has an Evidence section citing the error",
                    "conclusion_section": "Has a Conclusion section",
                    "fix_section": "Has a Fix section with concrete steps (dbt run --select stg_zoho_crm__deals_legacy, or check ref() spelling)",
                    "knows_dbt_schema": "Understands dbt writes to the 'westwise' schema in ClickHouse",
                },
                "must_have": ["Hypothesis", "Evidence", "Fix"],
                "must_not_have": [],
            },
            {
                "id": "dbt-logic-001",
                "customer": "dbt",
                "category": "logic_explanation",
                "language": "en",
                "prompt": "What source tables feed into int_ww_daily?",
                "ground_truth_id": None,
                "rubric": {
                    "traces_dag": "Traces the lineage: Google Ads → int_google_ads__* → int_ww_daily; Zoho CRM → int_sales__* → int_ww_daily",
                    "names_sources": "Names the actual source systems (Google Ads, Zoho CRM)",
                    "plain_language": "Explains in plain language — no SQL code blocks",
                    "concise": "≤150 words",
                },
                "must_have": [],
                "must_not_have": ["```sql", "```python"],
            },
            {
                "id": "dbt-sql-001",
                "customer": "dbt",
                "category": "sql_technical",
                "language": "en",
                "prompt": "Give me the raw compiled SQL for int_sales__deals_legacy_cleansed (resolve all refs)",
                "ground_truth_id": None,
                "rubric": {
                    "raw_sql_only": "Returns a SQL block, comment header, minimal prose",
                    "resolves_refs": "Replaces {{ ref('...') }} with actual table paths (analytics_prod.stg_zoho_crm__deals_legacy)",
                    "clickhouse_dialect": "Uses ClickHouse functions (toDate, concat, replaceRegexpAll, right)",
                    "comment_header": "SQL block starts with a comment describing the model",
                },
                "must_have": ["```sql", "toDate"],
                "must_not_have": ["{{ ref(", "Here is the SQL", "This query does", "This query returns"],
            },
            {
                "id": "dbt-logic-002",
                "customer": "dbt",
                "category": "logic_explanation",
                "language": "en",
                "prompt": "How does int_sales__deals_legacy_cleansed_stream_v combine batch and streaming data?",
                "ground_truth_id": None,
                "rubric": {
                    "explains_hybrid": "Explains the two-branch pattern: batch (stable historical) + streaming (today's updates)",
                    "mentions_final": "Mentions the FINAL clause used for ReplacingMergeTree deduplication",
                    "mentions_dedup": "Explains that the model deduplicates by id keeping latest modified_time",
                    "plain_language": "No SQL code blocks — plain language explanation",
                    "concise": "≤150 words",
                },
                "must_have": [],
                "must_not_have": ["```sql", "```python"],
            },
        ],
    }

    # Tag all grounded cases with customer
    for c in fixture["grounded_cases"]:
        c.setdefault("customer", fixture["name"])

    FIXTURE_DIR.mkdir(exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(fixture, indent=2, default=str))
    print(f"\nFixture written → {FIXTURE_PATH}")
    print(f"  {total} models enumerated")
    print(f"  {len(ground_truth)} ground-truth metrics")
    print(f"  {len(fixture['grounded_cases'])} grounded eval cases")
    print(f"\nRun: python3 eval/run.py --fixture dbt --customer dbt --yes")


if __name__ == "__main__":
    main()

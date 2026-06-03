#!/usr/bin/env python3
"""
Build the Westwise eval fixture.

Connects to the real ClickHouse instance (read-only, westwise_reader) and:
  1. Extracts a compact schema summary from the analytics_prod layer
  2. Runs a small set of ground-truth queries to get actual metric values
  3. Writes eval/fixtures/westwise.json

The fixture is consumed by eval/run.py --fixture westwise, which swaps the
simulated EVAL_CONTEXT_TURN for one grounded in real schema + real data.

Usage:
    python3 eval/fixture_westwise.py                    # build / refresh
    python3 eval/fixture_westwise.py --schema-only      # skip live queries
    python3 eval/fixture_westwise.py --metadata-cache   # use cached metadata_raw.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURE_PATH = FIXTURE_DIR / "westwise.json"
WESTWISE_INTERNAL = Path.home() / "dev" / "westwise-internal"
METADATA_CACHE = WESTWISE_INTERNAL / "data" / "metadata_raw.json"
ENV_FILE = WESTWISE_INTERNAL / ".env"

# Tables to include in the eval context (analytics_prod layer only)
SCHEMA_TABLES = [
    "int_sales__deals_legacy_cleansed",
    "int_sales__deals_information_legacy_cleansed",
    "int_sales__agent_performance",
    "int_sales__affiliate_performance",
    "int_platform_billing",
    "int_sales__cpl",
    "int_marketing__cpc_lhp",
    "int_sales__common_drops",
]

# Ground-truth queries — each returns a single scalar we can assert against
GROUND_TRUTH_QUERIES = [
    {
        "id": "total_deals",
        "label": "Total deals in int_sales__deals_legacy_cleansed",
        "sql": "SELECT count() FROM analytics_prod.int_sales__deals_legacy_cleansed",
        "description": "Total row count of deals table",
    },
    {
        "id": "signed_deals",
        "label": "Contract Signed deals",
        "sql": "SELECT count() FROM analytics_prod.int_sales__deals_legacy_cleansed WHERE stage = 'Contract Signed'",
        "description": "Count of deals with stage = Contract Signed",
    },
    {
        "id": "distinct_agents",
        "label": "Distinct active agents",
        "sql": "SELECT count(DISTINCT agent_email) FROM analytics_prod.int_sales__agent_performance",
        "description": "Number of distinct agent emails in the performance table",
    },
    {
        "id": "distinct_states",
        "label": "Distinct states in deals",
        "sql": "SELECT count(DISTINCT state) FROM analytics_prod.int_sales__deals_legacy_cleansed WHERE state IS NOT NULL",
        "description": "Number of distinct US states present in deals",
    },
    {
        "id": "total_affiliate_leads",
        "label": "Total affiliate distributed leads",
        "sql": "SELECT sum(total_affiliate_distributed_leads) FROM analytics_prod.int_sales__affiliate_performance",
        "description": "Sum of all affiliate distributed leads",
    },
    {
        "id": "latest_deal_date",
        "label": "Most recent deal creation date",
        "sql": "SELECT max(toDate(created_time)) FROM analytics_prod.int_sales__deals_legacy_cleansed",
        "description": "Latest date in the deals table",
    },
    {
        "id": "deal_stages",
        "label": "All distinct deal stages",
        "sql": "SELECT groupArray(DISTINCT stage) FROM analytics_prod.int_sales__deals_legacy_cleansed WHERE stage IS NOT NULL",
        "description": "List of all distinct stage values",
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
            val = val.strip().strip('"')
            os.environ.setdefault(key.strip(), val)


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


def run_query(client, sql: str):
    result = client.execute(sql, with_column_types=True)
    rows, col_types = result
    col_names = [c[0] for c in col_types]
    return [dict(zip(col_names, row)) for row in rows]


def build_schema_context(meta: dict) -> str:
    """Build a compact schema summary string for the eval context turn."""
    cols = meta["columns"]
    tables_meta = {t["name"]: t for t in meta["tables"] if t["database"] == "analytics_prod"}

    lines = [
        "Connected to ClickHouse (Westwise). Analytics layer: `analytics_prod`.",
        "",
        "Key tables:",
    ]

    for tbl in SCHEMA_TABLES:
        if tbl not in tables_meta:
            continue
        row_count = tables_meta[tbl].get("total_rows")
        row_str = f"{row_count:,}" if row_count else "?"
        tcols = [
            c for c in cols
            if c["database"] == "analytics_prod" and c["table"] == tbl
        ]
        col_summaries = []
        for c in tcols[:12]:
            comment = f" — {c['comment']}" if c.get("comment") else ""
            col_summaries.append(f"{c['name']} ({c['type']}){comment}")
        if len(tcols) > 12:
            col_summaries.append(f"+{len(tcols) - 12} more")

        lines.append(f"\n**{tbl}** ({row_str} rows)")
        for cs in col_summaries:
            lines.append(f"  • {cs}")

    return "\n".join(lines)


def build_ground_truth_context(ground_truth: list[dict]) -> str:
    """Append verified metric values to the context so the judge can assert against them."""
    lines = ["\n\nVerified ground-truth metrics (use these to validate model responses):"]
    for gt in ground_truth:
        val = gt.get("value", "—")
        lines.append(f"  • {gt['label']}: **{val}**")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Build Westwise eval fixture")
    parser.add_argument("--schema-only", action="store_true", help="Skip live ClickHouse queries")
    parser.add_argument("--metadata-cache", action="store_true", help="Use cached metadata_raw.json (default if exists)")
    args = parser.parse_args()

    load_env()

    # ------------------------------------------------------------------ schema
    print("Loading schema from metadata cache…", end=" ", flush=True)
    if not METADATA_CACHE.exists():
        print(f"\nMetadata cache not found at {METADATA_CACHE}", file=sys.stderr)
        print("Run: python3 ~/dev/westwise-internal/scripts/db_extract.py", file=sys.stderr)
        sys.exit(1)
    meta = json.loads(METADATA_CACHE.read_text())
    print(f"OK ({len(meta['tables'])} tables, {len(meta['columns'])} columns)")

    schema_context = build_schema_context(meta)

    # ----------------------------------------------------------- ground truth
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
                    # Flatten lists for readability
                    if isinstance(val, (list, tuple)):
                        val = sorted(str(v) for v in val)
                    ground_truth.append({**q, "value": val})
                    print(f"{val}")
                except Exception as e:
                    print(f"ERROR: {e}")
                    ground_truth.append({**q, "value": None, "error": str(e)})
        except Exception as e:
            print(f"Connection failed: {e}", file=sys.stderr)
            print("Use --schema-only to build fixture without live queries.", file=sys.stderr)
            sys.exit(1)
    else:
        print("Skipping live queries (--schema-only)")

    # ------------------------------------------------------- assemble fixture
    context_content = schema_context
    if ground_truth:
        context_content += build_ground_truth_context(ground_truth)

    fixture = {
        "name": "westwise",
        "description": "Westwise ClickHouse analytics layer — real schema + verified metrics",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "schema_tables": SCHEMA_TABLES,
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
                "    }\n  }\n}\n"
                "```\n\n"
                + context_content
                + "\n\nReady."
            ),
        },
        "ground_truth": ground_truth,
        # Eval cases that can be grounded against real data
        "grounded_cases": [
            {
                "id": "ww-metric-001",
                "customer": "westwise",
                "category": "metric_exact_number",
                "language": "en",
                "prompt": "How many total deals do we have?",
                "ground_truth_id": "total_deals",
                "rubric": {
                    "number_first": "Response leads with a number",
                    "correct_value": "Number matches the ground-truth total_deals count",
                    "filters_in_parens": "Any scope filter noted in parentheses",
                },
                "must_have": [],
                "must_not_have": ["Here is", "Let me"],
            },
            {
                "id": "ww-metric-002",
                "category": "metric_exact_number",
                "language": "en",
                "prompt": "How many Contract Signed deals are there?",
                "ground_truth_id": "signed_deals",
                "rubric": {
                    "number_first": "Response leads with a number",
                    "correct_value": "Number matches the ground-truth signed_deals count (stage = 'Contract Signed')",
                    "correct_filter": "Filters on stage = 'Contract Signed', not 'Signed'",
                },
                "must_have": [],
                "must_not_have": [],
            },
            {
                "id": "ww-metric-003",
                "category": "metric_exact_number",
                "language": "en",
                "prompt": "How many distinct agents are in the performance table?",
                "ground_truth_id": "distinct_agents",
                "rubric": {
                    "number_first": "Response leads with a number",
                    "correct_value": "Number matches ground-truth distinct_agents count",
                },
                "must_have": [],
                "must_not_have": [],
            },
            {
                "id": "ww-lookup-001",
                "category": "data_lookup",
                "language": "en",
                "prompt": "What are all the distinct deal stages?",
                "ground_truth_id": "deal_stages",
                "rubric": {
                    "lists_stages": "Lists the actual stage values (not a generic description)",
                    "correct_stages": "Stage values match the ground-truth deal_stages list",
                    "structured": "Output is a list or table, not prose",
                },
                "must_have": [],
                "must_not_have": [],
            },
            {
                "id": "ww-diagnostic-001",
                "category": "diagnostic",
                "language": "en",
                "prompt": "Why would the first row in int_sales__deals_legacy_cleansed have a NULL state?",
                "ground_truth_id": None,
                "rubric": {
                    "hypothesis_first": "States most likely root cause (no state captured at creation, LEFT JOIN null, data quality)",
                    "references_correct_table": "References int_sales__deals_legacy_cleansed and the state column",
                    "check_query_provided": "Provides a ClickHouse query to investigate",
                },
                "must_have": ["NULL", "state"],
                "must_not_have": [],
            },
            {
                "id": "ww-sql-001",
                "category": "sql_technical",
                "language": "en",
                "prompt": "Give me the SQL for total signed deals grouped by state, last 90 days",
                "ground_truth_id": None,
                "rubric": {
                    "raw_sql_only": "Returns a SQL block with comment header, no prose",
                    "correct_table": "Queries analytics_prod.int_sales__deals_legacy_cleansed",
                    "correct_filter": "Filters on stage = 'Signed' and created_time within 90 days",
                    "groups_by_state": "Groups by state column",
                    "clickhouse_dialect": "Uses ClickHouse syntax (toDate, now(), interval)",
                },
                "must_have": ["```sql", "Signed", "state"],
                "must_not_have": ["Here is the", "This query"],
            },
        ],
    }

    # Ensure all grounded cases have the customer tag for --customer filter
    for c in fixture["grounded_cases"]:
        c.setdefault("customer", fixture["name"])

    FIXTURE_DIR.mkdir(exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(fixture, indent=2, default=str))
    print(f"\nFixture written → {FIXTURE_PATH}")
    print(f"  {len(fixture['ground_truth'])} ground-truth metrics")
    print(f"  {len(fixture['grounded_cases'])} grounded eval cases")
    print(f"\nRun: python3 eval/run.py --fixture westwise")


if __name__ == "__main__":
    main()

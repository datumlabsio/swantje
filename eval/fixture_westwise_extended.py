#!/usr/bin/env python3
"""
Build the Westwise extended ClickHouse eval fixture.

Expands the base westwise fixture from 8 → 16 analytics_prod tables and
7 → 17 ground-truth queries, adding voice/call, marketing/ads, and billing domains.

Usage:
    ~/dev/westwise-internal/.venv/bin/python eval/fixture_westwise_extended.py
    ~/dev/westwise-internal/.venv/bin/python eval/fixture_westwise_extended.py --schema-only
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURE_PATH = FIXTURE_DIR / "westwise_extended.json"
WESTWISE_INTERNAL = Path.home() / "dev" / "westwise-internal"
METADATA_CACHE = WESTWISE_INTERNAL / "data" / "metadata_raw.json"
ENV_FILE = WESTWISE_INTERNAL / ".env"

SCHEMA_TABLES = [
    # Original 8 (sales layer)
    "int_sales__deals_legacy_cleansed",
    "int_sales__deals_information_legacy_cleansed",
    "int_sales__agent_performance",
    "int_sales__affiliate_performance",
    "int_platform_billing",
    "int_sales__cpl",
    "int_marketing__cpc_lhp",
    "int_sales__common_drops",
    # New: voice/call domain
    "int_voice_calls__agent_daily_report",
    "int_voice_calls__deals_calls_transcripts",
    "int_voice_calls__ringing_legacy_cleansed",
    # New: marketing domain
    "int_marketing__campaign_top_funnel",
    # New: sales extended
    "int_sales__drop_reasons_percentage",
    # New: source/staging
    "stg_callrails__calls",
    "stg_google_ads__campaigns",
]

GROUND_TRUTH_QUERIES = [
    # --- original 7 (carried over) ---
    {
        "id": "total_deals",
        "label": "Total deals in int_sales__deals_legacy_cleansed",
        "sql": "SELECT count() FROM analytics_prod.int_sales__deals_legacy_cleansed",
    },
    {
        "id": "signed_deals",
        "label": "Contract Signed deals",
        "sql": "SELECT count() FROM analytics_prod.int_sales__deals_legacy_cleansed WHERE stage = 'Contract Signed'",
    },
    {
        "id": "distinct_agents",
        "label": "Distinct active agents",
        "sql": "SELECT count(DISTINCT agent_email) FROM analytics_prod.int_sales__agent_performance",
    },
    {
        "id": "distinct_states",
        "label": "Distinct states in deals",
        "sql": "SELECT count(DISTINCT state) FROM analytics_prod.int_sales__deals_legacy_cleansed WHERE state IS NOT NULL",
    },
    {
        "id": "total_affiliate_leads",
        "label": "Total affiliate distributed leads",
        "sql": "SELECT sum(total_affiliate_distributed_leads) FROM analytics_prod.int_sales__affiliate_performance",
    },
    {
        "id": "latest_deal_date",
        "label": "Most recent deal creation date",
        "sql": "SELECT max(toDate(created_time)) FROM analytics_prod.int_sales__deals_legacy_cleansed",
    },
    {
        "id": "deal_stages",
        "label": "All distinct deal stages",
        "sql": "SELECT groupArray(DISTINCT stage) FROM analytics_prod.int_sales__deals_legacy_cleansed WHERE stage IS NOT NULL",
    },
    # --- new voice domain ---
    {
        "id": "voice_agent_events",
        "label": "Total rows in int_voice_calls__agent_daily_report",
        "sql": "SELECT count() FROM analytics_prod.int_voice_calls__agent_daily_report",
    },
    {
        "id": "total_transcripts",
        "label": "Total call-deal transcript rows",
        "sql": "SELECT count() FROM analytics_prod.int_voice_calls__deals_calls_transcripts",
    },
    {
        "id": "missed_calls_total",
        "label": "Sum of missed calls across all agents",
        "sql": "SELECT sum(total_missed_calls) FROM analytics_prod.int_sales__agent_performance",
    },
    # --- new source/affiliate ---
    {
        "id": "callrail_calls_total",
        "label": "Total CallRail call records",
        "sql": "SELECT count() FROM analytics_prod.stg_callrails__calls",
    },
    {
        "id": "warm_transfer_signed",
        "label": "Total warm transfer signed deals",
        "sql": "SELECT sum(warm_transfer_signed) FROM analytics_prod.int_sales__affiliate_performance",
    },
    # --- new marketing ---
    {
        "id": "google_campaigns_total",
        "label": "Total Google Ads campaign rows",
        "sql": "SELECT count() FROM analytics_prod.stg_google_ads__campaigns",
    },
    # --- new billing ---
    {
        "id": "total_platform_cost",
        "label": "Total platform billing cost (all time)",
        "sql": "SELECT round(sum(total_cost), 2) FROM analytics_prod.int_platform_billing",
    },
    # --- new sales extended ---
    {
        "id": "top_drop_reason",
        "label": "Most common drop reason",
        "sql": (
            "SELECT drop_reason1 FROM analytics_prod.int_sales__deals_legacy_cleansed "
            "WHERE drop_reason1 IS NOT NULL "
            "GROUP BY drop_reason1 ORDER BY count() DESC LIMIT 1"
        ),
    },
    {
        "id": "distinct_vendors",
        "label": "Distinct affiliate vendors",
        "sql": "SELECT count(DISTINCT vendor) FROM analytics_prod.int_sales__affiliate_performance WHERE vendor IS NOT NULL",
    },
    {
        "id": "avg_deal_amount",
        "label": "Average deal amount (non-null)",
        "sql": "SELECT round(avg(amount), 0) FROM analytics_prod.int_sales__deals_legacy_cleansed WHERE amount IS NOT NULL",
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


def build_schema_context(meta: dict, ground_truth: list) -> str:
    cols = meta["columns"]
    tables_meta = {t["name"]: t for t in meta["tables"] if t["database"] in ("analytics_prod",)}

    lines = [
        "Connected to ClickHouse (Westwise). Analytics layer: `analytics_prod`.",
        "",
        "Key tables (16 tables across sales, voice, marketing, billing, and source layers):",
    ]

    for tbl in SCHEMA_TABLES:
        if tbl not in tables_meta:
            continue
        row_count = tables_meta[tbl].get("total_rows")
        row_str = f"{row_count:,}" if row_count else "?"
        tcols = [c for c in cols if c["database"] == "analytics_prod" and c["table"] == tbl]
        col_summaries = []
        for c in tcols[:10]:
            comment = f" — {c['comment']}" if c.get("comment") else ""
            col_summaries.append(f"{c['name']} ({c['type']}){comment}")
        if len(tcols) > 10:
            col_summaries.append(f"+{len(tcols) - 10} more cols")

        domain = (
            "voice" if "voice" in tbl
            else "marketing" if "marketing" in tbl
            else "billing" if "billing" in tbl or "platform" in tbl
            else "source" if tbl.startswith("stg_")
            else "sales"
        )
        lines.append(f"\n**{tbl}** [{domain}] ({row_str} rows)")
        for cs in col_summaries:
            lines.append(f"  • {cs}")

    if ground_truth:
        lines += ["", "\nVerified ground-truth metrics:"]
        for gt in ground_truth:
            if gt.get("value") is not None:
                lines.append(f"  • {gt['label']}: **{gt['value']}**")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Build Westwise extended ClickHouse eval fixture")
    parser.add_argument("--schema-only", action="store_true")
    args = parser.parse_args()

    load_env()

    print("Loading schema from metadata cache…", end=" ", flush=True)
    if not METADATA_CACHE.exists():
        print(f"\nMetadata cache not found at {METADATA_CACHE}", file=sys.stderr)
        sys.exit(1)
    meta = json.loads(METADATA_CACHE.read_text())
    print(f"OK ({len(meta['tables'])} tables)")

    ground_truth = []
    if not args.schema_only:
        print("Running ground-truth queries…")
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
                    print(val if not isinstance(val, list) else f"{len(val)} values")
                except Exception as e:
                    print(f"ERROR: {e}")
                    ground_truth.append({**q, "value": None, "error": str(e)})
        except Exception as e:
            print(f"Connection failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Skipping live queries (--schema-only)")

    context_content = build_schema_context(meta, ground_truth)

    # Resolve ground-truth values for rubrics
    gt_map = {g["id"]: g.get("value") for g in ground_truth}

    fixture = {
        "name": "westwise_extended",
        "description": "Westwise ClickHouse analytics layer — 16 tables, voice/marketing/billing/sales + source",
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
        "grounded_cases": [
            # --- original 6 carried over ---
            {
                "id": "ww-metric-001",
                "customer": "westwise",
                "category": "metric_exact_number",
                "language": "en",
                "prompt": "How many total deals do we have?",
                "ground_truth_id": "total_deals",
                "rubric": {
                    "number_first": "Response leads with a number",
                    "correct_value": f"Number matches ground-truth total_deals ({gt_map.get('total_deals', '?')})",
                },
                "must_have": [],
                "must_not_have": ["Here is", "Let me"],
            },
            {
                "id": "ww-metric-002",
                "customer": "westwise",
                "category": "metric_exact_number",
                "language": "en",
                "prompt": "How many Contract Signed deals are there?",
                "ground_truth_id": "signed_deals",
                "rubric": {
                    "number_first": "Response leads with a number",
                    "correct_value": f"Number matches ground-truth signed_deals ({gt_map.get('signed_deals', '?')})",
                    "correct_filter": "Filters on stage = 'Contract Signed'",
                },
                "must_have": [],
                "must_not_have": [],
            },
            {
                "id": "ww-metric-003",
                "customer": "westwise",
                "category": "metric_exact_number",
                "language": "en",
                "prompt": "How many distinct agents are in the performance table?",
                "ground_truth_id": "distinct_agents",
                "rubric": {
                    "number_first": "Response leads with a number",
                    "correct_value": f"Number matches ground-truth distinct_agents ({gt_map.get('distinct_agents', '?')})",
                },
                "must_have": [],
                "must_not_have": [],
            },
            {
                "id": "ww-lookup-001",
                "customer": "westwise",
                "category": "data_lookup",
                "language": "en",
                "prompt": "What are all the distinct deal stages?",
                "ground_truth_id": "deal_stages",
                "rubric": {
                    "lists_stages": "Lists the actual stage values",
                    "structured": "Output is a list or table, not prose",
                },
                "must_have": [],
                "must_not_have": [],
            },
            {
                "id": "ww-diagnostic-001",
                "customer": "westwise",
                "category": "diagnostic",
                "language": "en",
                "prompt": "Why would the first row in int_sales__deals_legacy_cleansed have a NULL state?",
                "ground_truth_id": None,
                "rubric": {
                    "hypothesis_first": "States most likely root cause",
                    "references_correct_table": "References int_sales__deals_legacy_cleansed and the state column",
                    "check_query_provided": "Provides a ClickHouse query to investigate",
                },
                "must_have": ["NULL", "state"],
                "must_not_have": [],
            },
            {
                "id": "ww-sql-001",
                "customer": "westwise",
                "category": "sql_technical",
                "language": "en",
                "prompt": "Give me the SQL for total signed deals grouped by state, last 90 days",
                "ground_truth_id": None,
                "rubric": {
                    "raw_sql_only": "Returns a SQL block with comment header, no prose",
                    "correct_table": "Queries analytics_prod.int_sales__deals_legacy_cleansed",
                    "correct_filter": "Filters on stage = 'Contract Signed' and created_time within 90 days",
                    "groups_by_state": "Groups by state column",
                    "clickhouse_dialect": "Uses ClickHouse syntax (toDate, now(), INTERVAL)",
                },
                "must_have": ["```sql", "Contract Signed", "state"],
                "must_not_have": ["Here is the", "This query"],
            },
            # --- new voice domain ---
            {
                "id": "ww-voice-001",
                "customer": "westwise",
                "category": "metric_exact_number",
                "language": "en",
                "prompt": "How many total agent call events are recorded?",
                "ground_truth_id": "voice_agent_events",
                "rubric": {
                    "number_first": "Response leads with a number",
                    "correct_value": f"Number matches ground-truth voice_agent_events ({gt_map.get('voice_agent_events', '?')})",
                    "correct_table": "References int_voice_calls__agent_daily_report",
                },
                "must_have": [],
                "must_not_have": ["Here is", "Let me"],
            },
            {
                "id": "ww-voice-002",
                "customer": "westwise",
                "category": "metric_exact_number",
                "language": "en",
                "prompt": "What is the total number of missed calls across all agents?",
                "ground_truth_id": "missed_calls_total",
                "rubric": {
                    "number_first": "Response leads with a number",
                    "correct_value": f"Number matches ground-truth missed_calls_total ({gt_map.get('missed_calls_total', '?')})",
                    "uses_agent_perf": "Queries int_sales__agent_performance using total_missed_calls column",
                },
                "must_have": [],
                "must_not_have": [],
            },
            {
                "id": "ww-voice-003",
                "customer": "westwise",
                "category": "data_lookup",
                "language": "en",
                "prompt": "Show me the top 5 agents by missed calls",
                "ground_truth_id": None,
                "rubric": {
                    "table_format": "Returns a table (not prose)",
                    "correct_columns": "Table includes agent identifier and missed call count",
                    "ordered_desc": "Results are ordered by missed calls descending",
                    "limit_5": "Returns exactly 5 rows",
                },
                "must_have": ["|"],
                "must_not_have": [],
            },
            {
                "id": "ww-diagnostic-002",
                "customer": "westwise",
                "category": "diagnostic",
                "language": "en",
                "prompt": "Why would int_voice_calls__deals_calls_transcripts have more rows than stg_callrails__calls?",
                "ground_truth_id": None,
                "note": f"deals_calls_transcripts has {gt_map.get('total_transcripts', '?')} rows, stg_callrails__calls has {gt_map.get('callrail_calls_total', '?')} rows",
                "rubric": {
                    "hypothesis_first": "States most likely cause (fan-out from JOIN, multiple transcripts per call, different grain)",
                    "evidence_section": "Has Evidence section",
                    "fix_section": "Has Fix/next-step section",
                    "mentions_join_fanout": "Mentions JOIN fan-out or different granularity as the root cause",
                },
                "must_have": ["Hypothesis"],
                "must_not_have": [],
            },
            # --- new marketing domain ---
            {
                "id": "ww-marketing-001",
                "customer": "westwise",
                "category": "metric_exact_number",
                "language": "en",
                "prompt": "How many total Google Ads campaign rows are in the staging table?",
                "ground_truth_id": "google_campaigns_total",
                "rubric": {
                    "number_first": "Response leads with a number",
                    "correct_value": f"Number matches ground-truth google_campaigns_total ({gt_map.get('google_campaigns_total', '?')})",
                    "correct_table": "References stg_google_ads__campaigns",
                },
                "must_have": [],
                "must_not_have": [],
            },
            {
                "id": "ww-marketing-002",
                "customer": "westwise",
                "category": "metric_exact_number",
                "language": "en",
                "prompt": "What is the total platform cost across all time in the billing table?",
                "ground_truth_id": "total_platform_cost",
                "rubric": {
                    "number_first": "Response leads with a number or currency value",
                    "correct_value": f"Number matches ground-truth total_platform_cost ({gt_map.get('total_platform_cost', '?')})",
                    "correct_table": "References int_platform_billing",
                },
                "must_have": [],
                "must_not_have": [],
            },
            # --- new sales extended ---
            {
                "id": "ww-sales-002",
                "customer": "westwise",
                "category": "metric_exact_number",
                "language": "en",
                "prompt": "What is the most common drop reason?",
                "ground_truth_id": "top_drop_reason",
                "rubric": {
                    "names_reason": "Names the actual top drop reason string",
                    "correct_value": f"Drop reason matches ground-truth ({gt_map.get('top_drop_reason', '?')})",
                    "no_table": "Returns a single value, not a full table of all reasons",
                },
                "must_have": [],
                "must_not_have": [],
            },
            {
                "id": "ww-sales-003",
                "customer": "westwise",
                "category": "metric_exact_number",
                "language": "en",
                "prompt": "How many distinct affiliate vendors are in the performance table?",
                "ground_truth_id": "distinct_vendors",
                "rubric": {
                    "number_first": "Response leads with a number",
                    "correct_value": f"Number matches ground-truth distinct_vendors ({gt_map.get('distinct_vendors', '?')})",
                },
                "must_have": [],
                "must_not_have": [],
            },
            {
                "id": "ww-sql-002",
                "customer": "westwise",
                "category": "sql_technical",
                "language": "en",
                "prompt": "Give me the SQL for warm transfer signed deals grouped by vendor for the last 30 days",
                "ground_truth_id": None,
                "rubric": {
                    "raw_sql_only": "Returns raw SQL block with comment header, no prose",
                    "correct_table": "Queries int_sales__affiliate_performance",
                    "uses_warm_transfer_signed": "References warm_transfer_signed column",
                    "groups_by_vendor": "Groups by vendor column",
                    "date_filter": "Filters on last 30 days using ClickHouse date functions",
                    "clickhouse_dialect": "Uses ClickHouse syntax",
                },
                "must_have": ["```sql", "vendor", "warm_transfer_signed"],
                "must_not_have": ["Here is", "This query returns"],
            },
            {
                "id": "ww-diagnostic-003",
                "customer": "westwise",
                "category": "diagnostic",
                "language": "en",
                "prompt": "Why might the average deal amount from the database differ from what finance reports?",
                "ground_truth_id": "avg_deal_amount",
                "note": f"Database avg_deal_amount = {gt_map.get('avg_deal_amount', '?')}",
                "rubric": {
                    "hypothesis_first": "States most likely causes (NULL exclusion, different stage filters, currency/adjustment fields)",
                    "evidence_section": "Has Evidence section mentioning specific fields (amount vs adjusted_amount, stage filters)",
                    "fix_section": "Has Fix section proposing how to reconcile",
                    "mentions_filters": "Mentions that stage filters or NULL handling affect the average",
                },
                "must_have": ["Hypothesis"],
                "must_not_have": [],
            },
        ],
    }

    # Tag all grounded cases with customer
    for c in fixture["grounded_cases"]:
        c.setdefault("customer", fixture["name"])

    FIXTURE_DIR.mkdir(exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(fixture, indent=2, default=str))
    print(f"\nFixture written → {FIXTURE_PATH}")
    print(f"  {len(SCHEMA_TABLES)} schema tables")
    print(f"  {len(ground_truth)} ground-truth metrics")
    print(f"  {len(fixture['grounded_cases'])} grounded eval cases")
    print(f"\nRun: ~/dev/westwise-internal/.venv/bin/python eval/run.py --fixture westwise_extended --customer westwise --yes")


if __name__ == "__main__":
    main()

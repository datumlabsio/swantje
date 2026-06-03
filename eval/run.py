#!/usr/bin/env python3
"""
Swantje eval harness.

Subject model : dgpu LiteLLM (https://litellm.trydatumlabs.com/v1, Qwen3.6-27B)
Judge model   : Claude Haiku 4.5 via Anthropic API — independent, costs money.
                You will be asked to confirm before any Haiku judge calls.

Usage:
    python3 eval/run.py                       # full suite
    python3 eval/run.py --category metric_exact_number
    python3 eval/run.py --case metric-001
    python3 eval/run.py --update-baseline     # lock current scores as baseline
    python3 eval/run.py --compare-baseline    # run + fail on regressions >0.15
    python3 eval/run.py --yes                 # skip cost confirmation prompt

Config (env vars / .env override):
    DGPU_API_BASE     default: https://litellm.trydatumlabs.com/v1
    DGPU_API_KEY      default: read from ~/.continue/config.yaml
    DGPU_MODEL        default: best
    ANTHROPIC_API_KEY loaded from .env in project root
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

def _now() -> datetime:
    return datetime.now(timezone.utc)

try:
    from openai import OpenAI
except ImportError:
    print("pip install openai", file=sys.stderr)
    sys.exit(1)

try:
    import anthropic as _anthropic_module
except ImportError:
    _anthropic_module = None

try:
    import yaml
except ImportError:
    yaml = None

EVAL_DIR = Path(__file__).parent
SUITE_PATH = EVAL_DIR / "suite.json"
BASELINE_PATH = EVAL_DIR / "baseline.json"
RESULTS_DIR = EVAL_DIR / "results"
FIXTURES_DIR = EVAL_DIR / "fixtures"
SKILL_PATH = EVAL_DIR.parent / "skills" / "assistant" / "SKILL.md"
CONTINUE_CONFIG = Path.home() / ".continue" / "config.yaml"

RESULTS_DIR.mkdir(exist_ok=True)

DEFAULT_API_BASE = "https://litellm.trydatumlabs.com/v1"
DEFAULT_MODEL = "best"
DEFAULT_JUDGE_MODEL = "fast"  # dgpu fallback only; Haiku is primary judge
HAIKU_MODEL = "claude-haiku-4-5-20251001"
# Haiku pricing (input/output per 1M tokens as of 2025)
HAIKU_INPUT_COST_PER_1M = 0.80
HAIKU_OUTPUT_COST_PER_1M = 4.00
# Rough token estimate per judge call (system + rubric + response + output)
HAIKU_TOKENS_PER_CALL_IN = 1_200
HAIKU_TOKENS_PER_CALL_OUT = 200


def _load_dotenv():
    """Load .env from the project root (eval/../.env) into os.environ.
    Values in .env take precedence so the file is the source of truth."""
    env_path = EVAL_DIR.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, val = line.partition("=")
            # Strip surrounding whitespace and optional quotes
            val = val.strip().strip('"').strip("'").strip()
            os.environ[key.strip()] = val

_load_dotenv()

# Simulated config context injected as an initial assistant turn so the model
# behaves as if Step 0 (read config) already ran. Mirrors a typical Voltera/Hex setup.
EVAL_CONTEXT_TURN = {
    "role": "assistant",
    "content": (
        "Config loaded from `.swantje/config.json`:\n\n"
        "```json\n"
        "{\n"
        '  "connectors": {\n'
        '    "clickhouse": {\n'
        '      "enabled": true,\n'
        '      "host": "clickhouse.internal",\n'
        '      "database": "voltera"\n'
        "    },\n"
        '    "hex": {\n'
        '      "enabled": true,\n'
        '      "workspace_url": "https://app.hex.tech/datumlabs",\n'
        '      "default_connection_id": "019db994-e49a-7003-a43e-c563b7be9bab",\n'
        '      "default_connection_name": "ClickHouse — Voltera"\n'
        "    }\n"
        "  }\n"
        "}\n"
        "```\n\n"
        "Connected to ClickHouse (voltera database) and Hex. "
        "Key tables: `quotes` (quote_id, status, closer, planner, revenue, signed_at), "
        "`customers` (customer_id, name, segment, region), "
        "`invoices` (invoice_id, customer_id, amount, status, created_at).\n\n"
        "Glossary loaded from `.swantje/glossary.json`:\n"
        "- **closer**: Sales rep who signed/closed the deal → field `closer_id` in `quotes`\n"
        "- **planner**: Sales rep who planned the appointment → field `planner_id` in `quotes`\n"
        "- **live afspraak**: In-person appointment, appointment_type = 'live' in `appointments`\n"
        "- **getekende offerte**: Signed quote, status = 'signed' in `quotes`\n"
        "- **offerte**: Quote record in the `quotes` table\n\n"
        "Ready."
    ),
}


def _read_continue_key() -> str | None:
    if not CONTINUE_CONFIG.exists():
        return None
    try:
        if yaml:
            cfg = yaml.safe_load(CONTINUE_CONFIG.read_text())
            for m in cfg.get("models", []):
                key = m.get("apiKey")
                if key and m.get("apiBase", "").startswith("https://litellm.trydatumlabs.com"):
                    return key
        else:
            # fallback: grep for apiKey line after litellm URL
            text = CONTINUE_CONFIG.read_text()
            for line in text.splitlines():
                if "apiKey:" in line and "sk-" in line:
                    return line.split("apiKey:")[-1].strip()
    except Exception:
        pass
    return None


def _make_client() -> tuple["OpenAI", str, str]:
    api_base = os.environ.get("DGPU_API_BASE", DEFAULT_API_BASE)
    api_key = os.environ.get("DGPU_API_KEY") or _read_continue_key()
    if not api_key:
        print(
            "No dgpu API key found.\n"
            "Set DGPU_API_KEY or ensure ~/.continue/config.yaml has a litellm entry.",
            file=sys.stderr,
        )
        sys.exit(1)
    model = os.environ.get("DGPU_MODEL", DEFAULT_MODEL)
    judge_model = os.environ.get("DGPU_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)
    client = OpenAI(base_url=api_base, api_key=api_key)
    return client, model, judge_model


# --------------------------------------------------------------------------- #
# Prompt builders
# --------------------------------------------------------------------------- #

def build_system_prompt() -> str:
    skill_md = SKILL_PATH.read_text()
    if skill_md.startswith("---"):
        _, _, body = skill_md.split("---", 2)
        return body.strip()
    return skill_md.strip()


def build_messages(case: dict, context_turn: dict = EVAL_CONTEXT_TURN) -> list[dict]:
    messages = [
        {"role": "user", "content": "Hi"},
        context_turn,
    ]
    if case.get("prior_context"):
        ctx = case["prior_context"]
        # prior_context["assistant"] = what assistant said before the test prompt
        # prior_context["user"]      = the test prompt itself (current user turn)
        # Add a filler user turn so the assistant response has something to follow.
        messages.append({"role": "user", "content": "Show me the data."})
        messages.append({"role": "assistant", "content": ctx["assistant"]})
        messages.append({"role": "user", "content": ctx["user"]})
    else:
        messages.append({"role": "user", "content": case["prompt"]})
    return messages


JUDGE_SYSTEM = """You are an eval judge for a data platform assistant skill.
You receive a test case and the assistant's response, then score each rubric item.

Scoring scale:
  2 = Pass    — criterion clearly met
  1 = Partial — criterion partially met or ambiguous
  0 = Fail    — criterion not met

Return ONLY valid JSON matching this schema exactly (no markdown fences):
{
  "scores": { "<rubric_key>": <0|1|2>, ... },
  "overall": <float 0-1>,
  "notes": "<one-line summary of main issues, or empty string if all pass>"
}

overall = mean(scores.values()) / 2
"""


def _precheck(case: dict, response: str) -> dict | None:
    """Deterministic must_have / must_not_have check. Returns a failed verdict or None."""
    text = response.lower()
    # Strip markdown formatting for ^ anchor checks so **42** still matches ^\d
    stripped = re.sub(r"^[\*_`#>\s]+", "", response)

    for pattern in case.get("must_have", []):
        # Use stripped text for ^ patterns, full text otherwise
        target = stripped if pattern.startswith("^") else response
        try:
            if not re.search(pattern, target, re.IGNORECASE):
                return {
                    "scores": {"must_have": 0},
                    "overall": 0.0,
                    "notes": f"must_have failed: pattern '{pattern}' not found in response",
                }
        except re.error:
            if pattern.lower() not in text:
                return {
                    "scores": {"must_have": 0},
                    "overall": 0.0,
                    "notes": f"must_have failed: '{pattern}' not found in response",
                }
    for phrase in case.get("must_not_have", []):
        if phrase.lower() in text:
            return {
                "scores": {"must_not_have": 0},
                "overall": 0.0,
                "notes": f"must_not_have failed: '{phrase}' found in response",
            }
    return None


def _make_haiku_client() -> "anthropic.Anthropic | None":
    if _anthropic_module is None:
        return None
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    return _anthropic_module.Anthropic(api_key=key)


def judge_response(haiku: "anthropic.Anthropic | None", case: dict, response: str,
                   ground_truth: dict | None = None) -> dict:
    rubric_text = "\n".join(f"- {k}: {v}" for k, v in case["rubric"].items())

    gt_section = ""
    gt_id = case.get("ground_truth_id")
    if gt_id and ground_truth and gt_id in ground_truth:
        gt = ground_truth[gt_id]
        gt_section = f"\nGround-truth value for '{gt_id}': {gt['value']} ({gt['label']})\n"

    judge_prompt = (
        f"Test case: {case['id']} (category: {case['category']})\n\n"
        f"Prompt given to assistant:\n{case['prompt']}\n\n"
        f"Prior context:\n{json.dumps(case.get('prior_context'), indent=2)}\n"
        f"{gt_section}\n"
        f"Rubric:\n{rubric_text}\n\n"
        f"Assistant response:\n---\n{response}\n---\n\n"
        "Score each rubric item. Return JSON only."
    )

    if haiku is not None:
        # Independent Claude Haiku judge
        msg = haiku.messages.create(
            model=HAIKU_MODEL,
            max_tokens=512,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": judge_prompt}],
        )
        raw = msg.content[0].text.strip()
    else:
        # Fallback: same dgpu model (less independent, but functional)
        raw = _chat(_dgpu_client, "fast", [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": judge_prompt},
        ], max_tokens=512)
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"scores": {}, "overall": 0.0, "notes": f"judge parse error: {raw[:120]}"}


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #

def _chat(client: "OpenAI", model: str, messages: list, max_tokens: int, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model, max_tokens=max_tokens, messages=messages
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"\n    [retry {attempt+1}/{retries-1} after {wait}s: {type(e).__name__}]", end="", flush=True)
                time.sleep(wait)
            else:
                raise


def run_case(client: "OpenAI", system: str, model: str, haiku: "anthropic.Anthropic | None",
             case: dict, context_turn: dict | None = None, ground_truth: dict | None = None) -> dict:
    messages = build_messages(case, context_turn or EVAL_CONTEXT_TURN)

    raw = _chat(client, model, [{"role": "system", "content": system}] + messages, max_tokens=1024)
    response_text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Deterministic pre-check (free, always runs)
    precheck = _precheck(case, response_text)
    if precheck is not None:
        return {
            "id": case["id"],
            "category": case["category"],
            "language": case.get("language", "en"),
            "response": response_text,
            "precheck_failed": True,
            **precheck,
        }

    verdict = judge_response(haiku, case, response_text, ground_truth)

    return {
        "id": case["id"],
        "category": case["category"],
        "language": case.get("language", "en"),
        "response": response_text,
        "precheck_failed": False,
        "scores": verdict.get("scores", {}),
        "overall": verdict.get("overall", 0.0),
        "notes": verdict.get("notes", ""),
    }


_dgpu_client: "OpenAI | None" = None  # module-level so judge fallback can use it


def run_suite(cases: list[dict], fixture: dict | None = None, yes: bool = False) -> list[dict]:
    global _dgpu_client
    client, model, _ = _make_client()
    _dgpu_client = client
    system = build_system_prompt()

    haiku = _make_haiku_client()
    judge_label = f"Claude Haiku ({HAIKU_MODEL})" if haiku else "dgpu/fast (fallback — no ANTHROPIC_API_KEY)"

    # Cost estimate and confirmation
    n = len(cases)
    if haiku:
        est_cost = n * (
            HAIKU_INPUT_COST_PER_1M * HAIKU_TOKENS_PER_CALL_IN / 1_000_000
            + HAIKU_OUTPUT_COST_PER_1M * HAIKU_TOKENS_PER_CALL_OUT / 1_000_000
        )
        cost_str = f"~${est_cost:.3f}"
    else:
        cost_str = "$0.00 (dgpu fallback)"

    print(f"  subject  : dgpu/{model} @ {os.environ.get('DGPU_API_BASE', DEFAULT_API_BASE)}")
    print(f"  judge    : {judge_label}")
    print(f"  cases    : {n}    est. judge cost: {cost_str}")
    if fixture:
        print(f"  fixture  : {fixture['name']} ({len(fixture.get('ground_truth', []))} ground-truth metrics)")
    print()

    if haiku and not yes:
        try:
            ans = input(f"  Proceed with Haiku judge ({cost_str})? [y/N] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans not in ("y", "yes"):
            print("  Aborted. Use --yes to skip this prompt.")
            sys.exit(0)
        print()

    context_turn = fixture["context_turn"] if fixture else EVAL_CONTEXT_TURN
    ground_truth = {gt["id"]: gt for gt in fixture.get("ground_truth", [])} if fixture else {}

    results = []
    for i, case in enumerate(cases, 1):
        print(f"  [{i:02d}/{n:02d}] {case['id']} ({case['category']}) … ", end="", flush=True)
        result = run_case(client, system, model, haiku, case, context_turn, ground_truth)
        precheck_tag = "[precheck] " if result.get("precheck_failed") else ""
        symbol = "✓" if result["overall"] >= 0.75 else ("~" if result["overall"] >= 0.5 else "✗")
        print(f"{symbol} {result['overall']:.2f} {precheck_tag}")
        if result["notes"]:
            print(f"         {result['notes']}")
        results.append(result)

    return results


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def build_report(results: list[dict], baseline: dict | None = None) -> str:
    total = len(results)
    passed = sum(1 for r in results if r["overall"] >= 0.75)
    overall_score = sum(r["overall"] for r in results) / total if total else 0.0

    by_cat: dict[str, list] = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)

    lines = [
        f"# Swantje Skill Eval — {_now().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"**Overall:** {overall_score:.2f} ({passed}/{total} passed ≥0.75)",
        "",
        "## By Category",
        "",
        "| Category | Cases | Score | Δ Baseline |",
        "|---|---|---|---|",
    ]

    for cat, cat_results in sorted(by_cat.items()):
        cat_score = sum(r["overall"] for r in cat_results) / len(cat_results)
        if baseline:
            base_score = baseline.get("by_category", {}).get(cat, {}).get("score")
            delta = f"{cat_score - base_score:+.2f}" if base_score is not None else "—"
        else:
            delta = "—"
        lines.append(f"| {cat} | {len(cat_results)} | {cat_score:.2f} | {delta} |")

    lines += ["", "## Failures / Partials", ""]

    failures = [r for r in results if r["overall"] < 0.75]
    if failures:
        for r in sorted(failures, key=lambda x: x["overall"]):
            lines.append(f"### {r['id']} — score {r['overall']:.2f}")
            if r["notes"]:
                lines.append(f"> {r['notes']}")
            fail_items = {k: v for k, v in r["scores"].items() if v < 2}
            if fail_items:
                lines.append("\n**Rubric misses:**")
                for k, v in fail_items.items():
                    label = {0: "FAIL", 1: "partial"}.get(v, "")
                    lines.append(f"- `{k}`: {label}")
            lines.append("")
    else:
        lines.append("All cases passed ≥0.75.")

    return "\n".join(lines)


def build_baseline_record(results: list[dict]) -> dict:
    by_cat: dict[str, list] = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)

    return {
        "created": _now().isoformat(),
        "overall": sum(r["overall"] for r in results) / len(results) if results else 0.0,
        "by_category": {
            cat: {
                "score": sum(r["overall"] for r in items) / len(items),
                "cases": [r["id"] for r in items],
            }
            for cat, items in by_cat.items()
        },
        "case_scores": {r["id"]: r["overall"] for r in results},
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description="Run Swantje eval suite against dgpu LiteLLM")
    parser.add_argument("--category", help="Filter to a single category")
    parser.add_argument("--customer", help="Filter to a customer prefix (e.g. c2)")
    parser.add_argument("--case", help="Run a single case by ID")
    parser.add_argument("--fixture", help="Fixture name to use (e.g. westwise) — replaces simulated eval context with real schema + ground-truth data")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip Haiku judge cost confirmation prompt")
    parser.add_argument("--update-baseline", action="store_true", help="Lock current scores as baseline")
    parser.add_argument("--compare-baseline", action="store_true", help="Compare results to baseline")
    parser.add_argument("--output", help="Path to write results JSON (default: eval/results/<timestamp>.json)")
    args = parser.parse_args()

    suite = json.loads(SUITE_PATH.read_text())
    cases = suite["cases"]

    # Load fixture first so its grounded_cases are in the pool before filtering
    fixture = None
    if args.fixture:
        fixture_path = FIXTURES_DIR / f"{args.fixture}.json"
        if not fixture_path.exists():
            print(f"Fixture '{args.fixture}' not found at {fixture_path}", file=sys.stderr)
            print("Run: python3 eval/fixture_westwise.py", file=sys.stderr)
            sys.exit(1)
        fixture = json.loads(fixture_path.read_text())
        cases = fixture.get("grounded_cases", []) + cases

    # Apply filters after pool is fully assembled
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"Case '{args.case}' not found", file=sys.stderr)
            sys.exit(1)
    elif args.customer:
        prefix = args.customer.rstrip("-") + "-"
        cases = [c for c in cases if c["id"].startswith(prefix) or c.get("customer") == args.customer]
        if not cases:
            print(f"No cases found for customer '{args.customer}'", file=sys.stderr)
            sys.exit(1)
    elif args.category:
        cases = [c for c in cases if c["category"] == args.category]
        if not cases:
            print(f"Category '{args.category}' not found", file=sys.stderr)
            sys.exit(1)

    print(f"Running {len(cases)} case(s)…\n")
    results = run_suite(cases, fixture, yes=args.yes)

    baseline = None
    if (args.compare_baseline or not args.update_baseline) and BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text())

    report = build_report(results, baseline)
    print("\n" + report)

    ts = _now().strftime("%Y%m%d-%H%M%S")
    output_path = Path(args.output) if args.output else RESULTS_DIR / f"run-{ts}.json"
    output_path.write_text(json.dumps({"meta": {"run": ts}, "results": results}, indent=2))
    print(f"\nResults saved → {output_path}")

    if args.update_baseline:
        record = build_baseline_record(results)
        BASELINE_PATH.write_text(json.dumps(record, indent=2))
        print(f"Baseline updated → {BASELINE_PATH}")
        return

    if baseline and args.compare_baseline:
        regressions = []
        for r in results:
            base_score = baseline.get("case_scores", {}).get(r["id"])
            if base_score is not None and r["overall"] < base_score - 0.15:
                regressions.append(f"  {r['id']}: {base_score:.2f} → {r['overall']:.2f}")
        if regressions:
            print("\nREGRESSIONS detected:")
            print("\n".join(regressions))
            sys.exit(1)


if __name__ == "__main__":
    main()

"""
Report generator — produces CSV, per-prompt detail table, and a summary table.
"""

from __future__ import annotations

import csv
import io
from dataclasses import asdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .benchmark import ModelResult


# ── helpers ──────────────────────────────────────────────────────────────────

def _fmt_cost(usd: float) -> str:
    """Format cost: show at least 6 significant figures so small costs aren't $0.00."""
    if usd == 0:
        return "$0.000000"
    if usd < 0.01:
        return f"${usd:.6f}"
    return f"${usd:.4f}"


def _fmt_time(sec: float) -> str:
    if sec >= 60:
        return f"{sec/60:.2f} min"
    return f"{sec:.2f}s"


# ── CSV export ────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "model_display_name",
    "prompt_id",
    "prompt_category",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "ai_cost_usd",
    "response_time_sec",
    "accuracy_label",
    "accuracy_score",
    "error",
]


def to_csv(results: list["ModelResult"], filepath: str | None = None) -> str:
    """
    Write results to CSV.  Returns the CSV content as a string.
    If filepath is given, also saves to disk.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        writer.writerow(asdict(r))

    content = buf.getvalue()
    if filepath:
        with open(filepath, "w", newline="") as f:
            f.write(content)
        print(f"CSV saved → {filepath}")

    return content


# ── console tables ────────────────────────────────────────────────────────────

def _divider(widths: list[int], char: str = "─") -> str:
    return "┼".join(char * (w + 2) for w in widths)


def _row(cells: list[str], widths: list[int]) -> str:
    return "│".join(f" {c:<{w}} " for c, w in zip(cells, widths))


def print_detail_table(results: list["ModelResult"]) -> None:
    """One row per (model, prompt) — full detail."""
    headers = [
        "Model", "Prompt", "Category",
        "In Tok", "Out Tok", "Total Tok",
        "AI Cost", "Time", "Accuracy", "Status",
    ]

    rows = []
    for r in results:
        status = f"ERROR: {r.error[:30]}" if r.error else "OK"
        rows.append([
            r.model_display_name,
            r.prompt_id,
            r.prompt_category,
            str(r.input_tokens),
            str(r.output_tokens),
            str(r.total_tokens),
            _fmt_cost(r.ai_cost_usd),
            _fmt_time(r.response_time_sec),
            r.accuracy_label,
            status,
        ])

    widths = [max(len(h), max((len(row[i]) for row in rows), default=0))
              for i, h in enumerate(headers)]

    sep = _divider(widths)
    print("\n" + "=" * (sum(widths) + len(widths) * 3))
    print("  DETAIL RESULTS — per model per prompt")
    print("=" * (sum(widths) + len(widths) * 3))
    print(_row(headers, widths))
    print(sep)
    for row in rows:
        print(_row(row, widths))
    print()


def print_summary_table(results: list["ModelResult"]) -> None:
    """
    Aggregated per-model summary:
      avg tokens, total cost, avg response time, avg accuracy score.
    """
    from collections import defaultdict

    agg: dict[str, dict] = defaultdict(lambda: {
        "display": "",
        "calls": 0, "errors": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
        "total_time": 0.0,
        "total_accuracy": 0.0,
    })

    for r in results:
        key = r.model_id
        a = agg[key]
        a["display"] = r.model_display_name
        a["calls"] += 1
        if r.error:
            a["errors"] += 1
        a["total_tokens"] += r.total_tokens
        a["total_cost"] += r.ai_cost_usd
        a["total_time"] += r.response_time_sec
        a["total_accuracy"] += r.accuracy_score

    headers = [
        "Model", "Prompts", "Errors",
        "Avg Tokens", "Total AI Cost",
        "Avg Time", "Avg Accuracy",
    ]

    rows = []
    for a in agg.values():
        calls = a["calls"] or 1
        rows.append([
            a["display"],
            str(a["calls"]),
            str(a["errors"]),
            str(round(a["total_tokens"] / calls)),
            _fmt_cost(a["total_cost"]),
            _fmt_time(a["total_time"] / calls),
            f"{a['total_accuracy']/calls:.2f}",
        ])

    # sort by avg accuracy desc
    rows.sort(key=lambda r: float(r[6]), reverse=True)

    widths = [max(len(h), max((len(row[i]) for row in rows), default=0))
              for i, h in enumerate(headers)]

    sep = _divider(widths)
    print("\n" + "=" * (sum(widths) + len(widths) * 3))
    print("  SUMMARY — aggregated per model (sorted by accuracy)")
    print("=" * (sum(widths) + len(widths) * 3))
    print(_row(headers, widths))
    print(sep)
    for row in rows:
        print(_row(row, widths))
    print()


def generate_report(
    results: list["ModelResult"],
    csv_path: str | None = None,
    print_tables: bool = True,
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*60}")
    print(f"  LLM BENCHMARK REPORT  |  {ts}")
    print(f"{'='*60}")

    if print_tables:
        print_detail_table(results)
        print_summary_table(results)

    if csv_path:
        to_csv(results, csv_path)

"""
Entry point — run from project root:

  python -m src.llm_benchmark.run [--models gpt claude gemini] [--csv output.csv]

Environment variables required:
  DATABRICKS_HOST   https://adb-<workspace-id>.azuredatabricks.net
  DATABRICKS_TOKEN  <personal-access-token>
"""

from __future__ import annotations

import argparse
import sys

from .benchmark import run_benchmark
from .config import MODELS
from .report import generate_report

PROVIDER_FILTER = {
    "gpt":    "openai",
    "claude": "anthropic",
    "gemini": "google",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLM Benchmark on Databricks")
    parser.add_argument(
        "--models",
        nargs="+",
        choices=list(PROVIDER_FILTER),
        default=list(PROVIDER_FILTER),
        help="Which providers to test (default: all)",
    )
    parser.add_argument(
        "--csv",
        metavar="FILE",
        default=None,
        help="Save results to CSV file",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=256,
        help="Max output tokens per call (default: 256)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    selected_providers = {PROVIDER_FILTER[p] for p in args.models}
    selected_models = [m for m in MODELS if m["provider"] in selected_providers]

    if not selected_models:
        print("No models selected. Exiting.")
        sys.exit(1)

    print(f"\nRunning benchmark on {len(selected_models)} model(s) …")
    results = run_benchmark(models=selected_models, max_tokens=args.max_tokens)

    generate_report(results, csv_path=args.csv)


if __name__ == "__main__":
    main()

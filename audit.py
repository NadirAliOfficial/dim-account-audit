#!/usr/bin/env python3
"""CSV data audit tool: runs quality/business-rule checks and writes an HTML report.

Usage:
    python3 audit.py --input /path/to/file.csv [--config config.json] [--output-dir output]
"""
import argparse
import json
import os
import sys

import pandas as pd

from lib import checks, report


def load_config(path: str) -> dict:
    if path and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def run_checks(df: pd.DataFrame, cfg: dict) -> list:
    results = [checks.schema_summary(df)]

    results += checks.completeness(
        df,
        warn_pct=cfg.get("completeness_warn_pct", 5.0),
        fail_pct=cfg.get("completeness_fail_pct", 30.0),
        nullable_columns=cfg.get("nullable_columns", []),
    )

    results.append(checks.duplicate_rows(df))
    if cfg.get("primary_key"):
        results.append(checks.duplicate_key(df, cfg["primary_key"]))

    for col, allowed in cfg.get("categorical_domains", {}).items():
        results.append(checks.categorical_domain(df, col, allowed))

    for col in cfg.get("rare_value_columns", []):
        results.append(checks.rare_categories(df, col))

    for spec in cfg.get("outlier_columns", []):
        results.append(checks.outliers_iqr(df, spec["column"], spec.get("group_by")))

    # Account-domain business rules (no-ops if columns are absent)
    results.append(checks.rule_closed_requires_closed_date(df))
    results.append(checks.rule_open_has_no_closed_date(df))
    results.append(checks.rule_closed_after_open(df))
    results.append(checks.rule_no_future_dates(df))
    results.append(checks.rule_unexpected_negative_balance(df))

    return results


def write_outputs(source_file: str, df: pd.DataFrame, results: list, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)

    charts = report.build_charts(df)
    html = report.render_html(source_file, df, results, charts)
    html_path = os.path.join(out_dir, "report.html")
    with open(html_path, "w") as f:
        f.write(html)

    json_results = [{k: v for k, v in r.items() if k != "detail"} for r in results]
    json_results_path = os.path.join(out_dir, "results.json")
    with open(json_results_path, "w") as f:
        json.dump({
            "source_file": source_file,
            "rows": len(df),
            "columns": len(df.columns),
            "quality_score": report.quality_score(results),
            "checks": json_results,
        }, f, indent=2, default=str)

    flagged_details = [r["detail"] for r in results if r["status"] != "pass" and r["detail"] is not None]
    flagged_path = os.path.join(out_dir, "flagged_rows.csv")
    if flagged_details:
        pd.concat(flagged_details, axis=0).drop_duplicates().to_csv(flagged_path, index=False)
    else:
        flagged_path = None

    return html_path, json_results_path, flagged_path


def print_summary(results: list):
    fails = [r for r in results if r["status"] == "fail"]
    warns = [r for r in results if r["status"] == "warn"]
    score = report.quality_score(results)

    print(f"\nData Quality Score: {score}/100")
    print(f"  pass: {sum(1 for r in results if r['status']=='pass')}  "
          f"warn: {len(warns)}  fail: {len(fails)}")

    if fails:
        print("\nFAILED checks:")
        for r in fails:
            print(f"  [FAIL] {r['name']}: {r['message']}")
    if warns:
        print("\nWARNINGS:")
        for r in warns:
            print(f"  [WARN] {r['name']}: {r['message']}")


def main():
    parser = argparse.ArgumentParser(description="Audit a CSV file and generate an HTML report.")
    parser.add_argument("--input", required=True, help="path to the CSV file to audit")
    parser.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.json"),
                         help="path to a JSON config file with checks to run")
    parser.add_argument("--output-dir", default=os.path.join(os.path.dirname(__file__), "output"),
                         help="directory to write the report/results into")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    cfg = load_config(args.config)
    df = pd.read_csv(args.input, parse_dates=cfg.get("date_columns", []))

    results = run_checks(df, cfg)
    html_path, json_path, flagged_path = write_outputs(args.input, df, results, args.output_dir)
    print_summary(results)

    print(f"\nReport:  {html_path}")
    print(f"Results: {json_path}")
    if flagged_path:
        print(f"Flagged rows: {flagged_path}")


if __name__ == "__main__":
    main()

"""Builds the HTML audit report (summary table + charts) from check results."""
import base64
import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

STATUS_COLOR = {"pass": "#1a7f37", "warn": "#9a6700", "fail": "#cf222e"}


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def build_charts(df: pd.DataFrame) -> dict:
    charts = {}

    if "AccountType" in df.columns:
        fig, ax = plt.subplots(figsize=(5, 3.5))
        df["AccountType"].value_counts().plot(kind="bar", ax=ax, color="#2563eb")
        ax.set_title("Accounts by Type")
        ax.set_ylabel("count")
        charts["account_type"] = _fig_to_b64(fig)

    if "Status" in df.columns:
        fig, ax = plt.subplots(figsize=(4, 4))
        df["Status"].value_counts().plot(kind="pie", ax=ax, autopct="%1.0f%%",
                                          colors=["#2563eb", "#9ca3af"])
        ax.set_ylabel("")
        ax.set_title("Account Status")
        charts["status"] = _fig_to_b64(fig)

    if "Balance" in df.columns:
        fig, ax = plt.subplots(figsize=(5, 3.5))
        df["Balance"].plot(kind="hist", bins=30, ax=ax, color="#2563eb")
        ax.set_title("Balance Distribution")
        ax.set_xlabel("Balance")
        charts["balance_hist"] = _fig_to_b64(fig)

    if "Balance" in df.columns and "AccountType" in df.columns:
        fig, ax = plt.subplots(figsize=(5, 3.5))
        df.boxplot(column="Balance", by="AccountType", ax=ax)
        ax.set_title("Balance by Account Type")
        plt.suptitle("")
        charts["balance_by_type"] = _fig_to_b64(fig)

    if "OpenDate" in df.columns:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        df["OpenDate"].dt.to_period("Y").value_counts().sort_index().plot(kind="bar", ax=ax, color="#2563eb")
        ax.set_title("Accounts Opened by Year")
        charts["opened_by_year"] = _fig_to_b64(fig)

    return charts


def quality_score(results: list) -> float:
    weights = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    scored = [r for r in results if r["category"] != "schema"]
    if not scored:
        return 100.0
    total = sum(weights[r["status"]] for r in scored)
    return round(100 * total / len(scored), 1)


def _status_badge(status: str) -> str:
    return f'<span style="color:#fff;background:{STATUS_COLOR[status]};padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600;text-transform:uppercase">{status}</span>'


def render_html(source_file: str, df: pd.DataFrame, results: list, charts: dict) -> str:
    score = quality_score(results)
    score_color = "#1a7f37" if score >= 90 else ("#9a6700" if score >= 70 else "#cf222e")

    by_category = {}
    for r in results:
        by_category.setdefault(r["category"], []).append(r)

    fails = sum(1 for r in results if r["status"] == "fail")
    warns = sum(1 for r in results if r["status"] == "warn")
    passes = sum(1 for r in results if r["status"] == "pass")

    rows_html = []
    for category, items in by_category.items():
        rows_html.append(f'<tr><td colspan="3" style="background:#f6f8fa;font-weight:700;padding:8px">{category.replace("_"," ").title()}</td></tr>')
        for r in items:
            rows_html.append(
                f'<tr><td style="padding:6px 8px;border-bottom:1px solid #eee">{_status_badge(r["status"])}</td>'
                f'<td style="padding:6px 8px;border-bottom:1px solid #eee;font-family:monospace;font-size:13px">{r["name"]}</td>'
                f'<td style="padding:6px 8px;border-bottom:1px solid #eee">{r["message"]}</td></tr>'
            )

    charts_html = "".join(
        f'<div style="display:inline-block;margin:10px;text-align:center">'
        f'<img src="data:image/png;base64,{b64}" style="max-width:480px;border:1px solid #eee;border-radius:6px"/>'
        f'</div>'
        for b64 in charts.values()
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>Data Audit Report - {source_file}</title>
<style>
body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; margin: 0; padding: 30px; background: #fafafa; color: #1f2328; }}
.card {{ background: #fff; border: 1px solid #eee; border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
table {{ width: 100%; border-collapse: collapse; }}
h1 {{ font-size: 22px; }}
h2 {{ font-size: 16px; margin-top: 0; }}
.stat {{ display:inline-block; margin-right: 30px; }}
.stat .num {{ font-size: 28px; font-weight: 700; }}
.stat .label {{ font-size: 12px; color: #57606a; text-transform: uppercase; }}
</style></head>
<body>
<h1>Data Audit Report</h1>
<p style="color:#57606a">Source: <code>{source_file}</code> &middot; Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} &middot; {len(df)} rows &times; {len(df.columns)} columns</p>

<div class="card">
  <div class="stat"><div class="num" style="color:{score_color}">{score}</div><div class="label">Quality Score</div></div>
  <div class="stat"><div class="num" style="color:{STATUS_COLOR['pass']}">{passes}</div><div class="label">Passed</div></div>
  <div class="stat"><div class="num" style="color:{STATUS_COLOR['warn']}">{warns}</div><div class="label">Warnings</div></div>
  <div class="stat"><div class="num" style="color:{STATUS_COLOR['fail']}">{fails}</div><div class="label">Failed</div></div>
</div>

<div class="card">
  <h2>Charts</h2>
  {charts_html}
</div>

<div class="card">
  <h2>Check Results</h2>
  <table>{''.join(rows_html)}</table>
</div>

</body></html>"""

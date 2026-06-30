"""Generic + account-domain data quality checks. Each check returns a dict:
{name, category, status: pass/warn/fail, message, detail (df or None)}
"""
import pandas as pd
import numpy as np


def schema_summary(df: pd.DataFrame) -> dict:
    rows = [{"column": c, "dtype": str(df[c].dtype), "non_null": int(df[c].notna().sum())}
            for c in df.columns]
    return {"name": "schema_summary", "category": "schema", "status": "pass",
            "message": f"{len(df.columns)} columns, {len(df)} rows",
            "detail": pd.DataFrame(rows)}


def completeness(df: pd.DataFrame, warn_pct: float = 5.0, fail_pct: float = 30.0,
                  nullable_columns: list = None) -> list:
    nullable_columns = set(nullable_columns or [])
    results = []
    for c in df.columns:
        null_count = int(df[c].isna().sum())
        pct = round(100 * null_count / len(df), 2) if len(df) else 0.0
        if c in nullable_columns:
            status = "pass"
            note = " (nulls expected by design)" if null_count else ""
        else:
            status = "pass"
            if pct >= fail_pct:
                status = "fail"
            elif pct >= warn_pct:
                status = "warn"
            note = ""
        results.append({
            "name": f"completeness:{c}", "category": "completeness", "status": status,
            "message": f"{c}: {null_count} nulls ({pct}%){note}",
            "detail": None,
        })
    return results


def duplicate_rows(df: pd.DataFrame) -> dict:
    dupes = df[df.duplicated(keep=False)]
    status = "pass" if dupes.empty else "fail"
    return {"name": "duplicate_rows", "category": "uniqueness", "status": status,
            "message": f"{dupes.shape[0]} fully duplicated rows",
            "detail": dupes if not dupes.empty else None}


def duplicate_key(df: pd.DataFrame, key: str) -> dict:
    if key not in df.columns:
        return {"name": f"duplicate_key:{key}", "category": "uniqueness", "status": "warn",
                "message": f"key column '{key}' not found, skipped", "detail": None}
    dupes = df[df[key].duplicated(keep=False)]
    status = "pass" if dupes.empty else "fail"
    return {"name": f"duplicate_key:{key}", "category": "uniqueness", "status": status,
            "message": f"{dupes[key].nunique()} duplicated '{key}' values ({dupes.shape[0]} rows)",
            "detail": dupes if not dupes.empty else None}


def categorical_domain(df: pd.DataFrame, column: str, allowed: list) -> dict:
    if column not in df.columns:
        return {"name": f"domain:{column}", "category": "validity", "status": "warn",
                "message": f"column '{column}' not found, skipped", "detail": None}
    bad = df[~df[column].isin(allowed)]
    status = "pass" if bad.empty else "fail"
    return {"name": f"domain:{column}", "category": "validity", "status": status,
            "message": f"{bad.shape[0]} rows with '{column}' outside {allowed}",
            "detail": bad if not bad.empty else None}


def rare_categories(df: pd.DataFrame, column: str, threshold_pct: float = 1.0) -> dict:
    if column not in df.columns or len(df) == 0:
        return {"name": f"rare_values:{column}", "category": "validity", "status": "pass",
                "message": "skipped", "detail": None}
    counts = df[column].value_counts(normalize=True) * 100
    rare = counts[counts < threshold_pct]
    status = "pass" if rare.empty else "warn"
    return {"name": f"rare_values:{column}", "category": "validity", "status": status,
            "message": f"{len(rare)} rare value(s) in '{column}' (<{threshold_pct}% of rows): {list(rare.index)}",
            "detail": None}


def outliers_iqr(df: pd.DataFrame, column: str, group_by: str = None) -> dict:
    if column not in df.columns:
        return {"name": f"outliers:{column}", "category": "outliers", "status": "warn",
                "message": f"column '{column}' not found, skipped", "detail": None}
    flagged = []
    groups = df.groupby(group_by) if group_by and group_by in df.columns else [(None, df)]
    for g, sub in groups:
        q1, q3 = sub[column].quantile(0.25), sub[column].quantile(0.75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        out = sub[(sub[column] < lo) | (sub[column] > hi)]
        flagged.append(out)
    flagged_df = pd.concat(flagged) if flagged else df.iloc[0:0]
    status = "pass" if flagged_df.empty else "warn"
    label = f"{column} by {group_by}" if group_by else column
    return {"name": f"outliers:{column}", "category": "outliers", "status": status,
            "message": f"{flagged_df.shape[0]} outlier(s) in {label} (IQR method)",
            "detail": flagged_df if not flagged_df.empty else None}


# --- Account-domain business rules (apply only if expected columns exist) ---

def rule_closed_requires_closed_date(df: pd.DataFrame) -> dict:
    cols = {"Status", "ClosedDate"}
    if not cols.issubset(df.columns):
        return _skip("rule:closed_requires_closed_date", cols, df)
    bad = df[(df["Status"] == "Closed") & df["ClosedDate"].isna()]
    return _result("rule:closed_requires_closed_date", "business_rule", bad,
                    "Closed accounts missing a ClosedDate")


def rule_open_has_no_closed_date(df: pd.DataFrame) -> dict:
    cols = {"Status", "ClosedDate"}
    if not cols.issubset(df.columns):
        return _skip("rule:open_has_no_closed_date", cols, df)
    bad = df[(df["Status"] == "Open") & df["ClosedDate"].notna()]
    return _result("rule:open_has_no_closed_date", "business_rule", bad,
                    "Open accounts that have a ClosedDate set")


def rule_closed_after_open(df: pd.DataFrame) -> dict:
    cols = {"OpenDate", "ClosedDate"}
    if not cols.issubset(df.columns):
        return _skip("rule:closed_after_open", cols, df)
    bad = df[df["ClosedDate"].notna() & (df["ClosedDate"] < df["OpenDate"])]
    return _result("rule:closed_after_open", "business_rule", bad,
                    "ClosedDate earlier than OpenDate")


def rule_no_future_dates(df: pd.DataFrame) -> dict:
    date_cols = [c for c in ["OpenDate", "ClosedDate"] if c in df.columns]
    if not date_cols:
        return _skip("rule:no_future_dates", {"OpenDate/ClosedDate"}, df)
    today = pd.Timestamp.today().normalize()
    mask = False
    for c in date_cols:
        mask = mask | (df[c] > today)
    bad = df[mask]
    return _result("rule:no_future_dates", "business_rule", bad,
                    "Rows with a date in the future")


def rule_unexpected_negative_balance(df: pd.DataFrame, credit_type_value: str = "Credit") -> dict:
    cols = {"Balance", "AccountType"}
    if not cols.issubset(df.columns):
        return _skip("rule:unexpected_negative_balance", cols, df)
    bad = df[(df["Balance"] < 0) & (df["AccountType"] != credit_type_value)]
    return _result("rule:unexpected_negative_balance", "business_rule", bad,
                    f"Negative balance on non-{credit_type_value} accounts")


def _skip(name, cols, df):
    missing = cols - set(df.columns)
    return {"name": name, "category": "business_rule", "status": "warn",
            "message": f"skipped, missing column(s): {sorted(missing)}", "detail": None}


def _result(name, category, bad_df, label):
    status = "pass" if bad_df.empty else "fail"
    return {"name": name, "category": category, "status": status,
            "message": f"{bad_df.shape[0]} row(s): {label}",
            "detail": bad_df if not bad_df.empty else None}

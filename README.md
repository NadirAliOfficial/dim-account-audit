# dim-account-audit

A lightweight CSV data audit tool. Runs schema, completeness, uniqueness, validity,
outlier, and business-rule checks against a CSV file and generates an HTML report
with charts plus machine-readable results.

Originally built for a `DimAccount.csv` dimension table but the generic checks work
on any CSV — only the account-specific business rules are domain-specific (and they
no-op automatically if the relevant columns aren't present).

## Features

- **Schema summary** — column types, row/column counts
- **Completeness** — null counts/percentages per column, with configurable
  warn/fail thresholds and a `nullable_columns` exemption list for fields where
  nulls are expected by design (e.g. `ClosedDate` on open accounts)
- **Uniqueness** — full-row duplicates and primary-key duplicates
- **Validity** — categorical domain checks (e.g. `AccountType` must be one of a
  fixed set) and rare-value detection (typo/outlier categories)
- **Outliers** — IQR-based outlier detection, optionally grouped by another column
- **Business rules** — account-domain checks: Closed accounts must have a
  `ClosedDate`, Open accounts must not, `ClosedDate` must be after `OpenDate`,
  no dates in the future, no unexpected negative balances on non-Credit accounts
- **Automated report** — self-contained `report.html` with a data quality score,
  pass/warn/fail breakdown, and charts; plus `results.json` and `flagged_rows.csv`
  for downstream tooling

## Usage

```bash
pip install -r requirements.txt
python3 audit.py --input /path/to/file.csv
```

Optional flags:

```bash
python3 audit.py --input file.csv --config config.json --output-dir output
```

Outputs are written to `output/`:

- `report.html` — visual report with charts and a check-by-check breakdown
- `results.json` — full results, machine-readable
- `flagged_rows.csv` — every row that failed or triggered a warning on any check

## Configuration

`config.json` controls which checks run and their thresholds:

```json
{
  "primary_key": "AccountID",
  "date_columns": ["OpenDate", "ClosedDate"],
  "nullable_columns": ["ClosedDate"],
  "categorical_domains": {
    "AccountType": ["Checking", "Savings", "Credit"],
    "Status": ["Open", "Closed"]
  },
  "outlier_columns": [{ "column": "Balance", "group_by": "AccountType" }],
  "rare_value_columns": ["AccountType", "Status"],
  "completeness_warn_pct": 5.0,
  "completeness_fail_pct": 30.0
}
```

Adjust this file (or pass `--config other.json`) to audit a different CSV shape.

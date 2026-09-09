#!/usr/bin/env python3
"""Tier 2 — program-affiliated start-ups (OTL licensees + ATDC companies).

Reads the two analyst deliveries (PitchBook-resolved, de-duplicated against the
1,144-company alumni universe by ATDC) and writes output/tier2_metrics.json.
Both workbooks are licensed PitchBook data and are gitignored; only the
aggregates in the JSON go to the site.

Usage:  python3 build_tier2.py --otl <OTL.xlsx> --atdc <ATDC.xlsx> [--out output/tier2_metrics.json]
"""
import argparse, json, sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent


def is_ga(hq):
    return isinstance(hq, str) and hq.strip().endswith(", GA")


def load(path, sheet, tag):
    df = pd.read_excel(path, sheet_name=sheet)
    df["src"] = tag
    df["ga"] = df["HQ Location"].map(is_ga)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--otl", required=True)
    ap.add_argument("--atdc", required=True)
    ap.add_argument("--out", default=str(HERE.parent / "output" / "tier2_metrics.json"))
    a = ap.parse_args()

    otl = load(a.otl, "Companies", "OTL licensee")
    atdc = load(a.atdc, "Companies", "ATDC")
    assert not set(otl.PBId) & set(atdc.PBId.dropna()), "OTL/ATDC overlap on PBId"

    both = pd.concat([otl, atdc], ignore_index=True)
    ga = both[both.ga]

    # survival — OTL cohort only (ATDC rows carry no Business Status)
    otl_closed = otl["Business Status"].isin(["Out of Business", "Bankruptcy: Admin/Reorg", "Bankruptcy: Liquidation"]).sum()

    # relationship bars
    rel = atdc["relationship_type"].replace({
        "Former ATDC Member": "ATDC — former member", "ATDC Graduate": "ATDC — graduate",
        "Accelerate": "ATDC — Accelerate", "Signature": "ATDC — Signature"})
    rel_counts = rel.value_counts().to_dict()
    rel_counts["OTL — licensed Georgia Tech technology"] = len(otl)
    relationships = sorted(({"relationship": k, "companies": int(v)} for k, v in rel_counts.items()),
                           key=lambda d: -d["companies"])

    sectors = (ga["Primary PitchBook Industry Sector"].value_counts()
               .reset_index().values.tolist())
    sectors = [{"sector": s, "companies": int(n)} for s, n in sectors]

    top = both.sort_values("Total Raised", ascending=False).head(3)
    out = {
        "meta": {
            "otl_file_date": "2026-08-31", "atdc_export_date": "2026-09-02",
            "prepared_by": "ATDC (Caroline M. Ford) for CEDR", "built": pd.Timestamp.today().strftime("%Y-%m-%d"),
        },
        "headline": {
            "companies": int(len(both)),
            "companies_otl": int(len(otl)), "companies_atdc": int(len(atdc)),
            "companies_hq_known": int(both["HQ Location"].notna().sum()),
            "ga_companies": int(len(ga)),
            "ga_capital_musd": round(float(ga["Total Raised"].sum()), 1),
            "ga_capital_reporting": int(ga["Total Raised"].notna().sum()),
            "total_capital_musd": round(float(both["Total Raised"].sum()), 1),
            "total_capital_reporting": int(both["Total Raised"].notna().sum()),
            "ga_employees": int(ga["Employees"].sum()),
            "ga_employees_reporting": int(ga["Employees"].notna().sum()),
            "total_employees": int(both["Employees"].sum()),
            "total_employees_reporting": int(both["Employees"].notna().sum()),
            "otl_closed": int(otl_closed), "otl_closed_share": round(float(otl_closed) / len(otl), 3),
            "already_in_alumni_layer": {"atdc": 52, "otl": 19},
            "otl_not_in_pitchbook": 56,
            "atdc_survey_only_musd": 42.6,
        },
        "top_capital": [{"company": r.Companies, "hq": r["HQ Location"], "musd": round(float(r["Total Raised"]), 1)}
                        for _, r in top.iterrows()],
        "relationships": relationships,
        "sectors": sectors,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(json.dumps(out["headline"], indent=2)); print(out["top_capital"]); print(relationships); print(sectors)


if __name__ == "__main__":
    main()

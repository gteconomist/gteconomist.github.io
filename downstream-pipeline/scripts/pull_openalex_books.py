#!/usr/bin/env python3
"""
Track 1 - Family G: Scholarship & recognition — BOOKS (and scholarly output) via OpenAlex.

AAU's Phase I "Books" indicator counts books published by an institution's faculty
(AAU uses Academic Analytics, a licensed database). OpenAlex is the open analogue:
a free, no-key API that indexes Crossref/other records with author affiliations.

What this pulls, for Georgia Tech (OpenAlex institution I130701444, incl. GTRI etc.
via `lineage`):
  G1  books per year          (type:book)       — the AAU-style headline
  G1b book chapters per year  (type:book-chapter)
  G1c books by field          (primary_topic.field) — how many are humanities/social science
  G2  all works + citations per year (context; open analogue of the Citations indicator)

Row-level book records are written to CSV so titles/publishers can be eyeballed —
OpenAlex "book" can include edited volumes and proceedings volumes, so expect to
footnote that this is "books and monographs indexed in OpenAlex", not
"peer-reviewed books" in the Academic Analytics sense.

DATA SOURCE (public, no key): https://api.openalex.org  (polite pool via ?mailto=)

USAGE
  python3 pull_openalex_books.py                   # 2015..current year
  python3 pull_openalex_books.py --from 2015 --to 2025
OUTPUT
  output/openalex_books_<from>_<to>.csv
  output/openalex_summary.json                       (read by inject_downstream.py)
"""

import argparse
import csv
import datetime as dt
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

API = "https://api.openalex.org/works"
GT_ID = "I130701444"
MAILTO = "alfie@economicimpact.com"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

# OpenAlex "book" records that are not books in the AAU sense: edited conference/
# proceedings volumes (Trans Tech etc.) and datasets deposited with a book DOI type.
EXCLUDE_PUBLISHERS = ("trans tech",)
EXCLUDE_TITLE = re.compile(r"conference|proceedings|symposium|workshop|\bvol\.? ?\d|volume \d|\bICNB\b", re.I)


def exclusion_reason(row) -> str:
    if "zenodo" in (row.get("doi") or "").lower():
        return "dataset"
    if any(x in (row.get("publisher") or "").lower() for x in EXCLUDE_PUBLISHERS):
        return "proceedings"
    if EXCLUDE_TITLE.search(row.get("title") or ""):
        return "proceedings"
    return ""


# OpenAlex field ids that count as arts / humanities / social science
AHSS_FIELDS = {
    "12": "Arts and Humanities",
    "33": "Social Sciences",
    "20": "Economics, Econometrics and Finance",
    "32": "Psychology",
    "14": "Business, Management and Accounting",
    "18": "Decision Sciences",
}


def get(params, retries=6):
    params = dict(params, mailto=MAILTO)
    for i in range(retries):
        r = requests.get(API, params=params, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            wait = 2 ** i
            print(f"  {r.status_code} from OpenAlex, retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise SystemExit("OpenAlex kept rate-limiting; try again in a minute.")


def gt_filter(extra):
    return f"authorships.institutions.lineage:{GT_ID},{extra}"


def group_by_year(extra, y_from, y_to):
    data = get({"filter": gt_filter(f"{extra},publication_year:{y_from}-{y_to}"),
                "group_by": "publication_year", "per-page": 200})
    out = {}
    for g in data.get("group_by", []):
        try:
            out[int(g["key"])] = g["count"]
        except (ValueError, TypeError):
            pass
    return out


def sum_citations_by_year(y_from, y_to):
    """cited_by_count summed over works per year (OpenAlex has no group_by sum, so page it)."""
    totals = {}
    for y in range(y_from, y_to + 1):
        cursor, s, n = "*", 0, 0
        while cursor:
            data = get({"filter": gt_filter(f"publication_year:{y}"),
                        "select": "id,cited_by_count", "per-page": 200, "cursor": cursor})
            for w in data["results"]:
                s += w.get("cited_by_count") or 0
                n += 1
            cursor = data["meta"].get("next_cursor")
        totals[y] = {"works": n, "citations": s}
        print(f"  {y}: {n} works, {s} citations", file=sys.stderr)
    return totals


def fetch_books(y_from, y_to):
    rows, cursor = [], "*"
    while cursor:
        data = get({"filter": gt_filter(f"type:book,publication_year:{y_from}-{y_to}"),
                    "select": "id,doi,title,publication_year,type,primary_location,"
                              "primary_topic,authorships,cited_by_count",
                    "per-page": 200, "cursor": cursor})
        for w in data["results"]:
            gt_authors = [a["author"]["display_name"] for a in w.get("authorships", [])
                          if any(GT_ID in (i.get("lineage") or [i.get("id", "")])
                                 or i.get("id", "").endswith(GT_ID)
                                 for i in a.get("institutions", []))]
            loc = w.get("primary_location") or {}
            src = (loc.get("source") or {})
            topic = w.get("primary_topic") or {}
            field = (topic.get("field") or {})
            fid = str(field.get("id", "")).rsplit("/", 1)[-1]
            rows.append({
                "openalex_id": w["id"], "doi": w.get("doi") or "",
                "title": w.get("title") or "", "year": w.get("publication_year"),
                "publisher": src.get("host_organization_name") or src.get("display_name") or "",
                "field": field.get("display_name") or "", "field_id": fid,
                "ahss": "Y" if fid in AHSS_FIELDS else "",
                "gt_authors": "; ".join(gt_authors), "cited_by": w.get("cited_by_count") or 0,
            })
            rows[-1]["excluded"] = exclusion_reason(rows[-1])
        cursor = data["meta"].get("next_cursor")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="y_from", type=int, default=2015)
    ap.add_argument("--to", dest="y_to", type=int, default=dt.date.today().year)
    ap.add_argument("--no-citations", action="store_true", help="skip the slower citations pass")
    a = ap.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Books by year ...", file=sys.stderr)
    books = group_by_year("type:book", a.y_from, a.y_to)
    print("Book chapters by year ...", file=sys.stderr)
    chapters = group_by_year("type:book-chapter", a.y_from, a.y_to)
    print("Book rows ...", file=sys.stderr)
    rows = fetch_books(a.y_from, a.y_to)

    by_field = defaultdict(int)
    ahss_by_year = defaultdict(int)
    filtered_by_year = defaultdict(int)
    for r in rows:
        if r["excluded"]:
            continue
        filtered_by_year[r["year"]] += 1
        by_field[r["field"] or "Unclassified"] += 1
        if r["ahss"]:
            ahss_by_year[r["year"]] += 1

    csv_path = OUTPUT_DIR / f"openalex_books_{a.y_from}_{a.y_to}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["title"])
        w.writeheader(); w.writerows(sorted(rows, key=lambda r: (-(r["year"] or 0), r["title"])))

    cites = {}
    prev = OUTPUT_DIR / "openalex_summary.json"
    if a.no_citations and prev.exists():   # keep the last run's citation pass
        cites = {int(k): v for k, v in json.loads(prev.read_text()).get("works_citations_by_year", {}).items()}
    elif not a.no_citations:
        print("Works + citations by year (slower) ...", file=sys.stderr)
        cites = sum_citations_by_year(a.y_from, a.y_to)

    years = list(range(a.y_from, a.y_to + 1))
    summary = {
        "source": "OpenAlex (api.openalex.org), Georgia Tech lineage I130701444",
        "pulled": dt.date.today().isoformat(),
        "year_from": a.y_from, "year_to": a.y_to,
        "books_by_year": {str(y): books.get(y, 0) for y in years},
        "books_filtered_by_year": {str(y): filtered_by_year.get(y, 0) for y in years},
        "excluded_count": sum(1 for r in rows if r["excluded"]),
        "ahss_books_by_year": {str(y): ahss_by_year.get(y, 0) for y in years},
        "chapters_by_year": {str(y): chapters.get(y, 0) for y in years},
        "books_by_field": dict(sorted(by_field.items(), key=lambda kv: -kv[1])),
        "works_citations_by_year": {str(y): v for y, v in cites.items()},
        "note": ("books_by_year = every OpenAlex type:book record with a GT-affiliated author. "
                 "books_filtered_by_year drops edited conference/proceedings volumes and datasets "
                 "(see the 'excluded' column in the CSV) and is the series the site uses. "
                 "Not equivalent to Academic Analytics' book count used by AAU."),
    }
    (OUTPUT_DIR / "openalex_summary.json").write_text(json.dumps(summary, indent=2))

    print("\nBooks (OpenAlex type:book) with a Georgia Tech author:")
    for y in years:
        print(f"  {y}: {filtered_by_year.get(y,0):4d} books ({books.get(y,0)} before filtering; "
              f"{ahss_by_year.get(y,0)} arts/hum/soc-sci)   "
              f"{chapters.get(y,0):4d} chapters")
    print("\nTop fields:", ", ".join(f"{k} {v}" for k, v in list(summary["books_by_field"].items())[:8]))
    print(f"\nWrote {csv_path.name} ({len(rows)} rows) and openalex_summary.json")


if __name__ == "__main__":
    main()

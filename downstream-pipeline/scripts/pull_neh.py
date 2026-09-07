#!/usr/bin/env python3
"""
Track 1 - Family G: Scholarship & recognition — NEH GRANTS to Georgia Tech.

The liberal-arts counterpart to Family D (SBIR/STTR): competitively awarded federal
humanities funding. Uses NEH's open-data grant files (one zip per decade, XML inside).

DATA SOURCE (public, no key):  NEH open data (catalog.data.gov "NEH grant data"), hosted at
  https://nehopendatastorage.blob.core.windows.net/nehopendata/
  NEH_Grants2010s.zip, NEH_Grants2020s.zip  (each holds NEH_Grants20XXs.xml)

Counts awards + dollars (outright + matching) by year, division and program where
the grantee institution is Georgia Tech. Individual fellowships list the scholar's
home institution in the same field, so NEH Fellowships to GT faculty are included
and flagged separately.

USAGE
  python3 pull_neh.py                      # downloads the zips into output/neh_cache/ if missing
  python3 pull_neh.py --from 2015 --to 2025
OUTPUT
  output/neh_awards_<from>_<to>.csv
  output/neh_summary.json                  (read by inject_downstream.py)
"""

import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import requests

BASES = ["https://nehopendatastorage.blob.core.windows.net/nehopendata/",
         "https://apps.neh.gov/open/data/"]
DECADES = ["NEH_Grants2010s.zip", "NEH_Grants2020s.zip"]
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
CACHE = OUTPUT_DIR / "neh_cache"
GT_PATTERNS = [r"georgia institute of technology", r"georgia tech", r"gtrc", r"georgia tech research"]
UA = "Mozilla/5.0 (Macintosh) CEDR downstream pipeline"


def fetch(name: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / name
    if not p.exists():
        last = None
        for base in BASES:
            try:
                print(f"Downloading {base}{name} ...", file=sys.stderr)
                r = requests.get(base + name, headers={"User-Agent": UA}, timeout=120)
                r.raise_for_status()
                p.write_bytes(r.content)
                break
            except Exception as e:  # try the next host
                last = e
                print(f"  failed: {e}", file=sys.stderr)
        if not p.exists():
            raise SystemExit(f"Could not download {name}: {last}")
    return p


def text(el, tag):
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def money(s):
    s = re.sub(r"[^0-9.\-]", "", s or "")
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def parse(zip_path: Path):
    with zipfile.ZipFile(zip_path) as z:
        xml_names = [n for n in z.namelist() if n.lower().endswith(".xml")]
        if not xml_names:
            raise SystemExit(f"No XML inside {zip_path.name}: {z.namelist()}")
        data = z.read(xml_names[0])
    root = ET.parse(io.BytesIO(data)).getroot()
    grants = root.findall(".//Grant") or list(root)
    for g in grants:
        inst = text(g, "Institution")
        part_insts = [text(p, "Institution") for p in g.findall(".//Participant")]
        hit = lambda x: any(re.search(pat, x or "", re.I) for pat in GT_PATTERNS)
        if not (hit(inst) or any(hit(x) for x in part_insts)):
            continue
        yield {
            "application_number": text(g, "AppNumber") or text(g, "ApplicationNumber"),
            "year": int((text(g, "YearAwarded") or "0")[:4] or 0),
            "institution": inst,
            "city": text(g, "InstCity") or text(g, "InstitutionCity"),
            "state": text(g, "InstState") or text(g, "InstitutionState"),
            "title": text(g, "ProjectTitle"),
            "program": text(g, "Program"),
            "division": text(g, "Division"),
            "discipline": text(g, "PrimaryDiscipline"),
            "participant": text(g, "Participants") or "; ".join(
                f"{text(p, 'Firstname')} {text(p, 'Lastname')}".strip()
                for p in g.findall(".//Participant")),
            "outright": money(text(g, "AwardOutright")),
            "matching": money(text(g, "AwardMatching")),
            "begin": text(g, "BeginGrant"),
            "end": text(g, "EndGrant"),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="y_from", type=int, default=2015)
    ap.add_argument("--to", dest="y_to", type=int, default=dt.date.today().year)
    a = ap.parse_args()

    rows = []
    for name in DECADES:
        rows.extend(parse(fetch(name)))
    rows = [r for r in rows if a.y_from <= r["year"] <= a.y_to]
    for r in rows:
        r["total"] = r["outright"] + r["matching"]
        r["is_fellowship"] = "Y" if re.search(r"fellow|stipend", r["program"], re.I) else ""

    seen, dedup = set(), []
    for r in rows:
        k = r["application_number"] or (r["title"], r["year"])
        if k in seen:
            continue
        seen.add(k); dedup.append(r)
    rows = dedup

    csv_path = OUTPUT_DIR / f"neh_awards_{a.y_from}_{a.y_to}.csv"
    fields = ["year", "title", "program", "division", "discipline", "participant", "institution",
              "outright", "matching", "total", "is_fellowship", "application_number", "begin", "end", "city", "state"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(sorted(rows, key=lambda r: (-r["year"], r["title"])))

    by_year = defaultdict(lambda: {"awards": 0, "usd": 0.0, "fellowships": 0})
    by_div, by_prog = defaultdict(lambda: {"awards": 0, "usd": 0.0}), defaultdict(lambda: {"awards": 0, "usd": 0.0})
    for r in rows:
        y = by_year[r["year"]]; y["awards"] += 1; y["usd"] += r["total"]; y["fellowships"] += r["is_fellowship"] == "Y"
        d = by_div[r["division"] or "Unspecified"]; d["awards"] += 1; d["usd"] += r["total"]
        p = by_prog[r["program"] or "Unspecified"]; p["awards"] += 1; p["usd"] += r["total"]

    years = list(range(a.y_from, a.y_to + 1))
    summary = {
        "source": "NEH open data grant files (nehopendatastorage.blob.core.windows.net)",
        "pulled": dt.date.today().isoformat(),
        "year_from": a.y_from, "year_to": a.y_to,
        "by_year": {str(y): by_year.get(y, {"awards": 0, "usd": 0.0, "fellowships": 0}) for y in years},
        "cumulative": {"awards": len(rows), "usd": sum(r["total"] for r in rows)},
        "by_division": dict(sorted(by_div.items(), key=lambda kv: -kv[1]["usd"])),
        "by_program": dict(sorted(by_prog.items(), key=lambda kv: -kv[1]["usd"])),
    }
    (OUTPUT_DIR / "neh_summary.json").write_text(json.dumps(summary, indent=2))

    print("NEH awards where the grantee institution is Georgia Tech:")
    for y in years:
        v = summary["by_year"][str(y)]
        print(f"  {y}: {v['awards']:3d} awards  ${v['usd']:>12,.0f}   ({v['fellowships']} fellowships)")
    print(f"  cumulative {a.y_from}-{a.y_to}: {len(rows)} awards, ${summary['cumulative']['usd']:,.0f}")
    print(f"\nWrote {csv_path.name} and neh_summary.json")


if __name__ == "__main__":
    main()

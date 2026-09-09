"""Rebuild the STUDENTS constant in index.html from the AY2025 enrollment geographic
summary workbook (GT_AY2025_Enrollment_Geographic_Summary.xlsx).

Usage (from repo root):
    python3 upstream-pipeline/build_students.py "upstream-pipeline/data/GT_AY2025_Enrollment_Geographic_Summary.xlsx"

The workbook is gitignored (*.xlsx). The script reads the Summary, GA by Region and
GA County Detail tabs and writes one line `const STUDENTS = {...};` into index.html,
replacing the existing line. Spending estimates are not in this file yet; when they
arrive, add them here and the site picks them up.
"""
import json, re, sys
from pathlib import Path
import openpyxl

SITE = Path(__file__).resolve().parent.parent / 'index.html'
src = Path(sys.argv[1] if len(sys.argv) > 1 else 'upstream-pipeline/data/GT_AY2025_Enrollment_Geographic_Summary.xlsx')
wb = openpyxl.load_workbook(src, data_only=True)

COLS = ['total', 'ug', 'grad', 'inperson', 'online', 'ug_inperson', 'ug_online', 'grad_inperson', 'grad_online', 'housing']

def rec(vals):
    return {k: int(v or 0) for k, v in zip(COLS, vals)}

# --- Summary tab: geography rows ---
ws = wb['Summary']
summary = {}
key = {'Georgia residents': 'georgia', 'Other U.S. states & DC': 'other_states', 'U.S. territories': 'territories',
       'Military / APO-FPO': 'military', 'Location not reported': 'not_reported', 'GRAND TOTAL': 'all'}
for row in ws.iter_rows(min_row=4, values_only=True):
    if row[0] in key and isinstance(row[1], (int, float)):
        summary[key[row[0]]] = rec(row[1:11])

# --- GA by Region tab ---
ws = wb['GA by Region']
regions = {}
for row in ws.iter_rows(min_row=4, values_only=True):
    if isinstance(row[0], int) and 1 <= row[0] <= 12:
        regions[str(row[0])] = {'name': row[1], **rec(row[2:12])}
assert len(regions) == 12

# --- GA County Detail tab ---
ws = wb['GA County Detail']
counties = {}
cur = None
for row in ws.iter_rows(min_row=4, values_only=True):
    if row[0] and re.match(r'^\d+\.', str(row[0])):
        cur = int(str(row[0]).split('.')[0])
    elif row[1] and cur and isinstance(row[2], (int, float)) and str(row[1]).upper() != 'TOTAL':
        counties[row[1]] = {'region': cur, **rec(row[2:12])}

ga_check = sum(c['total'] for c in counties.values())
assert ga_check == summary['georgia']['total'], (ga_check, summary['georgia']['total'])
assert sum(r['total'] for r in regions.values()) == summary['georgia']['total']

# --- Other States tab (top 10 for the "where the rest come from" note) ---
ws = wb['Other States']
states = []
for row in ws.iter_rows(min_row=4, values_only=True):
    if row[0] and isinstance(row[1], (int, float)) and 'TOTAL' not in str(row[0]).upper():
        states.append({'name': str(row[0]).strip(), 'total': int(row[1])})
states.sort(key=lambda s: -s['total'])

STUDENTS = {
    'academic_year': 'AY2025',
    'source': 'Georgia Tech Institutional Research enrollment extract, AY2025 (county of residence)',
    'summary': summary,
    'regions': regions,
    'counties': counties,
    'top_states': states[:10],
    'counties_represented': len(counties),
}

html = SITE.read_text()
new = 'const STUDENTS = ' + json.dumps(STUDENTS) + ';'
html2, n = re.subn(r'const STUDENTS = \{.*?\};\n', lambda m: new + '\n', html, count=1, flags=re.S)
if n == 0:
    # first run: insert directly after the IMPACT line
    html2, n = re.subn(r'(const IMPACT = \{.*?\};\n)', lambda m: m.group(1) + new + '\n', html, count=1, flags=re.S)
assert n == 1, 'could not place STUDENTS constant'
SITE.write_text(html2)
print(f'STUDENTS written: GA {summary["georgia"]["total"]:,} of {summary["all"]["total"]:,}; '
      f'{len(regions)} regions, {len(counties)} counties, {len(states)} states')

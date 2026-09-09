#!/usr/bin/env python3
"""One-time patch: add the Tier 2 (program-affiliated start-ups, PRELIMINARY) block to index.html.

Everything lives OUTSIDE the DOWNSTREAM_DATA_START/END block so inject_downstream.py
cannot overwrite it (same pattern as Tier 3). Idempotent: exits if DOWNSTREAM_T2 exists.
Data: downstream-pipeline/output/tier2_metrics.json (from scripts/build_tier2.py).
Run from repo root:  python3 downstream-pipeline/scripts/patch_tier2.py
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = ROOT / "index.html"
JS = ROOT / "downstream-pipeline" / "output" / "tier2_metrics.json"

html = HTML.read_text(encoding="utf-8")
if "DOWNSTREAM_T2" in html:
    print("already patched"); sys.exit(0)
T2 = json.loads(JS.read_text())

# ---- 1. HTML block -----------------------------------------------------------
anchor = '<div class="fgrid" id="tier2fams"></div>\n'
assert anchor in html
block = anchor + '''
    <div id="t2Block">
    <div class="t3note"><b>Preliminary &mdash; companies with a documented Georgia Tech program relationship.</b>
      These are companies that licensed Georgia Tech technology through the Office of Technology
      Licensing, or that were members of ATDC, the Institute&rsquo;s technology incubator. Every
      company was matched to an administrative record; none entered through founder biographies.
      Activity is reported as it stands at these companies, not as a Georgia Tech-attributed total.
      Figures are lower bounds &mdash; see the notes below the charts.</div>
    <div class="kpis" id="dkpisT2"></div>
    <div class="dgrid2">
      <div class="panel"><h2>Companies by relationship</h2><div class="sub" id="drelsubT2">How each company connects to Georgia Tech</div><div id="drelT2"></div></div>
      <div class="panel"><h2>Sector mix</h2><div class="sub" id="dsectorsubT2">Georgia-headquartered companies by primary sector</div><div id="dsectorsT2"></div></div>
    </div>
    <div class="foot" id="dfootT2" style="margin-bottom:26px"></div>
    </div>
'''
html = html.replace(anchor, block, 1)
html = html.replace('Tier 2 &middot; Venture growth <span>matched data &middot; in development</span>',
                    'Tier 2 &middot; Venture growth <span>matched data &middot; preliminary</span>', 1)
html = html.replace('Built from matched administrative data with stated assumptions. Medium certainty. In development.',
                    'Built from matched administrative data with stated assumptions. Medium certainty. First figures published as preliminary.', 1)
old_t3 = ('Licensed-IP and faculty-founded companies (Tier 2) are not yet included. Figures\n'
          '      are lower bounds and will be restated &mdash; see the notes below the charts.')
assert old_t3 in html
html = html.replace(old_t3,
    'Companies that also hold a Georgia Tech licence or an ATDC relationship are counted here\n'
    '      only, not repeated in Tier 2. Figures are lower bounds and will be restated &mdash; see the notes below the charts.', 1)

# ---- 2. Data + card patch, after the Tier 3 card patch --------------------------
data_anchor = 'const fmtInt = d3.format(",.0f");'
assert data_anchor in html
data_js = '''/* ---- Tier 2 program-affiliated start-ups (PRELIMINARY) --------------------------
   Also outside the regenerated block. Source: OTL start-up list (31 Aug 2026) and ATDC
   roster, resolved in PitchBook and de-duplicated against the alumni universe by ATDC,
   September 2026. Regenerate from downstream-pipeline/output/tier2_metrics.json
   (scripts/build_tier2.py), then re-run scripts/patch_tier2.py after removing this block. */
const DOWNSTREAM_T2 = ''' + json.dumps(T2, indent=2) + ''';
if (DOWNSTREAM.families && DOWNSTREAM.families.tier2 && DOWNSTREAM.families.tier2[0]) {
  DOWNSTREAM.families.tier2[0].status  = "preliminary";
  DOWNSTREAM.families.tier2[0].name    = "Program-affiliated startups";
  DOWNSTREAM.families.tier2[0].desc    = "Companies that licensed Georgia Tech technology or came through ATDC, matched to administrative records: where they are headquartered, capital raised, employment, and how many are still operating.";
  DOWNSTREAM.families.tier2[0].metrics =
    "<b>" + DOWNSTREAM_T2.headline.ga_companies + "</b> Georgia companies &middot; <b>$"
    + (DOWNSTREAM_T2.headline.ga_capital_musd/1000).toFixed(2)
    + "B</b> capital raised &middot; <b>"
    + DOWNSTREAM_T2.headline.ga_employees.toLocaleString() + "</b> employees";
}
'''
html = html.replace(data_anchor, data_js + data_anchor, 1)

# ---- 3. Render function + call -------------------------------------------------------
fn_anchor = 'function renderT3(){'
assert fn_anchor in html
render_js = '''function renderT2(){
  const T=DOWNSTREAM_T2, h=T.headline;
  const cards=[
    {v:fmtInt(h.ga_companies),                        l:"Georgia-headquartered companies"},
    {v:"$"+(h.ga_capital_musd/1000).toFixed(2)+"B",   l:"Capital raised by Georgia companies &middot; lifetime"},
    {v:fmtInt(h.ga_employees),                        l:"Employees at Georgia companies&#8202;<sup>&dagger;</sup>"},
    {v:Math.round(h.otl_closed_share*100)+"%",        l:"Licensed-technology startups no longer operating"}
  ];
  const sel=d3.select("#dkpisT2").selectAll(".kpi").data(cards);
  const ent=sel.enter().append("div").attr("class","kpi");
  ent.append("div").attr("class","v"); ent.append("div").attr("class","l");
  const all=ent.merge(sel);
  all.select(".v").html(d=>d.v); all.select(".l").html(d=>d.l);

  const wpx=150;
  const r=T.relationships, rmax=d3.max(r,d=>d.companies)||1;
  d3.select("#drelsubT2").html("How each company connects to Georgia Tech &middot; n="+fmtInt(h.companies));
  d3.select("#drelT2").html(r.map(d=>
    `<div class="darea"><span class="dlab">${d.relationship}</span><span class="dbar" style="width:${Math.max(8,d.companies/rmax*wpx)}px"></span><span class="dval">${d.companies}</span></div>`).join(""));
  const s=T.sectors, smax=d3.max(s,d=>d.companies)||1;
  d3.select("#dsectorsubT2").html("Georgia-headquartered companies by primary sector &middot; n="+fmtInt(h.ga_companies));
  d3.select("#dsectorsT2").html(s.map(d=>
    `<div class="darea"><span class="dlab">${d.sector}</span><span class="dbar" style="width:${Math.max(8,d.companies/smax*wpx)}px"></span><span class="dval">${d.companies}</span></div>`).join(""));

  const top=T.top_capital;
  d3.select("#dfootT2").html(
    '<b>How these are built:</b> '+fmtInt(h.companies)+' companies with a documented Georgia Tech '+
    'relationship &mdash; '+fmtInt(h.companies_otl)+' that licensed Georgia Tech technology through the Office of '+
    'Technology Licensing and '+fmtInt(h.companies_atdc)+' ATDC member companies (relationship 2010 or later, '+
    'founded 2005 or later) &mdash; each resolved to a PitchBook record and checked against the alumni '+
    'layer so no company is counted twice; companies with these relationships that already appear in Tier 3 ('+
    h.already_in_alumni_layer.atdc+' ATDC, '+h.already_in_alumni_layer.otl+' licensees, some both) are not repeated. '+
    'Capital is PitchBook lifetime capital, disclosed for '+fmtInt(h.total_capital_reporting)+' of the '+
    fmtInt(h.companies)+' companies ($'+(h.total_capital_musd/1000).toFixed(2)+'B in total); blanks mean '+
    'no recorded figure, not no capital, so totals are lower bounds. Capital is concentrated: '+
    top[0].company+' ('+top[0].hq+', $'+(top[0].musd/1000).toFixed(2)+'B) and '+top[1].company+' ('+top[1].hq+
    ', $'+fmtInt(top[1].musd)+'M) hold about a third of the total and are headquartered outside Georgia. '+
    'Georgia counts use current headquarters; '+fmtInt(h.companies-h.companies_hq_known)+' companies have no location on record. '+
    '<sup>&dagger;</sup>&#8202;Employment reflects the '+fmtInt(h.ga_employees_reporting)+' Georgia companies reporting headcount. '+
    'The closure rate is measured on the licensed-technology cohort only ('+fmtInt(h.otl_closed)+' of '+fmtInt(h.companies_otl)+
    ' out of business or in bankruptcy), because an administrative list keeps failed companies where '+
    'database sources do not; ATDC records carry no operating status. '+
    '<b>Not counted:</b> '+fmtInt(h.otl_not_in_pitchbook)+' licensed-technology companies with no PitchBook record at all, '+
    'and $'+h.atdc_survey_only_musd.toFixed(1)+'M self-reported to ATDC by companies PitchBook records with no capital. '+
    'Company lists from Georgia Tech OTL (31 August 2026) and ATDC; PitchBook data exported 1&ndash;2 September 2026; '+
    'matching and de-duplication by ATDC, with CEDR review. VentureLab and CREATE-X company lists are still to be added.');
}
'''
html = html.replace(fn_anchor, render_js + fn_anchor, 1)
call_anchor = '  renderT3();'
assert html.count(call_anchor) == 1
html = html.replace(call_anchor, '  renderT2();\n' + call_anchor, 1)

HTML.write_text(html, encoding="utf-8")
print("patched", HTML)

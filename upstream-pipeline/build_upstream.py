"""Rebuild the upstream (traditional) IMPACT constant in index.html from CEDR's
FY impact workbook ("FY xx Economic Impact Emp Salary and ER Expense By Ga Region.xlsx").

Usage (from repo root):  python3 upstream-pipeline/build_upstream.py "upstream-pipeline/data/<workbook>.xlsx"

Reads the Data tab: regional rows 3-14, Georgia totals row 15, Final Table rows 26-32
(direct row 26 has Value Added and Output hard-coded from IMPLAN), state appropriation L43/M43.
Institute spending = Institute Spend + GTAA Spend (col U); indirect = Primary + Secondary (cols AH-AK).
"""
import openpyxl, json, re, sys
from pathlib import Path
XL=sys.argv[1]
SITE=Path(__file__).resolve().parent.parent/'index.html'
wb=openpyxl.load_workbook(XL,data_only=True); ws=wb['Data']
def c(r,col): 
    v=ws[f'{col}{r}'].value; return round(float(v),2) if isinstance(v,(int,float)) else v
emp_regions={}; inst_regions={}
for r in range(3,15):
    n=int(ws[f'A{r}'].value); name=ws[f'B{r}'].value
    emp_regions[str(n)]=dict(region=n,name=name,wages=c(r,'C'),employer_expense=c(r,'D'),employees=int(ws[f'E{r}'].value),
        direct_income=c(r,'H'),induced_income=c(r,'I'),total_income=c(r,'J'),induced_employment=c(r,'K'),value_added=c(r,'R'),output=c(r,'S'))
    inst_regions[str(n)]=dict(region=n,name=name,inst_spend=c(r,'U'),institute_spend=c(r,'F'),gtaa_spend=c(r,'G'),
        indirect_output=c(r,'AH'),indirect_emp=c(r,'AI'),indirect_income=c(r,'AJ'),
        induced_emp=c(r,'AD'),induced_output=c(r,'AC'),induced_income=c(r,'AE'))
r=15
emp_state=dict(wages=c(r,'C'),employer_expense=c(r,'D'),employees=int(ws['E15'].value),direct_income=c(r,'H'),induced_income=c(r,'I'),
    total_income=c(r,'J'),induced_employment=c(r,'K'),value_added=c(r,'R'),output=c(r,'S'))
inst_state=dict(inst_spend=c(r,'U'),institute_spend=c(r,'F'),gtaa_spend=c(r,'G'),indirect_output=c(r,'AH'),indirect_emp=c(r,'AI'),indirect_income=c(r,'AJ'),
    induced_emp=c(r,'AD'),induced_output=c(r,'AC'),induced_income=c(r,'AE'))
def row(rr): return dict(employment=c(rr,'I'),labor_income=c(rr,'J'),value_added=c(rr,'K'),output=c(rr,'L'))
combined=dict(direct=row(26),indirect=row(28),induced=row(30),total=row(32))
IMPACT=dict(fiscal_year='FY25',state_approp_share=round(float(ws['M43'].value),8),state_approp_amount=float(ws['L43'].value),
    combined=combined,employees=dict(statewide=emp_state,regions=emp_regions),institute=dict(statewide=inst_state,regions=inst_regions))
# sanity
for k in ['employment','labor_income','value_added','output']:
    s=sum(combined[t][k] for t in ['direct','indirect','induced']); assert abs(s-combined['total'][k])<1,(k,s)
assert abs(sum(v['indirect_output'] for v in inst_regions.values())-inst_state['indirect_output'])<1
print(json.dumps(combined,indent=1)); print(inst_state)
html=SITE.read_text()
new='const IMPACT = '+json.dumps(IMPACT)+';'
html2,n=re.subn(r'const IMPACT = \{.*?\};\n',lambda m:new+'\n',html,count=1,flags=re.S)
assert n==1
SITE.write_text(html2); print('updated',SITE)

import importlib.util
from pathlib import Path
from openpyxl import Workbook

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('dual',ROOT/'scripts/dual_track_acceptance.py');dual=importlib.util.module_from_spec(spec);spec.loader.exec_module(dual)

def book(path,point=('10.00','10.00','学校经办人'),assessment=('95','95','学校经办人')):
    wb=Workbook();ws=wb.active;ws.title='积分双轨';ws.append(dual.HEADERS);ws.append(['P-1','J001','2026年度',point[0],point[1],'POINT-v1',point[2],''])
    ws=wb.create_sheet('考核双轨');ws.append(dual.HEADERS);ws.append(['A-1','J001','2026年度',assessment[0],assessment[1],'ASSESS-v1',assessment[2],'']);wb.save(path);wb.close()

def test_dual_track_requires_explicit_school_signoff(tmp_path):
    p=tmp_path/'a.xlsx';book(p);r=dual.verify(p,False);assert r['status']=='BLOCKED' and r['points_match_rate']==1 and r['signed_off'] is False

def test_dual_track_100_percent_and_signed_rows_pass(tmp_path):
    p=tmp_path/'a.xlsx';book(p);r=dual.verify(p,True);assert r['status']=='PASS' and r['points_match_rate']==1 and r['assessment_match_rate']==1 and r['signed_off']

def test_dual_track_mismatch_or_missing_signer_blocks(tmp_path):
    p=tmp_path/'a.xlsx';book(p,assessment=('95','94.99',''));r=dual.verify(p,True);assert r['status']=='BLOCKED' and r['assessment_match_rate']==0 and not r['signed_off']

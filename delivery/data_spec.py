"""All data is synthetic. No official school names, identities, seals or contacts."""
from datetime import date
YEAR=2026
REASON={'reason':'R11独立环境合成演示数据','basis':'仅用于产品流程展示，不是学校真实数据或验收样本'}
ACCOUNTS=[
 ('teacher','show_teacher','合成教师一','YS001','d1','role-teacher'),
 ('teacher2','show_teacher2','合成教师二','YS002','d1','role-teacher'),
 ('teacher3','show_teacher3','合成教师三','YS003','d2','role-teacher'),
 ('other','show_other','合成教师四','YS004','d3','role-teacher'),
 ('teacher5','show_teacher5','合成教师五','YS005','d3','role-teacher'),
 ('teacher6','show_teacher6','合成教师六','YS006','d3','role-teacher'),
 ('dept','show_dept','合成教研室负责人',None,'d1','role-dept'),
 ('college','show_college','合成学院负责人',None,'c1','role-college'),
]
ORG_SPEC=[('c1','YS-C1','智能制造学院（合成）','college','school'),
 ('c2','YS-C2','现代服务学院（合成）','college','school'),
 ('d1','YS-D1','机电技术教研室（合成）','dept','c1'),
 ('d2','YS-D2','智能控制教研室（合成）','dept','c1'),
 ('d3','YS-D3','现代服务教研室（合成）','dept','c2')]
CATALOG=[('YS-P1','智能制造能力提升（合成）','YS-C01','工业安全（合成）','YS-B01','工业安全一班（合成）'),
 ('YS-P1','智能制造能力提升（合成）','YS-C02','设备维护（合成）','YS-B02','设备维护一班（合成）'),
 ('YS-P2','数字办公技能（合成）','YS-C03','数据整理（合成）','YS-B03','数字办公一班（合成）'),
 ('YS-P3','服务能力提升（合成）','YS-C04','服务沟通（合成）','YS-B04','服务沟通一班（合成）')]
RECORD_HEADERS=['来源唯一编号','教师工号','业务日期','项目编码','项目名称','课程编码','课程名称','班级编码','班级名称','授课学时','课程人次','归属培训收入','数据来源']
def record_spec():
    out=[]
    roles=['teacher']*22+['teacher2']*2+['teacher3']*2+['other']*2+['teacher5','teacher6']
    for i,role in enumerate(roles):
        p,pn,c,cn,b,bn=CATALOG[i%4]
        out.append({'key':f'record-{i+1:03}','role':role,'external_key':f'YS-2026-{i+1:03}',
          'event_date':f'{YEAR}-{i%6+1:02}-{i%20+1:02}','project_code':p,'project':pn,'course_code':c,'course':cn,
          'class_code':b,'class_name':bn,'hours':str(i%4+2),'participants':10+i,'income':str(500+i*100),
          'source':'经核对人工录入'})
    for i in range(3):
        p,pn,c,cn,b,bn=CATALOG[0]
        out.append({'key':f'old-record-{i}','role':'teacher','external_key':f'YS-2025-{i+1:03}',
          'event_date':f'{YEAR-1}-06-{i+1:02}','project_code':p,'project':pn,'course_code':c,'course':cn,
          'class_code':b,'class_name':bn,'hours':'5','participants':12,'income':'1200','source':'经核对人工录入'})
    return out

def excel_rows(valid=True):
    rows=[]
    for i in range(2):
        p,pn,c,cn,b,bn=CATALOG[i]
        rows.append([f'YS-EXCEL-{i+1:03}','YS001' if valid or i==0 else 'YS-NOT-EXIST',
            '2026-09-01',p,pn,c,cn,b,bn,3,20,800,'Excel导入'])
    return rows

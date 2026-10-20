"""学校码表（代码对照）：学校给的代码 -> 中文名称，管理员粘贴导入，页面按它把代码翻成中文。

Kept in one settings row, so importing a school code table needs no schema change.
在职状态 (hr_status) rows also say whether the code counts as 在职; the 教职工 inbound
derives `active` from it when the data hub sends a status code instead of a yes/no flag.
"""
from fastapi import HTTPException
from .models import Setting

SETTING_KEY='code_tables'
TYPES={
    'hr_status':'在职状态（当前状态码）','staff_type':'教职工类别','edu':'学历','degree':'学位','gender':'性别',
    'unit':'单位编号与名称','nature':'课程性质','category':'课程类别','attribute':'课程属性',
    'group':'课程大类','teach_mode':'授课方式','exam_mode':'考核方式',
}
MAX_ROWS=2000
YES={'是','在职','1','true','TRUE','Y','y'}
NO={'否','不在职','0','false','FALSE','N','n',''}


def tables(db):
    row=db.get(Setting,SETTING_KEY)
    value=row.value if row and isinstance(row.value,dict) else {}
    return {k:v for k,v in (value.get('tables') or {}).items() if k in TYPES}


def parse_rows(code_type,text):
    """Excel 复制的两列（代码、名称），在职状态可多一列“是否在职”。返回 {代码: {label, active?}}。"""
    if code_type not in TYPES:raise HTTPException(422,'码表类型无效')
    if not isinstance(text,str) or not text.strip():raise HTTPException(422,'请粘贴码表内容')
    out={};errors=[]
    lines=[x for x in text.replace('\r\n','\n').replace('\r','\n').split('\n') if x.strip()]
    if len(lines)>MAX_ROWS:raise HTTPException(422,f'一次最多导入 {MAX_ROWS} 行')
    for no,line in enumerate(lines,1):
        cells=[c.strip() for c in (line.split('\t') if '\t' in line else line.split(','))]
        code=cells[0] if cells else '';label=cells[1] if len(cells)>1 else ''
        if no==1 and not any(ch.isdigit() for ch in code) and code in {'代码','编码','码','code','CODE','DM'}:continue  # header row
        if not code or not label:errors.append(f'第 {no} 行缺代码或名称');continue
        if len(code)>64 or len(label)>100:errors.append(f'第 {no} 行太长');continue
        if code in out:errors.append(f'第 {no} 行代码 {code} 重复');continue
        item={'label':label}
        if code_type=='hr_status':
            flag=cells[2] if len(cells)>2 else ''
            if flag not in YES|NO:errors.append(f'第 {no} 行第三列应填“是”或“否”（是否算在职）');continue
            item['active']=flag in YES
        out[code]=item
    if errors:raise HTTPException(422,'；'.join(errors[:10])+('…' if len(errors)>10 else ''))
    if not out:raise HTTPException(422,'没有可导入的行')
    if code_type=='hr_status' and not any(x['active'] for x in out.values()):
        raise HTTPException(422,'在职状态码表里至少要有一个代码第三列填“是”')
    return out


def derive_hr_active(db,mapped,cache=None):
    """教职工 rows that carry 当前状态码 (hr_status_code) and no yes/no flag get `active` from the 在职状态 code table.

    Returns an error message when the code cannot be decided; never guesses.
    """
    if 'active' in mapped or mapped.get('hr_status_code') in (None,''):return None
    status=(cache if cache is not None else tables(db)).get('hr_status')
    if not status:return '在职状态码表还没导入，不能判断是否在职（到“系统管理 › 系统对接 › 代码对照”导入）'
    code=str(mapped['hr_status_code']).strip()
    if code not in status:return f'在职状态码 {code} 不在学校码表里'
    mapped['active']=bool(status[code].get('active'))
    return None

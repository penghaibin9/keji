"""Four roles, explicit permissions; an administrator is not a scope bypass."""
TEACHER = frozenset({'portal.read','records.read','qualification.read','qualification.write',
 'points.read','assessment.read','assessment.confirm','dispute.write','file.read','file.write',
 'notice.read','organization.read','export'})
DEPT = TEACHER | {'qualification.review','assessment.review','dispute.resolve','records.write','import'}
COLLEGE = DEPT
SCHOOL = COLLEGE | {'points.calculate','points.adjust','assessment.calculate','assessment.archive',
 'notice.manage','organization.manage','users.manage','roles.manage','settings.manage','rules.manage',
 'sync.manage','audit.read','operations.read','data.export'}
ALLOWED = {'teacher':TEACHER,'dept':DEPT,'college':COLLEGE,'school':SCHOOL}
# 系统管理权限：带任何一项的学校角色只能作为主身份（系统管理员），不能兼任。
SYSTEM_PERMISSIONS = frozenset({'organization.manage','users.manage','roles.manage','settings.manage','rules.manage',
 'sync.manage','audit.read','operations.read','notice.manage'})
# 学校业务审核：学校级审批职责的承担人员用，只办业务、不碰系统管理和批量计算。
SCHOOL_REVIEW = SCHOOL - SYSTEM_PERMISSIONS - {'points.calculate','points.adjust','assessment.calculate','assessment.archive','data.export'}

def validate_permissions(kind, permissions):
    if kind not in ALLOWED or not isinstance(permissions,list) or not all(isinstance(x,str) for x in permissions):
        return False
    return len(permissions)==len(set(permissions)) and set(permissions)<=ALLOWED[kind]

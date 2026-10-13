"""R2 input contracts derived from the preserved frontend and relational model."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator, StringConstraints

Text = Annotated[str,Field(min_length=1,max_length=160)]
Ident = Annotated[str,Field(min_length=1,max_length=64,pattern=r'^[A-Za-z0-9_\-]+$')]
PasswordText = Annotated[str,StringConstraints(strip_whitespace=False,min_length=12,max_length=256)]
Money = Annotated[Decimal,Field(max_digits=18,decimal_places=2,allow_inf_nan=False)]
class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True,str_strip_whitespace=True)
class Reason(Input):
    reason: str = Field(min_length=2,max_length=2000)
    basis: str = Field(default='',max_length=2000)
class VersionedReason(Reason):
    expected_version: int = Field(ge=1)
class Action(Reason):
    expected_version: int = Field(ge=1)
    action: str = Field(min_length=1,max_length=32)
class Login(Input):
    username: str = Field(min_length=1,max_length=64)
    password: str = Field(min_length=1,max_length=256,repr=False)
    @field_validator('password',mode='before')
    @classmethod
    def password_no_strip(cls,v):
        # Password whitespace is not normalized. Model-wide strip is disabled
        # below for password-bearing inputs.
        return v
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True,str_strip_whitespace=False)
class Password(Input):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True,str_strip_whitespace=False)
    old_password: str = Field(min_length=1,max_length=256,repr=False)
    new_password: PasswordText = Field(repr=False)
class ResetPassword(Reason):
    password: PasswordText = Field(repr=False)
    expected_version: int = Field(ge=1)
class OrgIn(Reason):
    code: Ident
    name: str = Field(min_length=1,max_length=120)
    kind: Literal['college','dept']
    parent_id: Ident
class OrgUpdate(Reason):
    name: str = Field(min_length=1,max_length=120)
    parent_id: Ident|None=None
    expected_version: int = Field(ge=1)
class UserIn(Reason):
    username: Ident
    staff_no: Ident|None=None
    name: str = Field(min_length=1,max_length=100)
    title: str = Field(default='',max_length=80)
    org_id: Ident
    role_id: Ident
    password: PasswordText = Field(repr=False)
class IdentityIn(Input):
    role_id: Ident
    org_id: Ident
    # 临时兼任（例如负责人出差、休假期间由他人代办）：到期日当天仍有效，之后自动失效。不填表示长期。
    valid_until: str|None=Field(default=None,max_length=10)
class UserUpdate(Reason):
    name: str = Field(min_length=1,max_length=100)
    title: str = Field(default='',max_length=80)
    org_id: Ident
    role_id: Ident
    active: bool
    is_admin: bool=False
    expected_version: int=Field(ge=1)
    # 兼任身份；不传表示不改。主身份仍是 org_id + role_id。
    extra_identities: list[IdentityIn]|None=Field(default=None,max_length=6)
class OrgHeadIn(Reason):
    user_id: Ident
    valid_until: str|None=Field(default=None,max_length=10)
class RoleCopy(Reason):
    code: Ident
    name: str = Field(min_length=1,max_length=100)
    copy_from: Ident
class RoleUpdate(Reason):
    permissions: list[str]=Field(max_length=100)
    active: bool
    expected_version: int=Field(ge=1)
class PeriodIn(Reason):
    name: str=Field(min_length=1,max_length=100)
    start_date: date
    end_date: date
    @model_validator(mode='after')
    def dates(self):
        if self.end_date<self.start_date: raise ValueError('结束日期不能早于开始日期')
        return self
class SettingUpdate(Reason):
    value: dict
    expected_version: int=Field(ge=1)
class SettingCreate(Reason):
    key: str=Field(min_length=6,max_length=48,pattern=r'^(dict|param):[a-z][a-z0-9_]{1,40}$')
    value: dict
class NoticeIn(Reason):
    title: str=Field(min_length=1,max_length=200)
    category: str=Field(min_length=1,max_length=40)
    org_id: Ident
    body: str=Field(min_length=1,max_length=20000)
    published: bool=True
class NoticeUpdate(NoticeIn):
    expected_version:int=Field(ge=1)
class RecordIn(Reason):
    external_key: str=Field(min_length=1,max_length=128)
    teacher_id: Ident
    event_date: date
    project_code: Ident
    project: Text
    course_code: Ident
    course: Text
    class_code: Ident
    class_name: Text
    hours: Decimal=Field(ge=0,max_digits=12,decimal_places=2,allow_inf_nan=False)
    participants: int=Field(ge=0,le=10000000)
    income: Money
    source: str=Field(default='经核对人工录入',min_length=1,max_length=100)
class RecordUpdate(RecordIn):
    expected_version:int=Field(ge=1)
class QualificationIn(Reason):
    teacher_id: Ident
    category: str=Field(min_length=1,max_length=80)
    name: Text
    certificate_no: str=Field(min_length=1,max_length=128)
    issuer: Text
    obtained: date
    expires: date|None=None
    @model_validator(mode='after')
    def dates(self):
        if self.expires and self.expires<self.obtained: raise ValueError('有效期不能早于取得日期')
        return self
class QualificationUpdate(QualificationIn):
    expected_version:int=Field(ge=1)
ScoreNumber = Annotated[Decimal,Field(ge=-1000000000000,le=1000000000000,allow_inf_nan=False,max_digits=18,decimal_places=4)]
class TierItem(Input):
    min: ScoreNumber
    value: ScoreNumber
class MethodFields(Input):
    # 10.1/9.1 optional extended scoring methods; absent => legacy formula unchanged.
    method: Literal['ratio','linear','tier','deduct','bonus']|None=None
    tiers: list[TierItem]|None=Field(default=None,max_length=20)
    tier_mode: Literal['score','multiplier']|None=None
    base: ScoreNumber|None=None
    unit: ScoreNumber|None=None
    per_unit: ScoreNumber|None=None
    floor: ScoreNumber|None=None
class Component(MethodFields):
    key: str=Field(pattern=r'^[a-z][a-z0-9_]{0,40}$')
    label: str=Field(min_length=1,max_length=100)
    source: Literal['hours','participants','income','qualifications','points','assessment_score','credits']
    factor: Decimal=Field(default=1,ge=0,le=1000000,allow_inf_nan=False,max_digits=16,decimal_places=4)
    weight: Decimal=Field(default=0,ge=0,le=100,allow_inf_nan=False,max_digits=7,decimal_places=2)
    target: Decimal=Field(default=1,gt=0,le=1000000000000,allow_inf_nan=False,max_digits=18,decimal_places=4)
    cap: Money|None=Field(default=None,ge=0)
class RuleConfig(Input):
    components:list[Component]=Field(min_length=1,max_length=30)
    @model_validator(mode='after')
    def unique(self):
        if len({c.key for c in self.components})!=len(self.components): raise ValueError('指标编码不能重复')
        return self
class RuleIn(Reason):
    kind:Literal['points','assessment']
    name:str=Field(min_length=1,max_length=100)
    period_id:Ident
    config:RuleConfig
    @model_validator(mode='after')
    def acyclic(self):
        if self.kind=='points' and any(c.source=='points' for c in self.config.components):
            raise ValueError('积分不能引用本期积分作为来源，防止循环累计')
        from .scoring_methods import normalize_method
        for c in self.config.components:normalize_method(c.model_dump(),self.kind)
        return self
class Trial(Input):
    teacher_ids:list[Ident]=Field(min_length=1,max_length=20)
class Calculate(Reason):
    period_id:Ident
    teacher_ids:list[Ident]=Field(min_length=1,max_length=200)
    item_keys:list[str]|None=None
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.teacher_ids))!=len(self.teacher_ids): raise ValueError('教师选择不能重复')
        if self.item_keys is not None and (not self.item_keys or len(set(self.item_keys))!=len(self.item_keys) or len(self.item_keys)>30):
            raise ValueError('积分项选择无效')
        return self
class PointAdjust(Reason):
    teacher_id:Ident
    period_id:Ident
    item_key:str=Field(pattern=r'^[a-z][a-z0-9_]{0,40}$')
    amount:Money
class ScoreAdjust(Reason):
    delta:Decimal=Field(ge=-100,le=100,max_digits=7,decimal_places=2,allow_inf_nan=False)
    expected_version:int=Field(ge=1)
class DisputeIn(Reason):
    object_type:Literal['record','points','assessment']
    object_id:Ident
class ResolveDispute(Reason):
    resolution:str=Field(min_length=2,max_length=2000)
    expected_version:int=Field(ge=1)

class OrgAssessmentComponent(MethodFields):
    key: str=Field(pattern=r'^[a-z][a-z0-9_]{0,40}$')
    label: str=Field(min_length=1,max_length=100)
    source: Literal['hours','participants','income','teachers','projects','courses','qualifications','points','assessment_score']
    weight: Decimal=Field(ge=0,le=100,max_digits=7,decimal_places=2,allow_inf_nan=False)
    target: Decimal=Field(gt=0,le=1000000000000,max_digits=18,decimal_places=4,allow_inf_nan=False)
    cap: Decimal|None=Field(default=None,ge=0,le=100,max_digits=7,decimal_places=2,allow_inf_nan=False)
class OrgAssessmentRuleConfig(Input):
    components:list[OrgAssessmentComponent]=Field(min_length=1,max_length=30)
    @model_validator(mode='after')
    def validate_items(self):
        if len({x.key for x in self.components})!=len(self.components):raise ValueError('组织考核指标编码不能重复')
        if sum((x.weight for x in self.components),Decimal(0))!=Decimal(100):raise ValueError('组织考核权重总和必须为100')
        return self
class OrgAssessmentRuleIn(Reason):
    target_kind:Literal['dept','college','school']
    name:str=Field(min_length=1,max_length=100)
    period_id:Ident
    config:OrgAssessmentRuleConfig
class RuleCopy(VersionedReason):
    name:str=Field(min_length=1,max_length=100)
    period_id:Ident
    config:RuleConfig|None=None
class OrgRuleCopy(VersionedReason):
    name:str=Field(min_length=1,max_length=100)
    period_id:Ident
    config:OrgAssessmentRuleConfig|None=None
class OrgRuleTrial(Input):
    target_ids:list[Ident]=Field(min_length=1,max_length=20)
class OrgAssessmentCalculate(Reason):
    period_id:Ident
    target_kind:Literal['dept','college','school']
    target_ids:list[Ident]=Field(min_length=1,max_length=200)
    @model_validator(mode='after')
    def unique_targets(self):
        if len(set(self.target_ids))!=len(self.target_ids):raise ValueError('组织选择不能重复')
        return self

class ConnectionUpdate(Reason):
    mappings:list[dict]=Field(max_length=300)
    config:dict
    expected_version:int=Field(ge=1)
class IntegrationProfileItem(Input):
    mappings:list[dict]=Field(max_length=300)
    config:dict
    expected_version:int=Field(ge=1)
class IntegrationProfileApply(Reason):
    format: Literal['YUEKE_R11_THREE_INTEGRATIONS_V2']
    connections: dict[str,IntegrationProfileItem]
class MappingValidate(Reason):
    connection_id:Ident
    data_type:str=Field(min_length=1,max_length=64)
    records:list[dict]=Field(min_length=1,max_length=100)
class SyncEnqueue(Reason):
    data_type:str=Field(min_length=1,max_length=64)
    records:list[dict]=Field(min_length=1,max_length=1000)
class LedgerSync(Reason):
    # 11.3 assemble province records from the local ledger (no pasted JSON).
    data_type:str=Field(min_length=1,max_length=64)
    start:str|None=Field(default=None,max_length=10)
    end:str|None=Field(default=None,max_length=10)
    period_id:Ident|None=None
    org_id:Ident|None=None
    expected_count:int|None=Field(default=None,ge=0)
class TaskRetry(Reason):
    expected_version:int=Field(ge=1)

class ExportRequest(Input):
    kind: Literal['records','participations','qualifications','points','assessments','organization_assessments','audit','handover']
    filters: dict = Field(default_factory=dict)
    confirmed: bool=False

class ParticipationIn(Reason):
    external_key: str=Field(min_length=1,max_length=128)
    teacher_id: Ident
    event_date: date
    project_code: Ident
    project: Text
    course_code: Ident
    course: Text
    hours: Decimal=Field(ge=0,max_digits=12,decimal_places=2,allow_inf_nan=False)
    source: str=Field(default='经核对人工录入',min_length=1,max_length=100)
class ParticipationUpdate(ParticipationIn):
    expected_version:int=Field(ge=1)

class InboundPreview(Reason):
    data_type: Literal['teacher_hr','training_project','course','training_income','course_participants','teacher_course','online_course','school_course']
    records: list[dict]=Field(min_length=1,max_length=1000)
    source_label: str=Field(default='手工脱敏联调样本',min_length=1,max_length=160)

class InboundPullRequest(Reason):
    data_type: Literal['teacher_hr','training_project','course','training_income','course_participants','teacher_course','online_course','school_course']
    mode: Literal['FULL','INCREMENTAL']

class IntegrationScheduleIn(Reason):
    connection_id: Ident
    data_type: Literal['teacher_hr','training_project','course','training_income','course_participants','teacher_course','online_course','school_course']
    frequency_minutes: int=Field(ge=1,le=10080)
    auto_commit: bool=False
    active: bool=False

class IntegrationScheduleUpdate(Reason):
    frequency_minutes: int=Field(ge=1,le=10080)
    auto_commit: bool=False
    active: bool=False
    expected_version: int=Field(ge=1)

class CreditReviewIn(Input):
    """教研室主任认定授课：一次认定或不计一批课程（教务、超星同步来的授课记录）。"""
    ids: list[Ident] = Field(min_length=1,max_length=200)
    decision: Literal['approve','exclude','reset']
    reason: str = Field(default='',max_length=500)

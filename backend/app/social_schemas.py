"""Validated school policy inputs. Missing decisions are never replaced by defaults."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, model_validator, HttpUrl
from .schemas import Input, Reason, Ident

Text = Annotated[str, Field(min_length=1, max_length=200)]
Code = Annotated[str, Field(min_length=1, max_length=64)]
Name = Annotated[str, Field(min_length=1, max_length=160)]
Nonnegative = Annotated[Decimal, Field(ge=0, le=1000000000000, max_digits=18, decimal_places=4, allow_inf_nan=False)]


class ProjectData(Input):
    code: Code
    name: Name
    cohort: Code
    org_id: Ident
    owner_id: Ident
    category: Literal['subsidy', 'enterprise', 'community', 'rural', 'other']
    high_risk: bool = False
    expected_income: Nonnegative
    expected_participants: int = Field(ge=0, le=10000000)
    expected_outcomes: Text
    start_date: date
    end_date: date
    mode: Literal['module', 'person_day']
    class_type: Literal['technical', 'lecture']
    level: Literal['province', 'city', 'school']
    level_basis: str = Field(default='', max_length=1000)
    scene: Literal['dispatched', 'full_day', 'ordinary']
    target_groups: str = Field(default='', max_length=1000)
    auxiliary_standard: str = Field(default='', max_length=2000)
    auxiliary_daily_cap: Nonnegative | None = None
    dates_confirmed: bool = False
    level_confirmed: bool = False
    scene_confirmed: bool = False
    mode_confirmed: bool = False
    @model_validator(mode='after')
    def valid_dates(self):
        if self.end_date < self.start_date: raise ValueError('结束日期不能早于开始日期')
        if self.category == 'subsidy' and not self.target_groups.strip(): raise ValueError('补贴项目须说明重点群体和行动对接内容')
        return self


class ProjectIn(Reason):
    data: ProjectData
    expected_version: int | None = Field(default=None, ge=1)


class Learner(Input):
    reference: Text
    full_time_student: bool = False
    graduate_exception: bool = False
    signed: bool
    hours_met: bool
    full_attendance: bool
    passed: bool
    priority_group: bool = False
    exclusion_reason: str = Field(default='', max_length=500)


class TeacherWork(Input):
    teacher_id: Ident
    staff_type: Literal['internal', 'external']
    role: Literal['lecturer', 'instructor', 'manager']


class UnitData(Input):
    external_key: str = Field(min_length=1,max_length=128)
    course_code: Code
    class_code: Code
    module: Text
    event_date: date
    mode: Literal['module', 'person_day']
    learners: list[Learner] = Field(min_length=1, max_length=1000)
    teachers: list[TeacherWork] = Field(min_length=1, max_length=50)
    evidence_note: Text
    @model_validator(mode='after')
    def no_duplicates(self):
        if len({v.reference for v in self.learners}) != len(self.learners): raise ValueError('同一核算单元的学员编号不能重复')
        if len({v.teacher_id for v in self.teachers}) != len(self.teachers): raise ValueError('同一核算单元的教师不能重复')
        return self


class UnitsIn(Reason):
    expected_version: int = Field(ge=1)
    rows: list[UnitData] = Field(min_length=1, max_length=100)
    preview_hash: str | None = None


class Closeout(Input):
    closed_on: date
    outcome_report: Text
    satisfaction: Decimal = Field(ge=0, le=100, allow_inf_nan=False)
    province_receipt: str = Field(default='', max_length=500)
    special_evidence: str = Field(default='', max_length=2000)
    actual_income: Nonnegative
    finance_reference: Text
    settlement_on: date | None = None
    implicit_cost: Nonnegative = Decimal(0)
    location: Literal['onsite', 'offsite']
    rectification: str = Field(default='', max_length=2000)
    rectification_due: date | None = None
    materials_checked: list[Literal['plan','filing_form','roster','attendance','hours','process','assessment','outcomes']] = Field(default_factory=list,max_length=8)
    retained: Nonnegative | None = None
    personnel: Nonnegative | None = None
    funding_source: Literal['other_training','government_special'] | None = None
    funding_basis: str = Field(default='',max_length=2000)
    @model_validator(mode='after')
    def distribution(self):
        # 管理办法第二十一条：校外办学校留存不低于10%、人员支出不高于70%；校内办学校留存不低于20%、人员支出不高于60%；项目公用为20%。
        if self.retained is None and self.personnel is None: return self
        if self.retained is None or self.personnel is None: raise ValueError('收入分配须同时填写学校留存和人员支出')
        income = self.actual_income
        if self.retained+self.personnel>income:raise ValueError('学校留存与人员支出合计不能超过到账收入')
        if self.funding_source=='government_special':return self
        low, high = (Decimal('0.2'), Decimal('0.6')) if self.location == 'onsite' else (Decimal('0.1'), Decimal('0.7'))
        public = income - self.retained - self.personnel
        if self.retained < income * low: raise ValueError(f'学校留存不能低于收入的{int(low*100)}%（{(income*low).quantize(Decimal("0.01"))} 元）')
        if self.personnel > income * high: raise ValueError(f'人员支出不能高于收入的{int(high*100)}%（{(income*high).quantize(Decimal("0.01"))} 元）')
        if abs(public - income * Decimal('0.2')) > Decimal('0.01'): raise ValueError(f'项目公用须为收入的20%（{(income*Decimal("0.2")).quantize(Decimal("0.01"))} 元），现在是 {public.quantize(Decimal("0.01"))} 元')
        return self


class SocialAction(Reason):
    expected_version: int = Field(ge=1)
    action: str = Field(min_length=1, max_length=40)
    closeout: Closeout | None = None
    prior_review_on: date | None = None


class PolicyData(Input):
    cap_mode: Literal['ratio_cap', 'over_standard_two'] | None = None
    person_day_unit: Literal['daily', 'whole_project'] | None = None
    precision: Literal[2] | None = None
    rounding: Literal['half_up'] | None = None
    step_mode: Literal['proportional', 'full_steps'] | None = None
    annual_model: Literal['four_indicators'] | None = None
    bonus_pool: Literal['all_bonus_shared_ten'] | None = None
    total_cap: Nonnegative | None = None
    grade_mode: Literal['three', 'four'] | None = None
    excellent_from: Nonnegative | None = None
    qualified_from: Nonnegative | None = None
    satisfaction_inclusive: bool | None = None
    achievement_dedup: Literal['highest_per_reference'] | None = None
    auxiliary_overlap: Literal['exclusive'] | None = None
    title_scope: Literal['teaching', 'all'] | None = None
    title_precision: Literal[0,1,2,3,4] | None = None
    title_rounding: Literal['half_up'] | None = None
    resubmission_mode: Literal['original_submission','resubmission_date'] | None = None
    organization_basis: Literal['project_units'] | None = None
    effective_date: date | None = None
    date_basis: Literal['closeout'] | None = None
    calendar_start: date | None = None
    calendar_end: date | None = None
    holidays: list[date] = Field(default_factory=list, max_length=400)
    workdays: list[date] = Field(default_factory=list, max_length=400)
    calendar_reference: str = Field(default='', max_length=500)
    interpretation_reference: str = Field(default='', max_length=2000)
    @model_validator(mode='after')
    def calendar(self):
        if set(self.holidays) & set(self.workdays): raise ValueError('同一天不能同时标为放假和补班')
        if self.calendar_start and self.calendar_end and self.calendar_end < self.calendar_start: raise ValueError('校历结束日期错误')
        if self.excellent_from is not None and self.qualified_from is not None and self.excellent_from <= self.qualified_from: raise ValueError('优秀门槛必须高于合格门槛')
        return self


class PolicyIn(Reason):
    period_id: Ident
    name: str = Field(min_length=1,max_length=100)
    data: PolicyData


class RecommendedPolicyIn(Reason):
    period_id: Ident


class Auxiliary(Input):
    work_date: date
    amount: Nonnegative
    description: Text


class ClaimIn(Reason):
    expected_version: int | None = Field(default=None, ge=1)
    project_id: Ident
    period_id: Ident
    policy_id: Ident
    recognition_form_reference: str = Field(default='',max_length=500)
    auxiliary: list[Auxiliary] = Field(default_factory=list, max_length=366)


class Achievement(Input):
    reference: Text
    name: Text
    level: Literal['national', 'province', 'school']
    confirmed_on: date | None = None
    recognition_reference: str = Field(default='',max_length=2000)


class AnnualData(Input):
    income_target: Nonnegative | None = None
    participants_target: int | None = Field(default=None, gt=0)
    priority_target: int | None = Field(default=None, gt=0)
    target_reference: str = Field(default='', max_length=1000)
    staff_denominator: int | None = Field(default=None, gt=0)
    staff_basis: str = Field(default='', max_length=1000)
    achievements: list[Achievement] = Field(default_factory=list, max_length=500)
    compliance_failures: int = Field(default=0, ge=0, le=1000)
    compliance_scope: Literal['other_only'] | None = None
    confirmed_veto: bool = False
    discipline_reference: str = Field(default='', max_length=1000)
    other_bonus: Decimal = Field(default=0, ge=0, le=10, allow_inf_nan=False)
    other_bonus_basis: str = Field(default='', max_length=1000)
    self_report: Text


class AnnualIn(Reason):
    expected_version: int | None = Field(default=None, ge=1)
    org_id: Ident
    period_id: Ident
    policy_id: Ident
    data: AnnualData


class ResourceIn(Reason):
    kind: Literal['base', 'achievement', 'course_resource']
    org_id: Ident
    code: Code
    name: Name
    location: str = Field(default='', max_length=500)
    onsite: bool = True
    recognition: Text
    level: Literal['national', 'province', 'school'] = 'school'
    course_code: str = Field(default='', max_length=64)
    resource_type: Literal['video','document','link'] = 'document'
    resource_url: HttpUrl | None = None
    duration_minutes: Nonnegative | None = None
    confirmed_on: date | None = None
    teacher_id: Ident | None = None
    teacher: str = Field(default='',max_length=200)
    @model_validator(mode='after')
    def course_resource(self):
        if self.kind=='course_resource' and not self.course_code:raise ValueError('课程资源须关联课程')
        if self.kind=='course_resource' and self.resource_type=='video' and self.duration_minutes is None:raise ValueError('视频须登记资源总时长（分钟）')
        return self


class ResourceUpdate(ResourceIn):
    expected_version: int = Field(ge=1)


class DutiesIn(Reason):
    expected_version: int = Field(ge=0)
    assignments: dict[str, list[Ident]]
    @model_validator(mode='after')
    def known_duties(self):
        allowed = {'dean', 'coordinator', 'vice_president', 'secretary', 'finance', 'academic', 'discipline', 'committee'}
        if set(self.assignments) - allowed or any(len(v) > 100 or len(v) != len(set(v)) for v in self.assignments.values()): raise ValueError('职责名称或人员列表无效')
        return self


class CourseIn(Reason):
    code: Code
    name: Name
    project_code: Code


class CourseImportRow(CourseIn):
    source: Literal['manual', 'chaoxing'] = 'manual'
    teacher: str = Field(default='', max_length=200)
    teacher_id: Ident | None = None
    video_count: int | None = Field(default=None, ge=0, le=100000)
    video_minutes: Nonnegative | None = None
    chapters: int | None = Field(default=None, ge=0, le=100000)
    learners: int | None = Field(default=None, ge=0, le=10000000)
    @model_validator(mode='after')
    def video_totals(self):
        if self.video_count and self.video_minutes is None: raise ValueError('登记视频数时须同时提供视频总时长（分钟）')
        return self


class CourseBatchIn(Reason):
    rows: list[CourseImportRow] = Field(min_length=1, max_length=200)
    preview_hash: str | None = None


class PointReviewIn(Reason):
    # 教研室/学院发现已归档积分有误时发起核对；reason 写明哪里不对，teaching/auxiliary 为建议更正的差额。
    claim_id: Ident
    period_id: Ident
    teaching: Decimal = Field(max_digits=18, decimal_places=2, allow_inf_nan=False)
    auxiliary: Decimal = Field(max_digits=18, decimal_places=2, allow_inf_nan=False)
    @model_validator(mode='after')
    def nonzero(self):
        if not self.teaching and not self.auxiliary:raise ValueError('建议更正分值不能同时为零')
        return self


class CorrectionIn(Reason):
    expected_version: int | None = Field(default=None, ge=1)
    claim_id: Ident
    period_id: Ident
    teaching: Decimal = Field(max_digits=18, decimal_places=2, allow_inf_nan=False)
    auxiliary: Decimal = Field(max_digits=18, decimal_places=2, allow_inf_nan=False)
    decision_reference: Text
    @model_validator(mode='after')
    def nonzero(self):
        if not self.teaching and not self.auxiliary:raise ValueError('更正分值不能同时为零')
        return self


class ReportIn(Reason):
    org_id: Ident
    policy_id: Ident
    year: int = Field(ge=2000,le=2200)
    start_month: int = Field(ge=1,le=12)
    end_month: int = Field(ge=1,le=12)
    @model_validator(mode='after')
    def window(self):
        if (self.start_month,self.end_month)!=(1,12) and not (self.start_month%2==1 and self.end_month==self.start_month+1):raise ValueError('请选择完整双月或全年')
        return self


class CaseNoteIn(Reason):
    expected_version: int = Field(ge=1)
    kind: Literal['complaint','rectification','settlement','violation']
    received_on: date
    investigation_on: date | None = None
    completed_on: date | None = None
    major: bool = False
    reply: str = Field(default='', max_length=2000)
    policy_id: Ident
    case_reference: Code
    due_on: date | None = None
    invalidate_cohort: bool = False
    annual_veto: bool = False
    settlement_result: Literal['noncompliant', 'exempt'] | None = None
    @model_validator(mode='after')
    def sequence(self):
        if self.investigation_on and self.investigation_on < self.received_on:raise ValueError('调查日期不能早于受理日期')
        if self.completed_on and self.completed_on < (self.investigation_on or self.received_on):raise ValueError('办结日期不能早于受理或调查日期')
        if (self.invalidate_cohort or self.annual_veto) and (self.kind!='violation' or not self.basis):raise ValueError('人次作废及否决须依据正式处理决定')
        if self.kind=='violation' and not self.basis:raise ValueError('登记或更正正式处理结论必须填写书面依据')
        if self.settlement_result and (self.kind!='settlement' or not self.basis):raise ValueError('结算核验结论仅用于结算事项，须填写财务认定或例外批准依据')
        return self

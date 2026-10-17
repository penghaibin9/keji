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


# 立德树人与质量（上级 1.2 立德树人表要的数，申报向导第 4 步）。老项目没有这一块，结项后由学院补填。
IDEOLOGY_MODES = {'ideology_course':'开设思政专题课','course_ideology':'课程思政融入专业教学','practice':'思政实践教学（参观、基地实践）','lecture':'专题讲座、报告','none':'未开展'}
REVIEW_KEYS = ('teacher_review','courseware_review')


# 上级项目表（服务面向类型、教学实施方式）的选项。
SERVICE_TYPES = {'national':'国家战略','regional':'区域发展','industry':'行业发展','other':'其他'}
TEACHING_METHODS = {'classroom':'课堂教学','case':'案例教学','onsite':'现场教学','field':'实地考察','seminar':'交流研讨','lab':'实验实训','internship':'岗位实习','peer':'学习者互助','other':'其他'}


class ProjectBase(Input):
    # 本项目设立的思政实践教学基地，随项目备案一并生效，不另走基地申请。
    name: Name
    location: str = Field(default='', max_length=500)
    onsite: bool = True
    partner: str = Field(default='', max_length=200)
    established_on: date | None = None
    @model_validator(mode='after')
    def partner_required(self):
        if not self.onsite and not self.partner.strip(): raise ValueError('校外基地请填写共建单位')
        return self


class ProjectVenue(Input):
    # 培训场地：校内基地、其他校内场所、校外。校外须附一事一议记录（外地点、理由、议定文号或会议日期）。
    type: Literal['base','campus','offsite']
    place: str = Field(min_length=1, max_length=200)
    offsite_reason: str = Field(default='', max_length=1000)
    offsite_ref: str = Field(default='', max_length=200)
    @model_validator(mode='after')
    def offsite_record(self):
        if self.type == 'offsite' and not (self.offsite_reason.strip() and self.offsite_ref.strip()):
            raise ValueError('校外培训须登记一事一议：外出理由、议定文号或会议日期')
        return self


class ReviewRecord(Input):
    checked: bool = False
    signer: str = Field(default='', max_length=100)
    reviewed_on: date | None = None
    reference: str = Field(default='', max_length=200)
    percent: int | None = Field(default=None, ge=0, le=100)  # 审查覆盖百分比，上级 1.2 表直接要这个数


class ProjectQuality(Input):
    ideology_modes: list[Literal['ideology_course','course_ideology','practice','lecture','none']] = Field(default_factory=list, max_length=5)
    ideology_hours: Nonnegative | None = None
    bases: list[ProjectBase] = Field(default_factory=list, max_length=20)
    # 主讲教师资格审查：用政审表，学院签字；课件内容审查：学院审。
    teacher_review: ReviewRecord = Field(default_factory=ReviewRecord)
    courseware_review: ReviewRecord = Field(default_factory=ReviewRecord)
    @model_validator(mode='after')
    def consistent(self):
        if 'none' in self.ideology_modes and len(self.ideology_modes) > 1: raise ValueError('选了“未开展”就不能再选其他思政实施方式')
        for key, label in (('teacher_review','主讲教师资格审查'),('courseware_review','课件内容审查')):
            r = getattr(self, key)
        return self


def review_done(r):
    """审查已登记：填了百分比，或老数据里学院已勾选。"""
    r = r or {}
    return r.get('percent') is not None or bool(r.get('checked'))


def review_percent(r):
    r = r or {}
    return r['percent'] if r.get('percent') is not None else (100 if r.get('checked') else 0)


def application_blockers(data):
    """申报提交学院前必须有的：总学时、受众群体。思政实施情况由学院之后补填，不拦申报。"""
    out = []
    if not (data or {}).get('total_hours'): out.append('请填写总学时')
    if not (data or {}).get('audiences') and not str((data or {}).get('audience_other') or '').strip(): out.append('请选择受众群体')
    if not (data or {}).get('service_types'): out.append('请选择服务面向类型')
    if not (data or {}).get('teaching_methods'): out.append('请选择教学实施方式')
    return out


def quality_blockers(data):
    """提交前检查第 4 步：思政实施方式、思政学时、两项审查。返回缺项说明。"""
    q = (data or {}).get('quality') or {}
    out = []
    if not q.get('ideology_modes'): out.append('请选择大思政课实施方式')
    elif q.get('ideology_modes') != ['none'] and q.get('ideology_hours') in (None, ''): out.append('请填写思政课学时')
    if not review_done(q.get('teacher_review')): out.append('请填写对主讲教师进行资格审查的百分比')
    if not review_done(q.get('courseware_review')): out.append('请填写对课件内容进行审查的百分比')
    if not (data or {}).get('total_hours'): out.append('请填写总学时')
    if not (data or {}).get('audiences') and not str((data or {}).get('audience_other') or '').strip(): out.append('请选择受众群体')
    return out


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
    total_hours: Nonnegative | None = None
    audiences: list[str] = Field(default_factory=list, max_length=12)
    audience_other: str = Field(default='', max_length=200)
    service_types: list[Literal['national','regional','industry','other']] = Field(default_factory=list, max_length=4)
    teaching_methods: list[Literal['classroom','case','onsite','field','seminar','lab','internship','peer','other']] = Field(default_factory=list, max_length=9)
    video_minutes: Nonnegative | None = None
    base_count: int | None = Field(default=None, ge=0, le=1000)
    quality: ProjectQuality | None = None
    venue: ProjectVenue | None = None
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
    materials_checked: list[Literal['plan','filing_form','roster','attendance','hours','process','assessment','outcomes','teacher_review','courseware_review']] = Field(default_factory=list,max_length=10)
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


class PolicyUpdate(PolicyIn):
    expected_version: int = Field(ge=1)


class RecommendedPolicyIn(Reason):
    period_id: Ident


class PolicyCalendarIn(Reason):
    expected_version: int = Field(ge=1)
    calendar_start: date
    calendar_end: date
    calendar_reference: str = Field(min_length=2, max_length=500)
    holidays: list[date] = Field(default_factory=list, max_length=400)
    workdays: list[date] = Field(default_factory=list, max_length=400)

    @model_validator(mode='after')
    def valid_calendar(self):
        if not self.calendar_reference.strip(): raise ValueError('学校工作日历依据必填')
        if self.calendar_end < self.calendar_start: raise ValueError('校历结束日期错误')
        if set(self.holidays) & set(self.workdays): raise ValueError('同一天不能同时标为放假和补班')
        if any(not self.calendar_start <= d <= self.calendar_end for d in self.holidays + self.workdays):
            raise ValueError('放假和补班日期必须位于校历期间内')
        return self


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
    # 培训基地：用途（实践教学 / 思政实践教学）、设立日期、共建单位。
    usages: list[Literal['practice', 'ideology']] = Field(default_factory=list, max_length=2)
    established_on: date | None = None
    partner: str = Field(default='', max_length=200)
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
        allowed = {'dean', 'coordinator', 'vice_president', 'secretary', 'finance', 'academic', 'discipline', 'committee', 'trainer_hr', 'trainer_filing'}
        if set(self.assignments) - allowed or any(len(v) > 100 or len(v) != len(set(v)) for v in self.assignments.values()): raise ValueError('职责名称或人员列表无效')
        return self


class CoursewareReview(Input):
    checked: bool = False
    reviewer: str = Field(default='', max_length=100)
    reviewed_on: date | None = None
    reference: str = Field(default='', max_length=200)
    percent: int | None = Field(default=None, ge=0, le=100)  # 审查覆盖百分比，上级 1.2 表直接要这个数


class CourseIn(Reason):
    code: Code
    name: Name
    project_code: Code
    # 培训课程五项：学时、教学方式、思政属性、主讲教师、课件审查（学校直接登记或批量导入时填写，存在课程资料记录里）。
    hours: Nonnegative | None = None
    teaching_mode: Literal['lecture', 'practice', 'case', 'onsite', 'online'] | None = None
    ideology: Literal['ideology_course', 'course_ideology', 'none'] | None = None
    teacher: str = Field(default='', max_length=200)
    teacher_id: Ident | None = None
    courseware: CoursewareReview | None = None
    # 管理办法第十六条：培训包遴选，重点开发“一人一技”专项培训包。
    package: bool = False
    one_skill: bool = False
    target_groups: str = Field(default='', max_length=1000)
    @model_validator(mode='after')
    def courseware_complete(self):
        if self.one_skill and not self.target_groups.strip():
            raise ValueError('“一人一技”专项课程须说明重点群体和行动对接内容')
        if self.courseware and self.courseware.checked and not (self.courseware.reviewer.strip() and self.courseware.reviewed_on):
            raise ValueError('课件已审查时，请填写审查人和审查日期')
        return self


class CourseImportRow(CourseIn):
    source: Literal['manual', 'chaoxing'] = 'manual'
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


# ---- 老师发起的申请（培训课程、培训基地），审批规则见 approvals.py ----
TEACHING_MODES = {'lecture':'讲授','practice':'实训实操','case':'案例研讨','onsite':'现场教学','online':'线上自学'}
IDEOLOGY = {'ideology_course':'思政课程','course_ideology':'课程思政','none':'无'}
BASE_USAGES = {'practice':'实践教学基地','ideology':'思政实践教学基地'}
BASE_LEVELS = {'school':'校级','city':'市级','province':'省级及以上'}


class CourseApplyData(Input):
    # teaching：老师把自己从教务、超星拉来的课申报为培训课程；manual：新填一门培训课程（学院可代老师登记）。
    source: Literal['teaching', 'manual']
    course_term_id: Ident | None = None
    code: str = Field(default='', max_length=64)
    name: str = Field(default='', max_length=160)
    project_code: str = Field(default='', max_length=64)
    teacher_id: Ident | None = None
    hours: Nonnegative | None = None
    teaching_mode: Literal['lecture', 'practice', 'case', 'onsite', 'online']
    ideology: Literal['ideology_course', 'course_ideology', 'none']
    audience: str = Field(default='', max_length=500)
    intro: str = Field(default='', max_length=2000)
    courseware: CoursewareReview = Field(default_factory=CoursewareReview)
    # 管理办法第十六条：是否按培训包开发、是否“一人一技”专项（专项须写重点群体和行动对接）。
    package: bool = False
    one_skill: bool = False
    target_groups: str = Field(default='', max_length=1000)
    @model_validator(mode='after')
    def required(self):
        if self.one_skill and not self.target_groups.strip():
            raise ValueError('“一人一技”专项课程须说明重点群体和行动对接内容')
        if self.source == 'teaching':
            if not self.course_term_id: raise ValueError('请选择要申报的课程')
            if not self.audience.strip(): raise ValueError('请填写面向对象（这门课准备面向哪些社会学员）')
        else:
            if not self.code.strip() or not self.name.strip(): raise ValueError('请填写课程编号和名称')
            if self.hours is None: raise ValueError('请填写学时')
        if self.courseware.checked and not (self.courseware.reviewer.strip() and self.courseware.reviewed_on):
            raise ValueError('勾选课件已审查时，请填写审查人和审查日期')
        return self


class CourseApplyIn(Reason):
    data: CourseApplyData
    expected_version: int | None = Field(default=None, ge=1)


class BaseApplyData(Input):
    teacher_id: Ident | None = None
    code: Code
    name: Name
    location: str = Field(default='', max_length=500)
    onsite: bool = True
    recognition: Text
    usages: list[Literal['practice', 'ideology']] = Field(min_length=1, max_length=2)
    established_on: date
    partner: str = Field(default='', max_length=200)
    project_id: Ident | None = None
    # 管理办法第十七条鼓励申报省级及以上培训基地。
    level: Literal['school', 'city', 'province'] = 'school'
    @model_validator(mode='after')
    def partner_required(self):
        if not self.onsite and not self.partner.strip(): raise ValueError('校外基地请填写共建单位')
        if len(set(self.usages)) != len(self.usages): raise ValueError('基地用途不能重复')
        return self


class BaseApplyIn(Reason):
    data: BaseApplyData
    expected_version: int | None = Field(default=None, ge=1)


TRAINER_DIRECTIONS = {'subsidy': '补贴性培训', 'enterprise': '社会化自主培训', 'community': '社区公益培训', 'rural': '对口帮扶培训', 'other': '其他非学历培训', 'one_skill': '“一人一技”专项'}


class TrainerApplyData(Input):
    # 管理办法第十五条培训师遴选：internal 校内老师申报；external 外聘培训师由学院登记、教务处审核备案。
    source: Literal['internal', 'external']
    teacher_id: Ident | None = None
    name: str = Field(default='', max_length=80)
    unit: str = Field(default='', max_length=160)
    title: str = Field(default='', max_length=100)
    directions: list[Literal['subsidy', 'enterprise', 'community', 'rural', 'other', 'one_skill']] = Field(min_length=1, max_length=6)
    qualification_ids: list[Ident] = Field(default_factory=list, max_length=10)
    qualification_basis: str = Field(min_length=1, max_length=2000)
    experience: str = Field(default='', max_length=2000)
    @model_validator(mode='after')
    def required(self):
        if len(set(self.directions)) != len(self.directions): raise ValueError('培训方向不能重复')
        if self.source == 'external' and not (self.name.strip() and self.unit.strip()): raise ValueError('外聘培训师请填写姓名和工作单位')
        return self


class TrainerApplyIn(Reason):
    data: TrainerApplyData
    expected_version: int | None = Field(default=None, ge=1)


class ApplicationAction(Reason):
    expected_version: int = Field(ge=1)
    action: Literal['submit', 'approve', 'return', 'withdraw']


PREP_ITEMS = {'plan':'教学计划','lecturers':'师资安排','venue':'场地','equipment':'设备','materials':'教材教具','notice':'培训告知书或邀请函'}


class PrepIn(Reason):
    """开班前准备清单：只提醒，不拦截任何办理。"""
    expected_version: int | None = Field(default=None, ge=1)
    items: dict[Literal['plan','lecturers','venue','equipment','materials','notice'], bool]


class ReportInfoIn(Reason):
    """学院给已结项的历史项目补填上报信息，不重新走审批。"""
    expected_version: int = Field(ge=1)
    total_hours: Nonnegative | None = None
    audiences: list[str] = Field(default_factory=list, max_length=12)
    audience_other: str = Field(default='', max_length=200)
    service_types: list[Literal['national','regional','industry','other']] = Field(default_factory=list, max_length=4)
    teaching_methods: list[Literal['classroom','case','onsite','field','seminar','lab','internship','peer','other']] = Field(default_factory=list, max_length=9)
    video_minutes: Nonnegative | None = None
    video_minutes: Nonnegative | None = None
    base_count: int | None = Field(default=None, ge=0, le=1000)


class DeadlineIn(Reason):
    # 从我的课程申报培训课程，每学年的申报截止日（默认学年结束后的 9 月 30 日）。
    school_year: str = Field(pattern=r'^20\d{2}-20\d{2}$')
    deadline: date
    expected_version: int = Field(ge=0)
    @model_validator(mode='after')
    def consecutive(self):
        if int(self.school_year[5:9]) != int(self.school_year[:4]) + 1: raise ValueError('学年写成 2025-2026 这样相邻的两年')
        return self


class ReopenIn(Reason):
    # 学院为本院开放截止后的补报；until 为空表示关闭补报。
    school_year: str = Field(pattern=r'^20\d{2}-20\d{2}$')
    until: date | None = None
    expected_version: int = Field(ge=0)

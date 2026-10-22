// 真实隔离浏览器采集，不含输入值。
export const HELP_FORMS={
  "apply_course": [
    {
      "title": "新填一门培训课程",
      "fields": [
        {
          "key": "code",
          "label": "课程编号",
          "explanation": "填写本业务的唯一编号；系统已生成的编号优先保留，避免与已有记录重复。",
          "requirement": "当前必填",
          "hints": [
            "填写课程材料上的编号；补正时保留原编号。"
          ],
          "limits": [],
          "options": [],
          "example": "例：SOC-2026-001",
          "documented": true
        },
        {
          "key": "name",
          "label": "课程名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：社区营养配餐",
          "documented": true
        },
        {
          "key": "hours",
          "label": "学时",
          "explanation": "按本次业务的实际安排或记录填写学时，核对页面是否允许半学时，不把分钟直接填作学时。",
          "requirement": "当前必填",
          "hints": [
            "按本次培训实际安排填写。"
          ],
          "limits": [
            "最小值：0",
            "步长：0.5"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "teaching_mode",
          "label": "教学方式（单选）",
          "explanation": "按实际教学组织方式选择，与培训方案一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "ideology",
          "label": "思政属性（单选）",
          "explanation": "按课程实际安排选择思政属性，不为提交而随意选择。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "intro",
          "label": "课程简介",
          "explanation": "说明面向哪些学员、培训什么内容，以及完成后能掌握什么技能。",
          "requirement": "当前选填",
          "hints": [
            "说明面向哪些社会学员、培训内容和预期学习效果。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "project_code",
          "label": "选择关联项目",
          "explanation": "选择本次业务所属的已有培训项目。没有关联项目且页面标为选填时可留空。",
          "requirement": "当前选填",
          "hints": [
            "可不关联项目；选择后自动使用该项目编号，无需手填。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "package",
          "label": "培训包",
          "explanation": "只有按成套教学包开发时勾选，与单门课程区分。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "one_skill",
          "label": "“一人一技”专项",
          "explanation": "确属“一人一技”专项培训行动时勾选，并补充重点群体及行动对接。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "target_groups",
          "label": "重点群体与行动对接",
          "explanation": "勾选“一人一技”专项时说明重点群体及如何对接行动。",
          "requirement": "当前选填",
          "hints": [
            "勾选“一人一技”专项时必填：面向哪些重点群体、怎么对接行动。"
          ],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "例：脱贫人口、返乡青年；对接“一人一技”行动，学员结业后推荐就业",
          "documented": true
        },
        {
          "key": "cw_checked",
          "label": "课件审查状态",
          "explanation": "已有学院课件审查记录才勾选，不能用勾选代替实际审查。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cw_reviewer",
          "label": "审查人或审查组",
          "explanation": "勾选已有课件审查记录时填写真实审查人或审查组。",
          "requirement": "当前选填",
          "hints": [
            "勾选已有审查记录时必填。"
          ],
          "limits": [],
          "options": [],
          "example": "例：学院课件审查组",
          "documented": true
        },
        {
          "key": "cw_on",
          "label": "审查日期",
          "explanation": "填写课件审查记录中的实际日期。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "cw_ref",
          "label": "审查记录编号",
          "explanation": "填写可查证的审查记录编号；没有编号且为选填时可留空。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：KJ-2026-03",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "课程封面（选填）",
          "explanation": "可选展示图片，不代替业务佐证附件。请使用与课程、基地或师资相符的图片。",
          "requirement": "当前选填",
          "hints": [
            "选填，PNG（图片） 或 JPG（照片），不超过 5 MB（兆字节）；仅用于展示，不能代替证明材料。"
          ],
          "limits": [
            "允许文件类型：.png,.jpg,.jpeg,image/png,image/jpeg",
            "最多 1 份（含已上传）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "本次申报说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前选填",
          "hints": [
            "可填写申报依据或需要审核人员了解的情况。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        }
      ],
      "user": "teacher",
      "role": "teacher",
      "action": "teacher-apply",
      "action_id": "courses|app-course-new"
    },
    {
      "title": "新填一门培训课程",
      "fields": [
        {
          "key": "teacher_id",
          "label": "主讲教师（输入工号或姓名检索）",
          "explanation": "从当前授权范围内选择教师，核对姓名及工号，不要选择同名的其他人员。",
          "requirement": "当前必填",
          "hints": [
            "仅可选择当前账号授权范围内的教师。"
          ],
          "limits": [],
          "options": [],
          "example": "输入教师姓名或工号",
          "documented": true
        },
        {
          "key": "code",
          "label": "课程编号",
          "explanation": "填写本业务的唯一编号；系统已生成的编号优先保留，避免与已有记录重复。",
          "requirement": "当前必填",
          "hints": [
            "填写课程材料上的编号；补正时保留原编号。"
          ],
          "limits": [],
          "options": [],
          "example": "例：SOC-2026-001",
          "documented": true
        },
        {
          "key": "name",
          "label": "课程名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：社区营养配餐",
          "documented": true
        },
        {
          "key": "hours",
          "label": "学时",
          "explanation": "按本次业务的实际安排或记录填写学时，核对页面是否允许半学时，不把分钟直接填作学时。",
          "requirement": "当前必填",
          "hints": [
            "按本次培训实际安排填写。"
          ],
          "limits": [
            "最小值：0",
            "步长：0.5"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "teaching_mode",
          "label": "教学方式（单选）",
          "explanation": "按实际教学组织方式选择，与培训方案一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "ideology",
          "label": "思政属性（单选）",
          "explanation": "按课程实际安排选择思政属性，不为提交而随意选择。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "intro",
          "label": "课程简介",
          "explanation": "说明面向哪些学员、培训什么内容，以及完成后能掌握什么技能。",
          "requirement": "当前选填",
          "hints": [
            "说明面向哪些社会学员、培训内容和预期学习效果。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "project_code",
          "label": "选择关联项目",
          "explanation": "选择本次业务所属的已有培训项目。没有关联项目且页面标为选填时可留空。",
          "requirement": "当前选填",
          "hints": [
            "可不关联项目；选择后自动使用该项目编号，无需手填。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "package",
          "label": "培训包",
          "explanation": "只有按成套教学包开发时勾选，与单门课程区分。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "one_skill",
          "label": "“一人一技”专项",
          "explanation": "确属“一人一技”专项培训行动时勾选，并补充重点群体及行动对接。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "target_groups",
          "label": "重点群体与行动对接",
          "explanation": "勾选“一人一技”专项时说明重点群体及如何对接行动。",
          "requirement": "当前选填",
          "hints": [
            "勾选“一人一技”专项时必填：面向哪些重点群体、怎么对接行动。"
          ],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "例：脱贫人口、返乡青年；对接“一人一技”行动，学员结业后推荐就业",
          "documented": true
        },
        {
          "key": "cw_checked",
          "label": "课件审查状态",
          "explanation": "已有学院课件审查记录才勾选，不能用勾选代替实际审查。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cw_reviewer",
          "label": "审查人或审查组",
          "explanation": "勾选已有课件审查记录时填写真实审查人或审查组。",
          "requirement": "当前选填",
          "hints": [
            "勾选已有审查记录时必填。"
          ],
          "limits": [],
          "options": [],
          "example": "例：学院课件审查组",
          "documented": true
        },
        {
          "key": "cw_on",
          "label": "审查日期",
          "explanation": "填写课件审查记录中的实际日期。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "cw_ref",
          "label": "审查记录编号",
          "explanation": "填写可查证的审查记录编号；没有编号且为选填时可留空。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：KJ-2026-03",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "课程封面（选填）",
          "explanation": "可选展示图片，不代替业务佐证附件。请使用与课程、基地或师资相符的图片。",
          "requirement": "当前选填",
          "hints": [
            "选填，PNG（图片） 或 JPG（照片），不超过 5 MB（兆字节）；仅用于展示，不能代替证明材料。"
          ],
          "limits": [
            "允许文件类型：.png,.jpg,.jpeg,image/png,image/jpeg",
            "最多 1 份（含已上传）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "本次申报说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前选填",
          "hints": [
            "可填写申报依据或需要审核人员了解的情况。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        }
      ],
      "user": "depthead",
      "role": "dept",
      "action": "teacher-apply",
      "action_id": "courses|app-course-new"
    }
  ],
  "apply_project": [
    {
      "title": "申报培训项目",
      "fields": [
        {
          "key": "code",
          "label": "项目编号",
          "explanation": "填写本业务的唯一编号；系统已生成的编号优先保留，避免与已有记录重复。",
          "requirement": "当前必填",
          "hints": [
            "填写项目材料上的编号；不清楚时请先向学院核实。"
          ],
          "limits": [],
          "options": [],
          "example": "例：SOC-2026-01",
          "documented": true
        },
        {
          "key": "name",
          "label": "项目名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026年社区茶艺公益培训",
          "documented": true
        },
        {
          "key": "cohort",
          "label": "项目期次",
          "explanation": "填写项目期次，如第一期；同一项目分期举办时按实际期次区分。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：第一期",
          "documented": true
        },
        {
          "key": "owner_view",
          "label": "项目负责人",
          "explanation": "老师申报的项目，负责人是本人，承办学院是本人所在学院。",
          "requirement": "自动带出／只读",
          "hints": [
            "老师申报的项目，负责人是本人，承办学院是本人所在学院。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "category",
          "label": "培训类别（单选）",
          "explanation": "选择最符合本事项的业务类别，按学校统一分类使用。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_0",
          "label": "企业职工",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_1",
          "label": "社区居民",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_2",
          "label": "退役军人",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_3",
          "label": "新型职业农民",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_4",
          "label": "中小学教师",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_5",
          "label": "机关事业单位人员",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_6",
          "label": "待业及转岗人员",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_7",
          "label": "老年学员",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "audience_other",
          "label": "其他受众群体",
          "explanation": "填写预设选项之外的培训对象，没有其他对象可留空。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多字数：200"
          ],
          "options": [],
          "example": "其他（选填）",
          "documented": true
        },
        {
          "key": "svc_national",
          "label": "国家战略",
          "explanation": "按项目实际服务方向勾选，相关依据在方案中说明。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "svc_regional",
          "label": "区域发展",
          "explanation": "按项目实际服务方向勾选，相关依据在方案中说明。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "svc_industry",
          "label": "行业发展",
          "explanation": "按项目实际服务方向勾选，相关依据在方案中说明。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "svc_other",
          "label": "其他",
          "explanation": "按项目实际服务方向勾选，相关依据在方案中说明。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "high_risk",
          "label": "高风险项目",
          "explanation": "按照项目实际风险和学校规定选择，涉及高风险活动时必须落实对应审批和安全措施。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "项目封面（选填）",
          "explanation": "可选展示图片，不代替业务佐证附件。请使用与课程、基地或师资相符的图片。",
          "requirement": "当前选填",
          "hints": [
            "选填，PNG（图片） 或 JPG（照片），不超过 5 MB（兆字节）；仅用于展示，不能代替证明材料。"
          ],
          "limits": [
            "允许文件类型：.png,.jpg,.jpeg,image/png,image/jpeg",
            "最多 1 份（含已上传）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "proof_files",
          "label": "项目方案材料（可一次选多份）",
          "explanation": "选填：现在附上，保存后不用再到详情里上传；提交审核前至少要有一份。支持 .pdf、.png、.jpg，单个文件不超过 10 兆字节。",
          "requirement": "当前选填",
          "hints": [
            "选填：现在附上，保存后不用再到详情里上传；提交审核前至少要有一份。支持 .pdf、.png、.jpg，单个文件不超过 10 兆字节。"
          ],
          "limits": [
            "允许文件类型：.pdf,.png,.jpg,.jpeg",
            "可多选",
            "最多 50 份（含已上传）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "start_date",
          "label": "开始日期",
          "explanation": "填写本次业务实际开始日期，结束日期不得早于开始日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "end_date",
          "label": "结束日期",
          "explanation": "填写本次业务实际结束日期，与方案或完成记录一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "expected_income",
          "label": "预计收入（元，公益类填0）",
          "explanation": "填写培训方案预计收入，单位为元；公益类按页面要求填0，不能以预计收入代替实际结算收入。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "例：0 或 30000",
          "documented": true
        },
        {
          "key": "expected_participants",
          "label": "预计人次",
          "explanation": "填写预计培训人次，按方案估算，结项时另核对实际数据。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：1"
          ],
          "options": [],
          "example": "例：120",
          "documented": true
        },
        {
          "key": "expected_outcomes",
          "label": "预期成果",
          "explanation": "写清培训结束后学员能够掌握的技能、项目预期取得的成果，以及如何核验；不要只写“完成培训”。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 200 字"
          ],
          "options": [],
          "example": "例：学员掌握基础茶艺，80%以上取得结业证书",
          "documented": true
        },
        {
          "key": "one_skill",
          "label": "“一人一技”专项",
          "explanation": "确属“一人一技”专项培训行动时勾选，并补充重点群体及行动对接。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "province_report",
          "label": "是否需要报省",
          "explanation": "根据上级及学校要求选择是否需报省，不能仅因系统可选就认定无需报送。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "province_basis",
          "label": "报省要求与依据",
          "explanation": "勾选“需要报省”时必填：写明省级专项文件、报送口径或学校要求。",
          "requirement": "当前选填",
          "hints": [
            "勾选“需要报省”时必填：写明省级专项文件、报送口径或学校要求。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "例：湘人社〔2026〕12号文，须在结项后15个工作日内报送",
          "documented": true
        },
        {
          "key": "target_groups",
          "label": "重点群体与行动对接",
          "explanation": "勾选“一人一技”专项时说明重点群体及如何对接行动。",
          "requirement": "当前选填",
          "hints": [
            "补贴性培训必填：写明面向哪些重点群体、对接哪项行动；其他类别可不填。"
          ],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "例：脱贫人口、退役军人；对接“一人一技”行动",
          "documented": true
        },
        {
          "key": "total_hours",
          "label": "总学时",
          "explanation": "草稿可暂留空；提交学院审批前必须填写。",
          "requirement": "当前选填",
          "hints": [
            "草稿可暂留空；提交学院审批前必须填写。"
          ],
          "limits": [
            "最小值：0",
            "步长：0.5"
          ],
          "options": [],
          "example": "例：32",
          "documented": true
        },
        {
          "key": "video_minutes",
          "label": "视频资源总时长（分钟）",
          "explanation": "项目建设的视频资源合计时长；没有填 0。",
          "requirement": "当前选填",
          "hints": [
            "项目建设的视频资源合计时长；没有填 0。"
          ],
          "limits": [
            "最小值：0",
            "步长：1"
          ],
          "options": [],
          "example": "例：199",
          "documented": true
        },
        {
          "key": "base_count",
          "label": "实践教学基地数量（个）",
          "explanation": "没有填 0。",
          "requirement": "当前选填",
          "hints": [
            "没有填 0。"
          ],
          "limits": [
            "最小值：0",
            "步长：1"
          ],
          "options": [],
          "example": "例：2",
          "documented": true
        },
        {
          "key": "tm_classroom",
          "label": "课堂教学",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_case",
          "label": "案例教学",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_onsite",
          "label": "现场教学",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_field",
          "label": "实地考察",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_seminar",
          "label": "交流研讨",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_lab",
          "label": "实验实训",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_internship",
          "label": "岗位实习",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_peer",
          "label": "学习者互助",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_other",
          "label": "其他",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "venue_type",
          "label": "培训场地",
          "explanation": "按实际教学地点选择校内基地、其他校内场所或校外，校外活动补充相关说明。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "venue_place",
          "label": "具体地点（基地名称、楼宇教室或外出地点）",
          "explanation": "填写可定位的基地名称、楼宇教室或校外具体地址。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "先选择培训场地类型",
          "documented": true
        },
        {
          "key": "venue_reason",
          "label": "校外培训的外出理由（一事一议）",
          "explanation": "选“校外”时必填：说明为什么不能在校内开展。",
          "requirement": "当前选填",
          "hints": [
            "选“校外”时必填：说明为什么不能在校内开展。"
          ],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "例：茶叶采摘与制作必须在茶园现场教学，校内没有条件",
          "documented": true
        },
        {
          "key": "venue_ref",
          "label": "议定文号或会议日期",
          "explanation": "选“校外”时必填：学校一事一议的会议日期或文号。",
          "requirement": "当前选填",
          "hints": [
            "选“校外”时必填：学校一事一议的会议日期或文号。"
          ],
          "limits": [],
          "options": [],
          "example": "例：校长办公会 2026-08-20 或 校办〔2026〕15号",
          "documented": true
        },
        {
          "key": "mode",
          "label": "核算方式（单选）",
          "explanation": "按学校确认的模块式或人天式计分方式选择，与实际组织方式一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "class_type",
          "label": "标准班类型（单选）",
          "explanation": "按项目实际内容选择技术类或讲座类等类型，影响计分时应核对制度依据。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "level",
          "label": "项目层级（单选）",
          "explanation": "按学校或上级认定依据选择项目或基地层级，不自行提高等级。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "scene",
          "label": "授课场景（单选）",
          "explanation": "按实际是否异地送教、全天实操或脱产等情况选择，保留相应依据。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "level_basis",
          "label": "专项层级认定依据",
          "explanation": "企业定制通常选市级；社区、免费帮扶通常选校级。属于更高层级专项时，填写正式认定依据并提交归口核验。",
          "requirement": "当前选填",
          "hints": [
            "企业定制通常选市级；社区、免费帮扶通常选校级。属于更高层级专项时，填写正式认定依据并提交归口核验。"
          ],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "例：省人社厅专项培训认定文件〔2026〕8号",
          "documented": true
        },
        {
          "key": "auxiliary_standard",
          "label": "随项目备案的辅助积分细则",
          "explanation": "填写随项目备案的辅助工作积分细则，写明工作内容、计分标准及依据。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：班主任每天0.5分，每人每天不超过1分",
          "documented": true
        },
        {
          "key": "auxiliary_daily_cap",
          "label": "个人辅助积分每日上限",
          "explanation": "按经学校确认的辅助积分规则填写个人每日上限，不以演示值代替正式规定。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "例：1",
          "documented": true
        },
        {
          "key": "reason",
          "label": "申报说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号（选填）",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "teacher",
      "role": "teacher",
      "action": "teacher-apply",
      "action_id": "projects|social-project-new"
    },
    {
      "title": "申报培训项目",
      "fields": [
        {
          "key": "code",
          "label": "项目编号",
          "explanation": "填写本业务的唯一编号；系统已生成的编号优先保留，避免与已有记录重复。",
          "requirement": "当前必填",
          "hints": [
            "填写项目材料上的编号；不清楚时请先向学院核实。"
          ],
          "limits": [],
          "options": [],
          "example": "例：SOC-2026-01",
          "documented": true
        },
        {
          "key": "name",
          "label": "项目名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026年社区茶艺公益培训",
          "documented": true
        },
        {
          "key": "cohort",
          "label": "项目期次",
          "explanation": "填写项目期次，如第一期；同一项目分期举办时按实际期次区分。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：第一期",
          "documented": true
        },
        {
          "key": "org_id",
          "label": "承办学院",
          "explanation": "选择实际所属组织；教师、教研室身份归属教研室，学院身份归属学院。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "owner_id",
          "label": "项目负责人（输入工号或姓名检索）",
          "explanation": "仅可选择当前账号授权范围内的教师。",
          "requirement": "当前必填",
          "hints": [
            "仅可选择当前账号授权范围内的教师。"
          ],
          "limits": [],
          "options": [],
          "example": "输入教师姓名或工号",
          "documented": true
        },
        {
          "key": "category",
          "label": "培训类别（单选）",
          "explanation": "选择最符合本事项的业务类别，按学校统一分类使用。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_0",
          "label": "企业职工",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_1",
          "label": "社区居民",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_2",
          "label": "退役军人",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_3",
          "label": "新型职业农民",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_4",
          "label": "中小学教师",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_5",
          "label": "机关事业单位人员",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_6",
          "label": "待业及转岗人员",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud_7",
          "label": "老年学员",
          "explanation": "按本次培训实际面向的人群勾选，可以选择多类对象。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "audience_other",
          "label": "其他受众群体",
          "explanation": "填写预设选项之外的培训对象，没有其他对象可留空。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多字数：200"
          ],
          "options": [],
          "example": "其他（选填）",
          "documented": true
        },
        {
          "key": "svc_national",
          "label": "国家战略",
          "explanation": "按项目实际服务方向勾选，相关依据在方案中说明。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "svc_regional",
          "label": "区域发展",
          "explanation": "按项目实际服务方向勾选，相关依据在方案中说明。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "svc_industry",
          "label": "行业发展",
          "explanation": "按项目实际服务方向勾选，相关依据在方案中说明。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "svc_other",
          "label": "其他",
          "explanation": "按项目实际服务方向勾选，相关依据在方案中说明。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "high_risk",
          "label": "高风险项目",
          "explanation": "按照项目实际风险和学校规定选择，涉及高风险活动时必须落实对应审批和安全措施。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "项目封面（选填）",
          "explanation": "可选展示图片，不代替业务佐证附件。请使用与课程、基地或师资相符的图片。",
          "requirement": "当前选填",
          "hints": [
            "选填，PNG（图片） 或 JPG（照片），不超过 5 MB（兆字节）；仅用于展示，不能代替证明材料。"
          ],
          "limits": [
            "允许文件类型：.png,.jpg,.jpeg,image/png,image/jpeg",
            "最多 1 份（含已上传）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "proof_files",
          "label": "项目方案材料（可一次选多份）",
          "explanation": "选填：现在附上，保存后不用再到详情里上传；提交审核前至少要有一份。支持 .pdf、.png、.jpg，单个文件不超过 10 兆字节。",
          "requirement": "当前选填",
          "hints": [
            "选填：现在附上，保存后不用再到详情里上传；提交审核前至少要有一份。支持 .pdf、.png、.jpg，单个文件不超过 10 兆字节。"
          ],
          "limits": [
            "允许文件类型：.pdf,.png,.jpg,.jpeg",
            "可多选",
            "最多 50 份（含已上传）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "start_date",
          "label": "开始日期",
          "explanation": "填写本次业务实际开始日期，结束日期不得早于开始日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "end_date",
          "label": "结束日期",
          "explanation": "填写本次业务实际结束日期，与方案或完成记录一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "expected_income",
          "label": "预计收入（元，公益类填0）",
          "explanation": "填写培训方案预计收入，单位为元；公益类按页面要求填0，不能以预计收入代替实际结算收入。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "例：0 或 30000",
          "documented": true
        },
        {
          "key": "expected_participants",
          "label": "预计人次",
          "explanation": "填写预计培训人次，按方案估算，结项时另核对实际数据。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：1"
          ],
          "options": [],
          "example": "例：120",
          "documented": true
        },
        {
          "key": "expected_outcomes",
          "label": "预期成果",
          "explanation": "写清培训结束后学员能够掌握的技能、项目预期取得的成果，以及如何核验；不要只写“完成培训”。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 200 字"
          ],
          "options": [],
          "example": "例：学员掌握基础茶艺，80%以上取得结业证书",
          "documented": true
        },
        {
          "key": "one_skill",
          "label": "“一人一技”专项",
          "explanation": "确属“一人一技”专项培训行动时勾选，并补充重点群体及行动对接。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "province_report",
          "label": "是否需要报省",
          "explanation": "根据上级及学校要求选择是否需报省，不能仅因系统可选就认定无需报送。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "province_basis",
          "label": "报省要求与依据",
          "explanation": "勾选“需要报省”时必填：写明省级专项文件、报送口径或学校要求。",
          "requirement": "当前选填",
          "hints": [
            "勾选“需要报省”时必填：写明省级专项文件、报送口径或学校要求。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "例：湘人社〔2026〕12号文，须在结项后15个工作日内报送",
          "documented": true
        },
        {
          "key": "target_groups",
          "label": "重点群体与行动对接",
          "explanation": "勾选“一人一技”专项时说明重点群体及如何对接行动。",
          "requirement": "当前选填",
          "hints": [
            "补贴性培训必填：写明面向哪些重点群体、对接哪项行动；其他类别可不填。"
          ],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "例：脱贫人口、退役军人；对接“一人一技”行动",
          "documented": true
        },
        {
          "key": "total_hours",
          "label": "总学时",
          "explanation": "草稿可暂留空；提交学院审批前必须填写。",
          "requirement": "当前选填",
          "hints": [
            "草稿可暂留空；提交学院审批前必须填写。"
          ],
          "limits": [
            "最小值：0",
            "步长：0.5"
          ],
          "options": [],
          "example": "例：32",
          "documented": true
        },
        {
          "key": "video_minutes",
          "label": "视频资源总时长（分钟）",
          "explanation": "项目建设的视频资源合计时长；没有填 0。",
          "requirement": "当前选填",
          "hints": [
            "项目建设的视频资源合计时长；没有填 0。"
          ],
          "limits": [
            "最小值：0",
            "步长：1"
          ],
          "options": [],
          "example": "例：199",
          "documented": true
        },
        {
          "key": "base_count",
          "label": "实践教学基地数量（个）",
          "explanation": "没有填 0。",
          "requirement": "当前选填",
          "hints": [
            "没有填 0。"
          ],
          "limits": [
            "最小值：0",
            "步长：1"
          ],
          "options": [],
          "example": "例：2",
          "documented": true
        },
        {
          "key": "tm_classroom",
          "label": "课堂教学",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_case",
          "label": "案例教学",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_onsite",
          "label": "现场教学",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_field",
          "label": "实地考察",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_seminar",
          "label": "交流研讨",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_lab",
          "label": "实验实训",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_internship",
          "label": "岗位实习",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_peer",
          "label": "学习者互助",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "tm_other",
          "label": "其他",
          "explanation": "按实际采用的教学方式勾选，可多选，与培训方案一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "venue_type",
          "label": "培训场地",
          "explanation": "按实际教学地点选择校内基地、其他校内场所或校外，校外活动补充相关说明。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "venue_place",
          "label": "具体地点（基地名称、楼宇教室或外出地点）",
          "explanation": "填写可定位的基地名称、楼宇教室或校外具体地址。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "先选择培训场地类型",
          "documented": true
        },
        {
          "key": "venue_reason",
          "label": "校外培训的外出理由（一事一议）",
          "explanation": "选“校外”时必填：说明为什么不能在校内开展。",
          "requirement": "当前选填",
          "hints": [
            "选“校外”时必填：说明为什么不能在校内开展。"
          ],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "例：茶叶采摘与制作必须在茶园现场教学，校内没有条件",
          "documented": true
        },
        {
          "key": "venue_ref",
          "label": "议定文号或会议日期",
          "explanation": "选“校外”时必填：学校一事一议的会议日期或文号。",
          "requirement": "当前选填",
          "hints": [
            "选“校外”时必填：学校一事一议的会议日期或文号。"
          ],
          "limits": [],
          "options": [],
          "example": "例：校长办公会 2026-08-20 或 校办〔2026〕15号",
          "documented": true
        },
        {
          "key": "mode",
          "label": "核算方式（单选）",
          "explanation": "按学校确认的模块式或人天式计分方式选择，与实际组织方式一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "class_type",
          "label": "标准班类型（单选）",
          "explanation": "按项目实际内容选择技术类或讲座类等类型，影响计分时应核对制度依据。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "level",
          "label": "项目层级（单选）",
          "explanation": "按学校或上级认定依据选择项目或基地层级，不自行提高等级。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "scene",
          "label": "授课场景（单选）",
          "explanation": "按实际是否异地送教、全天实操或脱产等情况选择，保留相应依据。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "level_basis",
          "label": "专项层级认定依据",
          "explanation": "企业定制通常选市级；社区、免费帮扶通常选校级。属于更高层级专项时，填写正式认定依据并提交归口核验。",
          "requirement": "当前选填",
          "hints": [
            "企业定制通常选市级；社区、免费帮扶通常选校级。属于更高层级专项时，填写正式认定依据并提交归口核验。"
          ],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "例：省人社厅专项培训认定文件〔2026〕8号",
          "documented": true
        },
        {
          "key": "auxiliary_standard",
          "label": "随项目备案的辅助积分细则",
          "explanation": "填写随项目备案的辅助工作积分细则，写明工作内容、计分标准及依据。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：班主任每天0.5分，每人每天不超过1分",
          "documented": true
        },
        {
          "key": "auxiliary_daily_cap",
          "label": "个人辅助积分每日上限",
          "explanation": "按经学校确认的辅助积分规则填写个人每日上限，不以演示值代替正式规定。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "例：1",
          "documented": true
        },
        {
          "key": "reason",
          "label": "申报说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号（选填）",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "collegehead",
      "role": "college",
      "action": "teacher-apply",
      "action_id": "projects|social-project-new"
    }
  ],
  "apply_base": [
    {
      "title": "申请培训基地",
      "fields": [
        {
          "key": "code",
          "label": "来源编号",
          "explanation": "填写本业务的唯一编号；系统已生成的编号优先保留，避免与已有记录重复。",
          "requirement": "当前必填",
          "hints": [
            "填写共建协议编号或学院登记编号。"
          ],
          "limits": [],
          "options": [],
          "example": "例：JD-2026-001",
          "documented": true
        },
        {
          "key": "name",
          "label": "基地名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：湘茶思政实践教学基地",
          "documented": true
        },
        {
          "key": "manager_name",
          "label": "基地负责人",
          "explanation": "校内基地填学校负责人，校外基地填共建单位联系人；未填写时按系统提示处理。",
          "requirement": "当前选填",
          "hints": [
            "校内基地填学校负责人，校外基地填共建单位联系人；不填则按申请人显示。"
          ],
          "limits": [],
          "options": [],
          "example": "例：张老师",
          "documented": true
        },
        {
          "key": "usage_practice",
          "label": "实践教学基地",
          "explanation": "实际作为实践教学基地时勾选，可与其他适用用途同时选择。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "usage_ideology",
          "label": "思政实践教学基地",
          "explanation": "实际承担思政实践教学用途时勾选，保留相应建设或使用依据。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "level",
          "label": "基地级别（单选）",
          "explanation": "按学校或上级认定依据选择项目或基地层级，不自行提高等级。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "onsite",
          "label": "校内 / 校外（单选）",
          "explanation": "按基地实际位置选择校内或校外；选择校外后共建单位必须填写。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "partner",
          "label": "共建单位",
          "explanation": "校外基地必填共建单位全称；选择校内时按页面条件办理。",
          "requirement": "当前选填",
          "hints": [
            "选择校外基地时必须填写；请使用共建单位全称。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "established_on",
          "label": "设立日期",
          "explanation": "填写基地实际设立日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "recognized_on",
          "label": "认定日期",
          "explanation": "填写学校或上级正式认定日期；没有认定且页面为选填时留空，不与设立日期混淆。",
          "requirement": "当前选填",
          "hints": [
            "学校或上级正式认定的日期；与设立日期、审批生效日期分开记录，没有认定可不填。"
          ],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "location",
          "label": "具体地点",
          "explanation": "填写活动或基地的实际地点，校区、楼宇或校外地址应足够明确。",
          "requirement": "当前选填",
          "hints": [
            "可填写基地所在校区、楼宇或校外地址。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "基地封面（选填）",
          "explanation": "可选展示图片，不代替业务佐证附件。请使用与课程、基地或师资相符的图片。",
          "requirement": "当前选填",
          "hints": [
            "选填，PNG（图片） 或 JPG（照片），不超过 5 MB（兆字节）；场地照片可在基地详情里继续添加。仅用于展示，不能代替认定材料。"
          ],
          "limits": [
            "允许文件类型：.png,.jpg,.jpeg,image/png,image/jpeg",
            "最多 1 份（含已上传）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "recognition",
          "label": "基地认定依据",
          "explanation": "填写成果认定或登记的文件名称、编号及可查证位置。",
          "requirement": "当前必填",
          "hints": [
            "填写共建协议、学校发文或学院会议纪要等正式依据。"
          ],
          "limits": [
            "最多 200 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "本次申请说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前选填",
          "hints": [
            "补充说明设立用途或本次申请事项，与上面的认定依据分开填写。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        }
      ],
      "user": "teacher",
      "role": "teacher",
      "action": "teacher-apply",
      "action_id": "bases|app-base-new"
    },
    {
      "title": "申请培训基地",
      "fields": [
        {
          "key": "teacher_id",
          "label": "基地负责人（输入工号或姓名检索）",
          "explanation": "从当前授权范围内选择教师，核对姓名及工号，不要选择同名的其他人员。",
          "requirement": "当前必填",
          "hints": [
            "仅可选择当前账号授权范围内的教师。"
          ],
          "limits": [],
          "options": [],
          "example": "输入教师姓名或工号",
          "documented": true
        },
        {
          "key": "code",
          "label": "来源编号",
          "explanation": "填写本业务的唯一编号；系统已生成的编号优先保留，避免与已有记录重复。",
          "requirement": "当前必填",
          "hints": [
            "填写共建协议编号或学院登记编号。"
          ],
          "limits": [],
          "options": [],
          "example": "例：JD-2026-001",
          "documented": true
        },
        {
          "key": "name",
          "label": "基地名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：湘茶思政实践教学基地",
          "documented": true
        },
        {
          "key": "manager_name",
          "label": "基地负责人",
          "explanation": "校内基地填学校负责人，校外基地填共建单位联系人；未填写时按系统提示处理。",
          "requirement": "当前选填",
          "hints": [
            "校内基地填学校负责人，校外基地填共建单位联系人；不填则按申请人显示。"
          ],
          "limits": [],
          "options": [],
          "example": "例：张老师",
          "documented": true
        },
        {
          "key": "usage_practice",
          "label": "实践教学基地",
          "explanation": "实际作为实践教学基地时勾选，可与其他适用用途同时选择。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "usage_ideology",
          "label": "思政实践教学基地",
          "explanation": "实际承担思政实践教学用途时勾选，保留相应建设或使用依据。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "level",
          "label": "基地级别（单选）",
          "explanation": "按学校或上级认定依据选择项目或基地层级，不自行提高等级。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "onsite",
          "label": "校内 / 校外（单选）",
          "explanation": "按基地实际位置选择校内或校外；选择校外后共建单位必须填写。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "partner",
          "label": "共建单位",
          "explanation": "校外基地必填共建单位全称；选择校内时按页面条件办理。",
          "requirement": "当前选填",
          "hints": [
            "选择校外基地时必须填写；请使用共建单位全称。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "established_on",
          "label": "设立日期",
          "explanation": "填写基地实际设立日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "recognized_on",
          "label": "认定日期",
          "explanation": "填写学校或上级正式认定日期；没有认定且页面为选填时留空，不与设立日期混淆。",
          "requirement": "当前选填",
          "hints": [
            "学校或上级正式认定的日期；与设立日期、审批生效日期分开记录，没有认定可不填。"
          ],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "location",
          "label": "具体地点",
          "explanation": "填写活动或基地的实际地点，校区、楼宇或校外地址应足够明确。",
          "requirement": "当前选填",
          "hints": [
            "可填写基地所在校区、楼宇或校外地址。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "基地封面（选填）",
          "explanation": "可选展示图片，不代替业务佐证附件。请使用与课程、基地或师资相符的图片。",
          "requirement": "当前选填",
          "hints": [
            "选填，PNG（图片） 或 JPG（照片），不超过 5 MB（兆字节）；场地照片可在基地详情里继续添加。仅用于展示，不能代替认定材料。"
          ],
          "limits": [
            "允许文件类型：.png,.jpg,.jpeg,image/png,image/jpeg",
            "最多 1 份（含已上传）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "recognition",
          "label": "基地认定依据",
          "explanation": "填写成果认定或登记的文件名称、编号及可查证位置。",
          "requirement": "当前必填",
          "hints": [
            "填写共建协议、学校发文或学院会议纪要等正式依据。"
          ],
          "limits": [
            "最多 200 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "本次申请说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前选填",
          "hints": [
            "补充说明设立用途或本次申请事项，与上面的认定依据分开填写。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        }
      ],
      "user": "depthead",
      "role": "dept",
      "action": "teacher-apply",
      "action_id": "bases|app-base-new"
    }
  ],
  "apply_trainer": [
    {
      "title": "申报培训师",
      "fields": [
        {
          "key": "title",
          "label": "职称或职务",
          "explanation": "填写当前真实职称、职业技能等级或岗位，与佐证材料一致。",
          "requirement": "当前选填",
          "hints": [
            "填写本人现有职称、职业技能等级或岗位。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "specialty",
          "label": "专业特长",
          "explanation": "填写能够承担培训的专业特长，例如茶艺、电商运营；与培训业务类别分开。",
          "requirement": "当前选填",
          "hints": [
            "例：茶艺、电商运营、家政服务；与下面的“培训业务类别”分开填写。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir_subsidy",
          "label": "补贴性培训",
          "explanation": "按本人实际能够承担的培训业务类别勾选，可多选；类别与专业特长分别填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir_enterprise",
          "label": "社会化自主培训",
          "explanation": "按本人实际能够承担的培训业务类别勾选，可多选；类别与专业特长分别填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir_community",
          "label": "社区公益培训",
          "explanation": "按本人实际能够承担的培训业务类别勾选，可多选；类别与专业特长分别填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir_rural",
          "label": "对口帮扶培训",
          "explanation": "按本人实际能够承担的培训业务类别勾选，可多选；类别与专业特长分别填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir_other",
          "label": "其他非学历培训",
          "explanation": "按本人实际能够承担的培训业务类别勾选，可多选；类别与专业特长分别填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir_one_skill",
          "label": "“一人一技”专项",
          "explanation": "按本人实际能够承担的培训业务类别勾选，可多选；类别与专业特长分别填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "qualification_basis",
          "label": "资格依据",
          "explanation": "说明职称、职业资格或行业经历，以及它们能够支持的培训方向。",
          "requirement": "当前必填",
          "hints": [
            "说明职称、职业资格或行业经历，以及它们能够支持的培训方向。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "培训师头像（选填）",
          "explanation": "可选展示图片，不代替业务佐证附件。请使用与课程、基地或师资相符的图片。",
          "requirement": "当前选填",
          "hints": [
            "选填，PNG（图片） 或 JPG（照片），不超过 5 MB（兆字节）；仅用于展示，不能代替证明材料。"
          ],
          "limits": [
            "允许文件类型：.png,.jpg,.jpeg,image/png,image/jpeg",
            "最多 1 份（含已上传）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "experience",
          "label": "授课经历",
          "explanation": "写清近年授课项目、承担工作、时间及学员情况，必要时提供对应依据。",
          "requirement": "当前选填",
          "hints": [
            "可填写近年授课项目、培训期数和学员人次。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "本次申报说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前选填",
          "hints": [
            "可补充说明本次申报的专业特长与相关依据。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        }
      ],
      "user": "teacher",
      "role": "teacher",
      "action": "teacher-apply",
      "action_id": "trainer|"
    }
  ],
  "qualifications": [
    {
      "title": "申报我的资质",
      "fields": [
        {
          "key": "category",
          "label": "资质类别",
          "explanation": "选择最符合本事项的业务类别，按学校统一分类使用。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "职业资格",
            "教学资质"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "name",
          "label": "证书名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "certificate_no",
          "label": "证书编号",
          "explanation": "按证书原件填写完整编号，保留字母和前导零。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "issuer",
          "label": "发证机构",
          "explanation": "填写证书或认定文件上的发证单位全称。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "obtained",
          "label": "取得日期",
          "explanation": "填写证书或资格实际取得日期，与材料一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "expires",
          "label": "有效期至",
          "explanation": "请选择到期日期，或勾选长期有效；判定考核资质以周期结束日是否有效为准。",
          "requirement": "当前必填",
          "hints": [
            "请选择到期日期，或勾选长期有效；判定考核资质以周期结束日是否有效为准。"
          ],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "",
          "label": "长期有效",
          "explanation": "请选择到期日期，或勾选长期有效；判定考核资质以周期结束日是否有效为准。",
          "requirement": "当前选填",
          "hints": [
            "请选择到期日期，或勾选长期有效；判定考核资质以周期结束日是否有效为准。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "file",
          "label": "证书图片或扫描件（可一次选多份）",
          "explanation": "按本事项上传清晰、完整且与填写内容一致的材料；逐份检查上传结果。",
          "requirement": "当前选填",
          "hints": [
            "可一次选择多张照片或多份扫描件，支持 .jpg、.jpeg、.png、.pdf，单个最大 10 兆字节，单份资质最多 20 份。草稿可稍后补传；提交审核前必须上传。"
          ],
          "limits": [
            "允许文件类型：.pdf,.png,.jpg,.jpeg",
            "可多选",
            "最多 20 份（含已上传）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "申报说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        }
      ],
      "user": "teacher",
      "role": "teacher",
      "action": "qualification-form",
      "action_id": ""
    }
  ],
  "records": [
    {
      "title": "新增培训业务记录",
      "fields": [
        {
          "key": "teacher_id",
          "label": "教师（输入工号或姓名检索）",
          "explanation": "从当前授权范围内选择教师，核对姓名及工号，不要选择同名的其他人员。",
          "requirement": "当前必填",
          "hints": [
            "仅可选择当前账号授权范围内的教师。"
          ],
          "limits": [],
          "options": [],
          "example": "输入教师姓名或工号",
          "documented": true
        },
        {
          "key": "external_key",
          "label": "来源唯一编号",
          "explanation": "填写能够唯一对应这笔来源业务的编号，避免重复导入或重复登记。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "event_date",
          "label": "业务日期",
          "explanation": "填写这笔业务实际发生日期，不以录入当天代替。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "source",
          "label": "人工来源说明",
          "explanation": "本入口按人工录入留痕，接口与表格来源由各自接入流程产生。",
          "requirement": "当前必填",
          "hints": [
            "本入口按人工录入留痕，接口与表格来源由各自接入流程产生。"
          ],
          "limits": [],
          "options": [
            "经核对人工录入"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "project_code",
          "label": "培训项目（名称或编号检索）",
          "explanation": "选择本次业务所属的已有培训项目。没有关联项目且页面标为选填时可留空。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "project",
          "label": "项目名称",
          "explanation": "填写与所选项目编号对应的项目全称。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "course_code",
          "label": "培训课程（名称或编号检索）",
          "explanation": "选择与当前项目对应的课程，核对课程名称，不能只填写一个未核实的编号。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "course",
          "label": "课程名称",
          "explanation": "填写与所选课程编号对应的课程名称。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "class_code",
          "label": "培训班级（名称或编号检索）",
          "explanation": "填写或选择本次教学班编号，与花名册及教学安排一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "class_name",
          "label": "班级名称",
          "explanation": "填写本次实际教学班名称，与花名册及班级编号对应。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "hours",
          "label": "授课学时",
          "explanation": "按本次业务的实际安排或记录填写学时，核对页面是否允许半学时，不把分钟直接填作学时。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "participants",
          "label": "课程人次",
          "explanation": "填写本项记录对应的课程人次，同一人参加不同课程可能分别计次，按学校确认口径填写。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：1"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "income",
          "label": "归属培训收入（元）",
          "explanation": "按已核实的财务依据填写本项归属培训收入，单位以页面为准。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "步长：0.01"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理意见 / 调整原因",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号（选填）",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        }
      ],
      "user": "depthead",
      "role": "dept",
      "action": "record-form",
      "action_id": ""
    }
  ],
  "imports": [
    {
      "title": "上传表格并生成校验预览",
      "fields": [
        {
          "key": "kind",
          "label": "导入类型",
          "explanation": "选择本次操作对应的类别；导入时类别须与下载模板一致，规则和组织类别须与实际对象一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "培训授课数据",
            "教师参训记录",
            "教师资质草稿"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "file",
          "label": "标准电子表格文件",
          "explanation": "按本事项上传清晰、完整且与填写内容一致的材料；逐份检查上传结果。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "允许文件类型：.xlsx"
          ],
          "options": [],
          "example": "",
          "documented": true
        }
      ],
      "user": "depthead",
      "role": "dept",
      "action": "import-form",
      "action_id": ""
    },
    {
      "title": "上传表格并生成校验预览",
      "fields": [
        {
          "key": "kind",
          "label": "导入类型",
          "explanation": "选择本次操作对应的类别；导入时类别须与下载模板一致，规则和组织类别须与实际对象一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "培训授课数据",
            "教师参训记录",
            "教师资质草稿",
            "教师账号（停用待配置）"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "file",
          "label": "标准电子表格文件",
          "explanation": "按本事项上传清晰、完整且与填写内容一致的材料；逐份检查上传结果。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "允许文件类型：.xlsx"
          ],
          "options": [],
          "example": "",
          "documented": true
        }
      ],
      "user": "schooladmin",
      "role": "school",
      "action": "import-form",
      "action_id": ""
    }
  ],
  "annual": [
    {
      "title": "学院年度自评",
      "fields": [
        {
          "key": "org_id",
          "label": "承办学院",
          "explanation": "选择实际所属组织；教师、教研室身份归属教研室，学院身份归属学院。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "policy_id",
          "label": "制度执行口径",
          "explanation": "选择本年度经确认并适用的制度执行口径版本。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "income_target",
          "label": "到账收入目标",
          "explanation": "填写本年度经确认的到账收入目标，按财务口径和页面单位核对。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：1"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "participants_target",
          "label": "有效人次目标",
          "explanation": "填写本年度经确认的有效人次目标，不用去重人数代替人次。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：1"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "priority_target",
          "label": "重点群体人次目标",
          "explanation": "填写经确认的重点群体培训人次目标，并核对对应群体范围。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：1"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "staff_denominator",
          "label": "组织人数基准",
          "explanation": "填写本次组织考核采用的人数基准，保留来源日期和依据。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：1"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "target_reference",
          "label": "年度任务下达依据",
          "explanation": "填写学校下达本年度任务的文件名称、编号或会议纪要依据，并与本页目标值对应。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "staff_basis",
          "label": "组织人数依据",
          "explanation": "说明组织人数的统计日期、人员范围及核验依据，人数基准应与学校确认口径一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "self_report",
          "label": "单位自评报告",
          "explanation": "按本年度实际任务、收入、人次、成果和管理工作逐项说明完成情况，列出问题与改进安排，并引用相应佐证。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 200 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "other_bonus",
          "label": "其他加分",
          "explanation": "仅填写有正式依据且不属于其他已登记项目的加分，避免重复计分。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "other_bonus_basis",
          "label": "其他加分依据",
          "explanation": "逐项说明申请加分的事项、认定文件及对应分值，核对是否已经计入其他项目，避免重复加分。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "compliance_failures",
          "label": "其他已确认不合规次数（不含项目结算核验）",
          "explanation": "填写已经确认的不合规次数；不重复计入项目结算核验已经反映的问题。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：1"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "discipline_reference",
          "label": "正式处理或处分依据",
          "explanation": "填写已经正式确认的处理或处分文件名称、编号和日期，说明与本次考核事项的对应关系。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "confirmed_veto",
          "label": "一票否决",
          "explanation": "只有学校已确认满足一票否决情形时勾选，并提供正式依据。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号（选填）",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "collegehead",
      "role": "college",
      "action": "social-annual-new",
      "action_id": ""
    }
  ],
  "outcomes": [
    {
      "title": "登记培训成果",
      "fields": [
        {
          "key": "org_id",
          "label": "承办学院",
          "explanation": "选择实际所属组织；教师、教研室身份归属教研室，学院身份归属学院。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "code",
          "label": "来源唯一编号",
          "explanation": "填写本业务的唯一编号；系统已生成的编号优先保留，避免与已有记录重复。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "name",
          "label": "名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "location",
          "label": "地点或资源说明",
          "explanation": "填写活动或基地的实际地点，校区、楼宇或校外地址应足够明确。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "recognition",
          "label": "认定或登记依据",
          "explanation": "填写成果认定或登记的文件名称、编号及可查证位置。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "level",
          "label": "成果等级",
          "explanation": "按学校或上级认定依据选择项目或基地层级，不自行提高等级。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "国家级",
            "省级",
            "校级"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "confirmed_on",
          "label": "成果正式认定日期",
          "explanation": "日期待补时，不计年度分数",
          "requirement": "当前选填",
          "hints": [
            "日期待补时，不计年度分数"
          ],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "成果封面（选填）",
          "explanation": "可选展示图片，不代替业务佐证附件。请使用与课程、基地或师资相符的图片。",
          "requirement": "当前选填",
          "hints": [
            "选填，PNG（图片） 或 JPG（照片），不超过 5 MB（兆字节）；仅用于展示，不能代替证明材料。"
          ],
          "limits": [
            "允许文件类型：.png,.jpg,.jpeg,image/png,image/jpeg",
            "最多 1 份（含已上传）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号（选填）",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "collegehead",
      "role": "college",
      "action": "social-resource-new",
      "action_id": "achievement"
    }
  ],
  "courses": [
    {
      "title": "登记培训课程",
      "fields": [
        {
          "key": "code",
          "label": "课程编号",
          "explanation": "填写本业务的唯一编号；系统已生成的编号优先保留，避免与已有记录重复。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "name",
          "label": "课程名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "project_code",
          "label": "选择关联项目",
          "explanation": "选择本次业务所属的已有培训项目。没有关联项目且页面标为选填时可留空。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "hours",
          "label": "学时",
          "explanation": "按本次业务的实际安排或记录填写学时，核对页面是否允许半学时，不把分钟直接填作学时。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.5"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "teaching_mode",
          "label": "教学方式",
          "explanation": "按实际教学组织方式选择，与培训方案一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "ideology",
          "label": "思政属性",
          "explanation": "按课程实际安排选择思政属性，不为提交而随意选择。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "package",
          "label": "培训包",
          "explanation": "只有按成套教学包开发时勾选，与单门课程区分。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "one_skill",
          "label": "“一人一技”专项",
          "explanation": "确属“一人一技”专项培训行动时勾选，并补充重点群体及行动对接。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "target_groups",
          "label": "重点群体与行动对接",
          "explanation": "勾选“一人一技”专项时说明重点群体及如何对接行动。",
          "requirement": "当前选填",
          "hints": [
            "勾选“一人一技”专项时必填。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "teacher_id",
          "label": "主讲教师（输入工号或姓名检索）",
          "explanation": "从当前授权范围内选择教师，核对姓名及工号，不要选择同名的其他人员。",
          "requirement": "当前必填",
          "hints": [
            "仅可选择当前账号授权范围内的教师。"
          ],
          "limits": [],
          "options": [],
          "example": "输入教师姓名或工号",
          "documented": true
        },
        {
          "key": "cw_checked",
          "label": "课件审查",
          "explanation": "已有学院课件审查记录才勾选，不能用勾选代替实际审查。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cw_reviewer",
          "label": "审查人",
          "explanation": "勾选已有课件审查记录时填写真实审查人或审查组。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cw_reviewed_on",
          "label": "审查日期",
          "explanation": "填写实际课件审查日期，与审查记录一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号（选填）",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "schooladmin",
      "role": "school",
      "action": "social-course-new",
      "action_id": ""
    }
  ],
  "permissions": [
    {
      "title": "新增组织机构",
      "fields": [
        {
          "key": "code",
          "label": "组织编码",
          "explanation": "填写本业务的唯一编号；系统已生成的编号优先保留，避免与已有记录重复。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "kind",
          "label": "组织层级",
          "explanation": "选择本次操作对应的类别；导入时类别须与下载模板一致，规则和组织类别须与实际对象一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "二级学院",
            "教研室"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "name",
          "label": "组织名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "parent_id",
          "label": "上级组织",
          "explanation": "选择该组织的直属上级，按学校、学院、教研室层级设置，不能选择自己。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "隔离测试学校"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理意见 / 调整原因",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "schooladmin",
      "role": "school",
      "action": "org-form",
      "action_id": ""
    },
    {
      "title": "新增本地账号",
      "fields": [
        {
          "key": "username",
          "label": "登录账号",
          "explanation": "使用学校分配的登录账号，核对是否已经存在。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "staff_no",
          "label": "教师工号",
          "explanation": "使用学校统一工号，保留前导零，不用身份证号代替。",
          "requirement": "当前选填",
          "hints": [
            "普通教师账号必填；非教师管理账号可留空。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "password",
          "label": "临时密码（至少 12 位）",
          "explanation": "设置至少12位且符合系统复杂度要求的临时密码，通过受控方式交接，用户首次登录后修改。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "name",
          "label": "姓名",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "title",
          "label": "职称 / 岗位",
          "explanation": "填写当前真实职称、职业技能等级或岗位，与佐证材料一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "role_id",
          "label": "角色",
          "explanation": "按实际职责选择角色；角色决定可见入口和数据范围。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "学院负责人",
            "教研室负责人",
            "学校管理员",
            "普通教师"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "org_id",
          "label": "所属组织",
          "explanation": "选择实际所属组织；教师、教研室身份归属教研室，学院身份归属学院。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "测试学院一",
            "测试学院二",
            "测试教研室一",
            "测试教研室二",
            "隔离测试学校"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理意见 / 调整原因",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "schooladmin",
      "role": "school",
      "action": "user-form",
      "action_id": ""
    }
  ],
  "policy": [
    {
      "title": "登记学校制度执行口径",
      "fields": [
        {
          "key": "name",
          "label": "规则版本名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "period_id",
          "label": "适用周期",
          "explanation": "选择本次申报、统计或考核对应的周期，注意周期与自然年、学年可能不同。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "2026隔离测试周期"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "cap_mode",
          "label": "单次积分封顶",
          "explanation": "按学校书面解释选择单次积分是否封顶及计算方式。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "人次÷标准人数，最高2",
            "超过标准人数直接按2"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "person_day_unit",
          "label": "人天式单次范围",
          "explanation": "明确人天式计算中“单次”的范围，必须与学校确认的场次或项目口径一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "每个培训日",
            "整个项目期次"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "precision",
          "label": "单元积分及汇总精度",
          "explanation": "填写积分计算及汇总保留的小数位数，保持与学校制度一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "逐单元及汇总均保留两位（须学校确认）"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "rounding",
          "label": "舍入方式",
          "explanation": "按已确认的规则选择舍入方式，不因期望分数改变口径。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "四舍五入"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "auxiliary_overlap",
          "label": "辅助工作重叠",
          "explanation": "明确同一天或同一时段多项辅助工作能否累计，按学校确认口径选择。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "同一工作不得重复计分"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "step_mode",
          "label": "不足计分步长",
          "explanation": "明确不足一个计分步长时如何处理，按学校书面解释选择。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "按比例计算",
            "只计算完整步长"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "annual_model",
          "label": "学院考核模型",
          "explanation": "选择学校正式采用的学院年度考核计算模型，启用前先核对试算。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "收入、人次、成果、资金管理四项"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "bonus_pool",
          "label": "总加分规则",
          "explanation": "明确加分项目如何汇总及受何上限约束，按学校考核办法填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "所有单项加分共用10分上限"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "grade_mode",
          "label": "考核等次",
          "explanation": "选择正式考核等次划分方式，核对分数边界。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "优秀、合格、不合格",
            "优秀、良好、合格、不合格"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "satisfaction_inclusive",
          "label": "恰好95%满意度",
          "explanation": "明确满意度恰好95%时是否满足条件，依据学校对边界值的书面解释选择。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "可以认定成果",
            "不认定，须超过95%"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "achievement_dedup",
          "label": "成果去重",
          "explanation": "明确同一成果重复出现时按何种范围去重，避免重复计分。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "同一成果依据仅取最高等级"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "total_cap",
          "label": "年度总分上限",
          "explanation": "填写学校确认的年度总分上限，核对是否包含加分。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "excellent_from",
          "label": "三等制优秀门槛",
          "explanation": "填写三等制中优秀等次的起始分数，与合格门槛协调。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "qualified_from",
          "label": "三等制合格门槛",
          "explanation": "填写三等制中合格等次的起始分数，应低于优秀门槛。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "title_scope",
          "label": "职称折算范围",
          "explanation": "明确职称折算应用到哪些积分项目，不自行扩大范围。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "仅授课积分",
            "授课及辅助积分"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "organization_basis",
          "label": "学院人次口径",
          "explanation": "明确学院汇总采用人次还是其他确认口径，避免将去重人数与人次混用。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "按项目核算单元汇总，不重复累计教师"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "date_basis",
          "label": "年度归属",
          "explanation": "按学校确认规则选择业务归属年度所依据的日期。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "按结项日期归属"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "title_precision",
          "label": "职称折算小数位",
          "explanation": "填写职称折算结果保留的小数位数，按学校书面口径设置。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "整数",
            "一位",
            "两位",
            "三位",
            "四位"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "title_rounding",
          "label": "职称折算舍入",
          "explanation": "选择职称折算的舍入方式，与学校确认规则一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "四舍五入"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "resubmission_mode",
          "label": "退回补正期限依据",
          "explanation": "根据学校文件明确退回补正的时限计算依据，不自行编造期限。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "按首次申报日期",
            "按补正再次提交日期"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "effective_date",
          "label": "本口径适用开始日期",
          "explanation": "填写该制度口径开始适用的日期，避免覆盖旧版本历史结果。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "calendar_start",
          "label": "校历开始日期",
          "explanation": "填写本校历覆盖的开始日期。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "calendar_end",
          "label": "校历结束日期",
          "explanation": "填写本校历覆盖的结束日期，不早于开始日期。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "holidays",
          "label": "放假日期（每行一个）",
          "explanation": "填写校历区间内的实际放假日期，一行一个；同一天不能同时为放假和补班。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "workdays",
          "label": "周末补班日期（每行一个）",
          "explanation": "填写校历区间内周末补班日期，一行一个，与放假日期不能重复。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "calendar_reference",
          "label": "学校工作日历依据",
          "explanation": "填写学校校历或调休通知名称、编号，作为工作日计算依据。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "interpretation_reference",
          "label": "学校书面解释依据",
          "explanation": "填写学校确认本口径的正式解释文件或会议记录，不能只填“按规定”。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号（选填）",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "schooladmin",
      "role": "school",
      "action": "social-policy-new",
      "action_id": ""
    },
    {
      "title": "学校社会培训审批职责",
      "fields": [
        {
          "key": "duty",
          "label": "选择要调整的职责",
          "explanation": "先选择要配置的审批职责，再选择具备对应有效身份与范围的人员；至少保留能满足本人回避的替代人选。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "二级学院院长",
            "归口学院复审",
            "分管副校长",
            "教学秘书",
            "财务核验",
            "成果核验",
            "纪检核验",
            "委员会评审",
            "培训师资格认定（组织人事部）",
            "外聘培训师备案（教务处）"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "",
          "label": "搜索姓名、工号或账号",
          "explanation": "输入姓名、工号或账号查找人员，再核对组织和有效身份。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "输入姓名或工号",
          "documented": true
        },
        {
          "key": "",
          "label": "学校测试管理员 · 隔离测试学校schooladmin",
          "explanation": "选择具备本职责有效身份的办理人；本人的业务须由其他有权人员办理。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "",
          "label": "测试学院负责人 · 测试学院一collegehead · 无有效审核身份或范围不符",
          "explanation": "选择具备本职责有效身份的办理人；本人的业务须由其他有权人员办理。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "",
          "label": "测试教师一 · 测试教研室一J001 · 无有效审核身份或范围不符",
          "explanation": "选择具备本职责有效身份的办理人；本人的业务须由其他有权人员办理。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "",
          "label": "测试教师二 · 测试教研室二J002 · 无有效审核身份或范围不符",
          "explanation": "选择具备本职责有效身份的办理人；本人的业务须由其他有权人员办理。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "",
          "label": "测试教研室二负责人 · 测试教研室二otherdept · 无有效审核身份或范围不符",
          "explanation": "选择具备本职责有效身份的办理人；本人的业务须由其他有权人员办理。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "",
          "label": "测试教研室负责人 · 测试教研室一depthead · 无有效审核身份或范围不符",
          "explanation": "选择具备本职责有效身份的办理人；本人的业务须由其他有权人员办理。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "",
          "label": "继续教育学院审核人 · 隔离测试学校reviewer",
          "explanation": "选择具备本职责有效身份的办理人；本人的业务须由其他有权人员办理。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号（选填）",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "schooladmin",
      "role": "school",
      "action": "social-duties",
      "action_id": ""
    }
  ],
  "rules": [
    {
      "title": "新建考核周期",
      "fields": [
        {
          "key": "name",
          "label": "周期名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "start_date",
          "label": "开始日期",
          "explanation": "填写本次业务实际开始日期，结束日期不得早于开始日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "end_date",
          "label": "结束日期",
          "explanation": "填写本次业务实际结束日期，与方案或完成记录一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理意见 / 调整原因",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "schooladmin",
      "role": "school",
      "action": "period-form",
      "action_id": ""
    },
    {
      "title": "新建组织考核规则",
      "fields": [
        {
          "key": "target_kind",
          "label": "考核对象",
          "explanation": "选择规则或考核针对的教研室、学院或学校，核对当前操作层级。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "教研室",
            "二级学院",
            "学校"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "name",
          "label": "规则名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "period_id",
          "label": "适用周期",
          "explanation": "选择本次申报、统计或考核对应的周期，注意周期与自然年、学年可能不同。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "2026隔离测试周期"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "label",
          "label": "指标名称",
          "explanation": "填写学校考核细则中的指标名称，名称应能明确表达考核内容。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "source",
          "label": "数据来源",
          "explanation": "选择该指标实际取数的来源，核对原始数据与统计范围，不使用未经确认的来源。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "授课学时",
            "课程人次",
            "归属培训收入",
            "参与教师数",
            "培训项目数",
            "课程数",
            "有效资质数",
            "本期积分",
            "已归档教师考核平均分"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "weight",
          "label": "考核权重",
          "explanation": "按经确认的考核规则填写权重，核对合计及页面单位。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最小值：0",
            "最大值：100",
            "步长：0.01"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "target",
          "label": "目标值",
          "explanation": "填写学校确认的达标值，不能用演示数值替代正式标准。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最小值：0.0001",
            "步长：0.0001"
          ],
          "options": [],
          "example": "请按学校考核细则填写",
          "documented": true
        },
        {
          "key": "method",
          "label": "评分方式",
          "explanation": "按学校确认的规则选择计算方法；切换方法后只填写当前适用的参数。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "达标比例 × 权重",
            "原始值 × 系数",
            "分档",
            "扣分",
            "加分"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "tiers",
          "label": "分档（门槛:分值，逗号分隔）",
          "explanation": "按学校确认的分档设置门槛和分值。格式示例（虚构）：60:10,80:20；实际门槛和分值以学校文件为准。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "分档 如 0:20, 8:60, 20:100",
          "documented": true
        },
        {
          "key": "tier_mode",
          "label": "分档计分方式",
          "explanation": "按学校确认的办法选择分档计分方式，核对是否只取达到的档位或按各档累计。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [],
          "options": [
            "命中档直接得分",
            "命中档系数"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "base",
          "label": "起始分",
          "explanation": "填写扣分或加分计算的起始分数，按正式规则设置。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "步长：0.01"
          ],
          "options": [],
          "example": "起始分",
          "documented": true
        },
        {
          "key": "unit",
          "label": "计数单位",
          "explanation": "填写每次触发扣分或加分的计数单位，按学校确认的规则设置。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "最小值：0.0001",
            "步长：0.0001"
          ],
          "options": [],
          "example": "每满多少计一次",
          "documented": true
        },
        {
          "key": "per_unit",
          "label": "每次扣/加分",
          "explanation": "填写每个计数单位对应的扣分或加分值，核对上限及保底值。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "每次扣/加分",
          "documented": true
        },
        {
          "key": "floor",
          "label": "保底",
          "explanation": "填写本项最低可得分数或保底值，按正式规则设置，不自行提高。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "步长：0.01"
          ],
          "options": [],
          "example": "保底",
          "documented": true
        },
        {
          "key": "cap",
          "label": "封顶",
          "explanation": "填写该项上限，明确零是否表示有效零值，不能凭经验填写。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "封顶",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理意见 / 调整原因",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "schooladmin",
      "role": "school",
      "action": "org-rule-form",
      "action_id": "",
      "scope": "#content",
      "setup": []
    },
    {
      "title": "新建规则版本",
      "fields": [
        {
          "key": "kind",
          "label": "规则类型",
          "explanation": "选择本次操作对应的类别；导入时类别须与下载模板一致，规则和组织类别须与实际对象一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "教师积分",
            "三级考核"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "name",
          "label": "规则名称",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "period_id",
          "label": "适用周期",
          "explanation": "选择本次申报、统计或考核对应的周期，注意周期与自然年、学年可能不同。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "2026隔离测试周期"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "label",
          "label": "指标名称",
          "explanation": "填写学校考核细则中的指标名称，名称应能明确表达考核内容。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "授课贡献",
          "documented": true
        },
        {
          "key": "source",
          "label": "指标数据来源",
          "explanation": "选择该指标实际取数的来源，核对原始数据与统计范围，不使用未经确认的来源。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "授课学时",
            "课程人次",
            "归属培训收入",
            "有效资质数",
            "上一已归档考核分",
            "授课学分（教务+超星）"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "factor",
          "label": "积分系数",
          "explanation": "填写经确认的计算系数，先试算核对再启用。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.0001"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "weight",
          "label": "考核权重",
          "explanation": "按经确认的考核规则填写权重，核对合计及页面单位。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "最小值：0",
            "最大值：100",
            "步长：0.01"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "target",
          "label": "考核达标值",
          "explanation": "填写学校确认的达标值，不能用演示数值替代正式标准。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "最小值：0.0001",
            "步长：0.0001"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cap",
          "label": "上限 / 封顶",
          "explanation": "填写该项上限，明确零是否表示有效零值，不能凭经验填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "不限",
          "documented": true
        },
        {
          "key": "method",
          "label": "评分方式",
          "explanation": "按学校确认的规则选择计算方法；切换方法后只填写当前适用的参数。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "达标比例 × 权重",
            "原始值 × 系数",
            "分档",
            "扣分",
            "加分"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "tiers",
          "label": "分档（门槛:分值，逗号分隔）",
          "explanation": "按学校确认的分档设置门槛和分值。格式示例（虚构）：60:10,80:20；实际门槛和分值以学校文件为准。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "分档 如 0:20, 8:60, 20:100",
          "documented": true
        },
        {
          "key": "tier_mode",
          "label": "分档计分方式",
          "explanation": "按学校确认的办法选择分档计分方式，核对是否只取达到的档位或按各档累计。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [],
          "options": [
            "命中档直接得分",
            "命中档系数"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "base",
          "label": "起始分",
          "explanation": "填写扣分或加分计算的起始分数，按正式规则设置。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "步长：0.01"
          ],
          "options": [],
          "example": "起始分",
          "documented": true
        },
        {
          "key": "unit",
          "label": "计数单位",
          "explanation": "填写每次触发扣分或加分的计数单位，按学校确认的规则设置。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "最小值：0.0001",
            "步长：0.0001"
          ],
          "options": [],
          "example": "每满多少计一次",
          "documented": true
        },
        {
          "key": "per_unit",
          "label": "每次扣/加分",
          "explanation": "填写每个计数单位对应的扣分或加分值，核对上限及保底值。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "每次扣/加分",
          "documented": true
        },
        {
          "key": "floor",
          "label": "保底",
          "explanation": "填写本项最低可得分数或保底值，按正式规则设置，不自行提高。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "步长：0.01"
          ],
          "options": [],
          "example": "保底",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理意见 / 调整原因",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "schooladmin",
      "role": "school",
      "action": "rule-form",
      "action_id": "",
      "scope": "#content",
      "setup": []
    }
  ],
  "notices": [
    {
      "title": "发布通知公告",
      "fields": [
        {
          "key": "title",
          "label": "通知标题",
          "explanation": "填写当前真实职称、职业技能等级或岗位，与佐证材料一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "category",
          "label": "分类",
          "explanation": "选择最符合本事项的业务类别，按学校统一分类使用。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "业务通知",
            "政策通知",
            "操作通知"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "",
          "label": "全选",
          "explanation": "选择具备本职责有效身份的办理人；本人的业务须由其他有权人员办理。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "org_ids",
          "label": "测试学院一二级学院",
          "explanation": "选择通知实际适用的组织范围，发布前核对，避免向无关人员发布。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "org_ids",
          "label": "测试学院二二级学院",
          "explanation": "选择通知实际适用的组织范围，发布前核对，避免向无关人员发布。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "org_ids",
          "label": "测试教研室一教研室",
          "explanation": "选择通知实际适用的组织范围，发布前核对，避免向无关人员发布。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "org_ids",
          "label": "测试教研室二教研室",
          "explanation": "选择通知实际适用的组织范围，发布前核对，避免向无关人员发布。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "org_ids",
          "label": "隔离测试学校学校管理部门",
          "explanation": "选择通知实际适用的组织范围，发布前核对，避免向无关人员发布。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "body",
          "label": "通知正文",
          "explanation": "写清通知对象、事项、时间、材料要求和联系部门，发布前核对正文。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "published",
          "label": "发布状态",
          "explanation": "确认通知内容和范围后再选择发布；草稿不等于已通知相关人员。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理原因",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        }
      ],
      "user": "schooladmin",
      "role": "school",
      "action": "notice-form",
      "action_id": ""
    }
  ],
  "projects": [
    {
      "title": "提交项目结项",
      "fields": [
        {
          "key": "closed_on",
          "label": "结项日期",
          "explanation": "填写实际结项日期，与完成记录和结项报告一致。",
          "requirement": "当前必填",
          "hints": [
            "已按培训结束日期带出，如实际结项日期不同请修改。"
          ],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "satisfaction",
          "label": "满意度（百分比）",
          "explanation": "填写实际调查的满意度百分比，与调查汇总依据一致，不填写小数比例或预期值。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最小值：0",
            "最大值：100",
            "步长：0.01"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "location",
          "label": "培训地点类型",
          "explanation": "填写活动或基地的实际地点，校区、楼宇或校外地址应足够明确。",
          "requirement": "当前必填",
          "hints": [
            "已按项目申报的培训场地带出。"
          ],
          "limits": [],
          "options": [
            "校内",
            "校外"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "outcome_report",
          "label": "成果报告",
          "explanation": "说明已完成的培训内容、实际成果及对应佐证。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 200 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "rectification",
          "label": "整改报告与期限",
          "explanation": "写清存在的问题、整改措施、责任人、完成期限及整改结果；尚未完成的说明当前进展和后续安排。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "rectification_due",
          "label": "整改办理期限",
          "explanation": "有整改要求时填写明确的整改办理期限，按审核意见确定并跟踪完成。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "actual_income",
          "label": "财务确认到账收入（元）",
          "explanation": "按结算依据填写实际收入，与财务核验材料一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "funding_source",
          "label": "财务确认的资金来源",
          "explanation": "按财务确认的资金来源选择；政府专项和其他培训收入执行不同核验要求。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "其他培训收入",
            "政府专项培训资金"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "finance_reference",
          "label": "财务核验凭据",
          "explanation": "填写可追溯的财务凭证或结算依据。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "implicit_cost",
          "label": "隐性成本（元）",
          "explanation": "填写已核实的隐性成本金额，单位为元，与财务依据一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "settlement_on",
          "label": "经费结算日期",
          "explanation": "填写实际结算日期，不以申报日期代替。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "例：2026-10-20",
          "documented": true
        },
        {
          "key": "retained",
          "label": "学校留存（元）",
          "explanation": "填写财务核实的学校留存金额，单位为元；核对页面的收入分配比例提示，不填写百分数。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "personnel",
          "label": "校内人员支出（元）",
          "explanation": "填写财务核实的校内人员支出金额，单位为元；核对页面分配上限，不填写百分数。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最小值：0",
            "步长：0.01"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "funding_basis",
          "label": "政府专项主管部门规定及财务核验依据",
          "explanation": "专项资金有收入时必填；按主管部门规定专款专用，不套用其他收入比例",
          "requirement": "当前选填",
          "hints": [
            "专项资金有收入时必填；按主管部门规定专款专用，不套用其他收入比例"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "",
          "label": "以下材料全部已核对",
          "explanation": "选择具备本职责有效身份的办理人；本人的业务须由其他有权人员办理。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "checked_plan",
          "label": "培训方案",
          "explanation": "逐项核对对应材料，确认清晰完整且内容一致后再勾选；缺少材料时先补齐，不用勾选代替真实核验。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "checked_filing_form",
          "label": "学校制式备案登记表",
          "explanation": "逐项核对对应材料，确认清晰完整且内容一致后再勾选；缺少材料时先补齐，不用勾选代替真实核验。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "checked_roster",
          "label": "学员名册",
          "explanation": "逐项核对对应材料，确认清晰完整且内容一致后再勾选；缺少材料时先补齐，不用勾选代替真实核验。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "checked_attendance",
          "label": "实名签到",
          "explanation": "逐项核对对应材料，确认清晰完整且内容一致后再勾选；缺少材料时先补齐，不用勾选代替真实核验。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "checked_hours",
          "label": "学时记录",
          "explanation": "逐项核对对应材料，确认清晰完整且内容一致后再勾选；缺少材料时先补齐，不用勾选代替真实核验。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "checked_process",
          "label": "培训过程影像",
          "explanation": "逐项核对对应材料，确认清晰完整且内容一致后再勾选；缺少材料时先补齐，不用勾选代替真实核验。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "checked_assessment",
          "label": "结业考核",
          "explanation": "逐项核对对应材料，确认清晰完整且内容一致后再勾选；缺少材料时先补齐，不用勾选代替真实核验。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "checked_outcomes",
          "label": "培训成果",
          "explanation": "逐项核对对应材料，确认清晰完整且内容一致后再勾选；缺少材料时先补齐，不用勾选代替真实核验。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号（选填）",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "collegehead",
      "role": "college",
      "action": "social-close",
      "action_id": "",
      "scope": "#modal-root",
      "setup": [
        {
          "action": "social-detail",
          "id": "social_project|d2a929a1-b705-4d87-85cb-e994b576f7a9"
        }
      ]
    }
  ],
  "recognition": [
    {
      "title": "本人积分申报",
      "fields": [
        {
          "key": "project_id",
          "label": "选择关联项目",
          "explanation": "选择已经满足申报条件、且与本人工作对应的培训项目；没有可选项目时先核对结项及参训明细。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "社区技能培训积分填写示范 · HELP-PROJECT-closed-1792666032 · 第一期"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "period_id",
          "label": "认定周期",
          "explanation": "选择本次申报、统计或考核对应的周期，注意周期与自然年、学年可能不同。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "2026隔离测试周期"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "policy_id",
          "label": "制度执行口径",
          "explanation": "选择本年度经确认并适用的制度执行口径版本。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "隔离确认口径 · 已确认启用"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "file",
          "label": "学校制式积分认定表及其他材料（可一次选多份）",
          "explanation": "按本事项上传清晰、完整且与填写内容一致的材料；逐份检查上传结果。",
          "requirement": "当前必填",
          "hints": [
            "支持 .jpg、.png、.pdf，单个文件最大 10 兆字节；每份单独上传并显示结果，失败的只需补传那一份。单个申报最多 50 份。"
          ],
          "limits": [
            "允许文件类型：.pdf,.png,.jpg,.jpeg",
            "可多选",
            "最多 50 份（含已上传）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "申报说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "basis",
          "label": "依据说明或材料编号（选填）",
          "explanation": "填写依据文件名称、编号或材料位置，便于审核人员核查；不填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "例：学院会议纪要〔2026〕3号、协议编号、材料编号",
          "documented": true
        }
      ],
      "user": "teacher",
      "role": "teacher",
      "action": "social-claim-new",
      "action_id": "",
      "scope": "#content",
      "setup": []
    }
  ],
  "trainers": [
    {
      "title": "登记外聘培训师",
      "fields": [
        {
          "key": "name",
          "label": "姓名",
          "explanation": "填写事项的完整名称，与方案、证书或认定文件一致，便于后续检索。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "unit",
          "label": "工作单位",
          "explanation": "填写外聘人员实际任职单位全称，与资质及授课经历材料一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "title",
          "label": "职称或职务",
          "explanation": "填写当前真实职称、职业技能等级或岗位，与佐证材料一致。",
          "requirement": "当前选填",
          "hints": [
            "填写本人现有职称、职业技能等级或岗位。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "specialty",
          "label": "专业特长",
          "explanation": "填写能够承担培训的专业特长，例如茶艺、电商运营；与培训业务类别分开。",
          "requirement": "当前选填",
          "hints": [
            "例：茶艺、电商运营、家政服务；与下面的“培训业务类别”分开填写。"
          ],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir_subsidy",
          "label": "补贴性培训",
          "explanation": "按本人实际能够承担的培训业务类别勾选，可多选；类别与专业特长分别填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir_enterprise",
          "label": "社会化自主培训",
          "explanation": "按本人实际能够承担的培训业务类别勾选，可多选；类别与专业特长分别填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir_community",
          "label": "社区公益培训",
          "explanation": "按本人实际能够承担的培训业务类别勾选，可多选；类别与专业特长分别填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir_rural",
          "label": "对口帮扶培训",
          "explanation": "按本人实际能够承担的培训业务类别勾选，可多选；类别与专业特长分别填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir_other",
          "label": "其他非学历培训",
          "explanation": "按本人实际能够承担的培训业务类别勾选，可多选；类别与专业特长分别填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir_one_skill",
          "label": "“一人一技”专项",
          "explanation": "按本人实际能够承担的培训业务类别勾选，可多选；类别与专业特长分别填写。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "qualification_basis",
          "label": "资格依据",
          "explanation": "说明职称、职业资格或行业经历，以及它们能够支持的培训方向。",
          "requirement": "当前必填",
          "hints": [
            "说明职称、职业资格或行业经历，以及它们能够支持的培训方向。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "培训师头像（选填）",
          "explanation": "可选展示图片，不代替业务佐证附件。请使用与课程、基地或师资相符的图片。",
          "requirement": "当前选填",
          "hints": [
            "选填，PNG（图片） 或 JPG（照片），不超过 5 MB（兆字节）；仅用于展示，不能代替证明材料。"
          ],
          "limits": [
            "允许文件类型：.png,.jpg,.jpeg,image/png,image/jpeg",
            "最多 1 份（含已上传）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "experience",
          "label": "授课经历",
          "explanation": "写清近年授课项目、承担工作、时间及学员情况，必要时提供对应依据。",
          "requirement": "当前选填",
          "hints": [
            "可填写近年授课项目、培训期数和学员人次。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "本次申报说明",
          "explanation": "说明本次申请、补正或办理的具体原因。退回时写清哪项有问题、需要如何补齐；常用语中的“请补充”必须替换。",
          "requirement": "当前选填",
          "hints": [
            "可补充说明本次申报的专业特长与相关依据。"
          ],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        }
      ],
      "user": "collegehead",
      "role": "college",
      "action": "app-trainer-new",
      "action_id": "external",
      "scope": "#content",
      "setup": []
    }
  ]
};

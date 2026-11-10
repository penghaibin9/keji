// 真实隔离浏览器采集，不含输入值。
export const HELP_FORMS={
  "apply_course": [
    {
      "title": "新填一门培训课程",
      "fields": [
        {
          "key": "code",
          "label": "课程编号",
          "explanation": "填写课程材料上的编号，例如 SOC-2026-001；被退回补正时保留原来的编号。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "SOC-2026-001",
          "documented": true
        },
        {
          "key": "name",
          "label": "课程名称",
          "explanation": "填写课程的完整名称，与课程材料一致，例如“社区营养配餐”。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "社区营养配餐",
          "documented": true
        },
        {
          "key": "hours",
          "label": "学时",
          "explanation": "按培训实际安排填写学时，可以填 0.5 学时这样的半学时；不要把分钟数直接填进来。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能填负数",
            "可以填 0.5 学时这样的半学时"
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
          "explanation": "按课程实际安排选择思政属性。",
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
          "explanation": "说明面向哪些社会学员、培训什么内容、学完能掌握什么技能。",
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
          "key": "project_code",
          "label": "选择关联项目",
          "explanation": "选择这门课所属的培训项目，系统自动带出项目编号，不用手填；页面标为选填时可以不关联。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "package",
          "label": "培训包",
          "explanation": "只有按成套教学包开发的课程才勾选。",
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
          "explanation": "属于“一人一技”专项培训行动时勾选，勾选后要填写重点群体与行动对接。",
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
          "explanation": "勾选“一人一技”专项时必填：写清面向哪些重点群体、怎样对接行动，例如“脱贫人口、返乡青年；结业后推荐就业”。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "脱贫人口、返乡青年；对接“一人一技”行动，学员结业后推荐就业",
          "documented": true
        },
        {
          "key": "cw_checked",
          "label": "课件审查状态",
          "explanation": "学院已经做过课件审查、有审查记录时才勾选。",
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
          "explanation": "勾选了课件审查状态时必填：填写实际做审查的人或审查组，例如“学院课件审查组”。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "学院课件审查组",
          "documented": true
        },
        {
          "key": "cw_on",
          "label": "审查日期",
          "explanation": "填写课件审查记录上的日期。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cw_ref",
          "label": "审查记录编号",
          "explanation": "填写审查记录编号，方便核查；没有编号可以不填。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "KJ-2026-03",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "课程封面（选填）",
          "explanation": "可以上传一张课程展示图片，只用于列表展示，不能代替证明材料。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "支持 PNG、JPG，单个不超过 5MB",
            "只能上传 1 份"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "本次申报说明",
          "explanation": "写清申报依据，或需要审核人员了解的情况；被退回后重新提交时，说明按意见改了哪些地方。",
          "requirement": "当前选填",
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
      "action": "teacher-apply",
      "action_id": "courses|app-course-new"
    },
    {
      "title": "新填一门培训课程",
      "fields": [
        {
          "key": "teacher_id",
          "label": "主讲教师（输入工号或姓名检索）",
          "explanation": "输入主讲教师的姓名或工号搜索后选择，核对工号，不要选成同名的人。只能选你授权范围内的老师。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "code",
          "label": "课程编号",
          "explanation": "填写课程材料上的编号，例如 SOC-2026-001；被退回补正时保留原来的编号。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "SOC-2026-001",
          "documented": true
        },
        {
          "key": "name",
          "label": "课程名称",
          "explanation": "填写课程的完整名称，与课程材料一致，例如“社区营养配餐”。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "社区营养配餐",
          "documented": true
        },
        {
          "key": "hours",
          "label": "学时",
          "explanation": "按培训实际安排填写学时，可以填 0.5 学时这样的半学时；不要把分钟数直接填进来。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能填负数",
            "可以填 0.5 学时这样的半学时"
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
          "explanation": "按课程实际安排选择思政属性。",
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
          "explanation": "说明面向哪些社会学员、培训什么内容、学完能掌握什么技能。",
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
          "key": "project_code",
          "label": "选择关联项目",
          "explanation": "选择这门课所属的培训项目，系统自动带出项目编号，不用手填；页面标为选填时可以不关联。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "package",
          "label": "培训包",
          "explanation": "只有按成套教学包开发的课程才勾选。",
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
          "explanation": "属于“一人一技”专项培训行动时勾选，勾选后要填写重点群体与行动对接。",
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
          "explanation": "勾选“一人一技”专项时必填：写清面向哪些重点群体、怎样对接行动，例如“脱贫人口、返乡青年；结业后推荐就业”。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "脱贫人口、返乡青年；对接“一人一技”行动，学员结业后推荐就业",
          "documented": true
        },
        {
          "key": "cw_checked",
          "label": "课件审查状态",
          "explanation": "学院已经做过课件审查、有审查记录时才勾选。",
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
          "explanation": "勾选了课件审查状态时必填：填写实际做审查的人或审查组，例如“学院课件审查组”。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "学院课件审查组",
          "documented": true
        },
        {
          "key": "cw_on",
          "label": "审查日期",
          "explanation": "填写课件审查记录上的日期。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cw_ref",
          "label": "审查记录编号",
          "explanation": "填写审查记录编号，方便核查；没有编号可以不填。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "KJ-2026-03",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "课程封面（选填）",
          "explanation": "可以上传一张课程展示图片，只用于列表展示，不能代替证明材料。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "支持 PNG、JPG，单个不超过 5MB",
            "只能上传 1 份"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "本次申报说明",
          "explanation": "写清申报依据，或需要审核人员了解的情况；被退回后重新提交时，说明按意见改了哪些地方。",
          "requirement": "当前选填",
          "hints": [],
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
          "explanation": "填写项目材料上的编号；不清楚时先向学院核实，不要自己编。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "SOC-2026-01",
          "documented": true
        },
        {
          "key": "name",
          "label": "项目名称",
          "explanation": "填写项目的完整名称，与培训方案一致，例如“2026年社区茶艺公益培训”。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "2026年社区茶艺公益培训",
          "documented": true
        },
        {
          "key": "cohort",
          "label": "项目期次",
          "explanation": "填写项目期次，例如“第一期”；同一项目分几期举办时按实际期次填写。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "第一期",
          "documented": true
        },
        {
          "key": "owner_view",
          "label": "项目负责人",
          "explanation": "老师本人申报的项目，负责人就是本人，承办学院是本人所在学院，不用另外选择。",
          "requirement": "自动带出／只读",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "category",
          "label": "培训类别（单选）",
          "explanation": "按项目实际性质选择培训类别。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud",
          "label": "受众群体",
          "explanation": "按本次培训实际面向的人群勾选，可以多选；没有合适选项时在“其他”里补充。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "企业职工",
            "社区居民",
            "退役军人",
            "新型职业农民",
            "中小学教师",
            "机关事业单位人员",
            "待业及转岗人员",
            "老年学员"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "audience_other",
          "label": "其他受众群体",
          "explanation": "上面的选项都不合适时，在这里补充其他培训对象；没有可以不填。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 200 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "svc",
          "label": "服务面向类型",
          "explanation": "按项目实际服务方向勾选，可以多选，相关依据在培训方案里说明。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "国家战略",
            "区域发展",
            "行业发展",
            "其他"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "high_risk",
          "label": "高风险项目",
          "explanation": "项目涉及高空、水上、用电、外出等高风险活动时勾选，并落实对应的审批和安全措施。",
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
          "explanation": "可以上传一张项目展示图片，只用于列表展示，不能代替证明材料。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "支持 PNG、JPG，单个不超过 5MB",
            "只能上传 1 份"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "proof_files",
          "label": "项目方案材料（可一次选多份）",
          "explanation": "上传培训方案等项目材料。现在可以先不传，保存后在详情里补；提交审核前至少要有一份。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "支持 PDF、PNG、JPG，单个不超过 10MB",
            "可以一次选多个文件",
            "最多 50 份（含已上传的）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "start_date",
          "label": "开始日期",
          "explanation": "填写实际开始日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "end_date",
          "label": "结束日期",
          "explanation": "填写实际结束日期，不能早于开始日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "expected_income",
          "label": "预计收入（元，公益类填0）",
          "explanation": "填写培训方案里的预计收入，单位为元；公益类项目填 0。结项时另填实际到账收入。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "0 或 30000",
          "documented": true
        },
        {
          "key": "expected_participants",
          "label": "预计人次",
          "explanation": "填写方案预计的培训人次；结项时再核对实际人次。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能填负数",
            "只能填整数"
          ],
          "options": [],
          "example": "120",
          "documented": true
        },
        {
          "key": "expected_outcomes",
          "label": "预期成果",
          "explanation": "写清培训结束后学员能掌握什么技能、项目预计取得什么成果，以及怎样核验；不要只写“完成培训”。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 200 字"
          ],
          "options": [],
          "example": "学员掌握基础茶艺，80%以上取得结业证书",
          "documented": true
        },
        {
          "key": "one_skill",
          "label": "“一人一技”专项",
          "explanation": "属于“一人一技”专项培训行动时勾选，勾选后要填写重点群体与行动对接。",
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
          "explanation": "按上级和学校要求选择是否需要报省；选“需要”时要在下面写明依据。",
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
          "explanation": "选择“需要报省”时必填：写明省级专项文件、报送口径或学校要求。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "湘人社〔2026〕12号文，须在结项后15个工作日内报送",
          "documented": true
        },
        {
          "key": "target_groups",
          "label": "重点群体与行动对接",
          "explanation": "勾选“一人一技”专项时必填：写清面向哪些重点群体、怎样对接行动，例如“脱贫人口、返乡青年；结业后推荐就业”。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "脱贫人口、退役军人；对接“一人一技”行动",
          "documented": true
        },
        {
          "key": "total_hours",
          "label": "总学时",
          "explanation": "填写项目的总学时；草稿可以先空着，提交学院审批前必须填。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "可以填 0.5 学时这样的半学时"
          ],
          "options": [],
          "example": "32",
          "documented": true
        },
        {
          "key": "video_minutes",
          "label": "视频资源总时长（分钟）",
          "explanation": "填写项目建设的视频资源合计时长，单位是分钟；没有填 0。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "只能填整数"
          ],
          "options": [],
          "example": "199",
          "documented": true
        },
        {
          "key": "base_count",
          "label": "实践教学基地数量（个）",
          "explanation": "填写项目使用的实践教学基地数量；没有填 0。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "只能填整数"
          ],
          "options": [],
          "example": "2",
          "documented": true
        },
        {
          "key": "tm",
          "label": "教学实施方式",
          "explanation": "按实际采用的教学方式勾选，可以多选，与培训方案一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "课堂教学",
            "案例教学",
            "现场教学",
            "实地考察",
            "交流研讨",
            "实验实训",
            "岗位实习",
            "学习者互助",
            "其他"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "venue_type",
          "label": "培训场地",
          "explanation": "按实际上课地点选择校内培训基地、其他校内场所或校外；选校外要另外说明理由。",
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
          "explanation": "填写能找得到的具体地点，例如基地名称、楼栋教室或校外详细地址。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "venue_reason",
          "label": "校外培训的外出理由（一事一议）",
          "explanation": "培训场地选“校外”时必填：说明为什么不能在校内开展。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "茶叶采摘与制作必须在茶园现场教学，校内没有条件",
          "documented": true
        },
        {
          "key": "venue_ref",
          "label": "议定文号或会议日期",
          "explanation": "培训场地选“校外”时必填：填写学校一事一议的会议日期或文号。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "校长办公会 2026-08-20 或 校办〔2026〕15号",
          "documented": true
        },
        {
          "key": "mode",
          "label": "核算方式（单选）",
          "explanation": "按学校确认的计分方式选择模块式或人天式，与项目实际组织方式一致。",
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
          "explanation": "按项目实际内容选择技术类、讲座类等标准班类型；这一项影响积分计算。",
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
          "explanation": "按认定依据选择项目层级：企业定制通常选市级，社区、免费帮扶通常选校级；不要自行提高等级。",
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
          "explanation": "按实际情况选择是否异地送教、全天实操或脱产培训，并保留相应依据。",
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
          "explanation": "项目层级高于常规时必填：填写正式认定文件名称和文号，提交后由归口核验。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "省人社厅专项培训认定文件〔2026〕8号",
          "documented": true
        },
        {
          "key": "auxiliary_standard",
          "label": "随项目备案的辅助积分细则",
          "explanation": "写明随项目备案的辅助工作积分细则：哪些工作、每天多少分、依据是什么。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "班主任每天0.5分，每人每天不超过1分",
          "documented": true
        },
        {
          "key": "auxiliary_daily_cap",
          "label": "个人辅助积分每日上限",
          "explanation": "填写学校确认的个人辅助积分每日上限，不要照抄示例。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "1",
          "documented": true
        },
        {
          "key": "reason",
          "label": "申报说明",
          "explanation": "写清申报的理由，以及需要审核人员了解的情况；没有特别情况可以简要说明。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "填写项目材料上的编号；不清楚时先向学院核实，不要自己编。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "SOC-2026-01",
          "documented": true
        },
        {
          "key": "name",
          "label": "项目名称",
          "explanation": "填写项目的完整名称，与培训方案一致，例如“2026年社区茶艺公益培训”。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "2026年社区茶艺公益培训",
          "documented": true
        },
        {
          "key": "cohort",
          "label": "项目期次",
          "explanation": "填写项目期次，例如“第一期”；同一项目分几期举办时按实际期次填写。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "第一期",
          "documented": true
        },
        {
          "key": "org_id",
          "label": "承办学院",
          "explanation": "选择这项业务所属的学院。",
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
          "explanation": "输入项目负责人的姓名或工号搜索后选择。只能选你授权范围内的老师。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "category",
          "label": "培训类别（单选）",
          "explanation": "按项目实际性质选择培训类别。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "aud",
          "label": "受众群体",
          "explanation": "按本次培训实际面向的人群勾选，可以多选；没有合适选项时在“其他”里补充。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "企业职工",
            "社区居民",
            "退役军人",
            "新型职业农民",
            "中小学教师",
            "机关事业单位人员",
            "待业及转岗人员",
            "老年学员"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "audience_other",
          "label": "其他受众群体",
          "explanation": "上面的选项都不合适时，在这里补充其他培训对象；没有可以不填。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 200 字"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "svc",
          "label": "服务面向类型",
          "explanation": "按项目实际服务方向勾选，可以多选，相关依据在培训方案里说明。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "国家战略",
            "区域发展",
            "行业发展",
            "其他"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "high_risk",
          "label": "高风险项目",
          "explanation": "项目涉及高空、水上、用电、外出等高风险活动时勾选，并落实对应的审批和安全措施。",
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
          "explanation": "可以上传一张项目展示图片，只用于列表展示，不能代替证明材料。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "支持 PNG、JPG，单个不超过 5MB",
            "只能上传 1 份"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "proof_files",
          "label": "项目方案材料（可一次选多份）",
          "explanation": "上传培训方案等项目材料。现在可以先不传，保存后在详情里补；提交审核前至少要有一份。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "支持 PDF、PNG、JPG，单个不超过 10MB",
            "可以一次选多个文件",
            "最多 50 份（含已上传的）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "start_date",
          "label": "开始日期",
          "explanation": "填写实际开始日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "end_date",
          "label": "结束日期",
          "explanation": "填写实际结束日期，不能早于开始日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "expected_income",
          "label": "预计收入（元，公益类填0）",
          "explanation": "填写培训方案里的预计收入，单位为元；公益类项目填 0。结项时另填实际到账收入。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "0 或 30000",
          "documented": true
        },
        {
          "key": "expected_participants",
          "label": "预计人次",
          "explanation": "填写方案预计的培训人次；结项时再核对实际人次。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能填负数",
            "只能填整数"
          ],
          "options": [],
          "example": "120",
          "documented": true
        },
        {
          "key": "expected_outcomes",
          "label": "预期成果",
          "explanation": "写清培训结束后学员能掌握什么技能、项目预计取得什么成果，以及怎样核验；不要只写“完成培训”。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多 200 字"
          ],
          "options": [],
          "example": "学员掌握基础茶艺，80%以上取得结业证书",
          "documented": true
        },
        {
          "key": "one_skill",
          "label": "“一人一技”专项",
          "explanation": "属于“一人一技”专项培训行动时勾选，勾选后要填写重点群体与行动对接。",
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
          "explanation": "按上级和学校要求选择是否需要报省；选“需要”时要在下面写明依据。",
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
          "explanation": "选择“需要报省”时必填：写明省级专项文件、报送口径或学校要求。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "湘人社〔2026〕12号文，须在结项后15个工作日内报送",
          "documented": true
        },
        {
          "key": "target_groups",
          "label": "重点群体与行动对接",
          "explanation": "勾选“一人一技”专项时必填：写清面向哪些重点群体、怎样对接行动，例如“脱贫人口、返乡青年；结业后推荐就业”。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "脱贫人口、退役军人；对接“一人一技”行动",
          "documented": true
        },
        {
          "key": "total_hours",
          "label": "总学时",
          "explanation": "填写项目的总学时；草稿可以先空着，提交学院审批前必须填。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "可以填 0.5 学时这样的半学时"
          ],
          "options": [],
          "example": "32",
          "documented": true
        },
        {
          "key": "video_minutes",
          "label": "视频资源总时长（分钟）",
          "explanation": "填写项目建设的视频资源合计时长，单位是分钟；没有填 0。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "只能填整数"
          ],
          "options": [],
          "example": "199",
          "documented": true
        },
        {
          "key": "base_count",
          "label": "实践教学基地数量（个）",
          "explanation": "填写项目使用的实践教学基地数量；没有填 0。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "只能填整数"
          ],
          "options": [],
          "example": "2",
          "documented": true
        },
        {
          "key": "tm",
          "label": "教学实施方式",
          "explanation": "按实际采用的教学方式勾选，可以多选，与培训方案一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "课堂教学",
            "案例教学",
            "现场教学",
            "实地考察",
            "交流研讨",
            "实验实训",
            "岗位实习",
            "学习者互助",
            "其他"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "venue_type",
          "label": "培训场地",
          "explanation": "按实际上课地点选择校内培训基地、其他校内场所或校外；选校外要另外说明理由。",
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
          "explanation": "填写能找得到的具体地点，例如基地名称、楼栋教室或校外详细地址。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "venue_reason",
          "label": "校外培训的外出理由（一事一议）",
          "explanation": "培训场地选“校外”时必填：说明为什么不能在校内开展。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "茶叶采摘与制作必须在茶园现场教学，校内没有条件",
          "documented": true
        },
        {
          "key": "venue_ref",
          "label": "议定文号或会议日期",
          "explanation": "培训场地选“校外”时必填：填写学校一事一议的会议日期或文号。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "校长办公会 2026-08-20 或 校办〔2026〕15号",
          "documented": true
        },
        {
          "key": "mode",
          "label": "核算方式（单选）",
          "explanation": "按学校确认的计分方式选择模块式或人天式，与项目实际组织方式一致。",
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
          "explanation": "按项目实际内容选择技术类、讲座类等标准班类型；这一项影响积分计算。",
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
          "explanation": "按认定依据选择项目层级：企业定制通常选市级，社区、免费帮扶通常选校级；不要自行提高等级。",
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
          "explanation": "按实际情况选择是否异地送教、全天实操或脱产培训，并保留相应依据。",
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
          "explanation": "项目层级高于常规时必填：填写正式认定文件名称和文号，提交后由归口核验。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 1000 字"
          ],
          "options": [],
          "example": "省人社厅专项培训认定文件〔2026〕8号",
          "documented": true
        },
        {
          "key": "auxiliary_standard",
          "label": "随项目备案的辅助积分细则",
          "explanation": "写明随项目备案的辅助工作积分细则：哪些工作、每天多少分、依据是什么。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "班主任每天0.5分，每人每天不超过1分",
          "documented": true
        },
        {
          "key": "auxiliary_daily_cap",
          "label": "个人辅助积分每日上限",
          "explanation": "填写学校确认的个人辅助积分每日上限，不要照抄示例。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "1",
          "documented": true
        },
        {
          "key": "reason",
          "label": "申报说明",
          "explanation": "写清申报的理由，以及需要审核人员了解的情况；没有特别情况可以简要说明。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "填写共建协议编号或学院登记编号，例如 JD-2026-001。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "JD-2026-001",
          "documented": true
        },
        {
          "key": "name",
          "label": "基地名称",
          "explanation": "填写基地的完整名称，与共建协议或认定文件一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "湘茶思政实践教学基地",
          "documented": true
        },
        {
          "key": "manager_name",
          "label": "基地负责人",
          "explanation": "校内基地填学校这边的负责人，校外基地填共建单位联系人；不填时显示为申请人。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "张老师",
          "documented": true
        },
        {
          "key": "usage_practice",
          "label": "实践教学基地",
          "explanation": "基地实际用于实践教学时勾选，可以和思政实践教学同时勾选。",
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
          "explanation": "基地实际承担思政实践教学时勾选，并保留建设或使用依据。",
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
          "explanation": "按认定文件选择基地级别，不要自行提高等级。",
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
          "explanation": "按基地实际位置选择校内或校外；选校外时必须填写共建单位。",
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
          "explanation": "选择校外基地时必须填写共建单位的全称；校内基地不用填。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "established_on",
          "label": "设立日期",
          "explanation": "填写基地实际设立的日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "recognized_on",
          "label": "认定日期",
          "explanation": "填写学校或上级正式认定的日期；还没有认定可以不填。不要和设立日期、审批日期混在一起。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "location",
          "label": "具体地点",
          "explanation": "填写基地所在的校区、楼栋或校外详细地址，能让人找到。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "基地封面（选填）",
          "explanation": "可以上传一张基地展示图片，场地照片也可以以后在基地详情里继续添加；封面不能代替认定材料。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "支持 PNG、JPG，单个不超过 5MB",
            "只能上传 1 份"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "recognition",
          "label": "基地认定依据",
          "explanation": "填写共建协议、学校发文或学院会议纪要等正式依据的名称和文号。",
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
          "key": "reason",
          "label": "本次申请说明",
          "explanation": "补充说明设立用途或本次申请事项；认定依据请填在上面的“基地认定依据”里。",
          "requirement": "当前选填",
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
      "action": "teacher-apply",
      "action_id": "bases|app-base-new"
    },
    {
      "title": "申请培训基地",
      "fields": [
        {
          "key": "teacher_id",
          "label": "基地负责人（输入工号或姓名检索）",
          "explanation": "输入负责老师的姓名或工号搜索后选择，核对工号。只能选你授权范围内的老师。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "code",
          "label": "来源编号",
          "explanation": "填写共建协议编号或学院登记编号，例如 JD-2026-001。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "JD-2026-001",
          "documented": true
        },
        {
          "key": "name",
          "label": "基地名称",
          "explanation": "填写基地的完整名称，与共建协议或认定文件一致。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "湘茶思政实践教学基地",
          "documented": true
        },
        {
          "key": "manager_name",
          "label": "基地负责人",
          "explanation": "校内基地填学校这边的负责人，校外基地填共建单位联系人；不填时显示为申请人。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "张老师",
          "documented": true
        },
        {
          "key": "usage_practice",
          "label": "实践教学基地",
          "explanation": "基地实际用于实践教学时勾选，可以和思政实践教学同时勾选。",
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
          "explanation": "基地实际承担思政实践教学时勾选，并保留建设或使用依据。",
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
          "explanation": "按认定文件选择基地级别，不要自行提高等级。",
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
          "explanation": "按基地实际位置选择校内或校外；选校外时必须填写共建单位。",
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
          "explanation": "选择校外基地时必须填写共建单位的全称；校内基地不用填。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "established_on",
          "label": "设立日期",
          "explanation": "填写基地实际设立的日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "recognized_on",
          "label": "认定日期",
          "explanation": "填写学校或上级正式认定的日期；还没有认定可以不填。不要和设立日期、审批日期混在一起。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "location",
          "label": "具体地点",
          "explanation": "填写基地所在的校区、楼栋或校外详细地址，能让人找到。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "基地封面（选填）",
          "explanation": "可以上传一张基地展示图片，场地照片也可以以后在基地详情里继续添加；封面不能代替认定材料。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "支持 PNG、JPG，单个不超过 5MB",
            "只能上传 1 份"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "recognition",
          "label": "基地认定依据",
          "explanation": "填写共建协议、学校发文或学院会议纪要等正式依据的名称和文号。",
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
          "key": "reason",
          "label": "本次申请说明",
          "explanation": "补充说明设立用途或本次申请事项；认定依据请填在上面的“基地认定依据”里。",
          "requirement": "当前选填",
          "hints": [],
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
          "explanation": "填写本人现有的职称、职业技能等级或岗位，与资质材料一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "specialty",
          "label": "专业特长",
          "explanation": "填写能承担培训的专业特长，例如茶艺、电商运营、家政服务；和下面的“培训业务类别”分开填。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir",
          "label": "培训业务类别（可多选）",
          "explanation": "勾选本人能够承担的培训业务类别，可以多选；具体专业特长在上面单独填写。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "补贴性培训",
            "企业定制培训",
            "社区公益培训",
            "乡村帮扶培训",
            "其他非学历培训",
            "“一人一技”专项"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "qualification_basis",
          "label": "资格依据",
          "explanation": "说明你的职称、职业资格或行业经历，以及这些能支持你承担哪些培训方向。",
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
          "key": "cover_file",
          "label": "培训师头像（选填）",
          "explanation": "可以上传一张本人照片，只用于师资库展示，不能代替证明材料。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "支持 PNG、JPG，单个不超过 5MB",
            "只能上传 1 份"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "experience",
          "label": "授课经历",
          "explanation": "写清近年的授课项目、培训期数和学员人次，必要时上传依据。",
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
          "key": "reason",
          "label": "本次申报说明",
          "explanation": "写清申报依据，或需要审核人员了解的情况；被退回后重新提交时，说明按意见改了哪些地方。",
          "requirement": "当前选填",
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
          "explanation": "选择证书属于哪一类资质。",
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
          "explanation": "按证书原件填写证书全称。",
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
          "explanation": "按证书原件填写完整编号，保留字母和前面的 0。",
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
          "explanation": "填写证书上的发证单位全称。",
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
          "explanation": "填写证书上的取得日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "expires",
          "label": "有效期至",
          "explanation": "选择证书的到期日期；没有到期日就勾选“长期有效”。考核时按周期最后一天证书是否有效来判断。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "",
          "label": "长期有效",
          "explanation": "证书没有到期日时勾选，勾选后不用填“有效期至”。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "file",
          "label": "证书图片或扫描件（可一次选多份）",
          "explanation": "上传清晰完整的证书照片或扫描件，可以一次选多张。草稿可以以后再补传，提交审核前必须至少有一份。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "支持 PDF、PNG、JPG，单个不超过 10MB",
            "可以一次选多个文件",
            "最多 20 份（含已上传的）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "申报说明",
          "explanation": "写清申报的理由，以及需要审核人员了解的情况；没有特别情况可以简要说明。",
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
          "explanation": "输入老师的姓名或工号搜索后选择，核对工号，不要选成同名的人。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "external_key",
          "label": "来源唯一编号",
          "explanation": "填写能唯一对应这笔记录的编号（例如成果证书编号或登记编号），避免重复登记。",
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
          "explanation": "填写这笔业务实际发生的日期，不要用录入当天代替。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "source",
          "label": "人工来源说明",
          "explanation": "这里登记的记录会标明为人工录入；从接口或表格导入的数据走各自的导入流程，不在这里补录。",
          "requirement": "当前必填",
          "hints": [],
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
          "explanation": "输入项目名称或编号搜索后选择这条记录所属的培训项目。",
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
          "explanation": "填写项目的完整名称，与培训方案一致，例如“2026年社区茶艺公益培训”。",
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
          "explanation": "选择与当前项目对应的课程，核对课程名称。",
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
          "explanation": "填写课程的完整名称，与课程材料一致，例如“社区营养配餐”。",
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
          "explanation": "填写或选择本次教学班编号，与花名册和教学安排一致。",
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
          "explanation": "填写实际教学班名称，与花名册和班级编号对应。",
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
          "explanation": "填写本条记录实际授课的学时，不要把分钟数直接填进来。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "participants",
          "label": "课程人次",
          "explanation": "填写本条记录对应的课程人次；同一人参加不同课程分别计次。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能填负数",
            "只能填整数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "income",
          "label": "归属培训收入（元）",
          "explanation": "按已核实的财务依据填写本条记录归属的培训收入，单位为元。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理意见 / 调整原因",
          "explanation": "写清这次登记或调整的原因和依据，方便以后核对。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
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
          "explanation": "选择这次要导入哪类数据；类型要和下载的模板一致，否则校验不通过。",
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
          "explanation": "上传按当前模板填好的表格文件，不要改表头。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "支持 Excel 表格（.xlsx）"
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
          "explanation": "选择这次要导入哪类数据；类型要和下载的模板一致，否则校验不通过。",
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
          "explanation": "上传按当前模板填好的表格文件，不要改表头。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "支持 Excel 表格（.xlsx）"
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
          "explanation": "选择这项业务所属的学院。",
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
          "explanation": "填写本年度学校确认的到账收入目标，单位为元。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "只能填整数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "participants_target",
          "label": "有效人次目标",
          "explanation": "填写本年度学校确认的有效人次目标；人次不等于去重后的人数。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "只能填整数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "priority_target",
          "label": "重点群体人次目标",
          "explanation": "填写学校确认的重点群体培训人次目标，并核对重点群体的范围。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "只能填整数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "staff_denominator",
          "label": "组织人数基准",
          "explanation": "填写本次组织考核使用的人数基准，并在下面写清人数依据。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "只能填整数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "target_reference",
          "label": "年度任务下达依据",
          "explanation": "填写学校下达本年度任务的文件名称、文号或会议纪要，和本页的目标值对应。",
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
          "explanation": "说明组织人数按哪一天统计、包括哪些人员、依据什么核对，和学校确认的口径一致。",
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
          "explanation": "按本年度实际完成的任务、收入、人次、成果和管理工作逐项说明，写出存在的问题和改进安排，并注明对应佐证。",
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
          "explanation": "只填写有正式依据、且没有在其他项目里计过的加分；没有填 0。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "other_bonus_basis",
          "label": "其他加分依据",
          "explanation": "逐项写明申请加分的事项、认定文件和分值，并确认没有在其他项目里重复计分。",
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
          "explanation": "填写已经确认的不合规次数；项目结算核验里已经反映的问题不要重复计。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "只能填整数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "discipline_reference",
          "label": "正式处理或处分依据",
          "explanation": "填写已经正式确认的处理或处分文件名称、文号和日期，并说明与本次考核的关系。",
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
          "explanation": "只有学校已经确认属于一票否决情形时才勾选，并在依据里写明正式文件。",
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
          "explanation": "写清这次操作的原因和依据，会记入操作记录，以后可以查到。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "选择这项业务所属的学院。",
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
          "explanation": "填写能唯一对应这笔记录的编号（例如成果证书编号或登记编号），避免重复登记。",
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
          "explanation": "填写成果的完整名称，与认定或登记文件一致。",
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
          "explanation": "填写成果对应的地点或资源存放位置，例如网址、档案编号。",
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
          "explanation": "填写成果认定或登记文件的名称、文号和可查找的位置。",
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
          "explanation": "按认定文件选择成果等级（如国家级、省级、校级）。",
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
          "explanation": "填写成果正式认定的日期；日期还没有时可以先空着，但空着的成果不计入年度分数。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cover_file",
          "label": "成果封面（选填）",
          "explanation": "可以上传一张成果展示图片，只用于展示，不能代替证明材料。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "支持 PNG、JPG，单个不超过 5MB",
            "只能上传 1 份"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理说明",
          "explanation": "写清这次操作的原因和依据，会记入操作记录，以后可以查到。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "填写课程材料上的编号，例如 SOC-2026-001；被退回补正时保留原来的编号。",
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
          "explanation": "填写课程的完整名称，与课程材料一致，例如“社区营养配餐”。",
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
          "explanation": "选择这门课所属的培训项目，系统自动带出项目编号，不用手填；页面标为选填时可以不关联。",
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
          "explanation": "按培训实际安排填写学时，可以填 0.5 学时这样的半学时；不要把分钟数直接填进来。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "可以填 0.5 学时这样的半学时"
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
          "explanation": "按课程实际安排选择思政属性。",
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
          "explanation": "只有按成套教学包开发的课程才勾选。",
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
          "explanation": "属于“一人一技”专项培训行动时勾选，勾选后要填写重点群体与行动对接。",
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
          "explanation": "勾选“一人一技”专项时必填：写清面向哪些重点群体、怎样对接行动，例如“脱贫人口、返乡青年；结业后推荐就业”。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "teacher_id",
          "label": "主讲教师（输入工号或姓名检索）",
          "explanation": "输入主讲教师的姓名或工号搜索后选择，核对工号，不要选成同名的人。只能选你授权范围内的老师。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cw_checked",
          "label": "课件审查",
          "explanation": "学院已经做过课件审查、有审查记录时才勾选。",
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
          "explanation": "填写实际做课件审查的人或审查组。",
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
          "explanation": "填写课件审查记录上的日期。",
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
          "explanation": "写清这次操作的原因和依据，会记入操作记录，以后可以查到。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "填写学校统一的组织编码，已有编码不要改，避免与其他组织重复。",
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
          "explanation": "选择这个组织是二级学院还是教研室；层级决定它的上级组织和由谁当负责人。",
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
          "explanation": "填写学院、教研室或部门的正式全称，与学校发文一致。",
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
          "explanation": "选择这个组织的直属上级：学院的上级是学校，教研室的上级是学院。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理意见 / 调整原因",
          "explanation": "写清这次登记或调整的原因和依据，方便以后核对。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "填写学校分配的登录账号，先搜索确认没有重复。",
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
          "explanation": "普通教师账号必须填学校统一工号，保留前面的 0；没有工号的管理账号可以不填。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "password",
          "label": "临时密码（至少 12 位）",
          "explanation": "设置至少 12 位的临时密码，当面或通过安全方式交给本人，本人第一次登录时会被要求修改。",
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
          "explanation": "填写本人身份证件上的真实姓名。",
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
          "explanation": "填写此人现在的职称或岗位，例如“副教授”“教务处科员”。",
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
          "explanation": "按实际职责选择角色；角色决定能看到哪些菜单和数据范围。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "org_id",
          "label": "所属组织",
          "explanation": "选择此人所属的组织：老师和教研室负责人选教研室，学院负责人选学院，学校部门人员选学校。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理意见 / 调整原因",
          "explanation": "写清这次登记或调整的原因和依据，方便以后核对。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "给这个制度口径版本起一个能区分的名称，例如“2026年度社会培训执行口径”。",
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
          "explanation": "选择本次申报、统计或考核对应的周期；周期不一定等于自然年或学年。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cap_mode",
          "label": "单次积分封顶",
          "explanation": "按学校书面解释选择单次积分是否封顶、怎样封顶。",
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
          "explanation": "选择人天式计算里“单次”指一天还是一个项目，按学校确认的口径选。",
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
          "explanation": "选择积分计算和汇总保留几位小数，与学校制度一致。",
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
          "explanation": "按学校确认的规则选择四舍五入或其他舍入方式。",
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
          "explanation": "选择同一天同时做多项辅助工作时能否累计积分，按学校确认口径选。",
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
          "explanation": "选择不足一个计分步长时怎么处理，按学校书面解释选。",
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
          "explanation": "选择学校正式采用的学院年度考核计算模型，启用前先试算核对。",
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
          "explanation": "选择各类加分怎样汇总、受什么上限约束，按学校考核办法选。",
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
          "explanation": "选择考核等次的划分方式（如四等制、三等制），并核对分数线。",
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
          "explanation": "选择满意度正好 95% 时算不算达标，按学校对边界值的书面解释选。",
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
          "explanation": "选择同一项成果多次出现时按什么范围去重，避免重复计分。",
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
          "explanation": "填写学校确认的年度总分上限，并确认是否包含加分。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "excellent_from",
          "label": "三等制优秀门槛",
          "explanation": "填写三等制里“优秀”的起始分数，要高于合格分数线。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "qualified_from",
          "label": "三等制合格门槛",
          "explanation": "填写三等制里“合格”的起始分数，要低于优秀分数线。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "title_scope",
          "label": "职称折算范围",
          "explanation": "选择职称折算用于哪些积分项目，不要自行扩大范围。",
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
          "explanation": "选择学院汇总用项目人次还是其他确认口径；人次和去重人数不要混用。",
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
          "explanation": "选择业务按哪个日期归属年度（如结项日期），按学校确认的规则选。",
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
          "explanation": "选择职称折算结果保留几位小数。",
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
          "explanation": "选择退回补正的期限从哪一天开始算，按学校文件选，不要自己定期限。",
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
          "explanation": "填写这个口径从哪一天开始执行；之前的历史结果不受影响。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "calendar_start",
          "label": "校历开始日期",
          "explanation": "填写这份校历覆盖的第一天。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "calendar_end",
          "label": "校历结束日期",
          "explanation": "填写这份校历覆盖的最后一天，不能早于开始日期。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "holidays",
          "label": "放假日期（每行一个）",
          "explanation": "填写校历区间内的放假日期，每行一个，例如 2026-10-01；同一天不能既放假又补班。",
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
          "explanation": "填写需要上班的周末补班日期，每行一个，不能和放假日期重复。",
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
          "explanation": "填写学校校历或调休通知的名称、文号，作为计算工作日的依据。",
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
          "explanation": "填写学校确认本口径的正式文件或会议记录，不能只写“按规定”。",
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
          "explanation": "写清这次操作的原因和依据，会记入操作记录，以后可以查到。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "先选要配置的审批职责（例如归口学院复审、分管副校长、教学秘书），下面的已选办理人和候选名单会随之切换。没配人的职责会在表单顶部提示。",
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
          "key": "duty_query",
          "label": "搜索姓名、工号或账号",
          "explanation": "输入姓名、工号或登录账号，点“查询”找人；名单分页显示，翻页或换关键词时已勾选的人会保留。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "duty_people",
          "label": "选择办理人（可多选）",
          "explanation": "在搜索结果里勾选这个职责的办理人，可以选多位，任何一位办理即生效。名单里灰色、不能勾选的人，是还没有“学校”类型且带审核权限的有效身份，或者所属组织不在你的管理范围内，需要先在“用户与权限”里给他添加相应的兼任身份。建议每个职责至少配两位：申请人是本人或申报过利益冲突时要回避，只有一位的话，他回避后这一环节就没人能办。",
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
          "explanation": "写清这次操作的原因和依据，会记入操作记录，以后可以查到。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "给考核周期起一个能区分的名称，例如“2026年度”。",
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
          "explanation": "填写实际开始日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "end_date",
          "label": "结束日期",
          "explanation": "填写实际结束日期，不能早于开始日期。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理意见 / 调整原因",
          "explanation": "写清这次登记或调整的原因和依据，方便以后核对。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "选择这条规则考核的对象：教研室、学院还是学校。",
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
          "explanation": "给这条规则起一个能区分的名称，例如“2026年度教研室考核”。",
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
          "explanation": "选择本次申报、统计或考核对应的周期；周期不一定等于自然年或学年。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "label",
          "label": "指标名称",
          "explanation": "填写学校考核细则里的指标名称，名称要能看出考核什么。",
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
          "explanation": "选择这个指标从哪里取数，例如授课学时、课程人次；核对统计范围，不使用没有确认的来源。",
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
          "explanation": "按学校确认的考核规则填写权重，各指标权重合计核对无误。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能填负数",
            "不能大于 100",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "target",
          "label": "目标值",
          "explanation": "填写学校考核细则规定的达标值，不要用演示数值。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能小于 0.0001",
            "最多保留四位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "method",
          "label": "评分方式",
          "explanation": "按学校确认的规则选择评分方式；切换方式后只需要填写当前方式用到的参数。",
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
          "explanation": "按学校确认的分档填写“门槛:分值”，多档用逗号隔开，例如 60:10,80:20；实际门槛和分值以学校文件为准。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "0:20, 8:60, 20:100",
          "documented": true
        },
        {
          "key": "tier_mode",
          "label": "分档计分方式",
          "explanation": "按学校确认的办法选择：只取达到的最高一档，还是各档累加。",
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
          "explanation": "填写计算加分或扣分的起始分数，按正式规则设置。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "unit",
          "label": "计数单位",
          "explanation": "填写每满多少计一次，例如每满 1 次、每满 10 人次，按学校确认的规则填写。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "不能小于 0.0001",
            "最多保留四位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "per_unit",
          "label": "每次扣/加分",
          "explanation": "填写每计一次加或扣多少分，同时核对封顶和保底。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "floor",
          "label": "保底",
          "explanation": "填写本项最低得分（保底分），按正式规则设置。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cap",
          "label": "封顶",
          "explanation": "填写本项最多能得多少分；不封顶时留空。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理意见 / 调整原因",
          "explanation": "写清这次登记或调整的原因和依据，方便以后核对。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "选择这条规则用于教师积分还是三级考核。",
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
          "explanation": "给这条规则起一个能区分的名称，例如“2026年度教研室考核”。",
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
          "explanation": "选择本次申报、统计或考核对应的周期；周期不一定等于自然年或学年。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "label",
          "label": "指标名称",
          "explanation": "填写学校考核细则里的指标名称，名称要能看出考核什么。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "source",
          "label": "指标数据来源",
          "explanation": "选择这个指标从哪里取数，核对统计范围，不使用没有确认的来源。",
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
          "explanation": "填写学校确认的计算系数，先试算核对再启用。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留四位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "weight",
          "label": "考核权重",
          "explanation": "按学校确认的考核规则填写权重，各指标权重合计核对无误。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "不能填负数",
            "不能大于 100",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "target",
          "label": "考核达标值",
          "explanation": "填写学校确认的达标值，不要用演示数值。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "不能小于 0.0001",
            "最多保留四位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "cap",
          "label": "上限 / 封顶",
          "explanation": "填写本项积分上限；不限时留空。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "method",
          "label": "评分方式",
          "explanation": "按学校确认的规则选择评分方式；切换方式后只需要填写当前方式用到的参数。",
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
          "explanation": "按学校确认的分档填写“门槛:分值”，多档用逗号隔开，例如 60:10,80:20；实际门槛和分值以学校文件为准。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "0:20, 8:60, 20:100",
          "documented": true
        },
        {
          "key": "tier_mode",
          "label": "分档计分方式",
          "explanation": "按学校确认的办法选择：只取达到的最高一档，还是各档累加。",
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
          "explanation": "填写计算加分或扣分的起始分数，按正式规则设置。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "unit",
          "label": "计数单位",
          "explanation": "填写每满多少计一次，例如每满 1 次、每满 10 人次，按学校确认的规则填写。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "不能小于 0.0001",
            "最多保留四位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "per_unit",
          "label": "每次扣/加分",
          "explanation": "填写每计一次加或扣多少分，同时核对封顶和保底。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "floor",
          "label": "保底",
          "explanation": "填写本项最低得分（保底分），按正式规则设置。",
          "requirement": "当前不可填写",
          "hints": [],
          "limits": [
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理意见 / 调整原因",
          "explanation": "写清这次登记或调整的原因和依据，方便以后核对。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "用一句话概括通知内容，例如“关于开展2026年社会培训项目申报的通知”。",
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
          "explanation": "选择通知的分类，方便大家按分类查找。",
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
          "key": "org_ids",
          "label": "发布范围（可多选）",
          "explanation": "勾选能看到这条通知的学院、教研室或学校部门，可以多选；点“全选”一次选中全部。发布前核对范围，避免发给无关人员。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "body",
          "label": "通知正文",
          "explanation": "写清通知对象、事项、时间、材料要求和联系部门，发布前再核对一遍。",
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
          "explanation": "内容和范围核对无误后再选择发布；保存为草稿时相关人员还看不到。",
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
          "explanation": "写清这次操作的原因，会记入操作记录。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
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
          "explanation": "填写实际结项日期；系统已按培训结束日期带出，实际不同时再改。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "satisfaction",
          "label": "满意度（百分比）",
          "explanation": "填写满意度调查的实际百分比，例如 96 表示 96%；不要填 0.96，也不要填预期值。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能填负数",
            "不能大于 100",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "location",
          "label": "培训地点类型",
          "explanation": "按实际情况选择校内或校外；系统已按项目申报时的培训场地带出，不同时再改。",
          "requirement": "当前必填",
          "hints": [],
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
          "explanation": "说明完成了哪些培训内容、取得了哪些成果，以及对应的佐证材料。",
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
          "explanation": "写清存在的问题、整改措施、责任人、完成期限和整改结果；还没整改完的，说明目前进展和后续安排。",
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
          "explanation": "有整改要求时填写整改完成期限，按审核意见确定。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "actual_income",
          "label": "财务确认到账收入（元）",
          "explanation": "按财务结算依据填写实际到账收入，单位为元。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "funding_source",
          "label": "财务确认的资金来源",
          "explanation": "按财务确认的资金来源选择；政府专项资金和其他培训收入的核验要求不同。",
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
          "explanation": "填写可追溯的财务凭证号或结算依据。",
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
          "explanation": "填写已核实的隐性成本金额，单位为元，和财务依据一致；没有填 0。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "settlement_on",
          "label": "经费结算日期",
          "explanation": "填写实际经费结算日期，不要用申报日期代替。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "retained",
          "label": "学校留存（元）",
          "explanation": "填写财务核实的学校留存金额，单位为元；页面会提示收入分配比例，这里填金额不填百分数。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "personnel",
          "label": "校内人员支出（元）",
          "explanation": "填写到账收入和学校留存后自动算出（到账收入 × 80% − 学校留存），使项目公用正好为收入的 20%；不用手填。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "不能填负数",
            "最多保留两位小数"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "funding_basis",
          "label": "政府专项主管部门规定及财务核验依据",
          "explanation": "资金来源是政府专项且有收入时必填：写明主管部门的规定和财务核验依据；专项资金专款专用，不套用其他收入的分配比例。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "checked",
          "label": "结项材料核对",
          "explanation": "老师提交结项不用勾。学校核验时点“同意”，系统会把下面 8 项材料自动记为已核对；材料不齐时请点“退回”，写明缺什么。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [
            "培训方案",
            "学校制式备案登记表",
            "学员名册",
            "实名签到",
            "学时记录",
            "培训过程影像",
            "结业考核",
            "培训成果"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "办理说明",
          "explanation": "写清这次操作的原因和依据，会记入操作记录，以后可以查到。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "选择本人参与、并且已经满足申报条件的培训项目；列表里没有时，先到“我的培训明细”核对项目是否已结项。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "period_id",
          "label": "认定周期",
          "explanation": "选择本次申报、统计或考核对应的周期；周期不一定等于自然年或学年。",
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
          "explanation": "选择本年度经学校确认并适用的制度执行口径版本。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "file",
          "label": "学校制式积分认定表及其他材料（可一次选多份）",
          "explanation": "上传填好并签字的学校制式积分认定表，以及其他证明材料。每份单独上传并显示结果，失败的只需补传那一份。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [
            "支持 PDF、PNG、JPG，单个不超过 10MB",
            "可以一次选多个文件",
            "最多 50 份（含已上传的）"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "reason",
          "label": "申报说明",
          "explanation": "写清申报的理由，以及需要审核人员了解的情况；没有特别情况可以简要说明。",
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
          "explanation": "填写依据文件名称、文号或材料编号，方便审核人员查找；不要填写密码或密钥。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "最多 2000 字"
          ],
          "options": [],
          "example": "学院会议纪要〔2026〕3号、协议编号、材料编号",
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
          "explanation": "填写本人身份证件上的真实姓名。",
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
          "explanation": "填写外聘人员现在任职单位的全称，与资质和授课经历材料一致。",
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
          "explanation": "填写本人现有的职称、职业技能等级或岗位，与资质材料一致。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "specialty",
          "label": "专业特长",
          "explanation": "填写能承担培训的专业特长，例如茶艺、电商运营、家政服务；和下面的“培训业务类别”分开填。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "dir",
          "label": "培训业务类别（可多选）",
          "explanation": "勾选本人能够承担的培训业务类别，可以多选；具体专业特长在上面单独填写。",
          "requirement": "当前必填",
          "hints": [],
          "limits": [],
          "options": [
            "补贴性培训",
            "企业定制培训",
            "社区公益培训",
            "乡村帮扶培训",
            "其他非学历培训",
            "“一人一技”专项"
          ],
          "example": "",
          "documented": true
        },
        {
          "key": "qualification_basis",
          "label": "资格依据",
          "explanation": "说明你的职称、职业资格或行业经历，以及这些能支持你承担哪些培训方向。",
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
          "key": "cover_file",
          "label": "培训师头像（选填）",
          "explanation": "可以上传一张本人照片，只用于师资库展示，不能代替证明材料。",
          "requirement": "当前选填",
          "hints": [],
          "limits": [
            "支持 PNG、JPG，单个不超过 5MB",
            "只能上传 1 份"
          ],
          "options": [],
          "example": "",
          "documented": true
        },
        {
          "key": "experience",
          "label": "授课经历",
          "explanation": "写清近年的授课项目、培训期数和学员人次，必要时上传依据。",
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
          "key": "reason",
          "label": "本次申报说明",
          "explanation": "写清申报依据，或需要审核人员了解的情况；被退回后重新提交时，说明按意见改了哪些地方。",
          "requirement": "当前选填",
          "hints": [],
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

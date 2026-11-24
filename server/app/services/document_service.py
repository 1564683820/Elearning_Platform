"""文档分类枚举和工具函数（教师端优化 Phase1）"""

# ── 文档分类 ──
DOC_CATEGORIES = {
    "exam": "试卷",
    "teaching_plan": "教案",
    "courseware": "课件/PPT",
    "textbook": "教材",
    "reference": "参考资料",
    "other": "其他",
}

# 分类 → Milvus source_type 前缀
DOC_CATEGORY_SOURCE_TYPE = {
    "exam": "doc_exam",
    "teaching_plan": "doc_teaching_plan",
    "courseware": "doc_courseware",
    "textbook": "doc_textbook",
    "reference": "doc_reference",
    "other": "doc_other",
}

# ── 学段定义 ──
STAGE_CATEGORIES = {
    "preschool": "启蒙",
    "primary": "小学",
    "junior": "初中",
    "senior": "高中",
    "college": "四六级",
    "other": "其他",
}

# 学段 → 对应年级（用于从现有 grade 字段推断）
STAGE_GRADE_MAP = {
    "preschool": ["启蒙", "学前", "幼儿园"],
    "primary": ["一年级", "二年级", "三年级", "四年级", "五年级", "六年级",
                "小三", "小四", "小五", "小六"],
    "junior": ["七年级", "八年级", "九年级", "初一", "初二", "初三"],
    "senior": ["高一", "高二", "高三", "十年级", "十一年级", "十二年级"],
    "college": ["四级", "六级", "考研", "大学", "雅思", "托福"],
    "other": [],
}

# 学段 → 支持题型（供前端联动）
STAGE_QUESTION_TYPES = {
    "preschool": ["picture_choice", "match", "follow_read", "pair"],
    "primary": ["choice", "fill", "reading", "writing"],
    "junior": ["choice", "cloze", "fill", "reading", "writing"],  # 中考无翻译题
    "senior": ["cloze", "reading", "seven_choice", "grammar_fill", "error_correction", "writing"],
    "college": ["choice", "cloze", "fill", "reading", "translation", "seven_choice", "writing"],
    "other": ["choice", "fill", "reading", "translation", "writing"],
}

# 题型中文标签
QUESTION_TYPE_LABELS = {
    "picture_choice": "图片选择",
    "match": "连线题",
    "follow_read": "跟读题",
    "pair": "配对题",
    "choice": "选择题",
    "fill": "填空题",
    "cloze": "完形填空",
    "reading": "阅读理解",
    "translation": "翻译题",
    "writing": "写作题",
    "seven_choice": "七选五",
    "grammar_fill": "语法填空",
    "error_correction": "短文改错",
}

# 学段 → 教学风格（用于 PPT 生成 prompt）
STAGE_TEACHING_STYLES = {
    "preschool": "游戏化、图片丰富、重复性高、TPR教学法",
    "primary": "趣味导入、情景教学、小组活动、游戏化",
    "junior": "任务型教学、语法讲解系统化、读写结合",
    "senior": "语篇分析、思维导图、高考题型专项、分层教学",
    "college": "学术英语、四六级备考、长难句分析、真题训练",
    "other": "按需定制",
}


def infer_stage_from_grade(grade: str) -> str:
    """根据 grade 字符串推断学段，匹配不到返回 'other'"""
    if not grade:
        return "other"
    grade_lower = grade.lower()
    for stage, grades in STAGE_GRADE_MAP.items():
        for g in grades:
            if g in grade or grade_lower in g.lower():
                return stage
    return "other"


def get_source_type_for_category(doc_category: str) -> str:
    """获取文档分类对应的 Milvus source_type"""
    return DOC_CATEGORY_SOURCE_TYPE.get(doc_category, "doc_other")

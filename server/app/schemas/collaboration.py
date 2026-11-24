# 协作增强模块 Pydantic 数据模型
# 助教管理、审计日志、学习报告、学校管理
from pydantic import BaseModel
from typing import Optional, Any, List
from datetime import datetime, date


# ========== 助教/课代表管理 ==========

class AssistantAddRequest(BaseModel):
    """添加助教请求"""
    class_id: int
    student_id: int
    permissions: Optional[dict] = None


class AssistantOut(BaseModel):
    """助教/课代表输出"""
    teacher_id: int
    nickname: str
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class UpdateRoleRequest(BaseModel):
    """更新班级角色请求"""
    teacher_id: int
    role: str  # teacher / assistant


# ========== 多教师协作批改 ==========

class GradingTask(BaseModel):
    """批改任务分配"""
    submission_id: int
    grader_id: int
    grader_role: str  # teacher / assistant
    assigned_questions: Optional[List[int]] = None  # 分配的题号（None=全部）


class GradingTaskOut(BaseModel):
    """批改任务输出"""
    submission_id: int
    student_id: int
    student_name: str = ""
    exam_id: int
    exam_title: str = ""
    grader_id: int
    grader_role: str
    assigned_questions: Optional[List[int]] = None
    status: str  # pending/grading/done
    created_at: datetime

    model_config = {"from_attributes": True}


class GradingResult(BaseModel):
    """助教/协作批改结果提交"""
    submission_id: int
    question_scores: List[dict]  # [{question_index: 0, score: 8, comment: "..."}]
    overall_comment: str = ""


class ReviewRequest(BaseModel):
    """主教师复核请求"""
    submission_id: int
    adjustments: dict
    final_score: int


class ReviewResultOut(BaseModel):
    """复核结果输出"""
    submission_id: int
    original_score: int
    adjusted_score: int
    review_comment: str
    reviewed_by: int
    reviewed_at: datetime


# ========== 审计日志 ==========

class AuditLogOut(BaseModel):
    """审计日志输出"""
    id: int
    class_id: Optional[int] = None
    operator_id: int
    operator_role: str
    action_type: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    detail: Optional[Any] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    """审计日志列表响应"""
    items: List[AuditLogOut]
    total: int
    page: int
    page_size: int


# ========== 学习报告 ==========

class PersonalReportOut(BaseModel):
    """个人学习报告"""
    user_id: int
    nickname: str = ""
    period_start: date
    period_end: date
    study_days: int = 0
    total_words: int = 0
    total_training: int = 0
    total_exams: int = 0
    overall_accuracy: float = 0.0
    module_breakdown: List[dict] = []  # 各模块正确率
    weakness_points: List[dict] = []  # 薄弱知识点
    daily_trend: List[dict] = []  # 每日趋势
    improvement_suggestions: List[str] = []  # AI 学习建议


class ClassReportOut(BaseModel):
    """班级学期报告"""
    class_id: int
    class_name: str
    student_count: int
    period_start: date
    period_end: date
    overall_accuracy: float = 0.0
    total_words: int = 0
    total_exams: int = 0
    total_training: int = 0
    avg_study_days: float = 0.0
    top_mistakes: List[dict] = []
    accuracy_trend: List[dict] = []
    active_trend: List[dict] = []
    student_ranking: List[dict] = []  # 学生排名


# ========== 学校管理 ==========

class SchoolAdminCreate(BaseModel):
    """创建学校管理员请求"""
    user_id: int
    school_name: str
    contact_phone: Optional[str] = None
    permissions: Optional[dict] = None


class SchoolAdminOut(BaseModel):
    """学校管理员输出"""
    id: int
    user_id: int
    school_name: str
    contact_phone: Optional[str] = None
    permissions: Optional[Any] = None
    is_active: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SchoolDashboardOut(BaseModel):
    """学校级数据看板"""
    school_name: str
    total_classes: int = 0
    total_students: int = 0
    total_teachers: int = 0
    total_exams: int = 0
    class_stats: List[dict] = []  # 班级统计数据

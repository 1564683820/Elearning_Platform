# 教师端 Pydantic 数据模型
from pydantic import BaseModel
from typing import Optional, Any, List
from datetime import datetime


# ========== 班级 ==========

class ClassCreate(BaseModel):
    """创建班级请求"""
    name: str
    description: str = ""
    stage: int = 0


class ClassOut(BaseModel):
    """班级输出"""
    id: int
    name: str
    description: str
    invite_code: str
    created_by: int
    stage: int
    student_count: int
    is_active: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ClassUpdate(BaseModel):
    """更新班级请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    stage: Optional[int] = None
    is_active: Optional[int] = None


class InviteCodeOut(BaseModel):
    """邀请码输出"""
    invite_code: str
    class_id: int
    class_name: str


# ========== 学生 ==========

class StudentOut(BaseModel):
    """班级学生概要"""
    id: int
    student_id: int
    nickname: str
    joined_at: datetime
    total_words: int = 0
    total_training: int = 0
    avg_accuracy: float = 0.0
    study_days: int = 0

    model_config = {"from_attributes": True}


# ========== 数据看板 ==========

class ClassDashboard(BaseModel):
    """班级看板数据"""
    class_id: int
    class_name: str
    student_count: int
    total_words: int = 0
    total_quiz: int = 0
    avg_accuracy: float = 0.0
    active_today: int = 0
    top_mistakes: List[dict] = []
    weekly_trend: List[dict] = []


class StudentDetail(BaseModel):
    """单个学生详情（教师视角）"""
    student_id: int
    nickname: str
    joined_days: int = 0
    total_words: int = 0
    total_training: int = 0
    avg_accuracy: float = 0.0
    category_breakdown: List[dict] = []
    weakness_points: List[dict] = []
    daily_trend: List[dict] = []


# ========== 学生信息表(Excel导入) ==========

class StudentInfoItem(BaseModel):
    """Excel 中一行学生信息"""
    student_number: int
    student_name: str
    exam_number: str
    created_account: str = ""


class StudentInfoUploadResult(BaseModel):
    """导入结果"""
    total: int
    imported: int
    skipped: int
    items: list[StudentInfoItem]


class StudentInfoOut(BaseModel):
    """已导入的学生信息"""
    id: int
    class_id: int
    student_number: int
    student_name: str
    exam_number: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ========== 学生考试错题(OCR批卷) ==========

class WrongQuestionItem(BaseModel):
    """单道错题信息"""
    question_index: int
    question_type: str
    stem: str
    user_answer: str
    correct_answer: str
    max_score: int
    score: float
    ai_comment: str = ""


class StudentExamResult(BaseModel):
    """学生在某次考试中的成绩+错题"""
    exam_id: int
    exam_title: str
    total_score: float
    max_score: int
    grading_status: str
    submitted_at: Optional[datetime] = None
    wrong_questions: list[WrongQuestionItem] = []


class StudentExamMistakesOut(BaseModel):
    """学生所有考试的错题汇总"""
    student_number: int
    student_name: str
    exam_number: str
    exam_count: int
    total_wrong: int
    exams: list[StudentExamResult] = []


# ========== AI 查询 ==========

class AIQueryRequest(BaseModel):
    """AI 自然语言查询请求"""
    class_id: int
    question: str


class AIQueryResponse(BaseModel):
    """AI 查询响应"""
    answer: str
    sql: str = ""
    data: Any = None

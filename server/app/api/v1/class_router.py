"""
学生端班级路由 — 加入班级、查看班级、班级详情、课堂状态、成绩统计
(教师端班级管理在 teacher.py 中)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.database import get_db
from app.api.deps import get_current_user, get_current_user_id
from app.models.user import User
from app.models.class_models import Class, ClassStudent, ClassTeacher
from app.models.ppt_models import ClassroomSession, LessonPPT
from app.models.exam_models import ExamSubmission, TeacherExam
from app.schemas.common import ResponseData
from pydantic import BaseModel
from datetime import datetime, timedelta

router = APIRouter(prefix="/class", tags=["学生班级"])


class JoinClassRequest(BaseModel):
    """加入班级请求"""
    invite_code: str


class MyClassOut(BaseModel):
    """学生视角的班级信息"""
    id: int
    name: str
    description: str
    student_count: int
    teacher_name: str = ""
    joined_at: datetime

    model_config = {"from_attributes": True}


@router.post("/join", response_model=ResponseData)
async def join_class(
    body: JoinClassRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """学生通过邀请码加入班级"""
    # 查找班级
    result = await db.execute(
        select(Class).where(
            Class.invite_code == body.invite_code.strip().upper(),
            Class.is_active == 1,
        )
    )
    cls = result.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="邀请码无效或班级已关闭")

    # 检查是否已在班级中
    result = await db.execute(
        select(ClassStudent).where(
            ClassStudent.class_id == cls.id,
            ClassStudent.student_id == user_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="你已在该班级中")

    # 加入班级
    cs = ClassStudent(class_id=cls.id, student_id=user_id)
    db.add(cs)

    # 更新班级人数
    cls.student_count = (cls.student_count or 0) + 1
    await db.flush()

    return ResponseData(data={"class_id": cls.id, "name": cls.name})


@router.get("/my", response_model=ResponseData)
async def get_my_classes(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取学生加入的所有班级"""
    stmt = (
        select(Class, ClassStudent.joined_at)
        .join(ClassStudent, ClassStudent.class_id == Class.id)
        .where(ClassStudent.student_id == user_id)
        .where(Class.is_active == 1)
        .order_by(ClassStudent.joined_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    classes = []
    for cls, joined_at in rows:
        # 查找班级创建者（教师）信息
        teacher_name = ""
        if cls.created_by:
            t_result = await db.execute(
                select(User.nickname).where(User.id == cls.created_by)
            )
            teacher_row = t_result.scalar_one_or_none()
            if teacher_row:
                teacher_name = teacher_row

        classes.append({
            "id": cls.id,
            "name": cls.name,
            "description": cls.description or "",
            "student_count": cls.student_count or 0,
            "teacher_name": teacher_name,
            "joined_at": joined_at.isoformat() if joined_at else "",
        })

    return ResponseData(data={"classes": classes})


@router.get("/{class_id}", response_model=ResponseData)
async def get_class_detail(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取班级详情（验证学生是否在班级中）"""
    # 验证学生在班级中
    result = await db.execute(
        select(ClassStudent).where(
            ClassStudent.class_id == class_id,
            ClassStudent.student_id == user_id,
        )
    )
    cs = result.scalar_one_or_none()
    if not cs:
        raise HTTPException(status_code=403, detail="你不在该班级中")

    # 获取班级信息
    result = await db.execute(
        select(Class).where(Class.id == class_id, Class.is_active == 1)
    )
    cls = result.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")

    # 获取教师信息
    teacher_name = ""
    if cls.created_by:
        t_result = await db.execute(
            select(User.nickname, User.avatar_url).where(User.id == cls.created_by)
        )
        teacher_row = t_result.one_or_none()
        if teacher_row:
            teacher_name = teacher_row.nickname or ""

    return ResponseData(data={
        "id": cls.id,
        "name": cls.name,
        "description": cls.description or "",
        "student_count": cls.student_count or 0,
        "teacher_name": teacher_name,
        "joined_at": cs.joined_at.isoformat() if cs.joined_at else "",
    })


@router.get("/{class_id}/active-session", response_model=ResponseData)
async def get_active_session(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """学生端：查询班级是否有活跃的课堂会话（教师正在授课）"""
    # 验证学生在班级中
    result = await db.execute(
        select(ClassStudent).where(
            ClassStudent.class_id == class_id,
            ClassStudent.student_id == user_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="你不在该班级中")

    # 查找该班级的授课教师（含创建者和 ClassTeacher 中注册的教师）
    teacher_ids = set()
    cls_result = await db.execute(
        select(Class).where(Class.id == class_id)
    )
    cls = cls_result.scalar_one_or_none()
    if cls and cls.created_by:
        teacher_ids.add(cls.created_by)

    ct_result = await db.execute(
        select(ClassTeacher.teacher_id).where(ClassTeacher.class_id == class_id)
    )
    for row in ct_result.all():
        teacher_ids.add(row[0])

    if not teacher_ids:
        return ResponseData(data={"has_active": False})

    # 查找这些教师发起的活跃课堂会话（60分钟内）
    time_threshold = datetime.now() - timedelta(hours=1)
    stmt = (
        select(ClassroomSession, LessonPPT.title)
        .join(LessonPPT, LessonPPT.id == ClassroomSession.ppt_id)
        .where(
            ClassroomSession.teacher_id.in_(list(teacher_ids)),
            ClassroomSession.status.in_(["active", "paused"]),
            ClassroomSession.started_at >= time_threshold,
        )
        .order_by(ClassroomSession.started_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    session_row = result.one_or_none()

    if not session_row:
        return ResponseData(data={"has_active": False})

    session, ppt_title = session_row
    return ResponseData(data={
        "has_active": True,
        "session_id": session.id,
        "ppt_id": session.ppt_id,
        "title": ppt_title or session.title,
        "status": session.status,
        "current_page": session.current_page,
        "started_at": session.started_at.isoformat() if session.started_at else "",
    })


@router.get("/ppt/{ppt_id}", response_model=ResponseData)
async def get_ppt_detail(
    ppt_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """学生端：获取 PPT 内容（仅限所属班级的学生访问）"""
    result = await db.execute(
        select(LessonPPT).where(LessonPPT.id == ppt_id)
    )
    ppt = result.scalar_one_or_none()
    if not ppt:
        raise HTTPException(status_code=404, detail="PPT 不存在")

    # 验证学生是否属于该 PPT 所属的班级
    if ppt.class_id is not None:
        membership = await db.execute(
            select(ClassStudent).where(
                ClassStudent.class_id == ppt.class_id,
                ClassStudent.student_id == user_id,
            )
        )
        if not membership.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="无权访问此 PPT（非本班级成员）")

    pages = ppt.pages_json or []
    if isinstance(pages, str):
        import json
        pages = json.loads(pages)

    return ResponseData(data={
        "id": ppt.id,
        "title": ppt.title,
        "pages": pages,
        "slide_count": ppt.slide_count or len(pages),
        "html_content": ppt.html_content or "",
        "theme_name": ppt.theme_name or "classic",
        "transition_type": ppt.transition_type or "slide",
        "transition_duration": ppt.transition_duration or 400,
    })


@router.get("/{class_id}/grade-stats", response_model=ResponseData)
async def get_grade_stats(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """学生端：获取考试成绩统计（趋势、题型错误占比）"""
    # 验证学生在班级中
    result = await db.execute(
        select(ClassStudent).where(
            ClassStudent.class_id == class_id,
            ClassStudent.student_id == user_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="你不在该班级中")

    # 获取该学生在该班级的所有提交记录
    sub_stmt = (
        select(
            ExamSubmission,
            TeacherExam.title,
            TeacherExam.questions,
        )
        .join(TeacherExam, TeacherExam.id == ExamSubmission.exam_id)
        .where(
            TeacherExam.class_id == class_id,
            ExamSubmission.student_id == user_id,
            ExamSubmission.score.isnot(None),
        )
        .order_by(ExamSubmission.submitted_at.asc())
    )
    result = await db.execute(sub_stmt)
    rows = result.all()

    scores = []
    type_errors = {}  # {type: {total: int, wrong: int}}

    for submission, title, questions in rows:
        score_val = submission.score or 0
        max_score = submission.max_score or 100
        scores.append({
            "exam_title": title,
            "score": score_val,
            "max_score": max_score,
            "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else "",
        })

        # 统计题型错误占比
        details = submission.ai_grade_detail or []
        for item in details:
            q_type = item.get("type", "choice")
            if q_type not in type_errors:
                type_errors[q_type] = {"total": 0, "wrong": 0}
            type_errors[q_type]["total"] += 1
            if not item.get("is_correct", False):
                type_errors[q_type]["wrong"] += 1

    # 计算题型错误占比百分比
    type_stats = []
    type_labels = {
        "choice": "选择题",
        "fill": "填空题",
        "reading": "阅读理解",
        "translation": "翻译",
        "writing": "写作",
    }
    for q_type, stats in type_errors.items():
        pct = round(stats["wrong"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0
        type_stats.append({
            "type": q_type,
            "label": type_labels.get(q_type, q_type),
            "total": stats["total"],
            "wrong": stats["wrong"],
            "error_rate": pct,
        })

    # 计算平均分
    avg_score = round(sum(s["score"] for s in scores) / len(scores), 1) if scores else 0

    return ResponseData(data={
        "exam_count": len(scores),
        "avg_score": avg_score,
        "scores": scores,
        "type_stats": type_stats,
        "current_total_score": scores[-1]["score"] if scores else 0,
        "current_max_score": scores[-1]["max_score"] if scores else 100,
    })

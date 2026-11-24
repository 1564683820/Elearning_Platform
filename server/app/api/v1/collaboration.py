# 协作增强模块 API 路由
# 助教管理、多教师协作批改、审计日志、学习报告、学校管理
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import date
from app.db.database import get_db, get_words_db
from app.api.deps import get_current_user_id, get_current_teacher_id, get_current_admin
from app.models.user import User
from app.schemas.common import ResponseData
from app.schemas.collaboration import (
    AssistantAddRequest, AssistantOut, UpdateRoleRequest,
    GradingResult, ReviewRequest,
    AuditLogOut, AuditLogListResponse,
    PersonalReportOut, ClassReportOut,
    SchoolAdminCreate, SchoolAdminOut, SchoolDashboardOut,
)
from app.services.collaboration_service import (
    AssistantService, CollaborativeGradingService,
    AuditService, LearningReportService, SchoolAdminService,
)

router = APIRouter(prefix="/collaboration", tags=["协作增强"])


# ========== 助教/课代表管理 ==========

@router.post("/assistants", response_model=ResponseData[AssistantOut])
async def add_assistant(
    body: AssistantAddRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """添加助教/课代表（将班级学生提升为助教）"""
    try:
        result = await AssistantService.add_assistant(
            db, body.class_id, body.student_id, teacher_id, body.permissions,
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/assistants/{class_id}/{assistant_id}")
async def remove_assistant(
    class_id: int, assistant_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """移除助教/课代表"""
    try:
        success = await AssistantService.remove_assistant(
            db, class_id, assistant_id, teacher_id
        )
        if not success:
            raise HTTPException(status_code=404, detail="助教不存在")
        return ResponseData(message="移除成功")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/assistants/{class_id}", response_model=ResponseData[list[AssistantOut]])
async def list_assistants(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取班级助教列表"""
    try:
        result = await AssistantService.list_assistants(db, class_id, teacher_id)
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.put("/assistants/role")
async def update_role(
    body: UpdateRoleRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """变更班级成员角色"""
    try:
        await AssistantService.update_role(
            db, body.teacher_id, teacher_id, body.role
        )
        return ResponseData(message="角色更新成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== 多教师协作批改 ==========

@router.post("/grading/assign")
async def assign_grading_task(
    body: dict,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """分配批改任务给教师/助教"""
    try:
        await CollaborativeGradingService.assign_grading_task(
            db=db,
            submission_id=body["submission_id"],
            grader_id=body.get("grader_id", teacher_id),
            grader_role=body.get("grader_role", "teacher"),
            assigned_questions=body.get("assigned_questions"),
            assigner_id=teacher_id,
        )
        return ResponseData(message="分配成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/grading/submit", response_model=ResponseData)
async def submit_grading_result(
    body: GradingResult,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """提交批改结果"""
    result = await CollaborativeGradingService.submit_grading_result(
        db=db, submission_id=body.submission_id,
        grader_id=teacher_id, grader_role="assistant",
        question_scores=[s.dict() for s in body.question_scores],
        overall_comment=body.overall_comment,
    )
    return ResponseData(data=result)


@router.post("/grading/review", response_model=ResponseData)
async def review_and_finalize(
    body: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """主教师复核并最终确定分数"""
    result = await CollaborativeGradingService.review_and_finalize(
        db=db, submission_id=body.submission_id,
        adjustments=body.adjustments, final_score=body.final_score,
        reviewer_id=teacher_id,
    )
    return ResponseData(data=result)


@router.get("/grading/status/{exam_id}")
async def get_grading_status(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取试卷批改进度"""
    statuses = await CollaborativeGradingService.get_grading_status(db, exam_id)
    return ResponseData(data=statuses)


# ========== 审计日志 ==========

@router.get("/audit-logs", response_model=ResponseData[AuditLogListResponse])
async def query_audit_logs(
    class_id: Optional[int] = Query(None, description="按班级筛选"),
    action_type: Optional[str] = Query(None, description="按操作类型筛选"),
    operator_id: Optional[int] = Query(None, description="按操作人筛选"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """查询审计日志（支持多维度筛选）"""
    result = await AuditService.query(
        db, class_id, action_type, operator_id,
        start_date, end_date, page, page_size,
    )
    return ResponseData(data=result)


# ========== 学习报告 ==========

@router.get("/reports/personal", response_model=ResponseData[PersonalReportOut])
async def get_personal_report(
    class_id: Optional[int] = Query(None),
    period_start: Optional[date] = Query(None, description="开始日期"),
    period_end: Optional[date] = Query(None, description="结束日期"),
    db: AsyncSession = Depends(get_db),
    words_db: AsyncSession = Depends(get_words_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取个人学习报告"""
    result = await LearningReportService.generate_personal_report(
        db, user_id, class_id, period_start, period_end, words_db=words_db,
    )
    return ResponseData(data=result)


@router.get("/reports/class/{class_id}", response_model=ResponseData[ClassReportOut])
async def get_class_report(
    class_id: int,
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    words_db: AsyncSession = Depends(get_words_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取班级学期报告"""
    try:
        result = await LearningReportService.generate_class_report(
            db, class_id, period_start, period_end, words_db=words_db,
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ========== 学校管理 ==========

@router.post("/school/admins", response_model=ResponseData[SchoolAdminOut])
async def create_school_admin(
    body: SchoolAdminCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """创建学校管理员（仅超级管理员可操作）"""
    try:
        result = await SchoolAdminService.create_admin(
            db, body.dict(), admin.id,
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/school/admins", response_model=ResponseData[list[SchoolAdminOut]])
async def list_school_admins(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """获取所有学校管理员（仅超级管理员可查看）"""
    result = await SchoolAdminService.list_admins(db)
    return ResponseData(data=result)


@router.get("/school/dashboard", response_model=ResponseData[SchoolDashboardOut])
async def get_school_dashboard(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """获取学校级数据看板（仅超级管理员可查看）"""
    try:
        result = await SchoolAdminService.get_school_dashboard(db, admin.id)
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/school/admins/{target_user_id}/toggle")
async def toggle_school_admin(
    target_user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """启用/禁用学校管理员（仅超级管理员可操作）"""
    success = await SchoolAdminService.toggle_admin(db, target_user_id, admin.id)
    if not success:
        raise HTTPException(status_code=404, detail="管理员不存在")
    return ResponseData(message="操作成功")

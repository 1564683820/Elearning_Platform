# 教师端 API 路由
# 班级 CRUD、邀请码管理、学生管理、数据看板、AI 智能查询、学段配置
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db, get_words_db
from app.api.deps import get_current_user_id, get_current_teacher_id, get_current_teacher_info, CurrentTeacher
from app.services.teacher_service import TeacherService
from app.schemas.common import ResponseData, PaginatedResponse
from app.schemas.teacher import (
    ClassCreate, ClassOut, ClassUpdate, ClassDashboard,
    StudentOut, StudentDetail, StudentInfoUploadResult, StudentInfoOut,
    StudentInfoItem, StudentExamMistakesOut,
    AIQueryRequest, AIQueryResponse,
)
from app.services.document_service import (
    STAGE_CATEGORIES, STAGE_QUESTION_TYPES,
    QUESTION_TYPE_LABELS, DOC_CATEGORIES,
)

router = APIRouter(prefix="/teacher", tags=["教师端"])


# ========== 班级管理 ==========

@router.post("/classes", response_model=ResponseData[ClassOut])
async def create_class(
    body: ClassCreate,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """创建班级"""
    result = await TeacherService.create_class(db, teacher_id, body)
    return ResponseData(data=result)


@router.get("/classes", response_model=ResponseData[list[ClassOut]])
async def list_classes(
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取教师所有班级"""
    result = await TeacherService.list_my_classes(db, teacher_id)
    return ResponseData(data=result)


@router.get("/classes/{class_id}", response_model=ResponseData[ClassOut])
async def get_class(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取班级详情"""
    try:
        result = await TeacherService.get_class_detail(db, class_id, teacher_id)
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/classes/{class_id}", response_model=ResponseData[ClassOut])
async def update_class(
    class_id: int,
    body: ClassUpdate,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """更新班级信息"""
    try:
        result = await TeacherService.update_class(
            db, class_id, teacher_id, body.model_dump(exclude_none=True)
        )
        if not result:
            raise HTTPException(status_code=404, detail="班级不存在")
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/classes/{class_id}/invite-code", response_model=ResponseData[dict])
async def regenerate_invite_code(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """重新生成邀请码"""
    try:
        code = await TeacherService.regenerate_invite_code(db, class_id, teacher_id)
        return ResponseData(data={"invite_code": code})
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/classes/{class_id}", response_model=ResponseData)
async def delete_class(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: CurrentTeacher = Depends(get_current_teacher_info),
):
    """删除班级"""
    try:
        await TeacherService.delete_class(db, class_id, teacher.id, is_admin=teacher.is_admin)
        return ResponseData(data={"message": "班级已删除"})
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ========== 学生管理 ==========

@router.get("/classes/{class_id}/students", response_model=ResponseData[list[StudentOut]])
async def list_students(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    words_db: AsyncSession = Depends(get_words_db),
    teacher: CurrentTeacher = Depends(get_current_teacher_info),
):
    """获取班级学生列表"""
    try:
        result = await TeacherService.get_class_students(
            db, class_id, teacher.id, words_db=words_db, is_admin=teacher.is_admin
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/classes/{class_id}/students/{student_id}")
async def remove_student(
    class_id: int,
    student_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """从班级移除学生"""
    try:
        success = await TeacherService.remove_student(db, class_id, student_id, teacher_id)
        if not success:
            raise HTTPException(status_code=404, detail="学生不在该班级中")
        return ResponseData(message="移除成功")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ========== 数据看板 ==========

@router.get("/classes/{class_id}/dashboard", response_model=ResponseData[ClassDashboard])
async def class_dashboard(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    words_db: AsyncSession = Depends(get_words_db),
    teacher: CurrentTeacher = Depends(get_current_teacher_info),
):
    """班级数据看板"""
    try:
        result = await TeacherService.get_class_dashboard(
            db, class_id, teacher.id, words_db=words_db, is_admin=teacher.is_admin
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/ai-query", response_model=ResponseData[AIQueryResponse])
async def ai_query(
    body: AIQueryRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """AI 自然语言查询：教师输入口语问题，AI 分析班级数据后回答"""
    result = await TeacherService.ai_query(db, body.class_id, body.question, teacher_id)
    return ResponseData(data=result)


@router.post("/ai-query/stream")
async def ai_query_stream(
    body: AIQueryRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """AI 自然语言查询 — SSE 流式版本"""
    stream_gen = TeacherService.ai_query_stream(
        db, body.class_id, body.question, teacher_id
    )
    return StreamingResponse(
        stream_gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/classes/{class_id}/students/{student_id}", response_model=ResponseData[StudentDetail])
async def student_detail(
    class_id: int,
    student_id: int,
    db: AsyncSession = Depends(get_db),
    words_db: AsyncSession = Depends(get_words_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """学生详细学习数据"""
    try:
        result = await TeacherService.get_student_detail(
            db, class_id, student_id, teacher_id, words_db=words_db
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ========== 学生信息 Excel 导入 ==========

@router.post("/classes/{class_id}/students/upload-excel", response_model=ResponseData[StudentInfoUploadResult])
async def upload_student_info_excel(
    class_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    teacher: CurrentTeacher = Depends(get_current_teacher_info),
):
    """上传学生信息 Excel（包含 序号/姓名/考号 三列）"""
    if not file.filename or not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 文件")
    try:
        content = await file.read()
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Excel upload API: filename={file.filename}, content_type={file.content_type}, "
                     f"size={len(content)} bytes")
        result = await TeacherService.import_students_from_excel(
            db, class_id, teacher.id, content,
            is_admin=teacher.is_admin, teacher_account=teacher.account,
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/classes/{class_id}/student-info", response_model=ResponseData[list[StudentInfoItem]])
async def list_student_info(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: CurrentTeacher = Depends(get_current_teacher_info),
):
    """获取班级已导入的学生信息列表"""
    try:
        items = await TeacherService.list_student_info(
            db, class_id, teacher.id, is_admin=teacher.is_admin,
        )
        return ResponseData(data=items)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/classes/{class_id}/student-info")
async def delete_student_info(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: CurrentTeacher = Depends(get_current_teacher_info),
):
    """清空班级已导入的学生信息"""
    try:
        await TeacherService.delete_student_info(
            db, class_id, teacher.id, is_admin=teacher.is_admin,
        )
        return ResponseData(message="已清空")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))



# ========== 学生考试错题(OCR批卷) ==========

@router.get("/classes/{class_id}/student-info/{exam_number}/exam-mistakes", response_model=ResponseData[StudentExamMistakesOut])
async def get_student_exam_mistakes(
    class_id: int,
    exam_number: str,
    db: AsyncSession = Depends(get_db),
    teacher: CurrentTeacher = Depends(get_current_teacher_info),
):
    """获取某学生（按考号）在班级所有考试中的错题（OCR批卷）"""
    try:
        result = await TeacherService.get_student_exam_mistakes(
            db, class_id, exam_number, teacher.id, is_admin=teacher.is_admin,
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ========== 学段配置 ==========

@router.get("/stages", response_model=ResponseData)
async def list_stages():
    """获取学段列表及对应题型"""
    stages = []
    for code, name in STAGE_CATEGORIES.items():
        qtypes = STAGE_QUESTION_TYPES.get(code, [])
        stages.append({
            "value": code,
            "label": name,
            "question_types": [
                {"value": qt, "label": QUESTION_TYPE_LABELS.get(qt, qt)}
                for qt in qtypes
            ],
        })
    return ResponseData(data={
        "stages": stages,
        "doc_categories": [
            {"value": k, "label": v} for k, v in DOC_CATEGORIES.items()
        ],
    })


@router.get("/stages/{stage}/question-types", response_model=ResponseData)
async def get_stage_question_types(
    stage: str,
):
    """获取某学段支持的题型"""
    if stage not in STAGE_CATEGORIES:
        raise HTTPException(status_code=404, detail=f"不支持的学段: {stage}")
    qtypes = STAGE_QUESTION_TYPES.get(stage, [])
    return ResponseData(data={
        "stage": stage,
        "label": STAGE_CATEGORIES.get(stage, ""),
        "question_types": [
            {"value": qt, "label": QUESTION_TYPE_LABELS.get(qt, qt)}
            for qt in qtypes
        ],
    })

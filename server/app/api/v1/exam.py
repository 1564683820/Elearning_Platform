# 试卷模块 API 路由
# AI 出卷、批卷、成绩汇总、组卷
import io
import math
import os
import re
import shutil
import logging
import traceback
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from app.db.database import get_db
from app.api.deps import (
    ExamScanPrincipal,
    get_exam_scan_principal,
    get_current_teacher_id,
    get_current_user_id,
)
from app.core.config import get_settings
from app.core.security import create_exam_scan_token
from fastapi.responses import HTMLResponse
from app.services.exam_service import ExamService
from app.services.paper_grading import grade_choice_answers
from app.services import fixed_paper_review
from app.services.exam_knowledge import read_exam_knowledge
from app.services.exam_knowledge_dates import ExamKnowledgePeriod
from app.services.exam_records import get_grading_photo, list_grading_records, read_grading_record
from app.services.paper_draft import (
    PaperDraftError, create_paper_draft as create_draft, read_paper_draft, save_paper_draft, supports_paper_template,
)
from app.services.exam_sources import (
    add_source, clean_exam_source_files, copy_paper_with_sources, detach_exam_sources,
    download_source, list_sources, remove_source, render_pdf_page,
)
from app.services.private_document_files import MAX_FILE_BYTES
from app.schemas.paper_draft import PaperDraftCopyIn, PaperDraftCreateIn, PaperDraftIn, PaperDraftOut
from app.schemas.fixed_paper_review import (
    PaperGradeRegrade, PaperGradeWithdraw, PaperGradingStateIn, PaperGradingStateOut, PaperRecognitionOut, PendingPaperReviews,
    PaperReviewConfirm, PaperReviewConflictOut, PaperReviewDiscard, PaperReviewEdits, PaperReviewOut, PaperReviewReceipt,
)
from app.schemas.exam_sources import ExamSourceOut
from app.utils.revisions import is_paper_draft
from app.services.wrong_book_service import WrongBookService
from app.schemas.common import ResponseData
from app.schemas.exam_knowledge import ExamKnowledgeOut
from app.schemas.exam_records import GradingRecordOut, GradingRecordsOut, RecordStatus
from pydantic import BaseModel
from typing import Literal, Optional, List
from datetime import date, datetime, timedelta, timezone
from app.utils.json_utils import safe_json_dumps
from app.models.exam_models import TeacherExam, ExamSubmission
from app.models.scan_models import WrongQuestionBook, ExamScanRecord
from app.models.class_models import Class, ClassStudentInfo, ClassStudent
from app.models.user import User
from sqlalchemy import select, func, delete
from urllib.parse import quote

logger = logging.getLogger(__name__)

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False
    logger.warning("fpdf2 未安装，答题卡 PDF 导出功能不可用")

try:
    from app.services.pdf_export_service import _ensure_font
except ImportError:
    def _ensure_font(): return None

from app.services.answer_sheet_generator import (
    generate_answer_sheet_html,
    generate_answer_sheet_from_exam,
    generate_answer_sheet_from_json,
    _make_option_letters,
    _make_digit_labels,
    _build_computed_regions,
    _build_computed_regions_from_json,
    generate_graderflow_sheet_html,
    generate_graderflow_sheet_from_exam,
    save_graderflow_sheet_html,
    save_graderflow_sheet_html_from_json,
    _build_graderflow_regions,
)


# ── 选项标签标准化 ──
# 选项在数据库中可能存储为 str("A. brings")、dict({"label":"A"}) 或 list(["A"])
def _opt_label(o):
    if isinstance(o, str):
        return o
    if isinstance(o, dict):
        return o.get("label", o.get("value", str(o)))
    if isinstance(o, list):
        return str(o[0]) if o else ""
    return str(o)


# 纸张尺寸映射
_PAGE_DIMS = {
    "A5": {"width": "148mm", "height": "210mm", "width_num": 148, "height_num": 210},
    "A4": {"width": "210mm", "height": "297mm", "width_num": 210, "height_num": 297},
}

router = APIRouter(prefix="/teacher/exam", tags=["教师端-试卷"])


def _require_legacy_exam(exam: TeacherExam | None, teacher_id: int):
    if exam and exam.teacher_id == teacher_id and is_paper_draft(exam.answer_sheet_config):
        raise HTTPException(status_code=409, detail="纸质批改草稿仍需完成固定答题卡配置")


# ========== 请求/响应模型 ==========

class GenerateExamRequest(BaseModel):
    """AI 出卷请求 — class_id 改为可选（发布时再选择班级）"""
    class_id: Optional[int] = None
    title: str
    knowledge_points: List[str] = []
    question_types: List[str] = ["choice", "fill", "translation"]
    question_type_counts: Optional[dict] = None  # 各题型数量，如 {"choice":5,"fill":3}
    difficulty: int = 2
    question_count: int = 10
    duration_minutes: int = 60
    grade: str = ""
    stage_category: str = ""  # 学段: preschool/primary/junior/senior/other
    use_rag: bool = True      # 是否启用 RAG 知识库参考
    additional_references: str = ""  # 用户补充参考内容（可粘贴参考试题、教材片段等）


class ComposeExamRequest(BaseModel):
    """组卷请求：从多张试卷选取题目组成新试卷"""
    title: str
    class_id: int
    selected_questions: List[dict]  # [{"exam_id":1,"question_index":0,"score":2},...]
    shuffle: bool = True
    grade: str = ""


class SaveExamRequest(BaseModel):
    """保存试卷请求"""
    class_id: Optional[int] = None
    title: str
    questions: list
    total_score: int = 100
    difficulty: int = 2
    duration_minutes: int = 60
    knowledge_points: List[str] = []
    grade: str = ""
    stage_category: str = ""
    choice_questions: Optional[List[dict]] = None  # 选择题JSON（用于答题卡配置）


class PublishExamRequest(BaseModel):
    """发布试卷请求"""
    class_id: int  # 发布时选择目标班级


class UpdateExamRequest(BaseModel):
    """更新试卷请求"""
    title: Optional[str] = None
    questions: Optional[list] = None
    total_score: Optional[int] = None
    difficulty: Optional[int] = None
    duration_minutes: Optional[int] = None
    knowledge_points: Optional[List[str]] = None
    grade: Optional[str] = None
    stage_category: Optional[str] = None
    class_id: Optional[int] = None


class GradeSubmissionRequest(BaseModel):
    """提交答案批改请求"""
    exam_id: int
    answers: list
    exam_number: str = ""


class TeacherReviewRequest(BaseModel):
    """教师复核请求"""
    adjustments: list


class AnswerSheetTemplateRequest(BaseModel):
    """答题卡模板创建/更新请求"""
    name: str
    choice_questions: List[dict]  # SKILL.md格式的选择题JSON列表
    grade: str = ""
    description: str = ""
    is_default: int = 0  # 0=否, 1=是
    create_only: bool = False


class AnswerSheetTemplateUpdate(AnswerSheetTemplateRequest):
    revision: str


# ========== 出卷 ==========

@router.post("/generate", response_model=ResponseData)
async def generate_exam(
    body: GenerateExamRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """AI 生成试卷（生成 + 保存为草稿，支持学段和 RAG 参考）"""
    # 如有 question_type_counts，用它计算总题数
    if body.question_type_counts:
        qcount = sum(body.question_type_counts.values())
    else:
        qcount = body.question_count

    class_id = body.class_id or 0  # 生成时未选择班级则用 0 占位，发布时再设

    # 使用新的 generate_and_save_with_rag 方法或直接调用 generate_exam
    exam_data = await ExamService.generate_exam(
        db, teacher_id, class_id, body.title,
        body.knowledge_points, body.question_types,
        body.difficulty, qcount, body.duration_minutes,
        body.question_type_counts, body.grade,
        stage_category=body.stage_category,
        use_rag=body.use_rag,
        additional_references=body.additional_references,
    )

    if "error" in exam_data:
        raise HTTPException(status_code=400, detail=exam_data["error"])

    # 保存试卷
    exam = await ExamService.save_exam(
        db, teacher_id,
        title=exam_data["title"],
        questions=exam_data["questions"],
        total_score=exam_data["total_score"],
        difficulty=body.difficulty,
        duration_minutes=body.duration_minutes,
        knowledge_points=body.knowledge_points,
        class_id=class_id,
        grade=body.grade,
        stage_category=body.stage_category,
    )

    # 增强题型信息：添加题号、选项数、是否多选
    questions_raw = exam_data["questions"]
    # 判断是否高中生高考卷：小题从21开始编号
    is_senior = bool(body.grade and (
        body.grade.startswith("高") or "高中" in body.grade or "高三" in body.grade
        or "senior" in body.grade.lower() or "高考" in body.grade
    ))
    start_num = 21 if is_senior else 1
    enhanced_questions = ExamService._enhance_questions(questions_raw, start_number=start_num)
    # 提取选择题JSON，基于JSON生成答题卡配置（支持每题不同选项数）
    choice_questions = ExamService._extract_choice_questions(questions_raw, exam_data["title"], start_number=start_num)
    if choice_questions:
        answer_sheet_config = ExamService._build_answer_sheet_config_from_json(exam.id, choice_questions)
    else:
        answer_sheet_config = ExamService._build_answer_sheet_config(exam.id, questions_raw)

    # 保存答题卡配置到试卷记录
    if answer_sheet_config:
        exam.answer_sheet_config = answer_sheet_config
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(exam, "answer_sheet_config")

    result = {
        "id": exam.id,
        "exam_id": exam.id,
        "title": exam.title,
        "class_id": class_id,
        "questions": enhanced_questions,
        "total_score": exam_data["total_score"],
        "question_count": exam_data["question_count"],
        "difficulty": body.difficulty,
        "duration_minutes": body.duration_minutes,
        "knowledge_points": body.knowledge_points,
        "grade": body.grade,
        "stage_category": body.stage_category,
        "status": exam.status,
        "answer_sheet": answer_sheet_config,
        "created_at": datetime.now().isoformat(),
    }

    # 如果服务返回了部分结果警告，透传给前端
    if partial_warning := exam_data.get("_partial_warning", ""):
        result["partial_warning"] = partial_warning
        return ResponseData(data=result, message=partial_warning)
    return ResponseData(data=result)


# ========== 流式生成试卷（SSE） ==========

class GenerateExamStreamRequest(GenerateExamRequest):
    """流式生成试卷请求（继承 GenerateExamRequest，无额外字段）"""
    pass


@router.post("/generate-stream")
async def generate_exam_stream(
    body: GenerateExamStreamRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """SSE 流式生成试卷，按题型逐事件推送进度

    SSE 事件格式：
      event: type_start / type_done / type_error / exam_done / error
      data: { ...json... }

    前端使用 EventSource 或 fetch + ReadableStream 消费。
    """
    # 如有 question_type_counts，用它计算总题数
    if body.question_type_counts:
        qcount = sum(body.question_type_counts.values())
    else:
        qcount = body.question_count

    class_id = body.class_id or 0  # 生成时未选择班级则用 0 占位

    async def event_generator():
        async for event in ExamService.generate_exam_stream(
            db=db, teacher_id=teacher_id, class_id=class_id,
            title=body.title, knowledge_points=body.knowledge_points,
            question_types=body.question_types, difficulty=body.difficulty,
            question_count=qcount, duration_minutes=body.duration_minutes,
            question_type_counts=body.question_type_counts, grade=body.grade,
            stage_category=body.stage_category, use_rag=body.use_rag,
            additional_references=body.additional_references,
        ):
            # 拦截 exam_done，保存到数据库并补上 id/status
            if event.get("type") == "exam_done":
                data = event.get("data", {})
                if data.get("questions"):
                    questions_raw = data["questions"]
                    exam = await ExamService.save_exam(
                        db, teacher_id,
                        title=data.get("title", body.title),
                        questions=questions_raw,
                        total_score=data.get("total_score", 100),
                        difficulty=body.difficulty,
                        duration_minutes=body.duration_minutes,
                        knowledge_points=body.knowledge_points,
                        class_id=class_id,
                        grade=body.grade,
                        stage_category=body.stage_category,
                    )
                    # 补上 id 和 status
                    data["id"] = exam.id
                    data["exam_id"] = exam.id
                    data["status"] = exam.status
                    data["created_at"] = datetime.now().isoformat()
                    # 增强题型信息：添加题号、选项数、是否多选
                    is_senior = bool(body.grade and (
                        body.grade.startswith("高") or "高中" in body.grade or "高三" in body.grade
                        or "senior" in body.grade.lower() or "高考" in body.grade
                    ))
                    start_num = 21 if is_senior else 1
                    data["questions"] = ExamService._enhance_questions(questions_raw, start_number=start_num)
                    choice_questions = ExamService._extract_choice_questions(questions_raw, data.get("title", body.title), start_number=start_num)
                    if choice_questions:
                        answer_sheet_config = ExamService._build_answer_sheet_config_from_json(exam.id, choice_questions)
                    else:
                        answer_sheet_config = ExamService._build_answer_sheet_config(exam.id, questions_raw)
                    # 保存答题卡配置到试卷记录
                    if answer_sheet_config:
                        data["answer_sheet"] = answer_sheet_config
                        exam.answer_sheet_config = answer_sheet_config
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(exam, "answer_sheet_config")
                    else:
                        data["answer_sheet"] = answer_sheet_config
                    event["data"] = data
                    # 立即提交事务，确保后续 PUT/POST 请求能看到刚创建的试卷
                    await db.commit()
            yield f"data: {safe_json_dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/manual-save", response_model=ResponseData)
async def save_exam(
    body: SaveExamRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """手动保存试卷（支持学段），支持选择题JSON配置答题卡"""
    exam = await ExamService.save_exam(
        db, teacher_id, body.title,
        body.questions, body.total_score, body.difficulty,
        body.duration_minutes, body.knowledge_points,
        class_id=body.class_id or 0,
        grade=body.grade,
        stage_category=body.stage_category,
        choice_questions=body.choice_questions,
    )
    return ResponseData(data={
        "exam_id": exam.id,
        "title": exam.title,
        "status": exam.status,
        "answer_sheet": exam.answer_sheet_config,
    })


@router.get("/list", response_model=ResponseData)
async def list_exams(
    class_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="筛选状态: draft/published"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=256),
    paper_status: Literal["draft", "ready", "grading", "completed"] | None = Query(None),
    grading_view: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取试卷列表（支持按状态筛选）"""
    result = await ExamService.list_exams(
        db, teacher_id, class_id, status, page, page_size,
        search=search.strip(), paper_status=paper_status, grading_view=grading_view,
    )
    return ResponseData(data=result)


@router.post("/paper-drafts", response_model=ResponseData[PaperDraftOut])
async def create_paper_draft(
    body: PaperDraftCreateIn,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        draft = await create_draft(db, teacher_id, body)
        await db.commit()
        return ResponseData(data=draft)
    except PaperDraftError as error:
        raise HTTPException(error.status, str(error)) from error


@router.post("/{exam_id:int}/paper-copy", response_model=ResponseData[PaperDraftOut])
async def copy_paper_draft(
    exam_id: int, body: PaperDraftCopyIn, db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        return ResponseData(data=await copy_paper_with_sources(db, teacher_id, exam_id, body.request_id))
    except PaperDraftError as error:
        raise HTTPException(error.status, detail=str(error)) from error


@router.get("/{exam_id:int}/sources", response_model=ResponseData[list[ExamSourceOut]])
async def get_exam_sources(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        return ResponseData(data=await list_sources(db, teacher_id, exam_id))
    except PaperDraftError as error:
        raise HTTPException(error.status, str(error)) from error


@router.post("/{exam_id:int}/sources", response_model=ResponseData[ExamSourceOut])
async def upload_exam_source(
    exam_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        data = await file.read(MAX_FILE_BYTES + 1)
        return ResponseData(data=await add_source(db, teacher_id, exam_id, file.filename or "", data))
    except PaperDraftError as error:
        raise HTTPException(error.status, str(error)) from error
    finally:
        await file.close()


@router.get("/{exam_id:int}/sources/{source_id:int}")
async def get_exam_source(
    exam_id: int,
    source_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        path, filename, media_type = await download_source(db, teacher_id, exam_id, source_id)
    except PaperDraftError as error:
        raise HTTPException(error.status, str(error)) from error
    return FileResponse(path, filename=filename, media_type=media_type, headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.delete("/{exam_id:int}/sources/{source_id:int}", response_model=ResponseData)
async def remove_exam_source(
    exam_id: int,
    source_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        await remove_source(db, teacher_id, exam_id, source_id)
    except PaperDraftError as error:
        raise HTTPException(error.status, str(error)) from error
    return ResponseData(message="已移除原件")


@router.get("/{exam_id:int}/sources/{source_id:int}/preview", response_class=Response)
async def preview_exam_source(
    exam_id: int,
    source_id: int,
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    from starlette.concurrency import run_in_threadpool

    try:
        path, _, _ = await download_source(db, teacher_id, exam_id, source_id)
        data, pages = await run_in_threadpool(render_pdf_page, path, page)
    except PaperDraftError as error:
        raise HTTPException(error.status, str(error)) from error
    return Response(content=data, media_type="image/png", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "X-Page-Count": str(pages),
    })


@router.get("/{exam_id:int}/paper-draft", response_model=ResponseData[PaperDraftOut])
async def get_paper_draft(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        return ResponseData(data=await read_paper_draft(db, teacher_id, exam_id))
    except PaperDraftError as error:
        raise HTTPException(error.status, str(error)) from error


@router.put("/{exam_id:int}/paper-draft", response_model=ResponseData[PaperDraftOut])
async def put_paper_draft(
    exam_id: int,
    body: PaperDraftIn,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        return ResponseData(data=await save_paper_draft(db, teacher_id, body, exam_id))
    except PaperDraftError as error:
        raise HTTPException(error.status, str(error)) from error


@router.get("/{exam_id:int}", response_model=ResponseData)
async def get_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取试卷详情"""
    result = await ExamService.get_exam_detail(db, exam_id, teacher_id)
    if not result:
        # 诊断日志 — 区分"不存在" 和 "无权限"
        db_exam = (await db.execute(select(TeacherExam).where(TeacherExam.id == exam_id))).scalar_one_or_none()
        if db_exam:
            import logging
            logger = logging.getLogger("exam_api")
            logger.warning(
                f"[exam_detail_mismatch] exam_id={exam_id}, "
                f"exam_teacher_id={db_exam.teacher_id}, "
                f"request_teacher_id={teacher_id}, "
                f"exam_title={db_exam.title}"
            )
        raise HTTPException(status_code=404, detail="试卷不存在")
    return ResponseData(data=result)


@router.get("/{exam_id:int}/grading-knowledge", response_model=ResponseData[ExamKnowledgeOut])
async def get_grading_knowledge(
    exam_id: int,
    question_number: int | None = Query(None, ge=1),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    if (date_from is None) != (date_to is None):
        raise HTTPException(status_code=422, detail="请同时提供开始和结束日期")
    try:
        period = ExamKnowledgePeriod(date_from, date_to) if date_from and date_to else None
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if question_number is None and period is None:
        raise HTTPException(status_code=422, detail="请选择题号或日期范围")
    result = await read_exam_knowledge(db, teacher_id, exam_id, question_number, period)
    if result is None or (question_number is not None and not result["questions"]):
        raise HTTPException(status_code=404, detail="未找到试卷题目")
    return ResponseData(data=ExamKnowledgeOut.model_validate(result))


@router.get("/{exam_id:int}/grading-records", response_model=ResponseData[GradingRecordsOut])
async def grading_records(
    exam_id: int,
    search: str = Query("", max_length=64),
    status: RecordStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_scans: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    result = await list_grading_records(
        db, exam_id, teacher_id, search=search.strip(), status=status or "", page=page, page_size=page_size,
        include_scans=include_scans,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="试卷不存在")
    return ResponseData(data=GradingRecordsOut.model_validate(result))


@router.get("/{exam_id:int}/grading-records/{submission_id:int}", response_model=ResponseData[GradingRecordOut])
async def grading_record_detail(
    exam_id: int,
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    result = await read_grading_record(db, exam_id, teacher_id, submission_id)
    if result is None:
        raise HTTPException(status_code=404, detail="批改记录不存在")
    return ResponseData(data=GradingRecordOut.model_validate(result))


@router.post("/{exam_id:int}/grading-records/{submission_id:int}/regrade", response_model=ResponseData[PaperRecognitionOut])
async def prepare_grading_record_regrade(
    exam_id: int, submission_id: int, body: PaperGradeRegrade,
    db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        result = await fixed_paper_review.prepare_regrade(db, exam_id, teacher_id, submission_id, body)
    except fixed_paper_review.PaperReviewError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    await db.commit()
    return ResponseData(data=result)


@router.post("/{exam_id:int}/grading-records/{submission_id:int}/withdraw", response_model=ResponseData[dict[str, int]])
async def withdraw_fixed_grade(
    exam_id: int, submission_id: int, body: PaperGradeWithdraw,
    db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        result = await fixed_paper_review.withdraw_grade(db, exam_id, teacher_id, submission_id, body)
    except fixed_paper_review.PaperReviewError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    await db.commit()
    return ResponseData(data=result)


@router.get("/{exam_id:int}/grading-records/{submission_id:int}/photo")
async def grading_record_photo(
    exam_id: int,
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    from starlette.concurrency import run_in_threadpool

    photo = await get_grading_photo(db, exam_id, teacher_id, submission_id)
    if photo is None or not await run_in_threadpool(photo.is_file):
        raise HTTPException(status_code=404, detail="答题卡照片不存在")
    return FileResponse(photo, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{exam_id:int}/paper-grading-state", response_model=ResponseData[PaperGradingStateOut])
async def paper_grading_state(
    exam_id: int, db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        result = await fixed_paper_review.read_grading_state(db, exam_id, teacher_id)
    except fixed_paper_review.PaperReviewError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    return ResponseData(data=result)


@router.get(
    "/{exam_id:int}/fixed-card/reference", response_class=Response,
    responses={200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}},
               204: {"description": "本卷暂无可用答题卡样张"}},
)
async def read_fixed_card_reference(
    exam_id: int, db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        sample = await fixed_paper_review.read_card_reference(db, exam_id, teacher_id)
    except fixed_paper_review.PaperReviewError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    if sample is None:
        return Response(status_code=204, headers=headers)
    reference, version = sample
    return Response(reference, media_type="image/png", headers={**headers, "X-Paper-Layout-Version": version})


@router.put("/{exam_id:int}/paper-grading-state", response_model=ResponseData[PaperGradingStateOut])
async def set_paper_grading_state(
    exam_id: int, body: PaperGradingStateIn,
    db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        result = await fixed_paper_review.update_grading_state(db, exam_id, teacher_id, body)
    except fixed_paper_review.PaperReviewError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    await db.commit()
    return ResponseData(data=result)


@router.post("/{exam_id:int}/fixed-scan", response_model=ResponseData[PaperRecognitionOut])
async def upload_fixed_card_photo(
    exam_id: int, image: UploadFile = File(...), request_id: str = Form(...),
    db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id),
):
    from pathlib import PurePath
    from app.services.answer_card_photos import MAX_SCAN_PHOTO_BYTES

    try:
        data = await image.read(MAX_SCAN_PHOTO_BYTES + 1)
        result = await fixed_paper_review.recognize_photo(
            db, exam_id, teacher_id, request_id, data, PurePath(image.filename or "").suffix,
        )
    except fixed_paper_review.PaperReviewError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    finally:
        await image.close()
    await db.commit()
    return ResponseData(data=result)


@router.get("/{exam_id:int}/fixed-reviews", response_model=ResponseData[PendingPaperReviews])
async def list_fixed_reviews(
    exam_id: int, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    status: Literal["pending_review", "discarded", "failed"] = "pending_review",
    db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        result = await fixed_paper_review.list_reviews(db, exam_id, teacher_id, page, page_size, status)
    except fixed_paper_review.PaperReviewError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    return ResponseData(data=result)


@router.get("/{exam_id:int}/fixed-reviews/{scan_id:int}", response_model=ResponseData[PaperReviewOut])
async def fixed_review(
    exam_id: int, scan_id: int, db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        result = await fixed_paper_review.read_review(db, exam_id, teacher_id, scan_id)
    except fixed_paper_review.PaperReviewError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    return ResponseData(data=result)


@router.get("/{exam_id:int}/fixed-reviews/{scan_id:int}/photo", response_class=FileResponse)
async def fixed_review_photo(
    exam_id: int, scan_id: int, db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        photo = await fixed_paper_review.read_review_photo(db, exam_id, teacher_id, scan_id)
    except fixed_paper_review.PaperReviewError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    if photo is None:
        raise HTTPException(status_code=404, detail="答题卡照片不存在")
    return FileResponse(photo, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.put("/{exam_id:int}/fixed-reviews/{scan_id:int}", response_model=ResponseData[PaperReviewOut])
async def edit_fixed_review(
    exam_id: int, scan_id: int, body: PaperReviewEdits,
    db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        result = await fixed_paper_review.edit_review(db, exam_id, teacher_id, scan_id, body)
    except fixed_paper_review.PaperReviewError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    await db.commit()
    return ResponseData(data=result)


@router.post("/{exam_id:int}/fixed-reviews/{scan_id:int}/discard", response_model=ResponseData[dict[str, bool]])
async def discard_fixed_review(
    exam_id: int, scan_id: int, body: PaperReviewDiscard,
    db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        result = await fixed_paper_review.discard_review(db, exam_id, teacher_id, scan_id, body)
    except fixed_paper_review.PaperReviewError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    await db.commit()
    return ResponseData(data=result)


@router.post(
    "/{exam_id:int}/fixed-reviews/{scan_id:int}/confirm",
    response_model=ResponseData[PaperReviewReceipt],
    responses={409: {"model": PaperReviewConflictOut}},
)
async def confirm_fixed_review(
    exam_id: int, scan_id: int, body: PaperReviewConfirm,
    db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        result = await fixed_paper_review.confirm_review(db, exam_id, teacher_id, scan_id, body)
    except fixed_paper_review.PaperReviewError as error:
        if error.conflict:
            await db.rollback()
            conflict = PaperReviewConflictOut(detail=str(error), error_code="paper_review_conflict")
            return JSONResponse(status_code=409, content=conflict.model_dump())
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    await db.commit()
    return ResponseData(data=result)


@router.put("/{exam_id}", response_model=ResponseData)
async def update_exam(
    exam_id: int,
    body: UpdateExamRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """更新试卷"""
    _require_legacy_exam(await db.get(TeacherExam, exam_id, with_for_update=True), teacher_id)
    kwargs = body.model_dump(exclude_none=True)
    result = await ExamService.update_exam(db, exam_id, teacher_id, **kwargs)
    if not result:
        raise HTTPException(status_code=404, detail="试卷不存在或无权限")
    return ResponseData(data={"exam_id": result.id, "status": result.status})


# ========== 组卷 ==========

@router.get("/list-for-pick", response_model=ResponseData)
async def list_exams_for_pick(
    stage_category: Optional[str] = Query(None, description="学段过滤"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取可用于选题的试卷列表（含每题预览）"""
    items = await ExamService.list_exams_for_pick(db, teacher_id, stage_category or "")
    return ResponseData(data={"exams": items})


@router.post("/compose", response_model=ResponseData)
async def compose_exam(
    body: ComposeExamRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """从多张试卷选取题目，组合生成新试卷"""
    try:
        result = await ExamService.compose_exam(
            db, teacher_id, body.title, body.class_id,
            body.selected_questions, body.shuffle, body.grade,
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{exam_id}/publish", response_model=ResponseData)
async def publish_exam(
    exam_id: int,
    body: PublishExamRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """发布试卷（需指定目标班级，自动生成答题卡配置）"""
    _require_legacy_exam(await db.get(TeacherExam, exam_id, with_for_update=True), teacher_id)
    result = await ExamService.publish_exam(db, exam_id, teacher_id, class_id=body.class_id)
    if not result:
        raise HTTPException(status_code=404, detail="试卷不存在或无权限")

    # 返回答题卡配置
    answer_sheet = None
    if result.answer_sheet_config:
        answer_sheet = result.answer_sheet_config
    else:
        questions = result.questions or []
        # 判断是否高中生高考卷
        is_senior = bool(result.grade and (
            result.grade.startswith("高") or "高中" in result.grade or "高三" in result.grade
            or "senior" in result.grade.lower() or "高考" in result.grade
        ))
        start_num = 21 if is_senior else 1
        choice_questions = ExamService._extract_choice_questions(questions, result.title, start_number=start_num)
        if choice_questions:
            answer_sheet = ExamService._build_graderflow_sheet_config_from_json(exam_id, choice_questions, result.title, id_digits=7)
        else:
            answer_sheet = ExamService._build_graderflow_sheet_config(exam_id, questions, result.title, id_digits=7)

    return ResponseData(data={
        "exam_id": result.id,
        "status": result.status,
        "answer_sheet": answer_sheet,
    })


@router.delete("/{exam_id}", response_model=ResponseData)
async def delete_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """删除试卷"""
    exam = await db.get(TeacherExam, exam_id, with_for_update=True)
    paths = await detach_exam_sources(db, teacher_id, exam_id) if (
        exam is not None and exam.teacher_id == teacher_id and is_paper_draft(exam.answer_sheet_config)
    ) else []
    result = await ExamService.delete_exam(db, exam_id, teacher_id)
    if not result:
        raise HTTPException(status_code=404, detail="试卷不存在或无权限")
    if paths:
        await db.commit()
        await clean_exam_source_files(paths)
    return ResponseData(message="删除成功")


# ========== 批卷 ==========

@router.post("/grade", response_model=ResponseData)
async def grade_submission(
    body: GradeSubmissionRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """AI 自动批改学生提交"""
    exam = await db.get(TeacherExam, body.exam_id)
    if not exam or exam.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="试卷不存在")
    _require_legacy_exam(exam, teacher_id)
    result = await ExamService.auto_grade_submission(
        db, body.exam_id, teacher_id, body.answers, teacher_id,
        exam_number=body.exam_number,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return ResponseData(data=result)


# ========== 成绩管理 ==========

@router.post("/{exam_id}/submissions/{submission_id}/review", response_model=ResponseData)
async def teacher_review(
    exam_id: int,
    submission_id: int,
    body: TeacherReviewRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """教师复核/调整评分"""
    exam = await db.get(TeacherExam, exam_id)
    submission = await db.get(ExamSubmission, submission_id)
    if not exam or exam.teacher_id != teacher_id or not submission or submission.exam_id != exam_id:
        raise HTTPException(status_code=404, detail="提交记录不存在")
    _require_legacy_exam(exam, teacher_id)
    result = await ExamService.teacher_review(
        db, submission_id, teacher_id, body.adjustments
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return ResponseData(data=result)


@router.get("/{exam_id}/submissions", response_model=ResponseData)
async def list_submissions(
    exam_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取试卷提交列表"""
    result = await ExamService.get_submissions(db, exam_id, teacher_id, page, page_size)
    if "error" in result:
        import logging
        logger = logging.getLogger("exam_api")
        logger.warning(
            f"[submissions_error] exam_id={exam_id}, teacher_id={teacher_id}, "
            f"error={result['error']}"
        )
        raise HTTPException(status_code=404, detail=result["error"])
    return ResponseData(data=result)


@router.get("/{exam_id}/results", response_model=ResponseData)
async def get_exam_results(
    exam_id: int,
    class_id: int = Query(..., description="班级ID"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取某班级所有学生的考试成绩列表（扫描答题卡批卷用）

    返回 ClassStudentInfo 花名册信息 + ExamSubmission 成绩，
    按成绩降序排列，未批改的排在最后且分数显示为 null。
    """
    result = await ExamService.get_class_exam_results(
        db, exam_id, class_id, teacher_id
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return ResponseData(data=result)


@router.get("/{exam_id}/statistics", response_model=ResponseData)
async def exam_statistics(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """试卷统计"""
    result = await ExamService.get_exam_statistics(db, exam_id, teacher_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return ResponseData(data=result)


class SubmitScanRequest(BaseModel):
    """摄像头扫描批改结果提交"""
    exam_number: str = ""
    student_id: Optional[int] = None
    score: int = 0
    max_score: int = 0
    multi_score: int = 0
    multi_max_score: int = 0
    grading_status: str = "ai_done"
    pending_count: int = 0
    answers: list = []
    wrong_questions: list = []
    scan_image_url: str = ""


# ========== 摄像头扫描批卷 ==========

@router.post("/{exam_id}/scan", response_model=ResponseData)
async def submit_scan_result(
    exam_id: int,
    body: SubmitScanRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """提交摄像头扫描批改结果"""
    _require_legacy_exam(await db.get(TeacherExam, exam_id), teacher_id)
    result = await ExamService.submit_scan_result(
        db, exam_id, teacher_id, body.model_dump()
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return ResponseData(data=result)


@router.get("/{exam_id}/scan-progress", response_model=ResponseData)
async def get_scan_progress(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取扫描批改进度"""
    result = await ExamService.get_scan_progress(db, exam_id, teacher_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return ResponseData(data=result)


# ========== 成绩报告 ==========

@router.get("/{exam_id}/report", response_model=ResponseData)
async def get_exam_report(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取试卷成绩统计报告（含正确率分布、高频错题等）"""
    result = await ExamService.get_exam_report(db, exam_id, teacher_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return ResponseData(data=result)


@router.get("/{exam_id}/report/question/{question_number}", response_model=ResponseData)
async def get_question_detail(
    exam_id: int,
    question_number: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取单题学情详情"""
    result = await ExamService.get_question_detail(
        db, exam_id, question_number, teacher_id
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return ResponseData(data=result)


@router.get("/{exam_id}/student/{student_id}", response_model=ResponseData)
async def get_student_exam_detail(
    exam_id: int,
    student_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取学生答卷详情"""
    result = await ExamService.get_student_exam_detail(
        db, exam_id, student_id, teacher_id
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return ResponseData(data=result)


@router.get("/{exam_id}/answer-sheet-template", response_model=ResponseData)
async def get_answer_sheet_template(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取答题卡模板配置（含坐标配置 + 可下载URL）

    返回:
        - coordinate_config: 摄像头扫描定位用的坐标配置
        - html_url: 答题卡HTML预览地址
        - pdf_url: 答题卡PDF下载地址
        - exam: 试卷基本信息
    """
    exam = await ExamService.get_exam_detail(db, exam_id, teacher_id)
    if not exam:
        raise HTTPException(status_code=404, detail="试卷不存在")

    questions = exam.get("questions", [])
    total_questions = len(questions)

    # 取第一道题的选项作为统一选项（兜底）
    if questions and questions[0].get("options"):
        unified_options = questions[0]["options"]
    else:
        unified_options = ["A", "B", "C", "D"]

    # 判断是否高中生高考卷
    grade_val = exam.get("grade", "") or ""
    is_senior = bool(grade_val and (
        grade_val.startswith("高") or "高中" in grade_val or "高三" in grade_val
        or "senior" in grade_val.lower() or "高考" in grade_val
    ))
    start_num = 21 if is_senior else 1
    # 提取选择题JSON，优先使用每题不同选项数的配置
    choice_questions = ExamService._extract_choice_questions(questions, exam.get("title", ""), start_number=start_num)
    if choice_questions:
        coord_config = _build_computed_regions_from_json(
            choice_questions=choice_questions,
            id_digits=6,
            id_options=_make_digit_labels(9),
        )
    else:
        coord_config = _build_computed_regions(
            question_count=total_questions,
            options=unified_options,
            id_digits=6,
            id_options=_make_digit_labels(9),
        )

    # 构建区域详情 — 必须用 choice_questions 而非原始 questions，
    # 因为 _extract_choice_questions 会展开阅读理解的子题、完形填空的空格等，
    # 与试卷发布时 _build_answer_sheet_config_from_json 用的数据一致。
    regions = []
    if choice_questions:
        for i, cq in enumerate(choice_questions):
            qr = coord_config["question_regions"][i] if i < len(coord_config["question_regions"]) else {}
            raw_opts = cq.get("options", list("ABCD"))
            opt_labels = _make_option_letters(len(raw_opts))
            regions.append({
                "question_number": cq.get("question_number", i + 1),
                "type": cq.get("question_type", "single_choice"),
                "score": cq.get("score", 1.0),
                "correct_answer": cq.get("correct_answer", ""),
                "options": opt_labels,
                "option_count": len(raw_opts),
                "option_regions": qr.get("option_regions", []),
            })
    else:
        # 无选择题时回退到原始 questions
        for i, q in enumerate(questions):
            qr = coord_config["question_regions"][i] if i < len(coord_config["question_regions"]) else {}
            raw_opts = q.get("options", unified_options)
            opt_labels = _make_option_letters(len(raw_opts))
            regions.append({
                "question_number": i + 1,
                "type": q.get("type", "single"),
                "score": q.get("score", 0),
                "correct_answer": q.get("correct_answer", ""),
                "options": opt_labels,
                "option_count": len(raw_opts),
                "option_regions": qr.get("option_regions", []),
            })

    return ResponseData(data={
        "exam_id": exam_id,
        "title": exam.get("title", ""),
        "total_questions": len(choice_questions) if choice_questions else total_questions,
        "option_count": len(unified_options),
        "options": unified_options,
        # 扫描定位配置
        "coordinate_config": {
            "canvas_width": coord_config["canvas_width"],
            "canvas_height": coord_config["canvas_height"],
            "id_regions": coord_config["id_regions"],
            "id_digits": coord_config["id_digits"],
            "id_options": coord_config["id_options"],
        },
        "regions": regions,
        # 下载链接
        "html_url": f"/teacher/exam/{exam_id}/answer-sheet-html",
        "pdf_url": f"/teacher/exam/{exam_id}/answer-sheet-pdf",
    })


class AnswerSheetFromJsonRequest(BaseModel):
    """基于选择题JSON生成答题卡的请求"""
    title: str = "标准答题卡"
    choice_questions: List[dict]  # 选择题JSON列表
    page_size: str = "A4"
    id_digits: int = 6


@router.post("/answer-sheet-from-json", response_model=ResponseData)
async def answer_sheet_from_json(
    body: AnswerSheetFromJsonRequest,
):
    """基于选择题JSON生成答题卡配置（支持每题不同选项数）

    接收 SKILL.md 格式的 choice_questions JSON，返回：
        - html: 答题卡HTML内容
        - coordinate_config: 扫描坐标配置
        - regions: 每题区域信息
    """
    if not body.choice_questions:
        raise HTTPException(status_code=400, detail="choice_questions 不能为空")

    page_dim = _PAGE_DIMS.get(body.page_size.upper(), _PAGE_DIMS["A4"])
    id_options = _make_digit_labels(9)

    # 生成答题卡HTML
    html = generate_answer_sheet_from_json(
        title=body.title,
        choice_questions=body.choice_questions,
        page_size=body.page_size,
        page_width=page_dim["width"],
        page_height=page_dim["height"],
        id_digits=body.id_digits,
        id_options=id_options,
        show_student_id=True,
    )

    # 计算坐标配置
    coord_config = _build_computed_regions_from_json(
        choice_questions=body.choice_questions,
        id_digits=body.id_digits,
        id_options=id_options,
        page_width_mm=page_dim["width_num"],
        page_height_mm=page_dim["height_num"],
    )

    # 构建每道题的区域信息
    regions = []
    for i, q in enumerate(body.choice_questions):
        qr = coord_config["question_regions"][i] if i < len(coord_config["question_regions"]) else {}
        opts = q.get("options", _make_option_letters(q.get("option_count", 4)))
        regions.append({
            "question_number": q.get("question_number", i + 1),
            "type": q.get("question_type", "single_choice"),
            "score": q.get("score", 1.0),
            "correct_answer": q.get("correct_answer", ""),
            "options": opts,
            "option_count": len(opts),
            "option_regions": qr.get("option_regions", []),
        })

    return ResponseData(data={
        "title": body.title,
        "total_questions": len(body.choice_questions),
        "max_option_count": max(
            (q.get("option_count", len(q.get("options", ["A","B","C","D"]))) for q in body.choice_questions),
            default=4,
        ),
        "html": html,
        "coordinate_config": {
            "canvas_width": coord_config["canvas_width"],
            "canvas_height": coord_config["canvas_height"],
            "id_regions": coord_config["id_regions"],
            "id_digits": coord_config["id_digits"],
            "id_options": coord_config["id_options"],
        },
        "regions": regions,
    })


@router.post("/answer-sheet-from-json/pdf")
async def answer_sheet_from_json_pdf(
    body: AnswerSheetFromJsonRequest,
):
    """基于选择题JSON生成答题卡PDF

    先生成答题卡HTML，再使用系统浏览器（Edge/Chrome）headless 模式渲染为PDF。
    """
    import traceback
    try:
        if not body.choice_questions:
            raise HTTPException(status_code=400, detail="choice_questions 不能为空")

        page_dim = _PAGE_DIMS.get(body.page_size.upper(), _PAGE_DIMS["A4"])

        # 1. 生成答题卡HTML（复用JSON生成逻辑）
        html_content = generate_answer_sheet_from_json(
            title=body.title,
            choice_questions=body.choice_questions,
            page_size=body.page_size,
            page_width=page_dim["width"],
            page_height=page_dim["height"],
            id_digits=body.id_digits,
            id_options=_make_digit_labels(9),
            show_student_id=True,
        )
        logger.info("答题卡HTML（模板）生成成功，长度=%d 字符", len(html_content))

        # 2. 使用系统浏览器 headless 转PDF
        pdf_bytes = _html_to_pdf_with_browser(html_content)
        if pdf_bytes is None:
            raise HTTPException(status_code=500, detail="PDF 生成失败：无法通过浏览器渲染 PDF")

        logger.info("PDF（模板）生成成功，大小=%d 字节", len(pdf_bytes))

        safe_name = body.title.replace("/", "_").replace("\\", "_").replace(" ", "_")
        # 中文文件名必须用 filename* (RFC 5987)，filename 留 ASCII fallback
        ascii_name = "".join(c for c in safe_name if ord(c) < 128) or "answer_sheet"
        encoded_name = quote(f"answer_sheet_{safe_name}.pdf", safe="")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="answer_sheet_{ascii_name}.pdf"; filename*=UTF-8\'\'{encoded_name}',
                "Content-Type": "application/pdf",
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.error("answer_sheet_from_json_pdf ValueError: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"PDF 生成内部错误: {e}")
    except Exception as e:
        logger.error("answer_sheet_from_json_pdf 异常: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"PDF 生成异常: {e}")


@router.get("/answer-sheet-template-static")
async def static_answer_sheet_html(
    question_count: int = Query(100, ge=1, le=300, description="题目总数"),
    option_count: int = Query(4, ge=2, le=10, description="每道题的选项数"),
    id_digits: int = Query(6, ge=1, le=12, description="考号位数"),
    questions_per_row: int = Query(5, ge=2, le=10, description="每行显示几道题"),
    show_answer_key: bool = Query(True, description="是否生成参考答案页"),
    title: str = Query("标准答题卡", description="试卷标题"),
    page_size: str = Query("A4", description="纸张尺寸 (A5/A4)"),
):
    """返回动态答题卡模板的 HTML 页面（可按参数调整题量/选项数/考号位数等）

    查询参数:
        question_count: 题目总数（1-300，默认 100）
        option_count: 选项数（2-10，默认 4，对应 A-D）
        id_digits: 考号位数（1-12，默认 6）
        questions_per_row: 每行几道题（2-10，默认 5）
        show_answer_key: 是否显示参考答案页（默认 true）
        title: 试卷标题（默认 "标准答题卡"）
        page_size: 纸张尺寸（A5 或 A4，默认 A4）
    """
    from fastapi.responses import HTMLResponse

    options = _make_option_letters(option_count)
    page_dim = _PAGE_DIMS.get(page_size.upper(), _PAGE_DIMS["A4"])
    html = generate_answer_sheet_html(
        title=title,
        page_size=page_size,
        page_width=page_dim["width"],
        page_height=page_dim["height"],
        question_count=question_count,
        options=options,
        questions_per_row=questions_per_row,
        id_digits=id_digits,
        show_answer_key=show_answer_key,
    )
    return HTMLResponse(content=html, status_code=200)


@router.get("/answer-sheet-template-pdf")
async def static_answer_sheet_pdf(
    question_count: int = Query(100, ge=1, le=300, description="题目总数"),
    option_count: int = Query(4, ge=2, le=10, description="每道题的选项数"),
    id_digits: int = Query(6, ge=1, le=12, description="考号位数"),
    show_answer_key: bool = Query(True, description="是否生成参考答案页"),
    title: str = Query("标准答题卡", description="试卷标题"),
    page_size: str = Query("A4", description="纸张尺寸 (A5/A4)"),
):
    """返回动态答题卡模板的 PDF（纯 fpdf2 实现，无需系统依赖）

    查询参数同 /answer-sheet-template-static
    """
    if not FPDF_AVAILABLE:
        raise HTTPException(status_code=501, detail="PDF 导出功能不可用（fpdf2 未安装）")

    options = _make_option_letters(option_count)
    page_dim = _PAGE_DIMS.get(page_size.upper(), _PAGE_DIMS["A4"])

    font_path = _ensure_font()

    # 使用 png 子图和 fpdf2 生成答题卡 PDF
    orientation = "P" if page_size.upper() in ("A4", "A5") else "L"
    pdf = FPDF(orientation=orientation, unit="mm", format=page_size.upper())
    pdf.set_auto_page_break(auto=True, margin=10)

    # 注册中文字体（TTC/TTF 均可），使用 try/except 避免返回值兼容性问题
    use_cjk = False
    if font_path:
        try:
            pdf.add_font("CJK", "", font_path, uni=True)
            use_cjk = True
            logger.info("static_answer_sheet_pdf 注册字体成功: %s", font_path)
        except Exception as e:
            logger.warning("static_answer_sheet_pdf 注册字体失败: %s", e)
            try:
                pdf.add_font("CJK", "", font_path)
                use_cjk = True
                logger.info("static_answer_sheet_pdf 注册字体成功（非 uni 模式）")
            except Exception as e2:
                logger.warning("static_answer_sheet_pdf 非 uni 模式也失败: %s", e2)

    if not use_cjk:
        font_path = None

    pdf.add_page()

    # ── 标题 ──
    if use_cjk:
        pdf.set_font("CJK", "", 11)
    else:
        pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, title, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # ── 左上：学生信息区 ──
    top_y = pdf.get_y()
    info_x = 8
    info_w = 55
    info_h = 35 if page_size.upper() == "A5" else 40
    pdf.set_draw_color(0, 0, 0)
    pdf.rect(info_x, top_y, info_w, info_h)
    if use_cjk:
        pdf.set_font("CJK", "", 6)
    else:
        pdf.set_font("Helvetica", "", 6)
    pdf.set_xy(info_x + 2, top_y + 1)
    pdf.cell(50, 4, "▼ 请用黑色签字笔填写", align="C")
    for i, label in enumerate(["姓名：_______________", "班级：_______________", "考号：_______________"]):
        pdf.set_xy(info_x + 2, top_y + 6 + i * 9)
        pdf.cell(50, 7, label)

    # ── 右上：考号填涂区 ──
    id_x = info_x + info_w + 5
    id_w = (page_dim["width_num"] if page_size.upper() == "A5" else 140) - id_x - 5
    id_h = info_h
    pdf.rect(id_x, top_y, id_w, id_h)
    if use_cjk:
        pdf.set_font("CJK", "", 6)
    else:
        pdf.set_font("Helvetica", "", 6)
    pdf.set_xy(id_x + 2, top_y + 1)
    pdf.cell(id_w - 4, 4, "考号填涂", align="C")

    cell_w = min(4, (id_w - 10) / id_digits)
    cell_h = 3.5
    for d in range(id_digits):
        cx = id_x + 4 + d * (cell_w + 0.8)
        pdf.set_xy(cx, top_y + 6)
        pdf.cell(cell_w, 3, str(d + 1), align="C")
        for n in range(10):
            cy = top_y + 9 + n * (cell_h + 0.5)
            pdf.rect(cx, cy, cell_w, cell_h)
            pdf.set_xy(cx, cy)
            pdf.cell(cell_w, cell_h, str(n), align="C")

    # ── 题目区 ──
    y = top_y + info_h + 5
    if use_cjk:
        pdf.set_font("CJK", "", 7)
    else:
        pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(8, y)
    pdf.cell(0, 5, "题目填涂区（请用2B铅笔涂满）", align="C")
    y += 7

    col_count = 2
    questions_per_col = math.ceil(question_count / col_count)
    opt_w = 4
    opt_h = 3.5

    for i in range(question_count):
        col = i // questions_per_col
        row = i % questions_per_col
        qx = 8 + col * (page_dim["width_num"] / 2)
        qy = y + row * 5.5

        if qy > 190 and page_size.upper() == "A5":
            break

        pdf.set_font("CJK", "", 6) if use_cjk else pdf.set_font("Helvetica", "", 6)
        pdf.set_xy(qx, qy)
        pdf.cell(6, opt_h, f"{i+1}.", align="R")

        for j, opt in enumerate(options):
            ox = qx + 8 + j * (opt_w + 4)
            pdf.rect(ox, qy, opt_w, opt_h)
            pdf.set_xy(ox, qy)
            pdf.cell(opt_w, opt_h, opt, align="C")

    # 生成 PDF 字节流
    buf = io.BytesIO()
    try:
        pdf.output(buf)
    except Exception as e:
        logger.error("fpdf2 静态答题卡 PDF 生成失败: %s", e)
        raise HTTPException(status_code=500, detail=f"PDF 生成失败: {str(e)}")

    buf.seek(0)
    pdf_bytes = buf.getvalue()

    if not pdf_bytes.startswith(b"%PDF"):
        logger.error("生成的 PDF 文件头异常，长度=%d", len(pdf_bytes))
        raise HTTPException(status_code=500, detail="PDF 生成异常")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="answer_sheet_q{question_count}_opt{option_count}.pdf"',
            "Content-Type": "application/pdf",
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@router.get("/{exam_id}/answer-sheet-html")
async def export_answer_sheet_html(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """生成可打印的答题卡 HTML 页面（基于试卷题目数据）"""
    from fastapi.responses import HTMLResponse

    exam = await ExamService.get_exam_detail(db, exam_id, teacher_id)
    if not exam:
        raise HTTPException(status_code=404, detail="试卷不存在")

    title = exam.get("title", "未命名试卷")
    questions = exam.get("questions", [])

    page_dim = _PAGE_DIMS.get("A4", {"width": "210mm", "height": "297mm"})
    html = generate_answer_sheet_from_exam(
        title=title,
        questions=questions,
        page_size="A4",
        page_width=page_dim["width"],
        page_height=page_dim["height"],
    )
    return HTMLResponse(content=html, status_code=200)


def _html_to_pdf_with_browser(html_content: str) -> Optional[bytes]:
    """使用系统浏览器（Edge/Chrome）headless 模式将 HTML 渲染为 PDF

    浏览器原生支持中文字体渲染，无需额外下载字体。
    """
    import subprocess
    import tempfile

    # 查找可用的浏览器（优先 Edge, 回退 Chrome）
    browser_candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    import shutil
    # 也尝试 PATH 中的 edge/chrome
    for name in ("msedge", "edge", "chrome", "google-chrome"):
        p = shutil.which(name)
        if p:
            browser_candidates.insert(0, p)

    browser_path = None
    for candidate in browser_candidates:
        if os.path.exists(candidate):
            browser_path = candidate
            break

    if not browser_path:
        logger.error("未找到 Edge 或 Chrome 浏览器，无法生成 PDF")
        return None

    # 将 HTML 写入临时文件
    fd, html_path = tempfile.mkstemp(suffix=".html")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html_content)

        pdf_path = html_path.replace(".html", ".pdf")

        # 调用浏览器 headless 打印为 PDF
        result = subprocess.run(
            [
                browser_path,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--no-margins",
                f"--print-to-pdf={pdf_path}",
                html_path,
            ],
            capture_output=True,
            timeout=60,
        )

        if result.returncode != 0 or not os.path.exists(pdf_path):
            stderr_text = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            logger.error("浏览器渲染 PDF 失败: returncode=%d, stderr=%s",
                         result.returncode, stderr_text[:500])
            return None

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        if not pdf_bytes.startswith(b"%PDF"):
            logger.error("生成的 PDF 文件头异常: %s", pdf_bytes[:20])
            return None

        return pdf_bytes

    except subprocess.TimeoutExpired:
        logger.error("浏览器渲染 PDF 超时（60秒）")
        return None
    except Exception as e:
        import traceback
        logger.error("浏览器渲染 PDF 异常: %s\n%s", e, traceback.format_exc())
        return None
    finally:
        try:
            if os.path.exists(html_path):
                os.unlink(html_path)
            pdf_p = html_path.replace(".html", ".pdf")
            if os.path.exists(pdf_p):
                os.unlink(pdf_p)
        except Exception:
            pass


@router.get("/{exam_id}/answer-sheet-pdf")
async def export_answer_sheet_pdf(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """生成可打印的答题卡 PDF（基于试卷题目数据）

    先生成答题卡 HTML，再使用系统浏览器（Edge/Chrome）headless 模式渲染为 PDF。
    彻底避免了字体下载和 fpdf2 手动绘制的问题。
    """
    import traceback
    try:
        exam = await ExamService.get_exam_detail(db, exam_id, teacher_id)
        if not exam:
            raise HTTPException(status_code=404, detail="试卷不存在")

        title = exam.get("title", "未命名试卷")
        questions = exam.get("questions", [])

        # 1. 先生成答题卡 HTML（与 HTML 预览端点使用相同逻辑）
        page_dim = _PAGE_DIMS.get("A4", {"width": "210mm", "height": "297mm"})
        html_content = generate_answer_sheet_from_exam(
            title=title,
            questions=questions,
            page_size="A4",
            page_width=page_dim["width"],
            page_height=page_dim["height"],
        )
        logger.info("答题卡 HTML 生成成功，长度=%d 字符", len(html_content))

        # 2. 使用系统浏览器 headless 模式转 PDF
        pdf_bytes = _html_to_pdf_with_browser(html_content)
        if pdf_bytes is None:
            raise HTTPException(status_code=500, detail="PDF 生成失败：无法通过浏览器渲染 PDF")

        logger.info("PDF 生成成功，大小=%d 字节", len(pdf_bytes))

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="answer_sheet_{exam_id}.pdf"',
                "Content-Type": "application/pdf",
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.error("export_answer_sheet_pdf ValueError: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"PDF 生成内部错误: {e}")
    except Exception as e:
        logger.error("export_answer_sheet_pdf 异常: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"PDF 生成异常: {e}")


@router.get("/{exam_id}/answer-sheet-png")
async def export_answer_sheet_png(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """生成答题卡 PNG 图片（可直接保存到手机相册）

    使用 Pillow 绘制答题卡，无需系统依赖。
    小程序端通过 wx.downloadFile 下载后可用 wx.saveImageToPhotosAlbum 保存。
    """
    import traceback
    try:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            logger.error("export_answer_sheet_png: Pillow 未安装")
            raise HTTPException(status_code=500, detail="PNG 导出功能不可用（Pillow 未安装）")

        # 教师端查看答题卡无需发布状态限制，直接按试卷ID查询
        exam_row = await db.get(TeacherExam, exam_id)
        if not exam_row:
            raise HTTPException(status_code=404, detail="试卷不存在")

        questions = exam_row.questions or []
        if not questions:
            raise HTTPException(status_code=400, detail="试卷无题目，无法生成答题卡")

        title = exam_row.title or "未命名试卷"
        total = len(questions)
        id_digits = max(2, min(10, len(str(max(total * 2, 99)))))

        # 选项列表
        if questions and questions[0].get("options"):
            option_labels = [_opt_label(opt) for opt in questions[0]["options"]]
            option_count = len(option_labels)
        else:
            option_labels = ["A", "B", "C", "D"]
            option_count = 4

        # ── 布局参数 ──
        dpi = 150
        mm_to_px = dpi / 25.4
        page_w = int(210 * mm_to_px)   # ~1240
        page_h = int(297 * mm_to_px)   # ~1754
        margin = int(8 * mm_to_px)     # ~47

        img = Image.new("RGB", (page_w, page_h), "white")
        draw = ImageDraw.Draw(img)

        # 字体
        font_path = _ensure_font()
        if font_path:
            try:
                font_title = ImageFont.truetype(font_path, 24)
                font_normal = ImageFont.truetype(font_path, 14)
                font_small = ImageFont.truetype(font_path, 11)
                font_tiny = ImageFont.truetype(font_path, 9)
            except Exception:
                font_title = ImageFont.load_default()
                font_normal = ImageFont.load_default()
                font_small = ImageFont.load_default()
                font_tiny = ImageFont.load_default()
        else:
            font_title = ImageFont.load_default()
            font_normal = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_tiny = ImageFont.load_default()

        # ── 标题 ──
        y = margin
        draw.text((margin, y), title, fill="black", font=font_title)
        y += 40

        # ── 上区：学生信息 + 考号填涂（左右并排） ──
        info_w = int(62 * mm_to_px)
        info_h = int(42 * mm_to_px)
        id_w = page_w - margin * 2 - info_w - 15
        id_h = info_h

        # 学生信息框
        draw.rectangle([margin, y, margin + info_w, y + info_h], outline="black", width=1)
        draw.text((margin + 10, y + 5), "▼ 请用黑色签字笔填写", fill="gray", font=font_tiny)
        draw.text((margin + 10, y + 22), "姓名：_______________", fill="black", font=font_small)
        draw.text((margin + 10, y + 45), "班级：_______________", fill="black", font=font_small)
        draw.text((margin + 10, y + 68), "考号：_______________", fill="black", font=font_small)
        draw.text((margin + 10, y + 90), "缺考标记：□", fill="black", font=font_small)

        # 考号填涂区
        id_x = margin + info_w + 15
        draw.rectangle([id_x, y, id_x + id_w, y + id_h], outline="black", width=1)
        draw.text((id_x + 5, y + 3), "考号填涂（黑色涂满）", fill="black", font=font_small)

        id_grid_x = id_x + 8
        id_grid_y = y + 22
        cell_s = int(3.2 * mm_to_px)  # 格子大小
        cell_gap = 2
        for d in range(id_digits):
            cx = id_grid_x + d * (cell_s + cell_gap + 12)
            draw.text((cx + 2, id_grid_y - 15), str(d + 1), fill="black", font=font_tiny)
            for n in range(10):
                ry = id_grid_y + n * (cell_s + cell_gap)
                draw.rectangle([cx, ry, cx + cell_s, ry + cell_s], outline="black", width=1)
                draw.text((cx + 2, ry), str(n), fill="gray", font=font_tiny)

        y += info_h + 20

        # ── 分隔线 ──
        draw.line([(margin, y), (page_w - margin, y)], fill="black", width=1)
        y += 10

        # ── 题目填涂区（双列布局） ──
        draw.text((margin, y), "题目填涂区（请用2B铅笔涂满）", fill="black", font=font_small)
        y += 22

        col_count = 2
        questions_per_col = math.ceil(total / col_count)
        opt_w = int(3.5 * mm_to_px)
        opt_h = int(3.5 * mm_to_px)
        col_w = (page_w - margin * 2 - 30) // col_count

        for i in range(total):
            col = i // questions_per_col
            row = i % questions_per_col
            col_x = margin + col * col_w
            row_y = y + row * 20

            # 题号
            draw.text((col_x, row_y + 2), f"{i+1}.", fill="black", font=font_small)
            # 选项
            for j, opt in enumerate(option_labels):
                ox = col_x + 26 + j * 24
                oy = row_y
                draw.rectangle([ox, oy, ox + opt_w, oy + opt_h], outline="black", width=1)
                draw.text((ox + 1, oy - 1), opt, fill="gray", font=font_tiny)

        # ── 底部提示 ──
        footer_y = page_h - margin - 20
        draw.line([(margin, footer_y - 10), (page_w - margin, footer_y - 10)], fill="black", width=1)
        draw.text((margin, footer_y), "请保持答题卡整洁，不要折叠。", fill="gray", font=font_small)

        # 输出 PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        png_bytes = buf.getvalue()

        logger.info("export_answer_sheet_png 成功: exam_id=%d, 大小=%d 字节", exam_id, len(png_bytes))

        safe_filename = title.replace(" ", "_").replace("/", "_")
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": f'attachment; filename="answer_sheet_{exam_id}_{safe_filename}.png"',
                "Content-Type": "image/png",
                "Content-Length": str(len(png_bytes)),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("export_answer_sheet_png 异常: exam_id=%d, %s\n%s", exam_id, e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"生成答题卡图片失败: {e}")


# ========== GraderFlow 答题卡（4列矩形填涂框，B模式扫描） ==========

@router.get("/{exam_id}/graderflow-sheet-template", response_model=ResponseData)
async def get_graderflow_sheet_template(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取 GraderFlow 答题卡模板配置（含坐标配置 + 可下载URL）

    和标准答题卡的区别：使用矩形填涂框（5mm×4.2mm）、4列B模式排列，
    适合 YOLOv5 检测 + OMR 识别的扫描流程。
    """
    exam = await ExamService.get_exam_detail(db, exam_id, teacher_id)
    if not exam:
        raise HTTPException(status_code=404, detail="试卷不存在")

    questions = exam.get("questions", [])
    grade_val = exam.get("grade", "") or ""
    is_senior = bool(grade_val and (
        grade_val.startswith("高") or "高中" in grade_val or "高三" in grade_val
        or "senior" in grade_val.lower() or "高考" in grade_val
    ))
    start_num = 21 if is_senior else 1
    choice_questions = ExamService._extract_choice_questions(questions, exam.get("title", ""), start_number=start_num)

    if choice_questions:
        config = ExamService._build_graderflow_sheet_config_from_json(
            exam_id, choice_questions, exam.get("title", "答题卡"), id_digits=7
        )
    else:
        config = ExamService._build_graderflow_sheet_config(
            exam_id, questions, exam.get("title", "答题卡"), id_digits=7
        )

    return ResponseData(data=config)


@router.get("/{exam_id}/graderflow-sheet-html")
async def export_graderflow_sheet_html(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """生成可打印的 GraderFlow 答题卡 HTML 页面（4列矩形填涂框格式）"""
    from fastapi.responses import HTMLResponse

    exam = await ExamService.get_exam_detail(db, exam_id, teacher_id)
    if not exam:
        raise HTTPException(status_code=404, detail="试卷不存在")

    title = exam.get("title", "未命名试卷")
    questions = exam.get("questions", [])

    html = generate_graderflow_sheet_from_exam(
        title=title,
        questions=questions,
        id_digits=7,
    )
    return HTMLResponse(content=html, status_code=200)


@router.get("/{exam_id}/graderflow-sheet-pdf")
async def export_graderflow_sheet_pdf(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """生成可打印的 GraderFlow 答题卡 PDF（使用浏览器 headless 渲染）"""
    import traceback

    try:
        exam = await ExamService.get_exam_detail(db, exam_id, teacher_id)
        if not exam:
            raise HTTPException(status_code=404, detail="试卷不存在")

        title = exam.get("title", "未命名试卷")
        questions = exam.get("questions", [])

        html_content = generate_graderflow_sheet_from_exam(
            title=title,
            questions=questions,
            id_digits=7,
        )
        logger.info("GraderFlow 答题卡 HTML 生成成功，长度=%d 字符", len(html_content))

        pdf_bytes = _html_to_pdf_with_browser(html_content)
        if pdf_bytes is None:
            raise HTTPException(status_code=500, detail="PDF 生成失败：无法通过浏览器渲染 PDF")

        logger.info("GraderFlow PDF 生成成功，大小=%d 字节", len(pdf_bytes))

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="graderflow_answer_sheet_{exam_id}.pdf"',
                "Content-Type": "application/pdf",
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("export_graderflow_sheet_pdf 异常: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"PDF 生成异常: {e}")


# 临时调试端点 — 用于验证 GET 路由是否工作
@router.get("/debug-test")
async def debug_test():
    print("[DEBUG debug_test] 端点被命中!", flush=True)
    return {"code": 0, "message": "success", "data": []}


# ========== 答题卡模板管理（CRUD） ==========

@router.post("/answer-sheet-template", response_model=ResponseData)
async def create_or_update_template(
    body: AnswerSheetTemplateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """创建或更新答题卡模板（同名模板存在则更新）

    返回: 创建或更新后的模板数据，包含 id / name / choice_questions 等字段。
    """
    name = body.name.strip()
    if not name or len(name) > 128:
        raise HTTPException(status_code=422, detail="模板名称应为 1 至 128 字")
    try:
        result = await ExamService.create_answer_sheet_template(
            db, teacher_id=teacher_id, name=name, choice_questions=body.choice_questions,
            grade=body.grade, description=body.description, is_default=body.is_default, create_only=body.create_only,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ResponseData(data=result)


@router.get("/templates/list", response_model=ResponseData)
async def list_templates(
    grade: Optional[str] = Query(None, description="按年级过滤（可选）"),
    paper_only: bool = False,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取当前教师的答题卡模板列表

    支持按年级过滤，默认模板排在前面。
    """
    templates = await ExamService.list_answer_sheet_templates(
        db, teacher_id=teacher_id, grade=grade or ""
    )
    if paper_only:
        templates = [item for item in templates if supports_paper_template(item["choice_questions"])]
    return ResponseData(data=templates)


@router.get("/answer-sheet-templates/{template_id}", response_model=ResponseData)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取单个答题卡模板详情"""
    template = await ExamService.get_answer_sheet_template(
        db, template_id=template_id, teacher_id=teacher_id
    )
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在或无权访问")
    template["paper_compatible"] = supports_paper_template(template["choice_questions"])
    return ResponseData(data=template)


@router.delete("/answer-sheet-templates/{template_id}", response_model=ResponseData)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """停用答题卡模板，保留历史试卷引用。"""
    success = await ExamService.archive_answer_sheet_template(
        db, template_id=template_id, teacher_id=teacher_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="模板不存在或无权删除")
    return ResponseData(data={"deleted": True, "archived": True}, message="模板已停用")


@router.put("/answer-sheet-templates/{template_id}", response_model=ResponseData)
async def update_template(
    template_id: int,
    body: AnswerSheetTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """按模板 ID 和版本保存修改。"""
    name = body.name.strip()
    if not name or len(name) > 128:
        raise HTTPException(status_code=422, detail="模板名称应为 1 至 128 字")
    try:
        result = await ExamService.create_answer_sheet_template(
            db, teacher_id=teacher_id, name=name, choice_questions=body.choice_questions,
            grade=body.grade, description=body.description, is_default=body.is_default,
            template_id=template_id, expected_revision=body.revision,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ResponseData(data=result)


@router.get("/answer-sheet-templates/{template_id}/pdf")
async def get_template_pdf(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取答题卡模板的 PDF 文件（基于已保存的模板选择题JSON即时生成）

    小程序端可直接通过该接口下载模板 PDF 并打开预览。
    """
    import traceback
    template = await ExamService.get_answer_sheet_template(
        db, template_id=template_id, teacher_id=teacher_id
    )
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在或无权访问")

    choice_questions = template.get("choice_questions", [])
    if not choice_questions:
        raise HTTPException(status_code=400, detail="模板中无选择题配置")

    try:
        page_dim = _PAGE_DIMS.get("A4", _PAGE_DIMS["A4"])
        html_content = generate_answer_sheet_from_json(
            title=template.get("name", "答题卡模板"),
            choice_questions=choice_questions,
            page_size="A4",
            page_width=page_dim["width"],
            page_height=page_dim["height"],
            id_digits=6,
            id_options=_make_digit_labels(9),
            show_student_id=True,
        )
        logger.info("答题卡模板 HTML 生成成功，长度=%d 字符", len(html_content))

        pdf_bytes = _html_to_pdf_with_browser(html_content)
        if pdf_bytes is None:
            raise HTTPException(status_code=500, detail="PDF 生成失败：无法通过浏览器渲染 PDF")

        logger.info("答题卡模板 PDF 生成成功，大小=%d 字节", len(pdf_bytes))

        safe_name = template.get("name", "答题卡模板").replace("/", "_").replace("\\", "_").replace(" ", "_")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="answer_sheet_template_{safe_name}.pdf"',
                "Content-Type": "application/pdf",
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_template_pdf 异常: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"PDF 生成异常: {e}")


# ========== 学生端（接收教师发布的试卷） ==========

student_router = APIRouter(prefix="/exam", tags=["学生端-试卷"])


@student_router.get("/list", response_model=ResponseData)
async def student_list_exams(
    status: Optional[str] = Query(None, description="筛选: pending(未提交)/submitted(已提交)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    student_id: int = Depends(get_current_user_id),
):
    """学生端：获取已发布到所属班级的试卷列表"""
    result = await ExamService.student_list_exams(db, student_id, status, page, page_size)
    return ResponseData(data=result)


@student_router.get("/{exam_id}/result", response_model=ResponseData)
async def student_get_exam_result(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    student_id: int = Depends(get_current_user_id),
):
    """学生端：获取已提交试卷的批改结果（含逐题评分详情、参考答案）"""
    result = await ExamService.student_get_exam_result(db, exam_id, student_id)
    if not result:
        raise HTTPException(status_code=404, detail="未找到提交记录")
    return ResponseData(data=result)


@student_router.get("/{exam_id:int}", response_model=ResponseData)
async def student_get_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    student_id: int = Depends(get_current_user_id),
):
    """学生端：获取已发布试卷的完整详情（含题目）"""
    result = await ExamService.student_get_exam_detail(db, exam_id, student_id)
    if not result:
        raise HTTPException(status_code=404, detail="试卷不存在或无权访问")
    return ResponseData(data=result)


class StudentSubmitRequest(BaseModel):
    """学生提交答案请求"""
    exam_id: int
    answers: list


@student_router.post("/submit", response_model=ResponseData)
async def student_submit_exam(
    body: StudentSubmitRequest,
    db: AsyncSession = Depends(get_db),
    student_id: int = Depends(get_current_user_id),
):
    """学生端：提交试卷答案"""
    result = await ExamService.auto_grade_submission(
        db, body.exam_id, student_id, body.answers, student_id
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return ResponseData(data=result)


@router.post("/{exam_id}/regenerate-answer-sheet", response_model=ResponseData)
async def regenerate_answer_sheet(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """重新生成答题卡HTML和坐标配置，保存到数据库并返回最新配置"""
    from sqlalchemy.orm.attributes import flag_modified

    exam = await db.get(TeacherExam, exam_id, with_for_update=True)
    if not exam or exam.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="试卷不存在")
    _require_legacy_exam(exam, teacher_id)

    questions = exam.questions or []
    if not questions:
        raise HTTPException(status_code=400, detail="试卷没有题目，无法生成答题卡")

    # 同 publish_exam 的生成逻辑
    is_senior = bool(exam.grade and (
        exam.grade.startswith("高") or "高中" in exam.grade or "高三" in exam.grade
        or "senior" in exam.grade.lower() or "高考" in exam.grade
    ))
    start_num = 21 if is_senior else 1
    choice_questions = ExamService._extract_choice_questions(questions, exam.title, start_number=start_num)
    if choice_questions:
        answer_sheet_config = ExamService._build_answer_sheet_config_from_json(exam_id, choice_questions, exam.title)
    else:
        answer_sheet_config = ExamService._build_answer_sheet_config(exam_id, questions, exam.title)

    exam.answer_sheet_config = answer_sheet_config
    flag_modified(exam, "answer_sheet_config")
    await db.flush()
    await db.commit()
    await db.refresh(exam)

    return ResponseData(data=answer_sheet_config)


@router.post("/{exam_id}/regenerate-graderflow-sheet", response_model=ResponseData)
async def regenerate_graderflow_sheet(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """重新生成 GraderFlow 答题卡（4列矩形填涂框）并保存到数据库"""
    from sqlalchemy.orm.attributes import flag_modified

    exam = await db.get(TeacherExam, exam_id, with_for_update=True)
    if not exam or exam.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="试卷不存在")
    _require_legacy_exam(exam, teacher_id)

    questions = exam.questions or []
    if not questions:
        raise HTTPException(status_code=400, detail="试卷没有题目，无法生成答题卡")

    is_senior = bool(exam.grade and (
        exam.grade.startswith("高") or "高中" in exam.grade or "高三" in exam.grade
        or "senior" in exam.grade.lower() or "高考" in exam.grade
    ))
    start_num = 21 if is_senior else 1
    choice_questions = ExamService._extract_choice_questions(questions, exam.title, start_number=start_num)
    if choice_questions:
        answer_sheet_config = ExamService._build_graderflow_sheet_config_from_json(
            exam_id, choice_questions, exam.title, id_digits=7
        )
    else:
        answer_sheet_config = ExamService._build_graderflow_sheet_config(
            exam_id, questions, exam.title, id_digits=7
        )

    exam.answer_sheet_config = answer_sheet_config
    flag_modified(exam, "answer_sheet_config")
    await db.flush()
    await db.commit()
    await db.refresh(exam)

    return ResponseData(data=answer_sheet_config)


# ========== 可打印答题卡生成（Pillow PNG） ==========

@router.post("/{exam_id}/generate-printable-sheet", response_model=ResponseData)
async def generate_printable_sheet(
    exam_id: int,
    page_size: str = Query("A4", description="纸张大小: A4/A5"),
    dpi: int = Query(200, description="分辨率"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """生成可打印的答题卡PNG图片（Pillow绘制，带定位块和考号区）"""
    from app.services.printable_sheet_generator import generate_printable_sheet as _gen_sheet

    exam = await db.get(TeacherExam, exam_id, with_for_update=True)
    if not exam or exam.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="试卷不存在")
    _require_legacy_exam(exam, teacher_id)

    # 提取选择题
    questions = exam.questions or []
    if not questions:
        raise HTTPException(status_code=400, detail="试卷无题目")

    # 同发布试卷的逻辑提取选择题
    is_senior = bool(exam.grade and (
        exam.grade.startswith("高") or "高中" in exam.grade or "高三" in exam.grade
        or "senior" in exam.grade.lower() or "高考" in exam.grade
    ))
    start_num = 21 if is_senior else 1
    choice_questions = ExamService._extract_choice_questions(questions, exam.title, start_number=start_num)

    if not choice_questions:
        raise HTTPException(status_code=400, detail="该试卷没有选择题，无法生成答题卡")

    # 计算最大选项数
    max_oc = max(
        (q.get("options", 4) if isinstance(q.get("options"), int)
         else len(q.get("options", [4])) if isinstance(q.get("options"), list)
         else 4)
        for q in choice_questions
    )

    # 获取班级名称
    class_name = ""
    if exam.class_id:
        from app.models.class_models import Class
        cls = await db.get(Class, exam.class_id)
        if cls:
            class_name = cls.name

    # 生成答题卡
    sheet_data = _gen_sheet(
        exam_id=exam_id,
        choice_questions=choice_questions,
        option_count=max_oc,
        page_size=page_size,
        dpi=dpi,
        title=exam.title,
        class_name=class_name,
    )

    # 持久化坐标配置到 DB
    stored_config = exam.answer_sheet_config or {}
    stored_config["printable_sheet"] = {
        "image_url": sheet_data["image_url"],
        "coordinate_config": sheet_data["coordinate_config"],
        "total_questions": sheet_data["total_questions"],
        "option_count": sheet_data["option_count"],
        "page_size": page_size,
        "dpi": dpi,
        "generated_at": datetime.utcnow().isoformat(),
    }
    # 同时也存一份到顶层，方便读取
    stored_config["coordinate_config"] = sheet_data["coordinate_config"]
    stored_config["image_url"] = sheet_data["image_url"]

    exam.answer_sheet_config = stored_config
    flag_modified(exam, "answer_sheet_config")
    await db.flush()
    await db.commit()

    return ResponseData(data=sheet_data)


# ========== 扫描批卷（拍照上传 + AI多模态识别 + 自动批改 + 错题入库） ==========

class ScanGradeResponse(BaseModel):
    """扫描批改响应"""
    submission_id: int
    student_name: str = ""
    exam_number: str = ""
    total_score: int = 0
    max_score: int = 100
    wrong_count: int = 0
    wrong_saved_count: int = 0
    scan_duration_ms: int = 0
    answers: list = []
    scan_image_url: str = ""


class MobileGradeSessionRequest(BaseModel):
    class_id: int = 0


@router.post("/{exam_id}/mobile-grade-session", response_model=ResponseData)
async def create_mobile_grade_session(
    exam_id: int,
    body: MobileGradeSessionRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """Create a short-lived, exam-scoped QR session for mobile answer-sheet scanning."""
    exam = await db.get(TeacherExam, exam_id)
    if not exam or exam.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="试卷不存在")
    _require_legacy_exam(exam, teacher_id)
    if body.class_id:
        selected_class = await db.get(Class, body.class_id)
        if not selected_class or selected_class.created_by != teacher_id:
            raise HTTPException(status_code=403, detail="所选班级不存在或无权访问")

    settings = get_settings()
    session_minutes = max(1, min(int(settings.SCAN_SESSION_EXPIRE_MINUTES), 60))
    expires_delta = timedelta(minutes=session_minutes)
    expires_at = datetime.now(timezone.utc) + expires_delta
    scan_token = create_exam_scan_token(teacher_id, exam_id, expires_delta)
    query = f"token={quote(scan_token)}&mode=omr"
    if body.class_id:
        query += f"&class_id={body.class_id}"

    return ResponseData(data={
        "path": f"/teacher/exam/{exam_id}/mobile-grade?{query}",
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "expires_in_seconds": session_minutes * 60,
    })


@router.post("/{exam_id}/scan-grade", response_model=ResponseData)
async def scan_and_grade(
    exam_id: int,
    background_tasks: BackgroundTasks,
    image: UploadFile = File(..., description="答题卡照片"),
    class_id: int = Form(0, description="批卷班级ID（0则使用试卷绑定班级）"),
    db: AsyncSession = Depends(get_db),
    principal: ExamScanPrincipal = Depends(get_exam_scan_principal),
):
    """拍照上传答题卡 → OMR识别 → 自动批改 → 错题入库

    完整流程：
    1. 保存上传图片到服务器
    2. OMR扫描识别答题卡（自动适配系统生成/外部答题卡格式）
    3. 匹配学生身份（通过考号查 class_student_info）
    4. 与标准答案对比批改
    5. 保存提交记录到 exam_submission
    6. 错题写入 wrong_question_book
    7. 后台异步触发RAG向量索引
    8. 记录扫描日志
    """
    import time
    teacher_id = principal.teacher_id
    if principal.exam_id is not None and principal.exam_id != exam_id:
        raise HTTPException(status_code=403, detail="扫描会话与当前试卷不匹配")
    start_time = time.time()

    exam = await db.get(TeacherExam, exam_id)
    if not exam or exam.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="试卷不存在")
    _require_legacy_exam(exam, teacher_id)

    roster_class_id = class_id if class_id else exam.class_id
    if roster_class_id:
        roster_class = await db.get(Class, roster_class_id)
        if not roster_class or roster_class.created_by != teacher_id:
            raise HTTPException(status_code=403, detail="所选班级不存在或无权访问")

    # 1. 校验并保存上传图片。二维码会暴露给手机浏览器，不能信任文件名或 MIME。
    allowed_image_types = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    content_type = (image.content_type or "").lower()
    if content_type not in allowed_image_types:
        raise HTTPException(status_code=415, detail="仅支持 JPEG、PNG 或 WebP 答题卡图片")

    max_upload_bytes = 12 * 1024 * 1024
    image_bytes = await image.read(max_upload_bytes + 1)
    await image.close()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="上传图片为空")
    if len(image_bytes) > max_upload_bytes:
        raise HTTPException(status_code=413, detail="答题卡图片不能超过 12MB")

    from PIL import Image, UnidentifiedImageError
    detected_formats = {
        "JPEG": ("image/jpeg", ".jpg"),
        "PNG": ("image/png", ".png"),
        "WEBP": ("image/webp", ".webp"),
    }
    try:
        with Image.open(io.BytesIO(image_bytes)) as uploaded_image:
            detected = detected_formats.get(uploaded_image.format or "")
            if not detected or detected[0] != content_type:
                raise HTTPException(status_code=415, detail="图片内容与文件类型不匹配")
            if uploaded_image.width * uploaded_image.height > 40_000_000:
                raise HTTPException(status_code=413, detail="答题卡图片像素尺寸过大")
            uploaded_image.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=415, detail="无法解析答题卡图片")

    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                              "uploads", "scans", str(exam_id))
    os.makedirs(upload_dir, exist_ok=True)

    file_ext = detected[1]
    safe_filename = f"{int(time.time() * 1000)}_{teacher_id}{file_ext}"
    save_path = os.path.join(upload_dir, safe_filename)

    try:
        with open(save_path, "wb") as f:
            f.write(image_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图片保存失败: {e}")

    scan_image_url = f"/static/scans/{exam_id}/{safe_filename}"

    # 2. OMR 扫描识别（根据答题卡配置自动适配格式）
    from app.services.omr_scanner import (
        scan_answer_sheet,
        REAL_SHEET_COORDINATES,
        EXTERNAL_SHEET_4OPTIONS,
        _is_external_sheet,
    )

    # 将 grading_mode 映射为短的 grading_status 值（≤16字符适配DB）
    def _shorten_grading_status(grading_mode: str) -> str:
        mapping = {
            "omr": "omr_done",
            "omr_external": "omr_ext",
            "omr_external_4options": "omr_ext4",
            "omr_real_sheet": "omr_real",
        }
        return mapping.get(grading_mode, "omr_done")

    questions = exam.questions or []

    # 读取答题卡坐标配置
    coordinate_config = None
    option_count = 4
    if exam.answer_sheet_config:
        coordinate_config = exam.answer_sheet_config.get("coordinate_config")
        option_count = exam.answer_sheet_config.get("option_count", 4) or 4

    # 如果没有坐标配置，或坐标配置缺少 reference 维度（不完整），使用默认答题卡
    if not coordinate_config or not coordinate_config.get("question_regions"):
        logger.info("无系统生成答题卡坐标配置，使用真实答题卡OMR扫描")
        total_q = len(questions)
        if total_q <= 10:
            coordinate_config = EXTERNAL_SHEET_4OPTIONS
            option_count = 4
            grading_mode = "omr_external_4options"
        else:
            coordinate_config = REAL_SHEET_COORDINATES
            option_count = 7
            grading_mode = "omr_real_sheet"
    elif not coordinate_config.get("reference_width"):
        # 有坐标配置但缺少参考维度 → 不完整，替换为外部答题卡配置
        logger.info("坐标配置缺少 reference_width，替换为外部答题卡配置")
        coordinate_config = EXTERNAL_SHEET_4OPTIONS
        option_count = 4
        grading_mode = "omr_external_4options"
    else:
        # 完整坐标配置
        if _is_external_sheet(coordinate_config):
            grading_mode = "omr_external"
        else:
            grading_mode = "omr"

    logger.info("OMR批卷开始 | exam_id=%d 题目数=%d 图片=%s mode=%s",
                exam_id, len(questions), safe_filename, grading_mode)

    scan_result = scan_answer_sheet(
        image_path=save_path,
        coordinate_config=coordinate_config,
        option_count=option_count,
    )

    if not scan_result.get("success"):
        # 记录扫描失败日志
        error_msg = scan_result.get("error", f"{grading_mode}识别失败")
        logger.warning("批卷识别失败 | exam_id=%d mode=%s detail=%s duration=%dms",
                       exam_id, grading_mode, error_msg,
                       scan_result.get("duration_ms", 0))
        scan_record = ExamScanRecord(
            exam_id=exam_id,
            teacher_id=teacher_id,
            scan_image_url=scan_image_url,
            error_message=error_msg,
            scan_duration_ms=scan_result.get("duration_ms", 0),
        )
        db.add(scan_record)
        await db.flush()
        await db.commit()

        # 对不同类型的错误使用不同的 HTTP 状态码
        if "API Key" in error_msg or "认证" in error_msg:
            status_code = 502  # 配置错误
        elif "超时" in error_msg or "timeout" in error_msg.lower():
            status_code = 504  # 上游超时
        elif "服务器错误" in error_msg or "server error" in error_msg.lower():
            status_code = 502  # 上游故障
        else:
            status_code = 400  # 通用识别失败

        raise HTTPException(status_code=status_code, detail=error_msg)

    # 4. 匹配学生身份（通过考号）
    # 优先使用传入的 class_id，否则回退到试卷绑定的班级
    # roster_class_id 已在保存和识别前完成所有权校验。
    exam_number = scan_result.get("exam_number", "")
    # 清理OCR结果：去除?等未识别字符，只保留数字
    exam_number_clean = re.sub(r'[^0-9]', '', exam_number) if exam_number else ""
    student_info = None
    student_id = None
    student_name = ""

    # 诊断日志：显示匹配所用的班级和花名册情况
    roster_count_stmt = select(func.count()).select_from(ClassStudentInfo).where(
        ClassStudentInfo.class_id == roster_class_id
    )
    roster_count = (await db.execute(roster_count_stmt)).scalar() or 0
    logger.info("考号匹配: exam_id=%s, roster_class_id=%s(exam.class_id=%s), 班级花名册人数=%s, OCR考号='%s'",
                exam_id, roster_class_id, exam.class_id, roster_count, exam_number)

    # 先用清理后的考号匹配，失败则用原始考号
    # 构建尝试列表：清理考号 -> 原始考号
    try_numbers = ([exam_number_clean] if exam_number_clean else []) + ([exam_number] if exam_number else [])
    # 如果清理后的考号有前导0，追加去前导0版本
    if exam_number_clean and len(exam_number_clean) > 1 and exam_number_clean.lstrip('0'):
        stripped = exam_number_clean.lstrip('0')
        if stripped not in try_numbers:
            try_numbers.append(stripped)
    # 如果考号较短（4位以内），尝试补前导0到常见长度
    if exam_number_clean and len(exam_number_clean) <= 4 and exam_number_clean.isdigit():
        for pad_len in (5, 6, 7):
            padded = exam_number_clean.zfill(pad_len)
            if padded not in try_numbers:
                try_numbers.append(padded)

    for try_number in try_numbers:
        if not try_number:
            continue
        info_stmt = select(ClassStudentInfo).where(
            ClassStudentInfo.class_id == roster_class_id,
            ClassStudentInfo.exam_number == try_number,
        )
        info_result = await db.execute(info_stmt)
        student_info = info_result.scalar_one_or_none()

        if student_info:
            student_name = student_info.student_name
            student_id = student_info.id
            exam_number = try_number  # 用匹配成功的考号
            logger.info("考号匹配成功: OCR=%s → 匹配=%s, 学生=%s", 
                         scan_result.get("exam_number", ""), try_number, student_name)
            break

    # 末四位匹配兜底：完整考号匹配失败后，用考号末4位匹配
    if not student_info and exam_number_clean and len(exam_number_clean) >= 4:
        last4 = exam_number_clean[-4:]
        logger.info("完整考号匹配失败，尝试末四位匹配: last4=%s", last4)
        # 查询班级所有学生的考号
        all_stmt = select(ClassStudentInfo).where(
            ClassStudentInfo.class_id == roster_class_id,
        )
        all_result = await db.execute(all_stmt)
        all_students = all_result.scalars().all()
        # 筛选考号末四位匹配的学生
        matched_students = [
            s for s in all_students
            if s.exam_number and s.exam_number[-4:] == last4
        ]
        if len(matched_students) == 1:
            student_info = matched_students[0]
            student_name = student_info.student_name
            student_id = student_info.id
            exam_number = student_info.exam_number  # 使用花名册中的完整考号
            logger.info("末四位匹配成功: OCR末四位=%s → 匹配=%s, 学生=%s",
                         last4, exam_number, student_name)
        elif len(matched_students) > 1:
            logger.warning("末四位匹配冲突: last4=%s 匹配到%s名学生, 姓名=%s",
                           last4, len(matched_students),
                           [s.student_name for s in matched_students])
        else:
            logger.warning("末四位匹配失败: last4=%s 无匹配学生", last4)

    # 通过 ClassStudent 查找真正的 User.id（ClassStudentInfo.id 是花名册行ID，不是用户ID）
    if student_id is not None and student_info is not None:
        cs_stmt = select(ClassStudent.student_id).join(
            User, User.id == ClassStudent.student_id
        ).where(
            ClassStudent.class_id == roster_class_id,
            User.nickname == student_info.student_name,
        )
        cs_result = await db.execute(cs_stmt)
        real_user_id = cs_result.scalar_one_or_none()
        if real_user_id:
            logger.info("通过 ClassStudent 找到真实 User.id: student_info.id=%s → user.id=%s",
                        student_id, real_user_id)
            student_id = real_user_id
        else:
            logger.warning("ClassStudentInfo 已匹配但无 ClassStudent 记录: class_id=%s, name=%s",
                           roster_class_id, student_info.student_name)
            # 未加入班级的学生，保留 student_id=None，后续可通过手动修正考号关联
            student_id = None
            student_name = ""

    if not student_info:
        logger.warning("考号未匹配: OCR原始=%s, 清理后=%s, 尝试列表=%s, roster_class_id=%s, 班级花名册人数=%s",
                       scan_result.get("exam_number", ""), exam_number_clean, try_numbers,
                       roster_class_id, roster_count)
        if roster_count == 0:
            logger.warning("班级(class_id=%s)花名册为空！请检查：1)是否已导入学生Excel 2)选择的班级是否正确", roster_class_id)

    # 5. 构建批改数据
    questions = exam.questions or []
    max_score = exam.total_score or 100
    start_number = 21 if any(k in str(exam.grade or "") for k in ["高中", "高三", "senior", "高考"]) else 1
    try:
        answers_data, ai_grade_detail, total_score = grade_choice_answers(
            questions,
            {str(a.get("question_number")): a for a in scan_result.get("answers", [])},
            start_number,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    wrong_count = sum(1 for a in answers_data if not a["is_correct"])
    correct_count = len(answers_data) - wrong_count

    # 6. 保存提交记录（如已存在同一考生提交则覆盖）
    existing_sub = None
    if student_id is not None:
        existing_stmt = select(ExamSubmission).where(
            ExamSubmission.exam_id == exam_id,
            ExamSubmission.student_id == student_id,
        )
        existing_result = await db.execute(existing_stmt)
        existing_sub = existing_result.scalar_one_or_none()

    grading_status_val = _shorten_grading_status(grading_mode)
    if existing_sub is not None:
        # 覆盖旧的提交记录
        existing_sub.answers = answers_data
        existing_sub.score = total_score
        existing_sub.max_score = max_score
        existing_sub.ai_grade_detail = ai_grade_detail
        existing_sub.exam_number = exam_number
        existing_sub.grading_status = grading_status_val
        existing_sub.scan_image_url = scan_image_url
        existing_sub.wrong_count = wrong_count
        existing_sub.submitted_at = datetime.utcnow()
        submission = existing_sub
        await db.flush()
        logger.info("覆盖旧的提交记录: submission_id=%s, exam_number=%s", existing_sub.id, exam_number)
    else:
        submission = ExamSubmission(
            exam_id=exam_id,
            student_id=student_id,
            answers=answers_data,
            score=total_score,
            max_score=max_score,
            ai_grade_detail=ai_grade_detail,
            exam_number=exam_number,
            grading_status=grading_status_val,
            scan_image_url=scan_image_url,
            wrong_count=wrong_count,
            submitted_at=datetime.utcnow(),
        )
        db.add(submission)
        await db.flush()

    # 7. 错题入库（只有匹配到学生时才入库，避免 student_id 为 null 导致 IntegrityError）
    wrong_saved = 0
    if student_id is not None:
        try:
            wrong_saved = await WrongBookService.save_from_submission(db, submission)
        except Exception as e:
            logger.error(f"错题入库失败: submission_id={submission.id}, error={e}")
            # 回滚事务，防止 PendingRollbackError 影响后续操作
            await db.rollback()
            # 回滚后重新添加 submission（被 rollback 移除的 pending 对象）
            db.add(submission)
    else:
        logger.warning(f"未匹配到学生 (exam_number={exam_number})，跳过错题入库")

    # 8. 后台异步索引RAG
    if wrong_saved > 0:
        sub_id = submission.id
        background_tasks.add_task(
            _index_wrong_questions, db_session=db, submission_id=sub_id
        )

    # 9. 记录扫描日志
    # OMR 用 valid_answers/total_questions，AI 用 recognized_count
    recognized_count = scan_result.get("recognized_count",
                      scan_result.get("valid_answers", 0))
    scan_record = ExamScanRecord(
        exam_id=exam_id,
        teacher_id=teacher_id,
        scan_image_url=scan_image_url,
        recognized_count=recognized_count,
        matched_student_id=student_id,
        exam_number=exam_number,
        raw_answers=scan_result.get("answers"),
        grading_result={"score": total_score, "wrong_count": wrong_count, "mode": grading_mode},
        scan_duration_ms=scan_result.get("duration_ms", 0),
    )
    db.add(scan_record)

    # 10. 更新试卷统计
    count_stmt = select(func.count()).where(ExamSubmission.exam_id == exam_id)
    total_sub = (await db.execute(count_stmt)).scalar() or 0
    avg_stmt = select(func.avg(ExamSubmission.score)).where(
        ExamSubmission.exam_id == exam_id,
        ExamSubmission.score.isnot(None),
    )
    avg_result = (await db.execute(avg_stmt)).scalar()
    exam.submission_count = total_sub
    exam.avg_score = round(avg_result, 1) if avg_result else None

    await db.flush()
    await db.commit()

    elapsed = int((time.time() - start_time) * 1000)

    return ResponseData(data={
        "submission_id": submission.id,
        "student_name": student_name,
        "student_id": student_id,
        "exam_number": exam_number,
        "total_score": total_score,
        "max_score": max_score,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "wrong_saved_count": wrong_saved,
        "scan_duration_ms": elapsed,
        "answers": answers_data,
        "scan_image_url": scan_image_url,
        "detail_summary": scan_result.get("detail_summary", ""),
        "grading_mode": grading_mode,
        "scan_method": scan_result.get("method", grading_mode),
        "recognized_count": recognized_count,
        "ai_raw_answers": [
            {
                "question_number": a["question_number"],
                "student_answer": a["student_answer"],
                "confidence": a.get("confidence", 0),
            }
            for a in scan_result.get("answers", [])
        ],
    })


async def _index_wrong_questions(db_session: AsyncSession, submission_id: int):
    """后台任务：错题索引到RAG向量库"""
    try:
        async with db_session.bind.begin() as conn:
            async with AsyncSession(bind=conn) as bg_db:
                await WrongBookService.index_to_rag(bg_db, submission_id)
    except Exception as e:
        logger.error(f"后台RAG索引失败: submission_id={submission_id}, error={e}")


# ========== 手动批卷（拍照上传 + 教师手动标注答案 + 自动批改 + 错题入库） ==========

class ManualGradeRequest(BaseModel):
    """手动批卷请求"""
    exam_number: str = ""          # 学生考号
    student_name: str = ""         # 学生姓名（若考号无法匹配则用此值，可选）
    manual_answers: dict = {}      # 手动标注的答案 {question_number: "A"/"B"/"C"/"D"}


@router.post("/{exam_id}/manual-grade", response_model=ResponseData)
async def manual_grade(
    exam_id: int,
    background_tasks: BackgroundTasks,
    image: UploadFile = File(..., description="答题卡照片"),
    exam_number: str = Form("", description="学生考号"),
    student_name: str = Form("", description="学生姓名"),
    manual_answers_json: str = Form("{}", description="手动标注答案 JSON 字符串 {question_number: 'A'}"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """拍照上传答题卡 → 教师手动标注答案 → 自动批改 → 错题入库

    替代方案：教师查看答题卡照片后手动标注答案，
    系统自动与标准答案对比批改。作为AI识别不准时的兜底方案。

    流程：
    1. 保存上传的答题卡照片到服务器
    2. 解析教师手动标注的答案
    3. 匹配学生身份（考号查 class_student_info，或使用直接输入的学生姓名）
    4. 与标准答案对比批改
    5. 保存提交记录到 exam_submission
    6. 错题写入 wrong_question_book
    7. 记录扫描日志
    """
    import time
    import json
    start_time = time.time()

    exam = await db.get(TeacherExam, exam_id)
    if not exam or exam.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="试卷不存在")
    _require_legacy_exam(exam, teacher_id)

    # 1. 保存上传的图片
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                              "uploads", "scans", str(exam_id))
    os.makedirs(upload_dir, exist_ok=True)

    file_ext = os.path.splitext(image.filename or ".jpg")[1] or ".jpg"
    safe_filename = f"manual_{int(time.time() * 1000)}_{teacher_id}{file_ext}"
    save_path = os.path.join(upload_dir, safe_filename)

    try:
        with open(save_path, "wb") as f:
            shutil.copyfileobj(image.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图片保存失败: {e}")
    finally:
        image.file.close()

    scan_image_url = f"/static/scans/{exam_id}/{safe_filename}"

    # 2. 解析手动答案
    try:
        manual_answers = json.loads(manual_answers_json) if isinstance(manual_answers_json, str) else manual_answers_json
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="manual_answers_json 格式错误，期望 JSON 字符串")

    if not manual_answers:
        raise HTTPException(status_code=400, detail="未提供手动标注的答案")

    logger.info("手动批卷: exam_id=%d, 答题数=%d, exam_number='%s', student_name='%s'",
                exam_id, len(manual_answers), exam_number, student_name)

    # 3. 匹配学生身份（通过考号）
    student_info = None
    student_id = None
    matched_name = student_name

    if exam_number:
        exam_number_clean = re.sub(r'[^0-9]', '', exam_number)
        # 考号归一化：构建尝试列表
        try_numbers = ([exam_number_clean] if exam_number_clean else []) + ([exam_number] if exam_number else [])
        if exam_number_clean and len(exam_number_clean) > 1 and exam_number_clean.lstrip('0'):
            stripped = exam_number_clean.lstrip('0')
            if stripped not in try_numbers:
                try_numbers.append(stripped)
        if exam_number_clean and len(exam_number_clean) <= 4 and exam_number_clean.isdigit():
            for pad_len in (5, 6, 7):
                padded = exam_number_clean.zfill(pad_len)
                if padded not in try_numbers:
                    try_numbers.append(padded)

        for try_number in try_numbers:
            if not try_number:
                continue
            info_stmt = select(ClassStudentInfo).where(
                ClassStudentInfo.class_id == exam.class_id,
                ClassStudentInfo.exam_number == try_number,
            )
            info_result = await db.execute(info_stmt)
            student_info = info_result.scalar_one_or_none()
            if student_info:
                matched_name = student_info.student_name
                student_id = student_info.id
                exam_number = try_number
                logger.info("手动批卷考号匹配: OCR=%s → 匹配=%s", exam_number_clean, try_number)
                break

        # 末四位匹配兜底：完整考号匹配失败后，用考号末4位匹配
        if not student_info and exam_number_clean and len(exam_number_clean) >= 4:
            last4 = exam_number_clean[-4:]
            logger.info("手动批卷完整考号匹配失败，尝试末四位匹配: last4=%s", last4)
            all_stmt = select(ClassStudentInfo).where(
                ClassStudentInfo.class_id == exam.class_id,
            )
            all_result = await db.execute(all_stmt)
            all_students = all_result.scalars().all()
            matched_students = [
                s for s in all_students
                if s.exam_number and s.exam_number[-4:] == last4
            ]
            if len(matched_students) == 1:
                student_info = matched_students[0]
                matched_name = student_info.student_name
                student_id = student_info.id
                exam_number = student_info.exam_number
                logger.info("手动批卷末四位匹配成功: last4=%s → 完整考号=%s, 学生=%s",
                             last4, exam_number, student_name)
            elif len(matched_students) > 1:
                logger.warning("手动批卷末四位匹配冲突: last4=%s 匹配到%s名学生",
                               last4, len(matched_students))
            else:
                logger.warning("手动批卷末四位匹配失败: last4=%s 无匹配学生", last4)

    if not student_info and not matched_name:
        logger.warning("手动批卷: 未匹配到学生 (exam_number=%s, student_name=%s)", exam_number, student_name)

    # 4. 构建批改数据（与 scan-grade 相同逻辑）
    questions = exam.questions or []
    max_score = exam.total_score or 100
    start_number = 21 if any(k in str(exam.grade or "") for k in ["高中", "高三", "senior", "高考"]) else 1
    if not isinstance(manual_answers, dict):
        raise HTTPException(status_code=400, detail="手动答案必须是题号到选项的对象")
    try:
        answers_data, ai_grade_detail, total_score = grade_choice_answers(questions, manual_answers, start_number)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    choice_count = len(answers_data)

    wrong_count = sum(1 for a in answers_data if not a["is_correct"])

    # 5. 保存提交记录（如已存在同一考生提交则覆盖）
    existing_sub = None
    if student_id is not None:
        existing_stmt = select(ExamSubmission).where(
            ExamSubmission.exam_id == exam_id,
            ExamSubmission.student_id == student_id,
        )
        existing_result = await db.execute(existing_stmt)
        existing_sub = existing_result.scalar_one_or_none()

    if existing_sub is not None:
        # 覆盖旧的提交记录
        existing_sub.answers = answers_data
        existing_sub.score = total_score
        existing_sub.max_score = max_score
        existing_sub.ai_grade_detail = ai_grade_detail
        existing_sub.exam_number = exam_number
        existing_sub.grading_status = "manual_done"
        existing_sub.scan_image_url = scan_image_url
        existing_sub.wrong_count = wrong_count
        existing_sub.submitted_at = datetime.utcnow()
        submission = existing_sub
        await db.flush()
        logger.info("手动批改覆盖旧提交: submission_id=%s, exam_number=%s", existing_sub.id, exam_number)
    else:
        submission = ExamSubmission(
            exam_id=exam_id,
            student_id=student_id,
            answers=answers_data,
            score=total_score,
            max_score=max_score,
            ai_grade_detail=ai_grade_detail,
            exam_number=exam_number,
            grading_status="manual_done",
            scan_image_url=scan_image_url,
            wrong_count=wrong_count,
            submitted_at=datetime.utcnow(),
        )
        db.add(submission)
        await db.flush()

    # 6. 错题入库
    wrong_saved = 0
    if student_id is not None:
        try:
            wrong_saved = await WrongBookService.save_from_submission(db, submission)
        except Exception as e:
            logger.error(f"错题入库失败: submission_id={submission.id}, error={e}")
            await db.rollback()
            db.add(submission)
    else:
        logger.warning(f"未匹配到学生，跳过错题入库 (exam_number={exam_number})")

    # 7. 后台异步索引RAG
    if wrong_saved > 0:
        sub_id = submission.id
        background_tasks.add_task(
            _index_wrong_questions, db_session=db, submission_id=sub_id
        )

    # 8. 记录扫描日志
    scan_record = ExamScanRecord(
        exam_id=exam_id,
        teacher_id=teacher_id,
        scan_image_url=scan_image_url,
        recognized_count=choice_count,
        matched_student_id=student_id,
        exam_number=exam_number,
        raw_answers=[{"question_number": k, "student_answer": v} for k, v in manual_answers.items()],
        grading_result={"score": total_score, "wrong_count": wrong_count, "method": "manual"},
        scan_duration_ms=int((time.time() - start_time) * 1000),
    )
    db.add(scan_record)

    # 9. 更新试卷统计
    count_stmt = select(func.count()).where(ExamSubmission.exam_id == exam_id)
    total_sub = (await db.execute(count_stmt)).scalar() or 0
    avg_stmt = select(func.avg(ExamSubmission.score)).where(
        ExamSubmission.exam_id == exam_id,
        ExamSubmission.score.isnot(None),
    )
    avg_result = (await db.execute(avg_stmt)).scalar()
    exam.submission_count = total_sub
    exam.avg_score = round(avg_result, 1) if avg_result else None

    await db.flush()
    await db.commit()

    elapsed = int((time.time() - start_time) * 1000)
    logger.info("手动批卷完成: submission_id=%d, score=%d/%d, wrong=%d, method=manual",
                submission.id, total_score, max_score, wrong_count)

    return ResponseData(data={
        "submission_id": submission.id,
        "student_name": matched_name,
        "exam_number": exam_number,
        "total_score": total_score,
        "max_score": max_score,
        "wrong_count": wrong_count,
        "wrong_saved_count": wrong_saved,
        "scan_duration_ms": elapsed,
        "answers": answers_data,
        "scan_image_url": scan_image_url,
        "detail_summary": f"手动批卷完成: {choice_count}道选择题, {wrong_count}道错误, 得分{total_score}/{max_score}",
        "recognized_count": choice_count,
        "raw_answers": [{"question_number": k, "student_answer": v} for k, v in manual_answers.items()],
        "grading_method": "manual",
    })


# ========== 获取答题卡预览信息（手动批卷页面用） ==========

@router.get("/{exam_id}/grading-info", response_model=ResponseData)
async def get_exam_grading_info(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取试卷批卷所需信息（题目列表、选项、标准答案等）

    用于手动批卷页面：前端显示题目列表，教师对照答题卡照片标注答案。
    不返回标准答案（correct_answer 置空），防止前端泄露答案。
    答案仅在后端批改时使用。
    """
    exam = await db.get(TeacherExam, exam_id)
    if not exam or exam.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="试卷不存在")

    questions = exam.questions or []
    is_senior2 = any(k in str(exam.grade or "") for k in ["高中","高三","senior","高考"])
    sn = 21 if is_senior2 else 1
    choice_questions = ExamService._extract_choice_questions(questions, exam.title or "", start_number=sn)

    grading_questions = []
    for q in choice_questions:
        qnum = q.get("question_number", 0)
        opts = q.get("options", [])
        option_labels = []
        if isinstance(opts, list):
            option_labels = [o.get("label", chr(65 + i)) if isinstance(o, dict) else str(o)[:1]
                           for i, o in enumerate(opts)]
        if not option_labels:
            option_labels = ["A", "B", "C", "D"]
        grading_questions.append({
            "question_number": qnum,
            "options": option_labels,
            "option_count": len(option_labels),
            # 不返回 correct_answer
        })

    return ResponseData(data={
        "exam_id": exam_id,
        "title": exam.title or "",
        "class_id": exam.class_id,
        "total_questions": len(grading_questions),
        "total_score": exam.total_score or 100,
        "questions": grading_questions,
        "start_question": sn,
    })


# ========== 手动修正考号 + 重新匹配学生 ==========

@router.post("/submission/{submission_id}/update-exam-number", response_model=ResponseData)
async def update_exam_number(
    submission_id: int,
    exam_number: str = Form(..., description="手动填入的考号"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    class_id: int = Form(0, description="批卷班级ID（0则使用试卷绑定班级）"),
    db: AsyncSession = Depends(get_db),
    principal: ExamScanPrincipal = Depends(get_exam_scan_principal),
):
    """手机端批改后手动修正考号，重新匹配学生并录入错题

    流程：
    1. 查找已有的 submission 记录
    2. 用新考号匹配学生（含末四位匹配兜底）
    3. 更新 exam_number 和 student_id
    4. 删除旧的错题记录，重新入库
    """
    import time
    teacher_id = principal.teacher_id
    start_time = time.time()

    # 1. 查找提交记录
    submission = await db.get(ExamSubmission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交记录不存在")
    if principal.exam_id is not None and principal.exam_id != submission.exam_id:
        raise HTTPException(status_code=403, detail="扫描会话与当前试卷不匹配")

    # 2. 验证试卷属于该教师
    exam = await db.get(TeacherExam, submission.exam_id)
    if not exam or exam.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="试卷不存在或无权访问")

    # 优先使用传入的 class_id，否则回退到试卷绑定的班级
    _require_legacy_exam(exam, teacher_id)
    roster_class_id = class_id if class_id else exam.class_id
    if roster_class_id:
        roster_class = await db.get(Class, roster_class_id)
        if not roster_class or roster_class.created_by != teacher_id:
            raise HTTPException(status_code=403, detail="所选班级不存在或无权访问")

    # 3. 考号归一化 + 匹配学生（使用与 scan-grade 相同的策略）
    exam_number_clean = re.sub(r'[^0-9]', '', exam_number) if exam_number else ""
    student_info = None
    student_id = None
    student_name = ""

    # 构建尝试列表：清理考号 -> 原始考号 -> 去前导0 -> 补前导0
    try_numbers = ([exam_number_clean] if exam_number_clean else []) + ([exam_number] if exam_number else [])
    if exam_number_clean and len(exam_number_clean) > 1 and exam_number_clean.lstrip('0'):
        stripped = exam_number_clean.lstrip('0')
        if stripped not in try_numbers:
            try_numbers.append(stripped)
    if exam_number_clean and len(exam_number_clean) <= 4 and exam_number_clean.isdigit():
        for pad_len in (5, 6, 7):
            padded = exam_number_clean.zfill(pad_len)
            if padded not in try_numbers:
                try_numbers.append(padded)

    for try_number in try_numbers:
        if not try_number:
            continue
        info_stmt = select(ClassStudentInfo).where(
            ClassStudentInfo.class_id == roster_class_id,
            ClassStudentInfo.exam_number == try_number,
        )
        info_result = await db.execute(info_stmt)
        student_info = info_result.scalar_one_or_none()
        if student_info:
            student_name = student_info.student_name
            student_id = student_info.id
            exam_number = try_number
            logger.info("更新考号匹配成功: %s → 学生=%s", try_number, student_name)
            break

    # 末四位匹配兜底
    if not student_info and exam_number_clean and len(exam_number_clean) >= 4:
        last4 = exam_number_clean[-4:]
        all_stmt = select(ClassStudentInfo).where(
            ClassStudentInfo.class_id == roster_class_id,
        )
        all_result = await db.execute(all_stmt)
        all_students = all_result.scalars().all()
        matched_students = [
            s for s in all_students
            if s.exam_number and s.exam_number[-4:] == last4
        ]
        if len(matched_students) == 1:
            student_info = matched_students[0]
            student_name = student_info.student_name
            student_id = student_info.id
            exam_number = student_info.exam_number
            logger.info("更新考号末四位匹配成功: %s → 学生=%s", last4, student_name)
        elif len(matched_students) > 1:
            logger.warning("更新考号末四位匹配冲突: last4=%s 匹配到%s名学生",
                           last4, len(matched_students))

    # 通过 ClassStudent 查找真正的 User.id
    if student_info is not None:
        cs_stmt = select(ClassStudent.student_id).join(
            User, User.id == ClassStudent.student_id
        ).where(
            ClassStudent.class_id == roster_class_id,
            User.nickname == student_info.student_name,
        )
        cs_result = await db.execute(cs_stmt)
        real_user_id = cs_result.scalar_one_or_none()
        if real_user_id:
            student_id = real_user_id
            logger.info("更新考号通过 ClassStudent 找到真实 User.id: user.id=%s", real_user_id)
        else:
            logger.warning("更新考号：ClassStudentInfo 已匹配但无 ClassStudent 记录: class_id=%s, name=%s",
                           roster_class_id, student_info.student_name)
            student_id = None
            student_name = ""

    # 4. 如果有新的 student_id，检查是否存在同一考试、同一考生的旧提交记录（覆盖）
    if student_id is not None:
        existing_stmt = select(ExamSubmission).where(
            ExamSubmission.exam_id == submission.exam_id,
            ExamSubmission.student_id == student_id,
            ExamSubmission.id != submission_id,
        )
        existing_result = await db.execute(existing_stmt)
        existing_sub = existing_result.scalar_one_or_none()
        if existing_sub is not None:
            # 删除旧提交的错题记录
            await db.execute(
                delete(WrongQuestionBook).where(
                    WrongQuestionBook.submission_id == existing_sub.id
                )
            )
            await db.delete(existing_sub)
            await db.flush()
            logger.info("覆盖旧的提交记录: old_submission_id=%s, new_submission_id=%s",
                        existing_sub.id, submission_id)

    # 5. 更新 submission 的考号和 student_id
    old_student_id = submission.student_id
    submission.exam_number = exam_number
    submission.student_id = student_id
    await db.flush()

    # 6. 如果学生匹配成功，删除旧的错题记录并重新入库
    wrong_saved = 0
    if student_id is not None:
        # 删除旧的错题记录
        old_wrong_stmt = delete(WrongQuestionBook).where(
            WrongQuestionBook.submission_id == submission_id,
        )
        await db.execute(old_wrong_stmt)
        await db.flush()

        # 重新入库错题
        try:
            wrong_saved = await WrongBookService.save_from_submission(db, submission)
        except Exception as e:
            logger.error(f"更新考号后错题入库失败: submission_id={submission_id}, error={e}")
            await db.rollback()
            db.add(submission)

        # 后台异步索引RAG
        if wrong_saved > 0:
            background_tasks.add_task(
                _index_wrong_questions, db_session=db, submission_id=submission_id
            )

    # 6. 更新试卷统计
    count_stmt = select(func.count()).where(ExamSubmission.exam_id == submission.exam_id)
    total_sub = (await db.execute(count_stmt)).scalar() or 0
    avg_stmt = select(func.avg(ExamSubmission.score)).where(
        ExamSubmission.exam_id == submission.exam_id,
        ExamSubmission.score.isnot(None),
    )
    avg_result = (await db.execute(avg_stmt)).scalar()
    exam.submission_count = total_sub
    exam.avg_score = round(avg_result, 1) if avg_result else None

    await db.commit()

    elapsed = int((time.time() - start_time) * 1000)
    logger.info("考号更新完成: submission_id=%d old_student=%s new_student=%s exam_number=%s wrong_saved=%d",
                submission_id, old_student_id, student_id, exam_number, wrong_saved)

    return ResponseData(data={
        "submission_id": submission_id,
        "exam_number": exam_number,
        "student_name": student_name,
        "student_id": student_id,
        "old_student_id": old_student_id,
        "wrong_saved_count": wrong_saved,
        "duration_ms": elapsed,
    })


# ========== 移动端扫码批卷页面 ==========

@router.get("/{exam_id}/mobile-grade", response_class=HTMLResponse)
async def mobile_grade_page(
    exam_id: int,
    mode: str = Query("omr", description="保留参数；移动端统一使用 OMR 批改"),
    class_id: int = Query(0, description="预选班级ID，0表示需要手动选择"),
    db: AsyncSession = Depends(get_db),
    principal: ExamScanPrincipal = Depends(get_exam_scan_principal),
):
    """返回手机扫码批卷的 HTML 页面（含摄像头拍照 + 上传批改功能）"""
    teacher_id = principal.teacher_id
    if principal.exam_id is not None and principal.exam_id != exam_id:
        raise HTTPException(status_code=403, detail="扫描会话与当前试卷不匹配")
    from app.models.exam_models import TeacherExam
    exam = await db.get(TeacherExam, exam_id)
    if not exam or exam.teacher_id != teacher_id:
        from fastapi.responses import HTMLResponse as HTMLResp
        return HTMLResp(
            content="<h2>试卷不存在或无权访问</h2>",
            status_code=404,
        )

    # 查询教师的所有班级（用于班级选择器）
    classes_stmt = select(Class).where(Class.created_by == teacher_id).order_by(Class.name)
    classes_result = await db.execute(classes_stmt)
    teacher_classes = classes_result.scalars().all()
    # 构建班级选项 HTML（class_id 作为字符串渲染，避免 JS 大整数精度丢失）
    class_options_html = ""
    for cls in teacher_classes:
        selected = " selected" if cls.id == class_id else ""
        class_options_html += f'<option value="{cls.id}"{selected}>{cls.name}</option>'

    # 如果没有预选班级且有班级可选，需要显示选择器
    need_selector = (class_id == 0 and len(teacher_classes) > 0) or (class_id != 0)
    default_class_id = class_id if class_id != 0 else (teacher_classes[0].id if teacher_classes else 0)

    # 构建后端 API base URL（从请求推断）
    import urllib.parse

    safe_token = urllib.parse.quote(principal.token)
    session_expires_at_ms = (principal.expires_at or 0) * 1000
    # 不把查询参数直接插入脚本，避免脚本注入，也避免界面误称为多模态批改。
    mode = "omr"

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>手机批卷 - {exam.title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #f0f7f0; color: #1a2e1a; min-height: 100vh;
}}
.header {{
  background: linear-gradient(135deg, #2d7d46, #5B9E6F);
  color: #fff; padding: 20px 16px; text-align: center;
}}
.header h1 {{ font-size: 18px; font-weight: 600; margin-bottom: 4px; }}
.header p {{ font-size: 13px; opacity: 0.9; }}
.container {{ padding: 16px; max-width: 480px; margin: 0 auto; }}
.card {{
  background: #fff; border-radius: 16px; padding: 20px;
  margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}}
.card h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 12px; color: #2d7d46; }}
.btn {{
  display: block; width: 100%; padding: 14px 20px; border-radius: 50px;
  font-size: 16px; font-weight: 500; border: none; cursor: pointer;
  text-align: center; transition: opacity 0.15s;
}}
.btn:active {{ opacity: 0.7; }}
.btn-primary {{ background: #2d7d46; color: #fff; }}
.btn-secondary {{ background: #e6f7e6; color: #2d7d46; border: 1.5px solid #88c8a0; }}
.btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
#cameraView {{
  width: 100%; border-radius: 12px; overflow: hidden;
  background: #000; min-height: 200px; display: flex;
  align-items: center; justify-content: center;
  position: relative;
}}
#cameraView video {{ width: 100%; display: block; }}
#cameraView .placeholder {{ color: #999; font-size: 14px; text-align: center; padding: 40px; }}
/* 扫描框遮罩：半透明背景 + 透明裁切区 */
.scan-frame-overlay {{
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  z-index: 10; pointer-events: none;
}}
/* 裁切区域：匹配答题卡比例(750:800=15:16)，居中显示，不随摄像头画面变形 */
.scan-frame-cutout {{
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  aspect-ratio: 15 / 16;
  /* 取宽度84%和高度88%按答题卡比例换算后较小的值，确保不溢出 */
  width: min(84%, calc(88% * 15 / 16));
  height: auto;
  box-shadow: 0 0 0 9999px rgba(0,0,0,0.55);
  border-radius: 6px;
}}
/* 四角括号 */
.scan-frame-corner {{
  position: absolute; width: 24px; height: 24px;
  border-color: rgba(45,125,70,0.9); border-style: solid;
}}
.scan-frame-corner.tl {{ top: -1px; left: -1px; border-width: 3px 0 0 3px; border-radius: 4px 0 0 0; }}
.scan-frame-corner.tr {{ top: -1px; right: -1px; border-width: 3px 3px 0 0; border-radius: 0 4px 0 0; }}
.scan-frame-corner.bl {{ bottom: -1px; left: -1px; border-width: 0 0 3px 3px; border-radius: 0 0 0 4px; }}
.scan-frame-corner.br {{ bottom: -1px; right: -1px; border-width: 0 3px 3px 0; border-radius: 0 0 4px 0; }}
/* 提示文字 */
.scan-frame-hint {{
  position: absolute; bottom: -32px; left: 0; right: 0;
  text-align: center; color: #fff; font-size: 13px;
  font-weight: 500; text-shadow: 0 1px 3px rgba(0,0,0,0.6);
  letter-spacing: 1px;
}}
.photo-preview {{ width: 100%; border-radius: 12px; overflow: hidden; }}
.photo-preview img {{ width: 100%; display: block; }}
.step {{ display: flex; gap: 12px; align-items: flex-start; margin-bottom: 12px; }}
.step-num {{
  width: 28px; height: 28px; border-radius: 50%;
  background: #2d7d46; color: #fff; display: flex;
  align-items: center; justify-content: center;
  font-size: 14px; font-weight: 600; flex-shrink: 0;
}}
.step-text {{ font-size: 14px; color: #333; line-height: 1.5; margin-top: 4px; }}
.status-msg {{ padding: 12px 16px; border-radius: 12px; margin-bottom: 12px; font-size: 14px; }}
.status-ok {{ background: #d1fae5; color: #2d7d46; }}
.status-err {{ background: #fee2e2; color: #dc2626; }}
.status-wait {{ background: #fef9c3; color: #92400e; }}
.result-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }}
.result-item {{ padding: 12px; border-radius: 10px; text-align: center; background: #f5f5f5; }}
.result-item .label {{ font-size: 11px; color: #666; margin-bottom: 4px; }}
.result-item .value {{ font-size: 18px; font-weight: 700; }}
.result-item .value.green {{ color: #2d7d46; }}
.result-item .value.red {{ color: #dc2626; }}
.answer-list {{ margin-top: 12px; }}
.answer-row {{
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 0; border-bottom: 1px solid #f0f0f0; font-size: 13px;
}}
.answer-row .qn {{ font-weight: 600; color: #333; }}
.answer-row .correct {{ color: #2d7d46; }}
.answer-row .wrong {{ color: #dc2626; }}
.toolbar {{ display: flex; gap: 10px; margin-top: 12px; }}
.toolbar .btn {{ flex: 1; }}
.action-buttons {{ display: flex; gap: 10px; margin-top: 16px; }}
.action-buttons .btn {{ flex: 1; }}
/* 全屏摄像头模式：camera-view 铺满屏幕 */
.camera-view-fullscreen {{
  position: fixed !important; top: 0 !important; left: 0 !important;
  width: 100vw !important; height: 100vh !important; height: 100dvh !important;
  z-index: 999 !important; border-radius: 0 !important; margin: 0 !important;
}}
.camera-view-fullscreen video {{
  width: 100% !important; height: 100% !important; object-fit: cover !important;
}}
/* 全屏扫描对准遮罩层 */
.scan-fullscreen-overlay {{
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  z-index: 1000; pointer-events: none;
}}
/* A4 纸比例裁切框 (1:1.414)，居中取屏幕高度 78% */
.scan-a4-cutout {{
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  height: 78vh; height: 78dvh;
  aspect-ratio: 1 / 1.414;
  box-shadow: 0 0 0 9999px rgba(0,0,0,0.55);
  border-radius: 6px; pointer-events: none;
}}
/* 全屏拍照按钮 */
.capture-fullscreen-btn {{
  position: fixed; bottom: 32px; left: 50%;
  transform: translateX(-50%);
  z-index: 1001; pointer-events: auto;
  width: auto; padding: 14px 48px;
  border-radius: 50px; background: #2d7d46; color: #fff;
  font-size: 16px; font-weight: 600; border: none; cursor: pointer;
  box-shadow: 0 4px 16px rgba(0,0,0,0.3);
}}
.capture-fullscreen-btn:active {{ opacity: 0.7; }}
/* 全屏顶部提示 */
.scan-fullscreen-hint {{
  position: fixed; top: 16px; left: 50%;
  transform: translateX(-50%);
  z-index: 1001; pointer-events: auto;
  color: #fff; font-size: 15px; font-weight: 500;
  background: rgba(0,0,0,0.4); padding: 8px 20px;
  border-radius: 20px; letter-spacing: 1px;
}}
/* 缩略图条 */
.thumbnail-strip {{
  display: flex; gap: 8px; overflow-x: auto; padding: 8px 0;
  scrollbar-width: none; -ms-overflow-style: none;
}}
.thumbnail-strip::-webkit-scrollbar {{ display: none; }}
.thumb-item {{
  width: 60px; height: 80px; border-radius: 8px; flex-shrink: 0;
  position: relative; border: 2px solid #e0e0e0;
  overflow: hidden; background: #f5f5f5; cursor: pointer;
}}
.thumb-item.on {{ border-color: #2d7d46; box-shadow: 0 0 0 2px rgba(45,125,70,0.25); }}
.thumb-item img {{ width: 100%; height: 100%; object-fit: cover; }}
.thumb-item .thumb-label {{
  position: absolute; bottom: 0; left: 0; right: 0;
  background: rgba(0,0,0,0.5); color: #fff;
  font-size: 9px; text-align: center; padding: 1px;
}}
.thumb-item .thumb-badge {{
  position: absolute; top: 2px; right: 2px;
  width: 16px; height: 16px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  z-index: 2; font-size: 9px; color: #fff; font-weight: 700;
}}
.thumb-badge.pass {{ background: #2d7d46; }} .thumb-badge.fail {{ background: #dc2626; }}
/* 处理中动画 */
.processing-box {{ text-align: center; padding: 20px 0; }}
.spinner {{
  width: 36px; height: 36px; margin: 0 auto 10px;
  border: 3px solid rgba(45,125,70,0.15); border-top-color: #2d7d46;
  border-radius: 50%; animation: spin 0.8s linear infinite;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
.processing-box .proc-text {{ color: #2d7d46; font-size: 13px; }}
/* Toast */
.toast-popup {{
  position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
  background: rgba(0,0,0,0.82); color: #fff; padding: 10px 20px;
  border-radius: 20px; font-size: 13px; z-index: 3000;
  pointer-events: none; opacity: 0; transition: opacity 0.3s;
}}
.toast-popup.visible {{
  opacity: 1;
}}
/* Modal 弹窗 */
.modal-overlay {{
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5); z-index: 2000;
  display: flex; flex-direction: column; justify-content: flex-end;
  animation: fadeIn 0.25s;
}}
@keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
.modal-sheet {{
  background: #fff; border-radius: 20px 20px 0 0; max-height: 80vh;
  display: flex; flex-direction: column;
  animation: slideUp 0.3s;
}}
@keyframes slideUp {{ from {{ transform: translateY(100%); }} to {{ transform: translateY(0); }} }}
.modal-header {{
  padding: 14px 20px 10px; border-bottom: 1px solid #f0f0f0;
  display: flex; justify-content: space-between; align-items: center;
}}
.modal-header h3 {{ font-size: 16px; font-weight: 600; }}
.modal-body {{ overflow-y: auto; padding: 0 20px; flex: 1; }}
.modal-footer {{ padding: 12px 20px 20px; border-top: 1px solid #f0f0f0; display: flex; gap: 10px; }}
.modal-footer .btn {{ flex: 1; }}
/* 汇总条 */
.summary-bar {{
  display: flex; align-items: center; gap: 10px; padding: 10px 14px;
  background: #f0faf0; border-radius: 10px; margin: 10px 0;
  font-size: 13px;
}}
.summary-bar .sm-val {{ font-weight: 700; font-size: 15px; }}
/* 结果列表项 */
.result-list-item {{
  display: flex; align-items: center; padding: 11px 4px;
  border-bottom: 1px solid #f5f5f5; gap: 6px; cursor: pointer;
  font-size: 13px;
}}
.result-list-item:last-child {{ border-bottom: none; }}
.result-list-item:active {{ background: #f9f9f9; }}
.result-list-item .ri-col {{
  text-align: left; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}}
.result-list-item .ri-col.exam-num {{
  width: 56px; flex-shrink: 0; font-weight: 600; color: #333; font-size: 12px;
}}
.result-list-item .ri-col.name {{
  flex: 1; font-weight: 500; color: #1a2e1a; min-width: 0;
}}
.result-list-item .ri-col.score {{
  width: 65px; flex-shrink: 0; text-align: center; font-weight: 700; font-size: 15px;
}}
.result-list-item .ri-col.score.pass {{ color: #2d7d46; }}
.result-list-item .ri-col.score.fail {{ color: #dc2626; }}
.result-list-item .ri-col.score.pending {{ color: #aaa; font-size: 12px; font-weight: 400; }}
.result-list-item .ri-col.detail-link {{
  width: 44px; flex-shrink: 0; text-align: right; color: #2d7d46; font-size: 12px; font-weight: 500;
}}
.result-list-item .ri-col.detail-link .arrow {{
  display: inline-block; transition: transform 0.15s;
}}
/* 表头 */
.result-header {{
  display: flex; align-items: center; padding: 8px 4px; gap: 6px;
  border-bottom: 1px solid #e8e8e8; font-size: 11px; color: #999;
  font-weight: 500; position: sticky; top: 0; background: #fff; z-index: 1;
}}
.result-header .rh-col.exam-num {{ width: 56px; flex-shrink: 0; }}
.result-header .rh-col.name {{ flex: 1; }}
.result-header .rh-col.score {{ width: 65px; flex-shrink: 0; text-align: center; }}
.result-header .rh-col.detail {{ width: 44px; flex-shrink: 0; text-align: right; }}
/* 详情头部 */
.detail-header {{
  background: linear-gradient(135deg,#f0faf0,#e6f7e6); border-radius: 12px;
  padding: 14px; text-align: center; margin: 10px 0;
}}
.detail-header .dh-name {{ font-size: 18px; font-weight: 700; color: #2d7d46; }}
.detail-header .dh-sub {{ font-size: 11px; color: #888; margin-top: 2px; }}
.detail-header .dh-stats {{ display: flex; justify-content: center; gap: 14px; margin-top: 8px; }}
.detail-header .dh-stats .ds-item {{ text-align: center; }}
.ds-item .ds-val {{ font-size: 17px; font-weight: 700; }}
.ds-item .ds-lbl {{ font-size: 10px; color: #888; }}
/* 详情答题行 */
.detail-answer-row {{
  display: flex; align-items: center; padding: 9px 10px;
  border-radius: 8px; margin-bottom: 3px; font-size: 13px;
}}
.detail-answer-row.correct {{ background: #f0faf0; }}
.detail-answer-row.wrong {{ background: #fef5f5; }}
.detail-answer-row .da-qn {{ font-weight: 700; width: 32px; flex-shrink: 0; }}
.detail-answer-row .da-ans {{ flex: 1; text-align: center; }}
.detail-answer-row .da-ans .sa {{ font-weight: 600; }}
.detail-answer-row .da-ans .ca {{ font-size: 11px; color: #888; margin-left: 4px; }}
.detail-answer-row .da-judge {{ font-weight: 700; width: 28px; text-align: right; }}
.da-judge.c {{ color: #2d7d46; }} .da-judge.w {{ color: #dc2626; }}
/* 进度条 */
.progress-bar {{
  width: 100%; height: 4px; background: #e5e7eb;
  border-radius: 2px; overflow: hidden; margin-top: 6px;
}}
.progress-bar .pb-fill {{ height: 100%; background: #2d7d46; border-radius: 2px; }}
/* 返回按钮 */
.back-link {{
  display: flex; align-items: center; gap: 6px; color: #2d7d46;
  font-size: 14px; padding: 6px 0; cursor: pointer; border: none; background: none;
}}
/* 批改中提示 */
.grading-hint {{
  text-align: center; padding: 10px; margin-bottom: 8px;
  background: #fef9c3; border-radius: 10px; font-size: 13px; color: #92400e;
  display: flex; align-items: center; justify-content: center; gap: 6px;
}}
.grading-hint .mini-spinner {{
  width: 14px; height: 14px; border: 2px solid rgba(146,64,14,0.2);
  border-top-color: #92400e; border-radius: 50%;
  animation: spin 0.7s linear infinite; display: inline-block;
}}
/* 隐藏工具类 */
.hidden {{ display: none !important; }}
/* 处理中指示器 */
.processing {{ text-align: center; padding: 24px 0; }}
.processing .proc-spinner {{
  width: 40px; height: 40px; margin: 0 auto 10px;
  border: 3px solid rgba(45,125,70,0.15);
  border-top-color: #2d7d46; border-radius: 50%;
  animation: spin 0.8s linear infinite;
}}
.processing .proc-text {{ color: #2d7d46; font-size: 14px; }}
/* 拍照闪白 */
#flash {{
  position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
  background: #fff; z-index: 9999; pointer-events: none; display: none;
}}
@keyframes flashAnim {{ 0% {{ opacity:1; }} 100% {{ opacity:0; }} }}
/* 后拍摄按钮区 */
.after-shot-btns {{ display: flex; gap: 10px; margin-top: 12px; }}
.after-shot-btns .btn {{ flex: 1; }}
/* 考号修正区 */
.exam-number-edit {{
  margin-top: 12px; padding: 14px; background: #fafcf8;
  border-radius: 12px; border: 1.5px dashed #d0e6d4;
}}
.exam-number-edit label {{
  display: block; font-size: 13px; font-weight: 600; color: #555; margin-bottom: 8px;
}}
.exam-number-edit .edit-row {{
  display: flex; gap: 8px; align-items: center;
}}
.exam-number-edit input {{
  flex: 1; padding: 11px 14px; border-radius: 50px;
  border: 1.5px solid #d0e0d4; font-size: 16px; outline: none;
  background: #fff; text-align: center; letter-spacing: 2px;
  transition: border-color 0.2s;
}}
.exam-number-edit input:focus {{
  border-color: #2d7d46; box-shadow: 0 0 0 3px rgba(45,125,70,0.1);
}}
.exam-number-edit .confirm-btn {{
  padding: 11px 20px; border-radius: 50px; background: #2d7d46;
  color: #fff; border: none; font-size: 14px; font-weight: 500;
  cursor: pointer; white-space: nowrap; transition: opacity 0.15s;
}}
.exam-number-edit .confirm-btn:active {{ opacity: 0.7; }}
.exam-number-edit .confirm-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
.exam-number-edit .match-msg {{
  margin-top: 8px; font-size: 12px; color: #2d7d46; font-weight: 500;
}}
.exam-number-edit .match-msg.fail {{
  color: #dc2626;
}}
.class-selector {{
  background: #f0f7ff; border: 1px solid #2563eb; border-radius: 12px;
  padding: 14px 16px; margin-bottom: 16px; text-align: center;
}}
.class-selector label {{
  display: block; font-size: 13px; color: #1e40af; margin-bottom: 8px; font-weight: 600;
}}
.class-selector select {{
  width: 100%; padding: 10px 12px; border: 1px solid #93c5fd; border-radius: 8px;
  font-size: 15px; background: white; color: #1e3a5f; appearance: auto;
}}
</style>
</head>
<body>
<div class="header">
  <h1>📝 手机批卷</h1>
  <p id="examTitle">{exam.title}</p>
</div>

  <!-- 班级选择器 -->
  <div class="class-selector" id="classSelector">
    <label>📚 选择批卷班级（用于考号匹配）</label>
    <select id="classIdSelect">
      {class_options_html}
    </select>
  </div>

<div class="container">

  <!-- 使用步骤 -->
  <div class="card" id="stepsCard">
    <h2>📋 使用步骤</h2>
    <div class="step"><span class="step-num">1</span><span class="step-text">将学生填涂好的答题卡置于光线充足处</span></div>
    <div class="step"><span class="step-num">2</span><span class="step-text">点击「拍照」按钮拍摄答题卡，每拍一张自动后台识别</span></div>
    <div class="step"><span class="step-num">3</span><span class="step-text">可连续拍摄多份，点击「完成」查看所有批改结果</span></div>
  </div>

  <!-- 状态提示 -->
  <div id="statusArea" class="status-msg status-wait" style="display:none;"></div>

  <!-- 拍照区域 -->
  <div class="card" id="cameraCard">
    <h2>📷 拍照</h2>
    <!-- 缩略图条 -->
    <div id="thumbStrip" class="thumbnail-strip" style="display:none;"></div>
    <!-- 摄像头视图 -->
    <div id="cameraView"><div class="placeholder">点击下方按钮启动摄像头</div></div>
    <!-- 预览图 -->
    <div id="photoPreview" class="photo-preview" style="display:none;">
      <img id="capturedImage" src="" alt="拍摄的答题卡" />
    </div>
    <!-- 处理中 -->
    <div id="processingArea" class="processing hidden">
      <div class="proc-spinner"></div>
      <p class="proc-text" id="procText">正在上传并识别答题卡...</p>
    </div>
    <!-- 启动按钮 -->
    <div id="startBtnArea" class="action-buttons">
      <button id="startCamBtn" class="btn btn-primary" onclick="startCamera()">📸 启动摄像头</button>
    </div>
    <!-- 拍后按钮 -->
    <div id="afterShotBtns" class="after-shot-btns hidden">
      <button class="btn btn-secondary" onclick="retake()">📷 继续拍摄</button>
      <button class="btn btn-primary" onclick="finish()">✅ 完成(<span id="counterSpan">0</span>)张</button>
    </div>
  </div>

  <!-- 单份结果卡片 -->
  <div id="singleResultCard" class="card hidden">
    <h2 id="singleResultTitle">✅ 批改结果</h2>
    <div id="singleResultContent"></div>
    <!-- 手动修正考号区 -->
    <div id="examNumberEdit" class="exam-number-edit hidden">
      <label>✏️ 考号有误？手动填入修正考号</label>
      <div class="edit-row">
        <input type="text" id="examNumberInput" placeholder="输入完整考号，如 0002603" inputmode="numeric" />
        <button class="confirm-btn" id="confirmExamBtn" onclick="confirmExamNumber()">确认</button>
      </div>
      <div class="match-msg" id="matchMsg" style="display:none;"></div>
    </div>
  </div>

</div>

<!-- 全屏扫描对准遮罩层 -->
<div class="scan-fullscreen-overlay" id="scanOverlay" style="display:none;">
  <div class="scan-a4-cutout">
    <div class="scan-frame-corner tl"></div>
    <div class="scan-frame-corner tr"></div>
    <div class="scan-frame-corner bl"></div>
    <div class="scan-frame-corner br"></div>
  </div>
  <div class="scan-fullscreen-hint" id="scanHint">请将答题卡对准此框</div>
  <button class="capture-fullscreen-btn" id="fullscreenCaptureBtn" onclick="capture()">📸 拍照</button>
</div>

<!-- Toast -->
<div id="toast" class="toast-popup"></div>

<!-- 汇总弹窗 -->
<div class="modal-overlay hidden" id="resultsModal">
  <div class="modal-sheet">
    <div class="modal-header">
      <h3>📊 批改结果（<span id="resultCount">0</span>份）</h3>
      <button style="border:none;background:none;font-size:20px;color:#999;cursor:pointer" onclick="closeResultModal()">✕</button>
    </div>
    <div class="modal-body" id="resultModalBody"></div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeResultModal()">📸 返回拍照</button>
      <button class="btn btn-primary" onclick="submitAll()">✅ 提交全部</button>
    </div>
  </div>
</div>

<!-- 详情弹窗 -->
<div class="modal-overlay hidden" id="detailModal">
  <div class="modal-sheet" style="max-height:90vh;">
    <div class="modal-header">
      <button class="back-link" onclick="closeDetailModal()">← 返回列表</button>
      <span style="font-size:13px;color:#888">答题详情</span>
      <span style="width:60px"></span>
    </div>
    <div class="modal-body" id="detailModalBody"></div>
  </div>
</div>

<!-- 拍照闪白 -->
<div id="flash"></div>

<script>
// 注意: exam_id/class_id 是超大整数(Snowflake ID), 必须用字符串避免JS精度丢失
const EXAM_ID = '{exam_id}';
const DEFAULT_CLASS_ID = '{default_class_id}';
const TOKEN = '{safe_token}';
const API_BASE = window.location.origin + window.location.pathname.split('/teacher/exam/')[0];
const GRADING_MODE = '{mode}';
const SESSION_EXPIRES_AT = {session_expires_at_ms};
const MAX_SHEETS = 30;

let stream = null;
let state = {{
  sheets: [],
  currentDisplayIdx: -1
}};

// ========== 工具函数 ==========
function showStatus(msg, type) {{
  const el = document.getElementById('statusArea');
  el.textContent = msg;
  el.className = 'status-msg status-' + type;
  el.style.display = 'block';
}}

function hideStatus() {{
  document.getElementById('statusArea').style.display = 'none';
}}

function toast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast-popup visible';
  clearTimeout(t._timer);
  t._timer = setTimeout(() => {{ t.className = 'toast-popup'; }}, 2000);
}}

function ensureSessionActive() {{
  if (SESSION_EXPIRES_AT && Date.now() >= SESSION_EXPIRES_AT) {{
    cleanupCamera();
    showStatus('二维码会话已过期，请返回电脑端刷新二维码后重新扫码', 'err');
    return false;
  }}
  return true;
}}

function flashEffect() {{
  const f = document.getElementById('flash');
  f.style.display = 'block';
  f.style.animation = 'none';
  f.offsetHeight;
  f.style.animation = 'flashAnim 0.4s ease-out forwards';
  setTimeout(() => {{ f.style.display = 'none'; }}, 400);
}}


// ========== 占位缩略图 ==========
function genPlaceholderThumb(examNum) {{
  const c = document.createElement('canvas'); c.width = 120; c.height = 160;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#fdfaf3'; ctx.fillRect(0, 0, 120, 160);
  ctx.strokeStyle = '#ddd'; ctx.lineWidth = 0.5;
  for (let y = 20; y < 150; y += 14) {{ ctx.beginPath(); ctx.moveTo(10, y); ctx.lineTo(110, y); ctx.stroke(); }}
  ctx.fillStyle = '#999'; ctx.font = '9px sans-serif'; ctx.fillText('NO.' + examNum, 8, 14);
  ctx.fillStyle = '#888'; ctx.font = 'bold 11px sans-serif'; ctx.fillText('批改中...', 8, 50);
  return c.toDataURL('image/png');
}}

function genResultThumb(sheet) {{
  const c = document.createElement('canvas'); c.width = 120; c.height = 160;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#fdfaf3'; ctx.fillRect(0, 0, 120, 160);
  ctx.strokeStyle = '#ddd'; ctx.lineWidth = 0.5;
  for (let y = 20; y < 150; y += 14) {{ ctx.beginPath(); ctx.moveTo(10, y); ctx.lineTo(110, y); ctx.stroke(); }}
  ctx.fillStyle = '#999'; ctx.font = '9px sans-serif'; ctx.fillText('NO.' + sheet.examNumber, 8, 14);
  ctx.fillStyle = '#2d7d46'; ctx.font = 'bold 12px sans-serif'; ctx.fillText(sheet.studentName, 8, 36);
  const passed = sheet.totalScore >= sheet.maxScore * 0.6;
  ctx.fillStyle = passed ? '#2d7d46' : '#dc2626';
  ctx.font = 'bold 18px sans-serif'; ctx.fillText(sheet.totalScore + '/' + sheet.maxScore, 8, 60);
  return c.toDataURL('image/png');
}}

// ========== 缩略图条 ==========
function renderStrip() {{
  const strip = document.getElementById('thumbStrip');
  strip.innerHTML = '';
  if (state.sheets.length === 0) {{ strip.style.display = 'none'; return; }}
  strip.style.display = 'flex';
  state.sheets.forEach((s, i) => {{
    const th = document.createElement('div');
    const isCurrent = (i === state.currentDisplayIdx);
    th.className = 'thumb-item' + (isCurrent ? ' on' : '');
    if (s.status === 'grading') {{
      th.innerHTML = '<img src="' + s.thumbUrl + '" style="opacity:0.6" />' +
        '<div style="position:absolute;top:0;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center">' +
        '<div class="spinner" style="width:20px;height:20px;border-width:2px"></div></div>' +
        '<div style="position:absolute;bottom:0;left:0;right:0;background:rgba(0,0,0,0.4);color:#fff;font-size:9px;text-align:center;padding:1px">批改中...</div>';
    }} else if (s.status === 'error') {{
      th.innerHTML = '<img src="' + s.thumbUrl + '" style="opacity:0.6" />' +
        '<div style="position:absolute;top:0;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center;font-size:20px">❌</div>' +
        '<div style="position:absolute;bottom:0;left:0;right:0;background:rgba(220,38,38,0.7);color:#fff;font-size:9px;text-align:center;padding:1px">失败</div>';
    }} else {{
      const passed = s.totalScore >= s.maxScore * 0.6;
      th.innerHTML = '<img src="' + s.thumbUrl + '" />' +
        '<div style="position:absolute;top:2px;right:2px;width:18px;height:18px;border-radius:50%;background:' + (passed ? 'rgba(45,125,70,0.85)' : 'rgba(220,38,38,0.85)') + ';color:#fff;font-size:10px;display:flex;align-items:center;justify-content:center">' + (passed ? '✓' : '!') + '</div>' +
        '<div style="position:absolute;bottom:0;left:0;right:0;background:rgba(0,0,0,0.5);color:#fff;font-size:9px;text-align:center;padding:1px">' + s.studentName + ' ' + s.totalScore + '/' + s.maxScore + '</div>';
    }}
    th.onclick = () => {{ state.currentDisplayIdx = i; showSingleResult(i); renderStrip(); }};
    strip.appendChild(th);
  }});
  strip.scrollLeft = strip.scrollWidth;
}}

// ========== 按钮状态 ==========
function updateButtons() {{
  const n = state.sheets.length;
  document.getElementById('counterSpan').textContent = n;
  if (n > 0) {{
    document.getElementById('startBtnArea').classList.add('hidden');
    document.getElementById('afterShotBtns').classList.remove('hidden');
  }} else {{
    document.getElementById('startBtnArea').classList.remove('hidden');
    document.getElementById('afterShotBtns').classList.add('hidden');
  }}
}}

// ========== 清理摄像头 ==========
function cleanupCamera() {{
  if (stream) {{
    stream.getTracks().forEach(t => t.stop());
    stream = null;
  }}
  const view = document.getElementById('cameraView');
  const oldVideo = view.querySelector('video');
  if (oldVideo) {{
    if (oldVideo.srcObject) {{
      oldVideo.srcObject.getTracks().forEach(t => t.stop());
      oldVideo.srcObject = null;
    }}
    oldVideo.remove();
  }}
  view.classList.remove('camera-view-fullscreen');
  document.getElementById('scanOverlay').style.display = 'none';
  view.innerHTML = '<div class="placeholder">点击下方按钮启动摄像头</div>';
}}

// ========== 摄像头操作 ==========
async function startCamera() {{
  if (!ensureSessionActive()) return;
  if (state.sheets.length >= MAX_SHEETS) {{ showStatus('单次最多批改' + MAX_SHEETS + '份', 'err'); return; }}
  hideStatus();
  document.getElementById('singleResultCard').classList.add('hidden');
  document.getElementById('photoPreview').style.display = 'none';
  document.getElementById('processingArea').classList.add('hidden');

  const view = document.getElementById('cameraView');
  try {{
    stream = await navigator.mediaDevices.getUserMedia({{
      video: {{
        facingMode: {{ ideal: 'environment' }},
        width: {{ ideal: 2560 }},
        height: {{ ideal: 1920 }},
        aspectRatio: {{ ideal: 1.414 }}
      }}
    }});
    const video = document.createElement('video');
    video.srcObject = stream;
    video.setAttribute('autoplay', '');
    video.setAttribute('playsinline', '');
    video.setAttribute('muted', '');
    video.onloadedmetadata = () => video.play();
    const placeholder = view.querySelector('.placeholder');
    if (placeholder) placeholder.remove();
    const oldVideo = view.querySelector('video');
    if (oldVideo) {{ oldVideo.srcObject = null; oldVideo.remove(); }}
    view.insertBefore(video, view.firstChild);
    view.classList.add('camera-view-fullscreen');
    document.getElementById('scanOverlay').style.display = 'block';
    document.getElementById('startBtnArea').classList.add('hidden');
  }} catch (e) {{
    showStatus('无法访问摄像头: ' + e.message, 'err');
  }}
}}


// ========== 拍照 ==========
function capture() {{
  if (!ensureSessionActive()) return;
  const view = document.getElementById('cameraView');
  const video = view.querySelector('video');
  if (!video) return;

  flashEffect();

  // 裁剪图片
  const fullCanvas = document.createElement('canvas');
  fullCanvas.width = video.videoWidth;
  fullCanvas.height = video.videoHeight;
  fullCanvas.getContext('2d').drawImage(video, 0, 0);

  const cutout = document.querySelector('.scan-a4-cutout');
  const crop = getCropRect(video, cutout);

  let finalCanvas;
  if (crop) {{
    finalCanvas = document.createElement('canvas');
    finalCanvas.width = crop.w; finalCanvas.height = crop.h;
    finalCanvas.getContext('2d').drawImage(fullCanvas, crop.x, crop.y, crop.w, crop.h, 0, 0, crop.w, crop.h);
  }} else {{
    finalCanvas = resizeCanvas(fullCanvas, 2048);
  }}

  finalCanvas = resizeCanvas(finalCanvas, 2400);
  const quality = assessCaptureQuality(finalCanvas);
  if (!quality.ok) {{
    toast('请重拍：' + quality.message);
    showStatus('照片质量检查未通过：' + quality.message + '。请保持手机稳定、光线均匀，并让答题卡铺满取景框。', 'err');
    return;
  }}

  // 停止摄像头
  cleanupCamera();

  // 创建占位 sheet 并立即加入状态
  const examNum = state.sheets.length + 1;
  const placeholder = {{
    examNumber: examNum,
    studentName: '...',
    totalScore: 0, maxScore: 0, correctCount: 0, wrongCount: 0,
    answers: [], scanDurationMs: 0, gradingMode: GRADING_MODE,
    thumbUrl: genPlaceholderThumb(examNum),
    submissionId: 0,
    status: 'grading'
  }};
  state.sheets.push(placeholder);
  const idx = state.sheets.length - 1;
  state.currentDisplayIdx = idx;

  // 立即更新 UI
  updateButtons(); renderStrip(); showSingleResult(idx);
  document.getElementById('singleResultCard').classList.remove('hidden');

  // 显示处理动画
  document.getElementById('processingArea').classList.remove('hidden');

  // 启动后台批改
  finalCanvas.toBlob(function(blob) {{
    backgroundGrade(idx, examNum, blob);
  }}, 'image/jpeg', 0.92);

  toast('📸 第' + examNum + '号已拍摄，后台批改中...');
}}

// 计算扫描框在视频坐标系中的裁剪矩形
// 考虑到 object-fit: cover 缩放并居中视频时，部分视频可能被裁剪
// 返回 null 表示裁剪无效，应发送原图
function getCropRect(video, cutoutEl) {{
  if (!cutoutEl) return null;

  const videoW = video.videoWidth || 0;
  const videoH = video.videoHeight || 0;
  if (videoW < 100 || videoH < 100) return null;

  const containerW = window.innerWidth;
  const containerH = window.innerHeight;

  // object-fit: cover 的缩放因子 —— 取较大方向的比例，保证覆盖全屏
  const scale = Math.max(containerW / videoW, containerH / videoH);
  const renderedW = videoW * scale;
  const renderedH = videoH * scale;

  // 视频在容器内的偏移（居中放置，超出部分被裁剪）
  const offsetX = (containerW - renderedW) / 2;
  const offsetY = (containerH - renderedH) / 2;

  // 扫描框在屏幕上的位置和尺寸
  const cutout = cutoutEl.getBoundingClientRect();

  // 映射到视频原生坐标系
  let cx = (cutout.left - offsetX) / scale;
  let cy = (cutout.top - offsetY) / scale;
  let cw = cutout.width / scale;
  let ch = cutout.height / scale;

  // 裁剪保护：确保不超出视频边界
  cx = Math.max(0, Math.round(cx));
  cy = Math.max(0, Math.round(cy));
  cw = Math.min(Math.round(cw), videoW - cx);
  ch = Math.min(Math.round(ch), videoH - cy);

  // 安全阀：裁剪区域太小（不足原图 5%）则放弃裁剪，返回原图
  if (cw < videoW * 0.05 || ch < videoH * 0.05) {{
    console.warn('裁剪区域过小，放弃裁剪，发送原图。crop=%dx%d video=%dx%d', cw, ch, videoW, videoH);
    return null;
  }}

  return {{ x: cx, y: cy, w: cw, h: ch }};
}}

// 缩放 canvas 到指定最大边长（保持宽高比），用于裁剪无效时压缩原图
function resizeCanvas(sourceCanvas, maxDim) {{
  let w = sourceCanvas.width, h = sourceCanvas.height;
  if (Math.max(w, h) <= maxDim) return sourceCanvas;

  const ratio = maxDim / Math.max(w, h);
  w = Math.round(w * ratio);
  h = Math.round(h * ratio);

  const out = document.createElement('canvas');
  out.width = w;
  out.height = h;
  const ctx = out.getContext('2d');
  ctx.drawImage(sourceCanvas, 0, 0, w, h);
  return out;
}}

// 在上传前做轻量质量检查，减少模糊、过暗、过曝图片造成的误判。
function assessCaptureQuality(sourceCanvas) {{
  const sample = resizeCanvas(sourceCanvas, 320);
  const ctx = sample.getContext('2d', {{ willReadFrequently: true }});
  const pixels = ctx.getImageData(0, 0, sample.width, sample.height).data;
  const luminance = new Float32Array(sample.width * sample.height);
  let sum = 0;
  for (let i = 0, p = 0; i < pixels.length; i += 4, p++) {{
    const value = pixels[i] * 0.299 + pixels[i + 1] * 0.587 + pixels[i + 2] * 0.114;
    luminance[p] = value;
    sum += value;
  }}
  const mean = sum / luminance.length;
  let variance = 0;
  let gradient = 0;
  let gradientCount = 0;
  for (let y = 0; y < sample.height; y++) {{
    for (let x = 0; x < sample.width; x++) {{
      const idx = y * sample.width + x;
      const delta = luminance[idx] - mean;
      variance += delta * delta;
      if (x > 0) {{ gradient += Math.abs(luminance[idx] - luminance[idx - 1]); gradientCount++; }}
      if (y > 0) {{ gradient += Math.abs(luminance[idx] - luminance[idx - sample.width]); gradientCount++; }}
    }}
  }}
  const contrast = Math.sqrt(variance / luminance.length);
  const sharpness = gradientCount ? gradient / gradientCount : 0;
  if (mean < 45) return {{ ok: false, message: '环境太暗' }};
  if (mean > 235) return {{ ok: false, message: '画面过曝' }};
  if (contrast < 22) return {{ ok: false, message: '答题卡与背景对比不足' }};
  if (sharpness < 4.5) return {{ ok: false, message: '画面可能模糊' }};
  return {{ ok: true, message: '质量通过', brightness: mean, contrast, sharpness }};
}}

// ========== 后台批改 ==========
async function backgroundGrade(idx, examNum, blob) {{
  if (!ensureSessionActive()) {{
    state.sheets[idx].status = 'error';
    renderStrip();
    return;
  }}
  const formData = new FormData();
  formData.append('image', blob, 'answer_sheet.jpg');
  // 从班级选择器获取 class_id（字符串形式，避免 JS 大整数精度丢失）
  const selectedClassId = document.getElementById('classIdSelect').value;
  formData.append('class_id', selectedClassId);

  try {{
    const res = await fetch(API_BASE + '/teacher/exam/' + EXAM_ID + '/scan-grade?mode=' + GRADING_MODE, {{
      method: 'POST',
      headers: {{ 'Authorization': 'Bearer ' + TOKEN }},
      body: formData
    }});

    if (!res.ok) {{
      const errData = await res.json().catch(() => ({{ detail: '请求失败: ' + res.status }}));
      throw new Error(errData.detail || errData.message || '上传失败');
    }}

    const json = await res.json();
    const data = json.data || json;
    const sname = data.student_name || '未识别';
    const tscore = data.total_score ?? 0;
    const mscore = data.max_score ?? 0;
    // 使用 API 返回的实际识别考号替换占位编号
    const actualExamNum = data.exam_number || examNum;
    console.log('批改完成 | 考号=' + actualExamNum + ' 姓名=' + sname + ' 得分=' + tscore + '/' + mscore);

    state.sheets[idx] = {{
      ...state.sheets[idx],
      examNumber: actualExamNum,
      studentName: sname,
      totalScore: tscore,
      maxScore: mscore,
      correctCount: data.correct_count ?? 0,
      wrongCount: data.wrong_count ?? 0,
      answers: data.answers || [],
      scanDurationMs: data.scan_duration_ms || 0,
      gradingMode: data.grading_mode || GRADING_MODE,
      thumbUrl: genResultThumb({{ studentName: sname, examNumber: actualExamNum, totalScore: tscore, maxScore: mscore }}),
      submissionId: data.submission_id || 0,
      studentMatched: (sname !== '未识别' && sname !== ''),
      status: 'done'
    }};

    renderStrip();
    toast('✅ 第' + examNum + '号 · ' + sname + ' ' + tscore + '/' + mscore);

    if (state.currentDisplayIdx === idx) showSingleResult(idx);
    if (!document.getElementById('resultsModal').classList.contains('hidden')) finish();
  }} catch (e) {{
    state.sheets[idx].status = 'error';
    state.sheets[idx].error = e.message;
    renderStrip();
    toast('❌ 第' + examNum + '号失败: ' + e.message);
    if (state.currentDisplayIdx === idx) showSingleResult(idx);
  }}
  document.getElementById('processingArea').classList.add('hidden');
}}

// ========== 继续拍摄 ==========
function retake() {{
  hideStatus();
  document.getElementById('singleResultCard').classList.add('hidden');
  document.getElementById('photoPreview').style.display = 'none';
  document.getElementById('processingArea').classList.add('hidden');
  cleanupCamera();
  startCamera();
}}

// ========== 单份结果卡片 ==========
function showSingleResult(idx) {{
  const s = state.sheets[idx];
  if (!s) return;
  const card = document.getElementById('singleResultCard');
  card.classList.remove('hidden');

  if (s.status === 'grading') {{
    document.getElementById('singleResultTitle').textContent = '⏳ 批改中...';
    document.getElementById('singleResultContent').innerHTML =
      '<div style="text-align:center;padding:16px">' +
      '<div class="spinner" style="margin:0 auto 8px"></div>' +
      '<p style="color:#2d7d46;font-size:14px">考号 ' + s.examNumber + ' — AI正在识别答题卡...</p></div>';
    document.getElementById('examNumberEdit').classList.add('hidden');
    return;
  }}

  if (s.status === 'error') {{
    document.getElementById('singleResultTitle').textContent = '❌ 批改失败';
    document.getElementById('singleResultContent').innerHTML =
      '<p style="color:#dc2626;text-align:center">考号 ' + s.examNumber + ' 批改失败：' + (s.error || '未知错误') + '</p>';
    document.getElementById('examNumberEdit').classList.add('hidden');
    return;
  }}

  const name = s.studentName || '未识别';
  const total = s.totalScore || 0;
  const max = s.maxScore || 0;
  const wrong = s.wrongCount || 0;
  const passed = total >= max * 0.6;
  const duration = s.scanDurationMs ? (s.scanDurationMs / 1000).toFixed(1) + '秒' : '-';

  document.getElementById('singleResultTitle').textContent = '✅ 批改结果';

  let answersHtml = '';
  if (s.answers && s.answers.length > 0) {{
    answersHtml = '<div class="answer-list">';
    s.answers.forEach(a => {{
      const ok = a.is_correct;
      const qScore = a.score !== undefined && a.score !== null ? a.score : 0;
      const maxScore = a.max_score || 0;
      answersHtml += '<div class="answer-row"><span class="qn">第' + a.question_number + '题</span>' +
        '<span>作答:<strong>' + (a.student_answer || '-') + '</strong> | 正确:<strong>' + (a.correct_answer || '-') + '</strong>' +
        '<span class="' + (ok ? 'correct' : 'wrong') + '">' + (ok ? '✓' : '✗') + '</span></span>' +
        '<span style="font-size:11px;color:#888;margin-left:4px">(' + qScore + '/' + (maxScore || qScore) + '分)</span></div>';
    }});
    answersHtml += '</div>';
  }}

  document.getElementById('singleResultContent').innerHTML =
    '<div style="text-align:center;margin-bottom:12px">' +
    '<p style="font-size:20px;font-weight:700;color:#2d7d46">' + s.studentName + '</p>' +
    '<p style="font-size:12px;color:#888;margin-top:2px">考号 ' + s.examNumber + ' | 耗时 ' + duration + '</p>' +
    '</div>' +
    '<div class="result-grid">' +
    '<div class="result-item"><div class="label">得分</div><div class="value ' + (passed ? 'green' : 'red') + '">' + total + '/' + max + '</div></div>' +
    '<div class="result-item"><div class="label">错题数</div><div class="value ' + (wrong > 0 ? 'red' : 'green') + '">' + wrong + '</div></div>' +
    '<div class="result-item"><div class="label">正确率</div><div class="value green">' + (s.answers && s.answers.length > 0 ? Math.round(s.correctCount / s.answers.length * 100) + '%' : '-') + '</div></div>' +
    '</div>' +
    '<div style="margin-top:12px;font-size:12px;color:#888;text-align:center">▼ 逐题作答详情</div>' + answersHtml;

  // 显示考号修正区
  const editSection = document.getElementById('examNumberEdit');
  const inputEl = document.getElementById('examNumberInput');
  const msgEl = document.getElementById('matchMsg');
  const confirmBtn = document.getElementById('confirmExamBtn');

  // 预填当前考号
  inputEl.value = s.examNumber;
  msgEl.style.display = 'none';
  confirmBtn.disabled = false;

  // 如果没匹配到学生，高亮提示
  if (!s.studentMatched) {{
    editSection.style.borderColor = '#f59e0b';
    editSection.style.background = '#fffdf0';
    msgEl.textContent = '⚠️ 考号未匹配到学生，请手动修正后确认';
    msgEl.className = 'match-msg fail';
    msgEl.style.display = 'block';
  }} else {{
    editSection.style.borderColor = '#d0e6d4';
    editSection.style.background = '#fafcf8';
    msgEl.textContent = '';
    msgEl.style.display = 'none';
  }}
  editSection.classList.remove('hidden');

  card.scrollIntoView({{ behavior: 'smooth' }});
}}

// ========== 汇总弹窗 ==========
function finish() {{
  if (state.sheets.length === 0) {{ showStatus('请先拍摄至少一份答题卡', 'err'); setTimeout(hideStatus, 2000); return; }}
  hideStatus();

  const total = state.sheets.length;
  document.getElementById('resultCount').textContent = total;

  const done = state.sheets.filter(r => r.status === 'done');
  const grading = state.sheets.filter(r => r.status === 'grading');
  const body = document.getElementById('resultModalBody');
  body.innerHTML = '';

  // 统计栏
  if (done.length > 0) {{
    const sumScore = done.reduce((s, r) => s + r.totalScore, 0);
    const avg = Math.round(sumScore / done.length);
    const passed = done.filter(r => r.totalScore >= r.maxScore * 0.6).length;
    const best = Math.max(...done.map(r => r.totalScore));
    const sb = document.createElement('div');
    sb.className = 'summary-bar';
    sb.innerHTML = '<span>平均分：<span class="sm-val" style="color:#2d7d46">' + avg + '</span></span>' +
      '<span>及格：<span class="sm-val" style="color:#2563eb">' + passed + '/' + done.length + '</span></span>' +
      '<span>最高：<span class="sm-val" style="color:#2d7d46">' + best + '</span></span>';
    body.appendChild(sb);
  }}

  // 批改中提示
  if (grading.length > 0) {{
    const hint = document.createElement('div');
    hint.className = 'grading-hint';
    hint.innerHTML = '<span class="mini-spinner"></span>还有 <b>' + grading.length + '</b> 份仍在批改中...';
    body.appendChild(hint);
  }}

  // 列表表头
  const headerRow = document.createElement('div');
  headerRow.className = 'result-header';
  headerRow.innerHTML = '<span class="rh-col exam-num">考号</span>' +
    '<span class="rh-col name">姓名</span>' +
    '<span class="rh-col score">得分</span>' +
    '<span class="rh-col detail">详情</span>';
  body.appendChild(headerRow);

  // 列表
  state.sheets.forEach((s, i) => {{
    const row = document.createElement('div');
    row.className = 'result-list-item';

    if (s.status === 'grading') {{
      row.style.opacity = '0.6';
      row.innerHTML = '<span class="ri-col exam-num" style="color:#aaa">' + s.examNumber + '</span>' +
        '<span class="ri-col name" style="color:#aaa">（批改中...）</span>' +
        '<span class="ri-col score pending">⏳</span>' +
        '<span class="ri-col detail-link" style="color:#ccc">-</span>';
    }} else if (s.status === 'error') {{
      row.style.opacity = '0.6';
      row.innerHTML = '<span class="ri-col exam-num" style="color:#dc2626">' + s.examNumber + '</span>' +
        '<span class="ri-col name" style="color:#dc2626">批改失败</span>' +
        '<span class="ri-col score pending" style="color:#dc2626">✗</span>' +
        '<span class="ri-col detail-link" style="color:#ccc">-</span>';
    }} else {{
      const passed = s.totalScore >= s.maxScore * 0.6;
      const name = s.studentName || '未识别';
      row.onclick = () => openDetail(i);
      row.style.cursor = 'pointer';
      row.innerHTML = '<span class="ri-col exam-num">' + s.examNumber + '</span>' +
        '<span class="ri-col name">' + name + '</span>' +
        '<span class="ri-col score ' + (passed ? 'pass' : 'fail') + '">' + s.totalScore + '/' + s.maxScore + '</span>' +
        '<span class="ri-col detail-link" style="cursor:pointer">详情<span class="arrow">›</span></span>';
    }}
    body.appendChild(row);
  }});

  document.getElementById('resultsModal').classList.remove('hidden');
}}

function closeResultModal() {{
  document.getElementById('resultsModal').classList.add('hidden');
}}

// ========== 详情弹窗 ==========
function openDetail(idx) {{
  document.getElementById('resultsModal').classList.add('hidden');
  document.getElementById('detailModal').classList.remove('hidden');

  const s = state.sheets[idx];
  const passed = s.totalScore >= s.maxScore * 0.6;
  const pct = s.maxScore > 0 ? Math.round(s.correctCount / s.answers.length * 100) : 0;

  let answersHtml = '';
  s.answers.forEach(a => {{
    const ok = a.is_correct;
    const qScore = a.score !== undefined && a.score !== null ? a.score : 0;
    const maxScore = a.max_score || 0;
    answersHtml += '<div class="detail-answer-row ' + (ok ? 'correct' : 'wrong') + '">' +
      '<span class="da-qn">' + a.question_number + '.</span>' +
      '<div class="da-ans"><span class="sa">' + (a.student_answer || '-') + '</span>' +
      '<span class="ca">（标准：' + (a.correct_answer || '-') + '）</span>' +
      '<span style="font-size:11px;color:#888;margin-left:4px">' + qScore + '/' + (maxScore || qScore) + '分</span></div>' +
      '<span class="da-judge ' + (ok ? 'c' : 'w') + '">' + (ok ? '✓' : '✗') + '</span></div>';
  }});

  document.getElementById('detailModalBody').innerHTML =
    '<div class="detail-header"><div class="dh-name">' + s.studentName + '</div>' +
    '<div class="dh-sub">考号 ' + s.examNumber + ' | 耗时 ' + (s.scanDurationMs ? (s.scanDurationMs / 1000).toFixed(1) + 's' : '-') + '</div>' +
    '<div class="dh-stats">' +
    '<div class="ds-item"><div class="ds-val" style="color:' + (passed ? '#2d7d46' : '#dc2626') + '">' + s.totalScore + '/' + s.maxScore + '</div><div class="ds-lbl">得分</div></div>' +
    '<div class="ds-item"><div class="ds-val" style="color:#2563eb">' + s.correctCount + '/' + s.answers.length + '</div><div class="ds-lbl">正确</div></div>' +
    '<div class="ds-item"><div class="ds-val" style="color:' + (s.wrongCount > 0 ? '#dc2626' : '#2d7d46') + '">' + s.wrongCount + '</div><div class="ds-lbl">错误</div></div></div>' +
    '<div class="progress-bar"><div class="pb-fill" style="width:' + pct + '%"></div></div></div>' +
    '<div>' + answersHtml + '</div>';
}}

function closeDetailModal() {{
  document.getElementById('detailModal').classList.add('hidden');
  document.getElementById('resultsModal').classList.remove('hidden');
}}

// ========== 手动确认考号 ==========
function confirmExamNumber() {{
  if (!ensureSessionActive()) return;
  const idx = state.currentDisplayIdx;
  if (idx < 0 || idx >= state.sheets.length) return;
  const sheet = state.sheets[idx];
  if (!sheet.submissionId) {{
    toast('⚠️ 未获取到提交记录ID，无法更新');
    return;
  }}

  const newExamNum = document.getElementById('examNumberInput').value.trim();
  if (!newExamNum) {{
    toast('⚠️ 请输入考号');
    return;
  }}

  const confirmBtn = document.getElementById('confirmExamBtn');
  const msgEl = document.getElementById('matchMsg');
  confirmBtn.disabled = true;
  confirmBtn.textContent = '匹配中...';
  msgEl.style.display = 'none';

  const formData = new FormData();
  formData.append('exam_number', newExamNum);
  formData.append('class_id', document.getElementById('classIdSelect').value);

  fetch(API_BASE + '/teacher/exam/submission/' + sheet.submissionId + '/update-exam-number', {{
    method: 'POST',
    headers: {{ 'Authorization': 'Bearer ' + TOKEN }},
    body: formData
  }})
  .then(res => {{
    if (!res.ok) return res.json().then(e => {{ throw new Error(e.detail || '请求失败'); }});
    return res.json();
  }})
  .then(json => {{
    const data = json.data || json;
    const newSname = data.student_name || '未识别';
    const newSid = data.student_id || 0;
    const newExamNumber = data.exam_number || newExamNum;

    // 更新 sheet 状态
    state.sheets[idx].examNumber = newExamNumber;
    state.sheets[idx].studentName = newSname;
    state.sheets[idx].studentMatched = (newSname !== '未识别' && newSname !== '');
    state.sheets[idx].thumbUrl = genResultThumb({{
      studentName: newSname,
      examNumber: newExamNumber,
      totalScore: sheet.totalScore,
      maxScore: sheet.maxScore
    }});

    renderStrip();
    showSingleResult(idx);

    if (newSid > 0) {{
      toast('✅ 匹配成功: ' + newSname + ' (' + newExamNumber + ')，错题已入库');
    }} else {{
      toast('⚠️ 考号 ' + newExamNumber + ' 仍未匹配到学生');
    }}
  }})
  .catch(e => {{
    toast('❌ 更新失败: ' + e.message);
    confirmBtn.disabled = false;
    confirmBtn.textContent = '确认';
    msgEl.textContent = '❌ ' + e.message;
    msgEl.className = 'match-msg fail';
    msgEl.style.display = 'block';
  }});
}}

// ========== 提交全部 ==========
function submitAll() {{
  const grading = state.sheets.filter(r => r.status === 'grading');
  if (grading.length > 0) {{
    showStatus('还有 ' + grading.length + ' 份仍在批改中，请稍等', 'err');
    setTimeout(hideStatus, 3000);
    return;
  }}
  showStatus('✅ 已提交 ' + state.sheets.length + ' 份成绩到系统！', 'ok');
  document.getElementById('resultsModal').classList.add('hidden');
  toast('🎉 提交成功！共 ' + state.sheets.length + ' 份成绩');
}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


# ========== 学生端：错题本 ==========

@student_router.get("/wrong-book", response_model=ResponseData)
async def student_get_wrong_book(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    knowledge_point: Optional[str] = Query(None, description="按知识点筛选"),
    class_id: Optional[int] = Query(None, description="按班级筛选"),
    db: AsyncSession = Depends(get_db),
    student_id: int = Depends(get_current_user_id),
):
    """学生端：获取个人错题本（分页）"""
    result = await WrongBookService.get_student_wrong_book(
        db, student_id, page, page_size, knowledge_point, class_id,
    )
    return ResponseData(data=result)


@student_router.get("/wrong-book/stats", response_model=ResponseData)
async def student_get_wrong_book_stats(
    class_id: Optional[int] = Query(None, description="按班级筛选"),
    db: AsyncSession = Depends(get_db),
    student_id: int = Depends(get_current_user_id),
):
    """学生端：错题知识点统计"""
    result = await WrongBookService.get_wrong_book_stats(db, student_id, class_id)
    return ResponseData(data=result)

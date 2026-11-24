"""Read existing exam submissions and audit logs for the teacher who owns the exam."""
import re
from pathlib import Path

from sqlalchemy import case, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.paths import SERVER_DIR
from app.models.class_models import ClassStudentInfo, ClassTeacher
from app.models.exam_models import ExamGradingLog, ExamSubmission, TeacherExam
from app.models.scan_models import ExamScanRecord
from app.models.user import User
from app.services.answer_card_photos import find_fixed_card_photo
from app.services.exam_knowledge import _marked_answers
from app.services.exam_result_state import effective_time, final_score, paper_review_settings, result_state
from app.services.exam_service import ExamService


def _serialize(submission: ExamSubmission, name: str | None, exam: TeacherExam, status: str) -> dict:
    return {
        "id": str(submission.id),
        "exam_number": submission.exam_number or "",
        "student_name": name or "",
        "score": (submission.adjusted_score if submission.adjusted_score is not None else submission.score)
        if status != "review" else None,
        "max_score": submission.max_score if submission.max_score is not None else exam.total_score,
        "status": status,
        "source": "manual" if submission.grading_status == "manual_done" else "scan"
        if submission.scan_image_url or submission.scan_record_id or (submission.grading_status or "").startswith("omr_") else "online",
        "updated_at": submission.updated_at or submission.submitted_at or submission.created_at,
    }


async def _owned_exam(db: AsyncSession, exam_id: int, teacher_id: int):
    return await db.scalar(select(TeacherExam).where(TeacherExam.id == exam_id, TeacherExam.teacher_id == teacher_id))


async def list_grading_records(
    db: AsyncSession, exam_id: int, teacher_id: int, *, search: str, status: str, page: int, page_size: int,
    include_scans: bool = False,
) -> dict | None:
    exam = await _owned_exam(db, exam_id, teacher_id)
    if exam is None:
        return None
    name = func.coalesce(func.nullif(User.nickname, ""), User.username, "")
    record_status = result_state(exam)
    is_scan = or_(ExamSubmission.scan_image_url != "", ExamSubmission.scan_record_id.is_not(None),
                  ExamSubmission.grading_status.startswith("omr_", autoescape=True))
    source = case(
        (ExamSubmission.grading_status == "manual_done", "manual"),
        (is_scan, case((ExamSubmission.grade_version > 0, "scan"), else_="legacy_scan") if include_scans else "scan"),
        else_="online",
    )
    submissions = (
        select(
            ExamSubmission.id, func.coalesce(ExamSubmission.exam_number, "").label("exam_number"),
            name.label("student_name"), case((record_status != "review", final_score(ExamSubmission))).label("score"),
            func.coalesce(ExamSubmission.max_score, exam.total_score).label("max_score"),
            record_status.label("status"), source.label("source"),
            effective_time(ExamSubmission).label("updated_at"), literal("submission").label("record_kind"),
        )
        .outerjoin(User, User.id == ExamSubmission.student_id)
        .where(ExamSubmission.exam_id == exam_id)
    )
    if include_scans:
        roster_name = (select(ClassStudentInfo.student_name)
                       .where(ClassStudentInfo.class_id == exam.class_id,
                              ClassStudentInfo.exam_number == ExamScanRecord.exam_number).scalar_subquery()
                       if exam.class_id else literal(""))
        scans = select(
            ExamScanRecord.id, func.coalesce(ExamScanRecord.exam_number, ""),
            func.coalesce(roster_name, ""), literal(None), literal(None),
            case((ExamScanRecord.status == "pending_review", "review"),
                 (ExamScanRecord.status == "failed", "failed"), else_="historical"),
            literal("scan"), func.coalesce(ExamScanRecord.updated_at, ExamScanRecord.created_at), literal("scan"),
        ).where(
            ExamScanRecord.exam_id == exam_id, ExamScanRecord.teacher_id == teacher_id,
            ExamScanRecord.status.in_(("pending_review", "failed", "discarded")),
        )
        if exam.class_id:
            scans = scans.where(select(ClassTeacher.id).where(
                ClassTeacher.class_id == exam.class_id, ClassTeacher.teacher_id == teacher_id,
            ).exists())
        records = union_all(submissions, scans).subquery()
    else:
        records = submissions.subquery()
    filters = []
    if search:
        filters.append(or_(records.c.exam_number.contains(search, autoescape=True),
                           records.c.student_name.contains(search, autoescape=True)))
    if status:
        filters.append(records.c.status == status)

    counts = dict((await db.execute(
        select(records.c.status, func.count()).group_by(records.c.status)
    )).all())
    total = await db.scalar(select(func.count()).select_from(records).where(*filters))
    rows = (await db.execute(select(records).where(*filters)
                             .order_by(records.c.updated_at.desc(), records.c.id.desc(), records.c.record_kind)
                             .offset((page - 1) * page_size).limit(page_size))).mappings()
    return {
        "title": exam.title, "total": total or 0, "confirmed": counts.get("confirmed", 0),
        "pending": counts.get("review", 0),
        "items": [{**row, "id": str(row["id"])} for row in rows],
    }


async def _record(db: AsyncSession, exam_id: int, teacher_id: int, submission_id: int):
    exam = await _owned_exam(db, exam_id, teacher_id)
    if exam is None:
        return None
    name = func.coalesce(func.nullif(User.nickname, ""), User.username)
    row = (await db.execute(
        select(ExamSubmission, name, result_state(exam)).outerjoin(User, User.id == ExamSubmission.student_id)
        .where(ExamSubmission.id == submission_id, ExamSubmission.exam_id == exam_id)
    )).one_or_none()
    return (exam, *row) if row else None


async def _scan(db: AsyncSession, exam: TeacherExam, teacher_id: int, submission: ExamSubmission):
    if not submission.scan_record_id and not submission.scan_image_url:
        return None
    identifier = ExamScanRecord.id == submission.scan_record_id if submission.scan_record_id else (
        ExamScanRecord.scan_image_url == submission.scan_image_url
    )
    scan = await db.scalar(select(ExamScanRecord).where(
        ExamScanRecord.exam_id == exam.id, ExamScanRecord.teacher_id == teacher_id, identifier,
    ).order_by(ExamScanRecord.id.desc()).limit(1))
    if scan and (scan.scan_image_url or "").startswith("fixed:") and exam.class_id and not await db.scalar(
        select(ClassTeacher.id).where(ClassTeacher.class_id == exam.class_id, ClassTeacher.teacher_id == teacher_id).limit(1)
    ):
        return None
    return scan


def _photo_path(exam_id: int, url: str | None) -> Path | None:
    if url and url.startswith("fixed:"):
        return find_fixed_card_photo(exam_id, url)
    prefix = f"/static/scans/{exam_id}/"
    if not url or not url.startswith(prefix):
        return None
    filename = url[len(prefix):]
    if not re.fullmatch(r"\d+_\d+\.(?:jpe?g|png|webp)", filename, re.IGNORECASE):
        return None
    base = SERVER_DIR / "app" / "uploads" / "scans"
    target = (base / str(exam_id) / filename).resolve()
    return target if target.is_relative_to(base.resolve() / str(exam_id)) else None


async def get_grading_photo(db: AsyncSession, exam_id: int, teacher_id: int, submission_id: int) -> Path | None:
    record = await _record(db, exam_id, teacher_id, submission_id)
    if record is None:
        return None
    exam, submission, _, _ = record
    scan = await _scan(db, exam, teacher_id, submission)
    return await run_in_threadpool(_photo_path, exam_id, scan.scan_image_url) if scan else None


async def read_grading_record(db: AsyncSession, exam_id: int, teacher_id: int, submission_id: int) -> dict | None:
    record = await _record(db, exam_id, teacher_id, submission_id)
    if record is None:
        return None
    exam, submission, name, status = record
    scan = await _scan(db, exam, teacher_id, submission)
    questions = ExamService._extract_choice_questions(exam.questions or [])
    positions = {(q["source_index"], q.get("sub_index")): q["question_number"] for q in questions}
    marks = _marked_answers(submission.answers, submission.ai_grade_detail, positions)
    raw = _marked_answers(scan.raw_answers, None, positions) if scan is not None else {}
    grades = {
        (entry.get("question_number") or positions.get((entry.get("index"), entry.get("sub_index")))): entry
        for entry in submission.ai_grade_detail or [] if isinstance(entry, dict)
    }

    def mark(value) -> str:
        if isinstance(value, dict):
            value = value.get("student_answer", value.get("user_answer"))
        return "".join(map(str, value)) if isinstance(value, list) else str(value or "")

    question_rows = []
    for question in questions:
        number = question["question_number"]
        key = str(number)
        selected = mark(marks.get(key))
        question_rows.append({
            "number": number, "marked": selected, "raw": mark(raw[key]) if key in raw else None,
            "invalid_mark": submission.grade_version > 0 and len(selected) > 1,
            "answer": question["correct_answer"], "score": grades.get(number, {}).get("score"), "max_score": question["score"],
        })
    logs = (await db.scalars(select(ExamGradingLog).where(ExamGradingLog.submission_id == submission_id)
                             .order_by(ExamGradingLog.created_at.desc(), ExamGradingLog.id.desc()).limit(100))).all()
    return {
        **_serialize(submission, name, exam, status),
        "title": exam.title,
        "withdrawable_grade_version": submission.grade_version if (
            scan is not None and scan.status == "confirmed" and status == "confirmed"
            and submission.grade_version > 0 and not paper_review_settings(exam).get("closed_at")
        ) else None,
        "has_photo": scan is not None and bool(await run_in_threadpool(_photo_path, exam_id, scan.scan_image_url)),
        "questions": question_rows,
        "history": [_history_item(log) for log in logs],
    }


def _history_item(log: ExamGradingLog) -> dict:
    detail = log.detail if isinstance(log.detail, dict) else {}
    old_score = detail.get("old_score")
    new_score = detail.get("new_score", detail.get("total_score"))
    return {
        "id": str(log.id), "action": log.action, "created_at": log.created_at,
        "reason": detail.get("reason") if isinstance(detail.get("reason"), str) else None,
        "old_score": old_score if isinstance(old_score, (int, float)) else None,
        "new_score": new_score if isinstance(new_score, (int, float)) else None,
    }

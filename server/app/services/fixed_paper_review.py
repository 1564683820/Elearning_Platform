"""Review fixed-card recognition and commit one authoritative grade per exam identity."""
import re
from datetime import datetime, timezone

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.class_models import Class, ClassStudent, ClassStudentInfo, ClassTeacher
from app.models.exam_models import ExamGradingLog, ExamSubmission, TeacherExam
from app.models.scan_models import ExamScanRecord
from app.models.user import User
from app.schemas.fixed_paper_review import (
    PaperGradeRegrade, PaperGradeWithdraw, PaperGradingStateIn, PaperReviewConfirm, PaperReviewDiscard, PaperReviewEdits,
)
from app.services.answer_card_photos import find_fixed_card_photo, photo_reference, save_fixed_card_photo
from app.services.fixed_card_layouts import CardLayout, FixedLayoutError, load_registered_layout, recognize
from app.services.exam_result_state import (
    paper_layout_configured, paper_readiness, paper_review_settings, paper_source_exam_ids, paper_state, result_state,
)
from app.services.private_document_files import PrivateFileError
from app.services.paper_grading import grade_choice_answers
from app.services.wrong_book_service import WrongBookService
from app.utils.revisions import content_revision, is_paper_draft


class PaperReviewError(Exception):
    def __init__(self, status: int, message: str, *, conflict: bool = False):
        super().__init__(message)
        self.status = status
        self.conflict = conflict


class PaperIdentityConflict(PaperReviewError):
    def __init__(self, message: str):
        super().__init__(409, message)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _version(exam: TeacherExam) -> str:
    settings = paper_review_settings(exam)
    return content_revision([exam.class_id, exam.questions, settings.get("layout_id"), settings.get("layout_version")])


def _questions(exam: TeacherExam) -> dict[int, dict]:
    return {question["question_number"]: question for question in exam.questions or []}


def _exam_number(value: str) -> str:
    return value.strip().upper()


async def _exam(db: AsyncSession, exam_id: int, teacher_id: int, *, lock: bool) -> TeacherExam:
    query = select(TeacherExam).where(TeacherExam.id == exam_id, TeacherExam.teacher_id == teacher_id)
    exam = await db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    if exam is None:
        raise PaperReviewError(404, "试卷不存在")
    if exam.class_id and not await db.scalar(select(ClassTeacher.id).where(
        ClassTeacher.class_id == exam.class_id, ClassTeacher.teacher_id == teacher_id,
    ).limit(1)):
        raise PaperReviewError(404, "班级不存在或无权访问")
    return exam


def _check_layout(exam: TeacherExam) -> dict:
    settings = paper_review_settings(exam)
    if not paper_layout_configured(exam, settings):
        raise PaperReviewError(409, "固定答题卡版式未配置")
    if settings.get("closed_at"):
        raise PaperReviewError(409, "批卷已结束，请先开启补批")
    questions = _questions(exam)
    if not questions or any(question.get("answer") not in question.get("options", []) for question in questions.values()):
        raise PaperReviewError(409, "请先保存本卷标准答案")
    return settings


async def _check_start(db: AsyncSession, exam: TeacherExam, *, lock: bool = False) -> dict:
    settings = _check_layout(exam)
    if exam.id not in await paper_source_exam_ids(db, exam.teacher_id, {exam.id}, lock=lock):
        raise PaperReviewError(409, "请先添加试卷原件")
    if not exam.answer_sheet_config["paper_draft"].get("template_id"):
        raise PaperReviewError(409, "请先应用题型分数模板")
    return settings


async def _grading_state(db: AsyncSession, exam: TeacherExam) -> dict:
    if not is_paper_draft(exam.answer_sheet_config):
        raise PaperReviewError(404, "此试卷未使用纸质批改")
    settings = paper_review_settings(exam)
    scans, pending = (await db.execute(select(
        func.count(), func.count(case((ExamScanRecord.status == "pending_review", True))),
    ).select_from(ExamScanRecord).where(
        ExamScanRecord.exam_id == exam.id, ExamScanRecord.teacher_id == exam.teacher_id,
        ExamScanRecord.status.in_(("pending_review", "withdrawn")),
    ))).one()
    confirmed = await db.scalar(select(func.count()).select_from(ExamSubmission).where(
        ExamSubmission.exam_id == exam.id, result_state(exam) == "confirmed",
    ))
    class_name = None
    expected = None
    if exam.class_id:
        class_name = await db.scalar(select(Class.name).where(Class.id == exam.class_id))
        roster_count = await db.scalar(select(func.count()).select_from(ClassStudentInfo).where(ClassStudentInfo.class_id == exam.class_id))
        if roster_count and roster_count >= pending + confirmed:
            expected = roster_count
    sources = await paper_source_exam_ids(db, exam.teacher_id, {exam.id})
    layouts = {}
    blocker = await run_in_threadpool(paper_readiness, exam, has_source=exam.id in sources, layouts=layouts)
    layout = layouts.get((settings.get("layout_id"), settings.get("layout_version")))
    return {
        "state": paper_state(exam, has_activity=bool(confirmed or scans), ready=blocker is None),
        "revision": settings.get("lifecycle_revision", 0), "class_name": class_name, "exam_title": exam.title,
        "layout_configured": paper_layout_configured(exam, settings),
        "recognition_available": blocker is None,
        "recognition_blocker": blocker,
        "capture_aspect_ratio": layout.capture_aspect_ratio if isinstance(layout, CardLayout) and layout.exam_number_cells else None,
        "confirmed": confirmed, "pending": pending, "expected": expected,
        "closed_at": settings.get("closed_at"),
    }


async def read_grading_state(db: AsyncSession, exam_id: int, teacher_id: int) -> dict:
    return await _grading_state(db, await _exam(db, exam_id, teacher_id, lock=False))


async def read_card_reference(db: AsyncSession, exam_id: int, teacher_id: int) -> tuple[bytes, str] | None:
    exam = await _exam(db, exam_id, teacher_id, lock=False)
    if not is_paper_draft(exam.answer_sheet_config):
        raise PaperReviewError(404, "此试卷未使用纸质批改")
    settings = paper_review_settings(exam)
    if not paper_layout_configured(exam, settings):
        return None
    try:
        _, reference = await run_in_threadpool(load_registered_layout, settings["layout_id"], settings["layout_version"])
    except FixedLayoutError:
        return None
    return reference, settings["layout_version"]


async def update_grading_state(db: AsyncSession, exam_id: int, teacher_id: int, data: PaperGradingStateIn) -> dict:
    exam = await _exam(db, exam_id, teacher_id, lock=True)
    current = await _grading_state(db, exam)
    revision = current["revision"]
    if data.revision not in (revision, revision - 1) or (
        data.revision != revision and data.state != current["state"]
    ):
        raise PaperReviewError(409, "批改状态已变化，请刷新后重试")
    if data.state == current["state"]:
        return current
    if data.state == "completed":
        if current["pending"]:
            raise PaperReviewError(409, "还有答题卡待复核，请处理后再结束批卷")
        if not current["confirmed"]:
            raise PaperReviewError(409, "确认至少一份成绩后才能结束批卷")
        closed_at = datetime.now(timezone.utc).isoformat()
    else:
        if current["state"] != "completed":
            raise PaperReviewError(409, "只有已完成的试卷可以开启补批")
        closed_at = None

    exam.answer_sheet_config = {
        **exam.answer_sheet_config,
        "paper_review": {**paper_review_settings(exam), "closed_at": closed_at, "lifecycle_revision": revision + 1},
    }
    await db.flush()
    return {**current, "state": data.state, "closed_at": closed_at, "revision": revision + 1}


async def _review(db: AsyncSession, exam_id: int, teacher_id: int, scan_id: int, *, lock: bool):
    exam = await _exam(db, exam_id, teacher_id, lock=lock)
    query = select(ExamScanRecord).where(
        ExamScanRecord.id == scan_id, ExamScanRecord.exam_id == exam_id, ExamScanRecord.teacher_id == teacher_id,
        ExamScanRecord.status.in_(("pending_review", "confirmed", "replaced", "discarded", "withdrawn", "failed")),
    )
    scan = await db.scalar(query.with_for_update() if lock else query)
    if scan is None:
        raise PaperReviewError(404, "复核记录不存在")
    return exam, scan


async def _scan_request(db: AsyncSession, exam_id: int, teacher_id: int, request_id: str, photo_digest: str | None, *, lock: bool):
    stmt = select(ExamScanRecord).where(
        ExamScanRecord.exam_id == exam_id, ExamScanRecord.teacher_id == teacher_id, ExamScanRecord.request_id == request_id,
    )
    scan = await db.scalar(stmt.with_for_update() if lock else stmt)
    if scan is not None and photo_digest is not None and (
        (scan.grading_result or {}).get("photo_digest") != photo_digest or (scan.grading_result or {}).get("regrade")
    ):
        raise PaperReviewError(409, "同一请求已使用其他照片")
    return scan


async def recognize_photo(
    db: AsyncSession, exam_id: int, teacher_id: int, request_id: str, photo_data: bytes, photo_suffix: str,
) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", request_id):
        raise PaperReviewError(422, "识别请求标识无效")
    try:
        key, digest = await run_in_threadpool(photo_reference, photo_data, photo_suffix)
        exam = await _exam(db, exam_id, teacher_id, lock=False)
        scan = await _scan_request(db, exam_id, teacher_id, request_id, digest, lock=False)
        if scan is None:
            settings = await _check_start(db, exam)
            layout_id, version = settings["layout_id"], settings["layout_version"]
            snapshot = _version(exam)
            options = {number: question["options"] for number, question in _questions(exam).items()}
            result = await run_in_threadpool(recognize, layout_id, version, options, photo_data, key.removeprefix("fixed:"))
            scan = await stage_recognition(
                db, exam_id, teacher_id, request_id=request_id, layout_id=layout_id, layout_version=version,
                photo_data=photo_data, photo_suffix=photo_suffix, exam_number=result.get("exam_number", ""),
                raw_answers=result.get("raw_answers", []), uncertain_questions=result.get("uncertain_questions", []),
                exam_number_length=result.get("exam_number_length"),
                exam_number_cells=result.get("exam_number_cells"),
                exam_number_overflow=result.get("exam_number_overflow", False),
                expected_snapshot=snapshot, failure_state=None if result["state"] == "review" else result["state"],
            )
    except FixedLayoutError as error:
        raise PaperReviewError(409, str(error)) from error
    except PrivateFileError as error:
        raise PaperReviewError(error.status, str(error)) from error
    return {"scan_id": str(scan.id), "state": (scan.grading_result or {}).get("failure_state") or "review"}


async def stage_recognition(
    db: AsyncSession, exam_id: int, teacher_id: int, *, request_id: str, layout_id: str, layout_version: str,
    photo_data: bytes, photo_suffix: str, exam_number: str, raw_answers: list[dict], uncertain_questions: list[int],
    expected_snapshot: str | None = None, failure_state: str | None = None, exam_number_length: int | None = None,
    exam_number_cells: list[dict] | None = None, exam_number_overflow: bool = False,
) -> ExamScanRecord:
    """Stage a trusted scanner result and its validated original image."""
    try:
        photo_key, photo_digest = await run_in_threadpool(photo_reference, photo_data, photo_suffix)
    except PrivateFileError as error:
        raise PaperReviewError(error.status, str(error)) from error
    exam = await _exam(db, exam_id, teacher_id, lock=True)
    previous = await _scan_request(db, exam_id, teacher_id, request_id, photo_digest, lock=True)
    if previous is not None:
        await _save_review_photo(exam_id, previous.scan_image_url, photo_data)
        return previous

    settings = await _check_start(db, exam, lock=True)
    if (layout_id, layout_version) != (settings["layout_id"], settings["layout_version"]):
        raise PaperReviewError(409, "答题卡版式与试卷不一致")
    if expected_snapshot is not None and expected_snapshot != _version(exam):
        raise PaperReviewError(409, "试卷评分配置已变化，请重新识别")
    questions = _questions(exam)
    recognized = _raw_marks(raw_answers)
    marks = {}
    unresolved = set(uncertain_questions) & questions.keys()
    for number, question in questions.items():
        mark = recognized.get(number, "")
        if mark and mark not in question["options"]:
            unresolved.add(number)
        marks[str(number)] = mark
    await _save_review_photo(exam_id, photo_key, photo_data)
    scan = ExamScanRecord(
        exam_id=exam_id, teacher_id=teacher_id, request_id=request_id, status="failed" if failure_state else "pending_review",
        error_message={"retake": "未能识别答题卡版式", "layout_mismatch": "答题卡版式不匹配"}.get(failure_state, ""),
        updated_at=_now(), scan_image_url=photo_key, raw_answers=raw_answers,
        exam_number=_exam_number(exam_number)[:64], recognized_count=sum(bool(mark) for mark in marks.values()),
        grading_result={
            "snapshot": _version(exam), "marks": marks, "unresolved": sorted(unresolved), "photo_digest": photo_digest,
            "failure_state": failure_state, "exam_number_length": exam_number_length,
            "exam_number_cells": exam_number_cells, "exam_number_overflow": exam_number_overflow,
        },
    )
    db.add(scan)
    await db.flush()
    return scan


async def _save_review_photo(exam_id: int, reference: str, data: bytes) -> None:
    try:
        await run_in_threadpool(save_fixed_card_photo, exam_id, reference, data)
    except PrivateFileError as error:
        raise PaperReviewError(error.status, str(error)) from error


async def read_review_photo(db: AsyncSession, exam_id: int, teacher_id: int, scan_id: int):
    _, scan = await _review(db, exam_id, teacher_id, scan_id, lock=False)
    return await run_in_threadpool(find_fixed_card_photo, exam_id, scan.scan_image_url)


def _raw_marks(answers: list[dict] | None) -> dict[int, str]:
    marks = {}
    for item in answers or []:
        if not isinstance(item, dict) or not isinstance(number := item.get("question_number"), int):
            continue
        mark = item.get("student_answer")
        if isinstance(mark, list):
            mark = "".join(str(value) for value in mark)
        marks[number] = str(mark or "").strip().upper()
    return marks


def _check_edit(exam: TeacherExam, scan: ExamScanRecord, revision: str) -> None:
    _check_layout(exam)
    if scan.status != "pending_review":
        raise PaperReviewError(409, "这张答题卡已处理", conflict=True)
    if scan.grading_result["snapshot"] != _version(exam):
        raise PaperReviewError(409, "试卷评分配置已变化，请重新识别")
    if revision != _review_revision(scan):
        raise PaperReviewError(409, "复核内容已更新，请重新打开", conflict=True)


def _review_revision(scan: ExamScanRecord) -> str:
    state = scan.grading_result
    return content_revision([scan.id, scan.exam_number, state["snapshot"], state["marks"], state["unresolved"]])


async def _identity(db: AsyncSession, exam: TeacherExam, number: str):
    if not exam.class_id or not number:
        return None
    students = (await db.execute(select(User.id, ClassStudentInfo.student_name).select_from(ClassStudentInfo)
        .join(ClassStudent, ClassStudent.class_id == ClassStudentInfo.class_id)
        .join(User, (User.id == ClassStudent.student_id) & (User.nickname == ClassStudentInfo.student_name))
        .where(ClassStudentInfo.class_id == exam.class_id, ClassStudentInfo.exam_number == number)
        .limit(2))).all()
    return students[0] if len(students) == 1 else None


async def _previous(
    db: AsyncSession, exam_id: int, number: str, student_id: int | None, *, lock: bool, by_number: bool = False,
):
    if not number:
        return None
    query = select(ExamSubmission).where(ExamSubmission.exam_id == exam_id)
    registered_number = func.upper(func.trim(ExamSubmission.exam_number))
    if by_number:
        identity = registered_number == number
        if student_id is not None:
            identity = or_(identity, ExamSubmission.student_id == student_id)
        query = query.where(identity)
    elif student_id is not None:
        query = query.where(ExamSubmission.student_id == student_id)
    else:
        query = query.where(or_(ExamSubmission.student_id.is_(None), ExamSubmission.student_id == 0),
                            registered_number == number)
    rows = (await db.scalars(query.limit(2).with_for_update() if lock else query.limit(2))).all()
    if by_number:
        if len(rows) > 1:
            raise PaperIdentityConflict("考号或学生存在多份历史成绩，请先核对批改记录")
        if rows:
            previous = rows[0]
            if _exam_number(previous.exam_number or "") != number:
                raise PaperIdentityConflict("该学生已有不同考号的成绩，请先核对批改记录")
            if previous.student_id and previous.student_id != student_id:
                raise PaperIdentityConflict("该考号已有其他学生的成绩，请先核对考号和花名册")
    if len(rows) > 1:
        raise PaperReviewError(409, "同一考号存在多份历史成绩，请先核对记录")
    return rows[0] if rows else None


def _grade(exam: TeacherExam, scan: ExamScanRecord):
    try:
        return grade_choice_answers(exam.questions, scan.grading_result["marks"])
    except ValueError as error:
        raise PaperReviewError(409, str(error)) from error


async def _view(db: AsyncSession, exam: TeacherExam, scan: ExamScanRecord) -> dict:
    state = scan.grading_result
    inactive = scan.status in ("discarded", "withdrawn", "replaced", "failed")
    grades, _, score = _grade(exam, scan) if not inactive else ([], [], 0)
    reason = scan.error_message if scan.status == "failed" else (state.get("discard") or state.get("withdraw") or {}).get("reason")
    receipt = state.get("receipt")
    student = await _identity(db, exam, scan.exam_number) if scan.status not in ("discarded", "failed") else None
    previous = identity_conflict = None
    if scan.status == "pending_review" and (student or not exam.class_id):
        try:
            previous = await _previous(
                db, exam.id, scan.exam_number, student[0] if student else None,
                lock=False, by_number=bool(state.get("exam_number_length")),
            )
        except PaperIdentityConflict as error:
            identity_conflict = str(error)
    questions = _questions(exam)
    raw_marks = _raw_marks(scan.raw_answers)
    class_name = await db.scalar(select(Class.name).where(Class.id == exam.class_id)) if exam.class_id else None
    return {
        "id": str(scan.id), "status": scan.status, "exam_title": exam.title, "revision": _review_revision(scan),
        "exam_number": scan.exam_number, "student_name": student[1] if student else None,
        "exam_number_length": state.get("exam_number_length"),
        "exam_number_cells": state.get("exam_number_cells"),
        "exam_number_overflow": state.get("exam_number_overflow", False),
        "identity_conflict": identity_conflict,
        "class_required": bool(exam.class_id), "class_id": str(exam.class_id) if exam.class_id else None,
        "class_name": class_name,
        "has_photo": bool(await run_in_threadpool(find_fixed_card_photo, exam.id, scan.scan_image_url)),
        "score": receipt["score"] if inactive and receipt else score,
        "max_score": receipt["max_score"] if inactive and receipt else sum(item["max_score"] for item in grades),
        "questions": [{
            "number": item["question_number"], "marked": item["student_answer"], "answer": item["correct_answer"],
            "raw_marked": raw_marks.get(item["question_number"], ""),
            "invalid_mark": bool(item["student_answer"] and
                                 item["student_answer"] not in questions[item["question_number"]]["options"]
                                 and item["question_number"] not in state["unresolved"]),
            "options": questions[item["question_number"]]["options"], "score": item["score"], "max_score": item["max_score"],
            "needs_review": item["question_number"] in state["unresolved"],
        } for item in grades],
        "previous_grade": {"submission_id": str(previous.id), "grade_version": previous.grade_version,
                           "score": _final_score(previous), "max_score": previous.max_score,
                           "withdrawn": previous.grading_status == "paper_withdrawn"} if previous else None,
        "regrade_submission_id": (state.get("regrade") or {}).get("submission_id"),
        "receipt": receipt, "created_at": scan.created_at, "updated_at": scan.updated_at, "reason": reason,
    }


def _final_score(submission: ExamSubmission | None):
    if submission is None:
        return None
    return submission.adjusted_score if submission.adjusted_score is not None else submission.score


async def read_review(db: AsyncSession, exam_id: int, teacher_id: int, scan_id: int) -> dict:
    exam, scan = await _review(db, exam_id, teacher_id, scan_id, lock=False)
    if scan.status == "pending_review" and scan.grading_result["snapshot"] != _version(exam):
        raise PaperReviewError(409, "试卷评分配置已变化，请重新识别")
    return await _view(db, exam, scan)


async def list_reviews(db: AsyncSession, exam_id: int, teacher_id: int, page: int, page_size: int, status: str) -> dict:
    await _exam(db, exam_id, teacher_id, lock=False)
    selection = select(ExamScanRecord).where(
        ExamScanRecord.exam_id == exam_id, ExamScanRecord.teacher_id == teacher_id,
        ExamScanRecord.status == status,
    )
    total = await db.scalar(select(func.count()).select_from(selection.subquery()))
    rows = await db.scalars(selection.order_by(ExamScanRecord.updated_at.desc(), ExamScanRecord.id.desc())
                            .offset((page - 1) * page_size).limit(page_size))
    return {
        "total": total,
        "items": [{"id": str(row.id), "exam_number": row.exam_number, "recognized_count": row.recognized_count,
                   "reason": row.error_message if status == "failed" else (row.grading_result.get("discard") or {}).get("reason"),
                   "updated_at": row.updated_at}
                  for row in rows],
    }


def _reason(value: str) -> str:
    reason = value.strip()
    if not reason:
        raise PaperReviewError(422, "请输入操作原因")
    return reason


async def discard_review(db: AsyncSession, exam_id: int, teacher_id: int, scan_id: int, data: PaperReviewDiscard) -> dict:
    _, scan = await _review(db, exam_id, teacher_id, scan_id, lock=True)
    reason = _reason(data.reason)
    change = {"revision": data.revision, "reason": reason}
    if scan.status == "discarded" and scan.grading_result.get("discard") == change:
        return {"discarded": True}
    if scan.status != "pending_review" or data.revision != _review_revision(scan):
        raise PaperReviewError(409, "复核记录已变化，请重新打开")
    scan.status = "discarded"
    scan.updated_at = _now()
    scan.grading_result = {**scan.grading_result, "discard": change}
    await db.flush()
    return {"discarded": True}


async def prepare_regrade(db: AsyncSession, exam_id: int, teacher_id: int, submission_id: int, data: PaperGradeRegrade) -> dict:
    exam = await _exam(db, exam_id, teacher_id, lock=True)
    target = {"submission_id": str(submission_id), "grade_version": data.grade_version}
    replay = await _scan_request(db, exam_id, teacher_id, data.request_id, None, lock=True)
    if replay is not None:
        if (replay.grading_result or {}).get("regrade") != target:
            raise PaperReviewError(409, "同一请求已用于其他答题卡")
        return {"scan_id": str(replay.id), "state": "review"}

    submission = await db.scalar(select(ExamSubmission).where(
        ExamSubmission.id == submission_id, ExamSubmission.exam_id == exam_id,
        ExamSubmission.grade_version > 0,
    ).with_for_update())
    if submission is None or submission.scan_record_id is None:
        raise PaperReviewError(404, "固定卡成绩不存在")
    _, source = await _review(db, exam_id, teacher_id, submission.scan_record_id, lock=True)
    if (source.status != "confirmed" or submission.grading_status != "teacher_reviewed"
            or submission.grade_version != data.grade_version):
        raise PaperReviewError(409, "成绩已变化，请重新打开")
    await _check_start(db, exam, lock=True)
    snapshot = _version(exam)
    if source.grading_result["snapshot"] != snapshot:
        raise PaperReviewError(409, "试卷评分配置已变化，请重新识别")
    if not await run_in_threadpool(find_fixed_card_photo, exam_id, source.scan_image_url):
        raise PaperReviewError(404, "答题卡照片不存在")

    pending = await db.scalar(select(ExamScanRecord.id).where(
        ExamScanRecord.exam_id == exam_id, ExamScanRecord.teacher_id == teacher_id,
        ExamScanRecord.status == "pending_review",
        ExamScanRecord.grading_result["regrade"]["submission_id"].as_string() == target["submission_id"],
        ExamScanRecord.grading_result["regrade"]["grade_version"].as_integer() == data.grade_version,
    ).limit(1).with_for_update())
    if pending is not None:
        return {"scan_id": str(pending), "state": "review"}

    review = ExamScanRecord(
        exam_id=exam_id, teacher_id=teacher_id, request_id=data.request_id, status="pending_review",
        updated_at=_now(), scan_image_url=source.scan_image_url, raw_answers=source.raw_answers,
        exam_number=source.exam_number, recognized_count=source.recognized_count, grading_result={
            "snapshot": snapshot, "marks": source.grading_result["marks"], "unresolved": [],
            "photo_digest": source.grading_result["photo_digest"], "regrade": target,
            "exam_number_length": source.grading_result.get("exam_number_length"),
            "exam_number_cells": source.grading_result.get("exam_number_cells"),
            "exam_number_overflow": source.grading_result.get("exam_number_overflow", False),
        },
    )
    db.add(review)
    await db.flush()
    return {"scan_id": str(review.id), "state": "review"}


async def withdraw_grade(db: AsyncSession, exam_id: int, teacher_id: int, submission_id: int, data: PaperGradeWithdraw) -> dict:
    exam = await _exam(db, exam_id, teacher_id, lock=True)
    submission = await db.scalar(select(ExamSubmission).where(
        ExamSubmission.id == submission_id, ExamSubmission.exam_id == exam_id,
        ExamSubmission.grade_version > 0,
    ).with_for_update())
    if submission is None or not submission.scan_record_id:
        raise PaperReviewError(404, "固定卡成绩不存在")
    _, scan = await _review(db, exam_id, teacher_id, submission.scan_record_id, lock=True)
    reason = _reason(data.reason)
    change = {"grade_version": data.grade_version, "reason": reason}
    if submission.grading_status == "paper_withdrawn" and scan.grading_result.get("withdraw") == change:
        return {"grade_version": submission.grade_version}
    if (scan.status != "confirmed" or submission.grading_status != "teacher_reviewed"
            or submission.grade_version != data.grade_version):
        raise PaperReviewError(409, "成绩已变化，请重新打开")
    _check_layout(exam)

    submission.grading_status = "paper_withdrawn"
    submission.grade_version += 1
    scan.status = "withdrawn"
    scan.updated_at = _now()
    scan.grading_result = {**scan.grading_result, "withdraw": change}
    await WrongBookService.remove_from_submission(db, submission.id)
    db.add(ExamGradingLog(
        submission_id=submission.id, grader_type="teacher", grader_id=teacher_id, action="paper_withdraw",
        detail={"old_score": _final_score(submission), "scan_id": str(scan.id),
                "grade_version": submission.grade_version, "reason": reason},
    ))
    await db.flush()
    return {"grade_version": submission.grade_version}


async def edit_review(db: AsyncSession, exam_id: int, teacher_id: int, scan_id: int, data: PaperReviewEdits) -> dict:
    exam, scan = await _review(db, exam_id, teacher_id, scan_id, lock=True)
    _check_edit(exam, scan, data.revision)
    questions = _questions(exam)
    marks = dict(scan.grading_result["marks"])
    length = scan.grading_result.get("exam_number_length")
    number = data.exam_number if length else _exam_number(data.exam_number)
    if scan.grading_result.get("regrade") and number != scan.exam_number:
        raise PaperReviewError(422, "重批须沿用原成绩考号")
    if length and not re.fullmatch(rf"[0-9]{{0,{length}}}", number):
        raise PaperReviewError(422, f"考号只能填写最多 {length} 位数字")
    if not length and number and not re.fullmatch(r"[0-9A-Z-]{1,64}", number):
        raise PaperReviewError(422, "考号只能包含字母、数字和连字符")
    if data.answers.keys() & data.invalid_answers.keys():
        raise PaperReviewError(422, "同一题只能保存一种核对结果")
    for index, mark in data.answers.items():
        mark = mark.strip().upper()
        if index not in questions or (mark and mark not in questions[index]["options"]):
            raise PaperReviewError(422, f"第 {index} 题选项无效")
        marks[str(index)] = mark
    for index, selected in data.invalid_answers.items():
        options = questions.get(index, {}).get("options", [])
        normalized = {option.strip().upper() for option in selected}
        if len(normalized) != len(selected) or not normalized.issubset(options):
            raise PaperReviewError(422, f"第 {index} 题请选择至少两个不同的有效选项")
        marks[str(index)] = "".join(option for option in options if option in normalized)
    unresolved = sorted(set(scan.grading_result["unresolved"]) - data.answers.keys() - data.invalid_answers.keys())
    scan.exam_number = number
    scan.grading_result = {**scan.grading_result, "marks": marks, "unresolved": unresolved}
    scan.updated_at = _now()
    await db.flush()
    return await _view(db, exam, scan)


async def confirm_review(db: AsyncSession, exam_id: int, teacher_id: int, scan_id: int, data: PaperReviewConfirm) -> dict:
    exam, scan = await _review(db, exam_id, teacher_id, scan_id, lock=True)
    state = scan.grading_result
    confirmation = [data.revision, data.previous_submission_id, data.previous_grade_version]
    if scan.status in ("confirmed", "replaced") and state.get("confirmation") == confirmation:
        return state["receipt"]
    _check_edit(exam, scan, data.revision)
    length = state.get("exam_number_length")
    pattern = rf"[0-9]{{{length}}}" if length else r"[0-9A-Z-]{1,64}"
    if not re.fullmatch(pattern, scan.exam_number or ""):
        if length:
            raise PaperReviewError(422, f"请核对完整的 {length} 位考号")
        raise PaperReviewError(422, "请先核对考号")
    if state["unresolved"]:
        raise PaperReviewError(422, "还有待核对的选项")
    student = await _identity(db, exam, scan.exam_number)
    if exam.class_id and student is None:
        raise PaperReviewError(422, "未匹配到学生，请核对考号")
    student_id = student[0] if student else None
    submission = await _previous(db, exam_id, scan.exam_number, student_id, lock=True, by_number=bool(length))
    previous_id = submission.id if submission else None
    previous_version = submission.grade_version if submission else None
    target = state.get("regrade")
    if target and (str(previous_id) != target["submission_id"] or submission.grading_status != "teacher_reviewed"):
        raise PaperReviewError(409, "原成绩已不可重批，请重新打开批改记录")
    if (previous_id, previous_version) != (data.previous_submission_id, data.previous_grade_version):
        raise PaperReviewError(409, "已有成绩已变化，请重新核对后确认", conflict=True)

    answers, detail, score = _grade(exam, scan)
    maximum = sum(item["max_score"] for item in answers)
    old_score = _final_score(submission)
    old_scan_id = submission.scan_record_id if submission else None
    old_answers = submission.answers if submission and not previous_version else None
    submission = submission or ExamSubmission(exam_id=exam_id, student_id=student_id)
    submission.student_id = student_id
    submission.exam_number = scan.exam_number
    submission.answers = answers
    submission.ai_grade_detail = detail
    submission.score = score
    submission.max_score = maximum
    submission.teacher_adjustment = None
    submission.adjusted_score = None
    submission.grading_status = "teacher_reviewed"
    submission.scan_record_id = scan.id
    submission.scan_image_url = ""
    submission.wrong_count = sum(not item["is_correct"] for item in answers)
    submission.submitted_at = _now()
    submission.grade_version = (previous_version or 0) + 1
    db.add(submission)
    await db.flush()
    if student_id is not None:
        await WrongBookService.save_from_submission(db, submission)

    if old_scan_id:
        old_scan = await db.scalar(select(ExamScanRecord).where(
            ExamScanRecord.id == old_scan_id, ExamScanRecord.exam_id == exam_id,
            ExamScanRecord.teacher_id == teacher_id, ExamScanRecord.status == "confirmed",
        ).with_for_update())
        if old_scan:
            old_scan.status = "replaced"
    receipt = {"submission_id": str(submission.id), "grade_version": submission.grade_version, "score": score, "max_score": maximum}
    scan.matched_student_id = student_id or 0
    scan.status = "confirmed"
    scan.grading_result = {**state, "receipt": receipt, "confirmation": confirmation}
    db.add(ExamGradingLog(
        submission_id=submission.id, grader_type="teacher", grader_id=teacher_id,
        action="paper_regrade" if previous_id else "paper_confirm",
        detail={"old_score": old_score, "new_score": score, "old_scan_id": str(old_scan_id) if old_scan_id else None,
                "scan_id": str(scan.id), "grade_version": submission.grade_version, "old_answers": old_answers},
    ))
    await db.flush()
    return receipt

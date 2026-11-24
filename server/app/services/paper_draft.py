"""Save and resume paper-grading drafts using the existing exam and template tables."""
from copy import deepcopy

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.class_models import ClassTeacher
from app.models.exam_models import AnswerSheetTemplate, ExamSubmission, TeacherExam
from app.models.scan_models import ExamScanRecord
from app.models.user import User
from app.schemas.paper_draft import PaperDraftCreateIn, PaperDraftIn, PaperDraftOut
from app.services.exam_service import ExamService
from app.services.exam_result_state import paper_readiness, paper_review_settings, paper_source_exam_ids
from app.services.fixed_card_layouts import default_binding, layout_available
from app.utils.revisions import content_revision, is_paper_draft, template_revision


class PaperDraftError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _metadata(exam: TeacherExam) -> dict:
    config = exam.answer_sheet_config or {}
    return config.get("paper_draft", {}) if isinstance(config, dict) else {}


def _revision(exam: TeacherExam) -> str:
    return content_revision([exam.title, exam.description or "", exam.class_id, exam.questions, _metadata(exam)])


def _valid_score(score: object) -> bool:
    return type(score) in (int, float) and 1 <= score <= 100 and score == int(score)


def _new_questions(rows: list[dict] | None) -> list[dict]:
    if not isinstance(rows, list) or not rows or len(rows) > 300:
        raise PaperDraftError(422, "该模板题量超出纸质批改范围")
    questions = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise PaperDraftError(422, "模板包含无法读取的题目")
        kind = row.get("type", row.get("question_type", "single"))
        score = row.get("score")
        options = row.get("options")
        count = row.get("option_count", len(options) if isinstance(options, list) else 0)
        if kind not in {"choice", "single", "single_choice"} or row.get("is_multi_choice"):
            raise PaperDraftError(422, "纸质批改模板仅支持单选题")
        if not _valid_score(score) or type(count) is not int or not 2 <= count <= 8:
            raise PaperDraftError(422, f"第 {number} 题的选项数量或分值不符合纸质批改范围")
        questions.append({
            "type": "choice", "question_number": number, "score": int(score), "option_count": count,
            "options": [chr(65 + index) for index in range(count)], "answer": "",
        })
    return questions


def supports_paper_template(rows: list[dict] | None) -> bool:
    try:
        _new_questions(rows)
    except PaperDraftError:
        return False
    return True


def _editable_questions(exam: TeacherExam) -> list[dict]:
    questions = exam.questions or []
    result = []
    seen = set()
    for position, question in enumerate(questions, 1):
        if not isinstance(question, dict) or question.get("type", "choice") not in {"choice", "single", "single_choice"}:
            raise PaperDraftError(409, "此草稿包含其他题型，请从网页端原编辑入口修改")
        number = question.get("question_number", position)
        if type(number) is not int or number < 1 or number in seen:
            raise PaperDraftError(409, "草稿的卡面题号无效或重复")
        seen.add(number)
        count = question.get("option_count") or len(question.get("options") or [])
        score = question.get("score")
        answer = question.get("answer") or ""
        if type(count) is not int or not 2 <= count <= 8 or not _valid_score(score):
            raise PaperDraftError(409, "草稿题型与纸质批改不兼容，请从网页端原编辑入口修改")
        options = [chr(65 + index) for index in range(count)]
        if question.get("is_multi_choice") or not isinstance(answer, str) or (answer and answer not in options):
            raise PaperDraftError(409, "此草稿包含其他题型，请从网页端原编辑入口修改")
        result.append({"question_number": number, "score": int(score), "options": options, "answer": answer})
    return result


async def _draft(db: AsyncSession, teacher_id: int, exam_id: int, *, lock: bool = False) -> TeacherExam:
    stmt = select(TeacherExam).where(TeacherExam.id == exam_id, TeacherExam.teacher_id == teacher_id)
    exam = await db.scalar(stmt.with_for_update() if lock else stmt)
    if not exam:
        raise PaperDraftError(404, "试卷不存在")
    config = exam.answer_sheet_config or {}
    if exam.status != "draft" or (config and not _metadata(exam)):
        raise PaperDraftError(409, "此试卷已不处于可编辑的纸质草稿状态")
    if lock:
        submission_exists = await db.scalar(select(ExamSubmission.id).where(ExamSubmission.exam_id == exam.id).limit(1))
        scan_exists = await db.scalar(select(ExamScanRecord.id).where(
            ExamScanRecord.exam_id == exam.id, or_(ExamScanRecord.status.is_(None), ExamScanRecord.status.not_in(("discarded", "failed"))),
        ).limit(1))
        if submission_exists is not None or scan_exists is not None:
            raise PaperDraftError(409, "试卷已有批改记录，无法修改评分配置和班级")
    return exam


async def _out(db: AsyncSession, exam: TeacherExam, *, created_revision: str | None = None) -> PaperDraftOut:
    metadata = _metadata(exam)
    template_id = metadata.get("template_id")
    name = metadata.get("template_name")
    if name is None and template_id:
        name = await db.scalar(select(AnswerSheetTemplate.name).where(
            AnswerSheetTemplate.id == template_id, AnswerSheetTemplate.teacher_id == exam.teacher_id,
        ))
    binding = paper_review_settings(exam)
    layout_id, version = binding.get("layout_id"), binding.get("layout_version")
    configured = bool(await run_in_threadpool(layout_available, layout_id, version)) if layout_id and version else bool(
        await run_in_threadpool(default_binding),
    )
    return PaperDraftOut(
        id=str(exam.id), title=exam.title, description=exam.description or "", class_id=str(exam.class_id or 0),
        template_id=str(template_id) if template_id else None, template_revision=metadata.get("template_revision"),
        template_name=name, questions=_editable_questions(exam), revision=_revision(exam), paper_draft=bool(metadata),
        layout_configured=configured, created_revision=created_revision,
    )


async def read_paper_draft(db: AsyncSession, teacher_id: int, exam_id: int) -> PaperDraftOut:
    return await _out(db, await _draft(db, teacher_id, exam_id))


async def prepare_paper_copy(
    db: AsyncSession, teacher_id: int, exam_id: int, request_id: str,
) -> tuple[TeacherExam, bool]:
    source = await db.scalar(select(TeacherExam).where(
        TeacherExam.id == exam_id, TeacherExam.teacher_id == teacher_id, TeacherExam.status != "archived",
    ).with_for_update())
    if source is None or not is_paper_draft(source.answer_sheet_config):
        raise PaperDraftError(404, "纸质试卷不存在")
    if source.class_id and not await db.scalar(select(ClassTeacher.id).where(
        ClassTeacher.class_id == source.class_id, ClassTeacher.teacher_id == teacher_id,
    ).limit(1)):
        raise PaperDraftError(404, "班级不存在或无权访问")
    existing = await db.scalar(select(TeacherExam).where(
        TeacherExam.teacher_id == teacher_id, TeacherExam.source_exam_ids == str(source.id),
        TeacherExam.answer_sheet_config["paper_copy"]["request_id"].as_string() == request_id,
    ).with_for_update())
    if existing is not None:
        return existing, False

    _editable_questions(source)
    config = {
        "paper_draft": deepcopy(_metadata(source)),
        "paper_copy": {"request_id": request_id},
    }
    layout = paper_review_settings(source)
    if layout.get("mode") == "provided_fixed" and layout.get("layout_id") and layout.get("layout_version"):
        config["paper_review"] = {key: layout[key] for key in ("mode", "layout_id", "layout_version")}
    suffix = "（副本）"
    draft = TeacherExam(
        title=source.title[:256 - len(suffix)] + suffix, description=source.description,
        teacher_id=teacher_id, class_id=source.class_id, questions=deepcopy(source.questions),
        total_score=source.total_score, difficulty=source.difficulty, duration_minutes=source.duration_minutes,
        knowledge_points=source.knowledge_points, grade=source.grade, stage_category=source.stage_category,
        source_exam_ids=str(source.id), answer_sheet_config=config, status="draft",
    )
    db.add(draft)
    await db.flush()
    return draft, True


async def create_paper_draft(db: AsyncSession, teacher_id: int, data: PaperDraftCreateIn) -> PaperDraftOut:
    if data.request_id is None:
        return await save_paper_draft(db, teacher_id, data)

    # Serialize creates for a teacher before looking up the durable receipt.
    owner = await db.scalar(select(User.id).where(User.id == teacher_id).with_for_update())
    if owner is None:
        raise PaperDraftError(404, "教师不存在")
    excluded = {"request_id", "revision"}
    if data.question_numbers is None:
        excluded.add("question_numbers")  # Preserve receipts created before explicit card numbering.
    fingerprint = content_revision(data.model_dump(mode="json", exclude=excluded))
    existing = await db.scalar(select(TeacherExam).where(
        TeacherExam.teacher_id == teacher_id,
        TeacherExam.answer_sheet_config["paper_create"]["request_id"].as_string() == data.request_id,
    ).limit(1).with_for_update())
    if existing is not None:
        receipt = existing.answer_sheet_config["paper_create"]
        if receipt["fingerprint"] != fingerprint:
            raise PaperDraftError(409, "草稿创建请求的内容已变化")
        if existing.status != "draft":
            raise PaperDraftError(409, "此创建请求对应的草稿已不可编辑")
        return await _out(db, existing, created_revision=receipt["revision"])

    return await save_paper_draft(db, teacher_id, data, creation={
        "request_id": data.request_id, "fingerprint": fingerprint,
    })


async def save_paper_draft(
    db: AsyncSession, teacher_id: int, data: PaperDraftIn, exam_id: int | None = None,
    *, creation: dict[str, str] | None = None,
) -> PaperDraftOut:
    title = data.title.strip()
    if not title:
        raise PaperDraftError(422, "请输入试卷名称")
    if data.class_id and not await db.scalar(select(ClassTeacher.id).where(
        ClassTeacher.class_id == data.class_id, ClassTeacher.teacher_id == teacher_id,
    ).limit(1)):
        raise PaperDraftError(404, "班级不存在或无权访问")

    exam = await _draft(db, teacher_id, exam_id, lock=True) if exam_id is not None else None
    if exam is not None and data.revision != _revision(exam):
        raise PaperDraftError(409, "草稿已在其他页面更新，请重新打开")
    if data.finalize and exam is None:
        raise PaperDraftError(409, "请先添加试卷原件")
    metadata = _metadata(exam) if exam else {}
    if data.template_id is not None:
        template = await db.scalar(select(AnswerSheetTemplate).where(
            AnswerSheetTemplate.id == data.template_id, AnswerSheetTemplate.teacher_id == teacher_id,
        ).with_for_update())
        if not template:
            raise PaperDraftError(404, "评分模板不存在")
        if template.archived_at is not None:
            raise PaperDraftError(409, "评分模板已停用，请重新选择")
        revision = template_revision(template)
        if data.template_revision != revision:
            raise PaperDraftError(409, "评分模板已更新，请重新选择")
        questions = _new_questions(template.choice_questions)
        metadata = {"template_id": str(template.id), "template_revision": revision, "template_name": template.name}
    elif exam:
        kinds = _editable_questions(exam)
        questions = [{**original, "question_number": kind["question_number"]}
                     for original, kind in zip(exam.questions or [], kinds)]
    else:
        questions = []
    if data.question_numbers is not None:
        numbers = data.question_numbers
        if len(numbers) != len(questions) or len(set(numbers)) != len(numbers):
            raise PaperDraftError(422, "每道题必须绑定一个不同的卡面题号")
        for question, number in zip(questions, numbers):
            question["question_number"] = number
    valid_questions = {question["question_number"]: question for question in questions}
    for number, answer in data.answers.items():
        question = valid_questions.get(number)
        count = (question.get("option_count") or len(question.get("options") or [])) if question else 0
        if not question or (answer and answer not in [chr(65 + index) for index in range(count)]):
            raise PaperDraftError(422, f"第 {number} 题的答案无效")
        question["answer"] = answer

    points = sum(int(question["score"]) for question in questions)
    if exam is None:
        exam = await ExamService.save_exam(db, teacher_id, title, questions, points, 2, 60, [], class_id=data.class_id)
        if data.question_numbers is not None:
            exam.questions = [{**row, "question_number": number}
                              for row, number in zip(exam.questions, data.question_numbers)]
    else:
        exam.title = title
        exam.class_id = data.class_id
        exam.questions = questions
        exam.total_score = points
    exam.description = data.description.strip()
    config = {**(exam.answer_sheet_config or {}), "paper_draft": metadata or {"created": True}}
    current_binding = config.get("paper_review") or {}
    if not current_binding.get("layout_id") and (binding := default_binding()):
        config["paper_review"] = {**current_binding, **binding}
    exam.answer_sheet_config = config
    created_revision = None
    if creation:
        created_revision = _revision(exam)
        config["paper_create"] = {**creation, "revision": created_revision}
    if data.finalize:
        source_ids = await paper_source_exam_ids(db, teacher_id, {exam.id}, lock=True)
        blocker = await run_in_threadpool(paper_readiness, exam, has_source=exam.id in source_ids)
        if blocker:
            raise PaperDraftError(409, blocker)
    await db.flush()
    return await _out(db, exam, created_revision=created_revision)

"""Shared read-side selection of current, reviewable and historical exam results."""
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.exam_models import ExamSubmission
from app.models.stats import UserDocument
from app.services.document_scope import EXAM_SOURCE
from app.services.fixed_card_layouts import CardLayout, FixedLayoutError, check_question_mapping, load_registered_layout
from app.utils.revisions import is_paper_draft


FINAL_GRADES = ("ai_done", "teacher_reviewed", "manual_done", "omr_done", "omr_ext", "omr_ext4", "omr_real")


def paper_review_settings(exam) -> dict:
    config = exam.answer_sheet_config
    if isinstance(config, dict) and isinstance(config.get("paper_review"), dict):
        return config["paper_review"]
    return {}


def paper_layout_configured(exam, settings: dict) -> bool:
    return bool(is_paper_draft(exam.answer_sheet_config) and settings.get("mode") == "provided_fixed"
                and settings.get("layout_id") and settings.get("layout_version"))


async def paper_source_exam_ids(
    db: AsyncSession, teacher_id: int, exam_ids: set[int], *, lock: bool = False,
) -> set[int]:
    if not exam_ids:
        return set()
    stmt = select(UserDocument.exam_id).where(
        UserDocument.exam_id.in_(exam_ids), UserDocument.user_id == teacher_id,
        UserDocument.doc_category == EXAM_SOURCE,
    )
    return set(await db.scalars(stmt.with_for_update() if lock else stmt.distinct()))


def paper_readiness(
    exam, *, has_source: bool, layouts: dict[tuple[str, str], CardLayout | str] | None = None,
) -> str | None:
    settings = paper_review_settings(exam)
    metadata = (exam.answer_sheet_config or {}).get("paper_draft", {})
    if not has_source:
        return "请先添加试卷原件"
    if not isinstance(metadata, dict) or not metadata.get("template_id"):
        return "请先应用题型分数模板"
    questions = exam.questions or []
    if not questions or any(not isinstance(item, dict) or item.get("answer") not in (item.get("options") or [])
                            for item in questions):
        return "请先保存本卷标准答案"
    if not paper_layout_configured(exam, settings):
        return "固定答题卡版式未配置"
    key = (settings["layout_id"], settings["layout_version"])
    cache = layouts if layouts is not None else {}
    if key not in cache:
        try:
            cache[key] = load_registered_layout(*key)[0]
        except FixedLayoutError as error:
            cache[key] = str(error)
    layout = cache[key]
    if isinstance(layout, str):
        return layout
    try:
        check_question_mapping(layout, {item["question_number"]: item["options"] for item in questions})
    except KeyError:
        return "本卷缺少题号配置"
    except FixedLayoutError as error:
        return str(error)
    return None


def paper_state(exam, *, has_activity: bool, ready: bool) -> str:
    settings = paper_review_settings(exam)
    if settings.get("closed_at"):
        return "completed"
    if has_activity or settings.get("lifecycle_revision"):
        return "grading"
    return "ready" if ready else "draft"


def effective_time(entry):
    return func.coalesce(entry.updated_at, entry.submitted_at, entry.created_at)


def final_score(entry):
    return func.coalesce(entry.adjusted_score, entry.score)


def result_state(exam):
    submission = ExamSubmission
    unmatched = or_(submission.student_id.is_(None), submission.student_id == 0)
    has_identity = or_(
        submission.student_id > 0,
        and_(exam.class_id == 0, unmatched, func.trim(submission.exam_number) != ""),
    )
    final = and_(submission.grading_status.in_(FINAL_GRADES), final_score(submission).is_not(None), has_identity)
    other = aliased(ExamSubmission)
    newer = select(other.id).where(
        other.exam_id == submission.exam_id,
        or_(other.student_id.is_(None), other.student_id == 0),
        func.trim(other.exam_number) == func.trim(submission.exam_number),
        other.grading_status.in_(FINAL_GRADES),
        final_score(other).is_not(None),
        or_(effective_time(other) > effective_time(submission),
            and_(effective_time(other) == effective_time(submission), other.id > submission.id)),
    ).correlate(submission).exists()
    return case(
        (or_(submission.grading_status == "paper_withdrawn", and_(final, unmatched, newer)), "historical"),
        (final, "confirmed"),
        else_="review",
    )

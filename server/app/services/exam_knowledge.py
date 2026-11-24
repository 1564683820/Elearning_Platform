"""Ground teaching-assistant answers in confirmed, teacher-owned exam results."""
import hashlib
import logging
import os
import re
import unicodedata
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exam_models import ExamSubmission, TeacherExam
from app.services.embedding_service import EmbeddingService
from app.services.exam_knowledge_dates import ExamKnowledgePeriod, is_exam_period_followup, parse_exam_period
from app.services.exam_result_state import effective_time, final_score, result_state
from app.services.exam_service import ExamService
from app.services.exam_source_text import read_original_questions


logger = logging.getLogger(__name__)
EXAM_QUESTION_SOURCE = "exam_question"
QUESTION_NUMBER = re.compile(r"(?:第\s*(\d{1,3})\s*[小大]?题|题号\s*[:：]?\s*(\d{1,3}))")
GRADING_WORDS = re.compile(r"批改|判分|成绩|正确率|答对|选错|错选|错在|错题|失分|哪些题.*错|均分|平均分|答卷")
RECENT = re.compile(r"最近|近期")
FOLLOW_UP = re.compile(r"(?:这|那)[份张道一]?题|(?:这|那)(?:[两几]?[份张套])?卷|刚才|继续")
COMPARISON = re.compile(r"对比|比较|相比|分别|哪[份张套]卷.*(?:高|低|难|好)")
SINGLE_QUESTION_FOLLOW_UP = re.compile(r"(?:这|那)(?:道|一[道]?)题")
OriginalQuestions = dict[int, tuple[str, dict[str, str]]]
TitleMention = tuple[int, int, list[TeacherExam]]


def _normalized(value: str) -> str:
    return re.sub(r"[\s·・:：\-—]", "", unicodedata.normalize("NFKC", value)).casefold()


def _aliases(exam: TeacherExam) -> set[str]:
    return {_normalized(name) for name in (exam.title, re.split(r"[·・]", exam.title)[-1])}


def _title_mentions(exams: list[TeacherExam], text: str) -> list[TitleMention]:
    spans: dict[tuple[int, int], list[TeacherExam]] = {}
    for exam in exams:
        for alias in _aliases(exam):
            if len(alias) >= 3:
                for match in re.finditer(re.escape(alias), text):
                    spans.setdefault(match.span(), []).append(exam)
    selected: list[TitleMention] = []
    for start, end in sorted(spans, key=lambda span: (span[0] - span[1], span[0])):
        if all(end <= left or start >= right for left, right, _ in selected):
            selected.append((start, end, spans[(start, end)]))
    return sorted(selected, key=lambda mention: mention[0])


def _mentioned_exams(mentions: list[TitleMention]) -> list[TeacherExam]:
    return list({exam.id: exam for _, _, matches in mentions for exam in matches}.values())


def _question_numbers(text: str) -> set[int]:
    return {int(match[1] or match[2]) for match in QUESTION_NUMBER.finditer(text)}


def _comparison_targets(
    mentions: list[TitleMention], text: str, overrides: set[int],
) -> list[tuple[TeacherExam, int | None]]:
    if any(len(matches) != 1 for _, _, matches in mentions):
        return []
    numbers = overrides or _question_numbers(text)
    if len(numbers) <= 1:
        number = next(iter(numbers), None)
        return [(exam, number) for exam in _mentioned_exams(mentions)]
    if overrides:
        return []
    targets = []
    for i, (_, end, matches) in enumerate(mentions):
        stop = mentions[i + 1][0] if i + 1 < len(mentions) else len(text)
        local_numbers = _question_numbers(text[end:stop])
        if len(local_numbers) != 1:
            return []
        targets.append((matches[0], next(iter(local_numbers))))
    if numbers != {number for _, number in targets}:
        return []
    return targets


def _questions(exam: TeacherExam) -> dict:
    raw = exam.questions or []
    return {
        item["question_number"]: item
        for item in ExamService._extract_choice_questions(raw, title=exam.title)
        if item["question_type"] == "single_choice" and item["correct_answer"] in item["options"]
    }


def _original_question(question: dict, original: OriginalQuestions | None) -> tuple[str, dict[str, str]]:
    item = (original or {}).get(question["question_number"])
    return item if item and set(item[1]) == set(question["options"]) else ("", {})


def question_stem(exam: TeacherExam, question: dict, original: OriginalQuestions | None = None) -> str:
    raw = exam.questions[question["source_index"]]
    nested = raw.get("sub_questions") or raw.get("questions") or []
    sub_index = question.get("sub_index")
    source = nested[sub_index] if sub_index is not None and sub_index < len(nested) else raw
    stem = str(source.get("stem") or source.get("question") or "").strip()
    return stem[:400] if stem else _original_question(question, original)[0]


def exam_question_chunks(exam: TeacherExam, original: OriginalQuestions | None = None) -> list[dict]:
    if exam.status == "archived":
        return []
    chunks = []
    for number, question in _questions(exam).items():
        stem = question_stem(exam, question, original)
        if not stem:
            continue
        content = f"{exam.title} 第 {number} 题\n{stem}"
        version = hashlib.sha256(f"{exam.class_id or 0}\n{content}".encode()).hexdigest()[:24]
        chunks.append({
            "source_type": EXAM_QUESTION_SOURCE, "source_id": exam.id, "user_id": exam.teacher_id,
            "class_id": exam.class_id or 0, "content": content, "chunk_order": number,
            "chunk_id": f"exam-question:{exam.id}:{number}:{version}", "level": 3,
        })
    return chunks


def _literal_matches(
    exams: list[TeacherExam], query: str, number: int | None, originals: dict[int, OriginalQuestions],
) -> list[tuple[TeacherExam, int]]:
    text = _normalized(query)
    matches = []
    for exam in exams:
        for key, item in _questions(exam).items():
            if number is not None and key != number:
                continue
            stem = _normalized(question_stem(exam, item, originals.get(exam.id))).strip("？?。！!")
            if len(stem) >= 6 and stem in text:
                matches.append((exam, key))
    return matches


def _retrieval_hint(query: str) -> str:
    hint = QUESTION_NUMBER.sub("", query)
    hint = GRADING_WORDS.sub("", hint)
    return re.sub(r"[\s？?的：:。,，]|请问|帮我|这道题|那道题|是多少|怎么样", "", hint)


async def _vector_matches(
    db: AsyncSession, exams: list[TeacherExam], teacher_id: int, class_id: int | None,
    query: str, number: int | None, originals: dict[int, OriginalQuestions],
) -> list[tuple[TeacherExam, int]]:
    if not exams or os.environ.get("EXAM_QUESTION_VECTOR_SEARCH") != "1" or len(_retrieval_hint(query)) < 8:
        return []
    scoped = {exam.id: exam for exam in exams}
    filters = f"user_id == {teacher_id}"
    if class_id is not None:
        filters += f" and class_id == {class_id}"
    if len(scoped) <= 30:
        filters += " and source_id in [" + ",".join(str(i) for i in scoped) + "]"
    try:
        hits = await EmbeddingService.hybrid_search(
            db, query[:650], EmbeddingService.TEACHER_DOCUMENTS, top_k=6,
            user_id=teacher_id, source_type=EXAM_QUESTION_SOURCE, extra_filter=filters,
            output_fields=["source_id", "source_type", "user_id", "class_id", "chunk_id", "chunk_order"],
        )
    except Exception:
        logger.warning("试卷题目语义检索不可用，继续使用现有定位条件", exc_info=True)
        return []
    candidates = {}
    for hit in hits:
        exam = scoped.get(hit.get("source_id"))
        if (not exam or hit.get("source_type") != EXAM_QUESTION_SOURCE
                or hit.get("user_id") != teacher_id or hit.get("class_id") != (exam.class_id or 0)):
            continue
        key = hit.get("chunk_order")
        if number is not None and key != number:
            continue
        if any(chunk["chunk_id"] == hit.get("chunk_id") and chunk["chunk_order"] == key
               for chunk in exam_question_chunks(exam, originals.get(exam.id))):
            candidates.setdefault((exam.id, key), (exam, key))
    return list(candidates.values())


def _marked_answers(answers: object, detail: object, numbers_by_position: dict) -> dict:
    if isinstance(answers, dict):
        marks = {str(key): value for key, value in answers.items()}
    else:
        marks = {}
        for value in answers if isinstance(answers, list) else []:
            if isinstance(value, dict) and value.get("question_number") is not None:
                marks[str(value["question_number"])] = value.get("student_answer", value.get("user_answer"))
            elif isinstance(value, dict) and (number := numbers_by_position.get((value.get("question_index"), None))) is not None:
                marks[str(number)] = value.get("answer")
    for value in detail if isinstance(detail, list) else []:
        if not isinstance(value, dict):
            continue
        number = value.get("question_number") or numbers_by_position.get((value.get("index"), value.get("sub_index")))
        if number is not None and "user_answer" in value:
            marks[str(number)] = value["user_answer"]
        for sub_index, sub in enumerate(value.get("sub_details") or []):
            number = numbers_by_position.get((value.get("index"), sub_index))
            if number is not None and isinstance(sub, dict) and "user_answer" in sub:
                marks[str(number)] = sub["user_answer"]
    return marks


async def _aggregate(
    db: AsyncSession, exam: TeacherExam, number: int | None, original: OriginalQuestions | None,
    period: ExamKnowledgePeriod | None = None,
) -> dict:
    questions = _questions(exam)
    if number is not None:
        questions = {number: questions[number]} if number in questions else {}
    counters = {key: Counter() for key in questions}
    numbers_by_position = {
        (question["source_index"], question.get("sub_index")): number
        for number, question in questions.items()
    }
    score = final_score(ExamSubmission)
    stmt = (
        select(score, ExamSubmission.answers, ExamSubmission.ai_grade_detail, effective_time(ExamSubmission))
        .where(
            ExamSubmission.exam_id == exam.id,
            result_state(exam) == "confirmed",
        )
        .order_by(effective_time(ExamSubmission).desc(), ExamSubmission.id.desc())
        .execution_options(yield_per=200)
    )
    if period:
        stmt = stmt.where(*_period_conditions(period))
    count = total = 0
    updated_at = None
    rows = await db.stream(stmt)
    try:
        async for points, answers, detail, updated in rows:
            count += 1
            total += points
            updated_at = updated_at or updated
            marks = _marked_answers(answers, detail, numbers_by_position)
            for key, question in questions.items():
                marked = marks.get(str(key))
                if isinstance(marked, dict):
                    marked = marked.get("student_answer", marked.get("user_answer"))
                if isinstance(marked, list):
                    marked = "".join(map(str, marked))
                label = ExamService._extract_option_letter(str(marked or ""))
                counters[key][label if label in question["options"] else "无效填涂" if label else "空白"] += 1
    finally:
        await rows.close()

    result = []
    for key, question in questions.items():
        correct = counters[key][question["correct_answer"]]
        counters[key].setdefault(question["correct_answer"], 0)
        stem = question_stem(exam, question, original)
        original_stem, option_text = _original_question(question, original)
        result.append({
            "number": key, "stem": stem, "answer": question["correct_answer"],
            "option_text": option_text if stem == original_stem else {},
            "correct": correct, "distribution": dict(counters[key]),
        })
    result.sort(key=lambda item: (item["correct"], item["number"]))
    return {
        "id": str(exam.id), "title": exam.title, "count": count,
        "average": round(total / count, 1) if count else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "questions": result[:12], **(period.fields() if period else {}),
    }


def _owned_exams(teacher_id: int):
    return select(TeacherExam).where(TeacherExam.teacher_id == teacher_id, TeacherExam.status != "archived")


def _confirmed_exam_rows(teacher_id: int, class_id: int | None = None):
    rows = _owned_exams(teacher_id).with_only_columns(TeacherExam.id).join(
        ExamSubmission, ExamSubmission.exam_id == TeacherExam.id,
    ).where(result_state(TeacherExam) == "confirmed")
    return rows.where(TeacherExam.class_id == class_id) if class_id is not None else rows


async def has_exam_knowledge(db: AsyncSession, teacher_id: int) -> bool:
    return await db.scalar(_confirmed_exam_rows(teacher_id).limit(1)) is not None


def _period_conditions(period: ExamKnowledgePeriod):
    start, end = period.bounds
    timestamp = effective_time(ExamSubmission)
    return timestamp >= start, timestamp < end


async def _active_exams(
    db: AsyncSession, teacher_id: int, class_id: int | None, period: ExamKnowledgePeriod | None,
) -> list[TeacherExam]:
    rows = _confirmed_exam_rows(teacher_id, class_id)
    if period:
        rows = rows.where(*_period_conditions(period))
    activity = rows.add_columns(
        func.max(effective_time(ExamSubmission)).label("latest"),
    ).group_by(TeacherExam.id).subquery()
    selection = select(TeacherExam).join(activity, activity.c.id == TeacherExam.id).order_by(
        activity.c.latest.desc(), TeacherExam.id.desc(),
    )
    return list(await db.scalars(selection if period else selection.limit(5)))


async def read_exam_knowledge(
    db: AsyncSession, teacher_id: int, exam_id: int, number: int | None, period: ExamKnowledgePeriod | None = None,
) -> dict | None:
    exam = await db.scalar(_owned_exams(teacher_id).where(TeacherExam.id == exam_id))
    if exam is None:
        return None
    originals = await read_original_questions(db, [exam])
    return await _aggregate(db, exam, number, originals.get(exam.id), period)


def _scope_text(text: str, exams: list[TeacherExam]) -> str:
    for exam in exams:
        name = unicodedata.normalize("NFKC", exam.title)
        for alias in (name, re.split(r"[·・]", name)[-1].strip()):
            if alias:
                text = re.sub(r"\s*".join(map(re.escape, alias.split())), "", text)
    return text


async def find_exam_knowledge(
    db: AsyncSession, teacher_id: int, class_id: int | None, question: str, recent: list[dict],
) -> dict | None:
    normalized = unicodedata.normalize("NFKC", question)
    qno = QUESTION_NUMBER.search(normalized)
    follow_up = FOLLOW_UP.search(normalized)
    has_signal = bool(GRADING_WORDS.search(normalized) or qno or follow_up)
    last = recent[-1] if recent else {}
    prior = recent[:-1] if last.get("role") == "user" and last.get("content") == question else recent
    previous_turn = next((message for message in reversed(prior) if message["role"] == "user"), {})
    previous = unicodedata.normalize("NFKC", previous_turn.get("content", ""))
    previous_number = QUESTION_NUMBER.search(previous)
    previous_is_grading = bool(previous_number or GRADING_WORDS.search(previous))
    if not has_signal and not previous_is_grading:
        return None
    stmt = _owned_exams(teacher_id)
    if class_id is not None:
        stmt = stmt.where(TeacherExam.class_id == class_id)
    exams = list(await db.scalars(stmt.order_by(TeacherExam.created_at.desc(), TeacherExam.id.desc())))
    current_title_query = title_query = _normalized(question)
    mentions = _title_mentions(exams, title_query)
    candidates = _mentioned_exams(mentions)
    search_query = question
    inherited_turn = None
    exact_title = title_query.strip("。.!！?？《》「」『』")
    exact_exams = [exam for exam in candidates if exact_title in _aliases(exam)]
    if exact_exams and previous_number:
        candidates = exact_exams
        qno = previous_number
        inherited_turn = previous_turn
    elif not has_signal and not exact_exams:
        if not is_exam_period_followup(normalized):
            return None
        title_query = _normalized(previous)
        mentions = _title_mentions(exams, title_query)
        candidates = _mentioned_exams(mentions)
        qno = previous_number
        search_query = previous
    elif not candidates and follow_up:
        for message in reversed(prior):
            if message["role"] != "user":
                continue
            context_query = _normalized(message["content"])
            context_mentions = _title_mentions(exams, context_query)
            candidates = _mentioned_exams(context_mentions)
            if search_query == question and GRADING_WORDS.search(message["content"]):
                search_query = message["content"]
                inherited_turn = message
            if candidates:
                title_query, mentions = context_query, context_mentions
                qno = qno or QUESTION_NUMBER.search(unicodedata.normalize("NFKC", message["content"]))
                inherited_turn = message
                break
    if not candidates and not qno and not GRADING_WORDS.search(search_query):
        return None
    number = int(qno[1] or qno[2]) if qno else None
    if not candidates and re.search(r"《[^》]+》|[「『][^」』]+[」』]", normalized):
        return {"exams": [], "clarification": "未找到指定试卷，请确认卷名或当前班级。"}
    try:
        period = parse_exam_period(_scope_text(normalized, candidates))
        if not period and inherited_turn:
            context = unicodedata.normalize("NFKC", inherited_turn["content"])
            period = parse_exam_period(_scope_text(context, candidates), at=inherited_turn.get("created_at"))
    except (ValueError, OverflowError):
        return {"exams": [], "clarification": "请确认批改日期，提供单一日期或一段连续的日期范围。",
                "invalid_period": True}
    if len(candidates) > 1 and COMPARISON.search(title_query):
        inherited_titles = title_query != current_title_query
        if inherited_titles and SINGLE_QUESTION_FOLLOW_UP.search(normalized):
            return {"exams": [], "clarification": "请确认要查询哪份试卷的哪道题。",
                    "titles": [exam.title for exam in candidates[:5]]}
        overrides = _question_numbers(normalized) if inherited_titles else set()
        targets = _comparison_targets(mentions, title_query, overrides)
        if not targets:
            return {"exams": [], "clarification": "请确认要对比的试卷，并说明每份试卷对应的题号。"}
        originals = await read_original_questions(db, candidates)
        return {"exams": [await _aggregate(db, exam, key, originals.get(exam.id), period) for exam, key in targets]}
    inferred_scope = not candidates and (period is not None or bool(RECENT.search(search_query)))
    if inferred_scope:
        exams = await _active_exams(db, teacher_id, class_id, period)
    originals = await read_original_questions(db, candidates or exams)
    if not candidates or number is None:
        scoped = candidates or exams
        hits = _literal_matches(scoped, search_query, number, originals)
        if not hits and (period or not inferred_scope):
            hits = await _vector_matches(db, scoped, teacher_id, class_id, search_query, number, originals)
        if len(hits) == 1:
            exam, key = hits[0]
            return {"exams": [await _aggregate(db, exam, key, originals.get(exam.id), period)]}
        if len(hits) > 1:
            return {"exams": [], "clarification": "匹配到多道题，请确认卷名或题号。",
                    "titles": [f"{exam.title} · 第 {key} 题" for exam, key in hits[:5]]}
    if not candidates:
        if number is not None:
            candidates = [exam for exam in exams if number in _questions(exam)]
        elif inferred_scope:
            scope = f"{period.start} 至 {period.end} 的有效成绩（北京时间）" if period else "最近最多 5 份已批试卷"
            return {"exams": [await _aggregate(db, exam, None, originals.get(exam.id), period) for exam in exams],
                    "scope": scope}
        else:
            return {"exams": [], "clarification": "请提供要查询的试卷名称。"}
    if len(candidates) > 1:
        return {"exams": [], "clarification": "有多份符合条件的试卷，请确认卷名。", "titles": [e.title for e in candidates[:5]]}
    return {"exams": [await _aggregate(db, exam, number, originals.get(exam.id), period) for exam in candidates]}

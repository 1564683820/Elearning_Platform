"""Exam Agent — Teacher-side AI exam paper generation

Responsibilities:
- AI exam paper generation (with RAG knowledge base references)
- Robust JSON parsing
- Prompt template management

Related services (CRUD + DB in original):
- app.services.exam_service.ExamService
"""

import json
import re
from sqlalchemy.ext.asyncio import AsyncSession
from agent.agents.base import BaseAgent
from app.services.ai_service import AIService
from app.services.embedding_service import EmbeddingService


QUESTION_TYPES = {
    "choice": "\u9009\u62e9\u9898",
    "fill": "\u586b\u7a7a\u9898",
    "translation": "\u7ffb\u8bd1\u9898",
    "reading": "\u9605\u8bfb\u7406\u89e3",
    "writing": "\u5199\u4f5c\u9898",
    "listening": "\u542c\u529b\u9898",
}


class ExamAgent(BaseAgent):
    """Exam generation Agent — AI-powered exam paper creation"""

    @staticmethod
    async def _fetch_rag_references(
        db: AsyncSession,
        teacher_id: int,
        stage_category: str,
        title: str = "",
        knowledge_points: list[str] | None = None,
        question_types: list[str] | None = None,
        top_k: int = 5,
    ) -> list[str]:
        """Retrieve reference questions from knowledge base"""
        kps = knowledge_points or []
        qt_labels = [QUESTION_TYPES.get(t, t) for t in (question_types or [])]
        query_parts = [title, "English exam paper test questions"]
        if kps:
            query_parts.extend(kps)
        if qt_labels:
            query_parts.extend(qt_labels)
        query = " ".join(p for p in query_parts if p)

        results = await EmbeddingService.hybrid_search(
            db, query, EmbeddingService.TEACHER_DOCUMENTS,
            top_k=top_k, user_id=teacher_id,
            stage=stage_category,
            source_type="doc_exam",
        )
        return [r["content"] for r in results]

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Robust JSON extraction from AI response text."""
        cleaned = text.strip()

        # 1) Try code blocks
        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("json"):
                    content = stripped[4:].strip()
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        cleaned = content
                        break
            else:
                for part in parts:
                    stripped = part.strip()
                    if stripped and not stripped.startswith("```"):
                        try:
                            return json.loads(stripped)
                        except json.JSONDecodeError:
                            cleaned = stripped
                            break

        # 2) Try direct parse
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 3) Find matching braces for outer JSON
        def _find_matching_brace(text: str, open_idx: int) -> int | None:
            depth = 0
            in_str = False
            esc = False
            for j in range(open_idx, len(text)):
                c = text[j]
                if esc:
                    esc = False
                    continue
                if c == "\\":
                    esc = True
                    continue
                if c == '"' and not esc:
                    in_str = not in_str
                    continue
                if in_str:
                    continue
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        return j
            return None

        # Find questions key
        questions_key_pos = cleaned.find('"questions"')
        if questions_key_pos != -1:
            outer_start = cleaned.rfind("{", 0, questions_key_pos)
            if outer_start != -1:
                outer_end = _find_matching_brace(cleaned, outer_start)
                if outer_end is not None:
                    outer_text = cleaned[outer_start:outer_end + 1]
                    try:
                        return json.loads(outer_text)
                    except json.JSONDecodeError:
                        pass

        # 4) Try all brace-matched candidates
        candidates = []
        pos = 0
        while True:
            obj_start = cleaned.find("{", pos)
            if obj_start == -1:
                break
            obj_end = _find_matching_brace(cleaned, obj_start)
            if obj_end is not None:
                candidates.append(cleaned[obj_start:obj_end + 1])
                pos = obj_end + 1
            else:
                pos = obj_start + 1

        candidates.sort(key=len, reverse=True)
        for candidate in candidates:
            try:
                result = json.loads(candidate)
                if isinstance(result, dict) and "questions" in result:
                    return result
            except json.JSONDecodeError:
                continue

        for candidate in candidates:
            try:
                result = json.loads(candidate)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue

        raise json.JSONDecodeError("Cannot extract valid JSON", cleaned[:200], 0)

    @staticmethod
    async def generate_exam_content(
        db: AsyncSession,
        teacher_id: int,
        title: str,
        knowledge_points: list[str],
        question_types: list[str],
        difficulty: int,
        duration_minutes: int,
        question_type_counts: dict | None = None,
        grade: str = "",
        stage_category: str = "",
        use_rag: bool = True,
        additional_references: str = "",
    ) -> dict:
        """AI generates exam content, returns parsed JSON"""
        type_names = [QUESTION_TYPES.get(t, t) for t in question_types]
        difficulty_names = {1: "\u7b80\u5355", 2: "\u4e2d\u7b49", 3: "\u56f0\u96be"}

        if question_type_counts:
            type_desc = "\u3001".join(
                "{}{}\u7bc7".format(QUESTION_TYPES.get(t, t), c)
                if t == "reading" else "{}{}\u9053".format(QUESTION_TYPES.get(t, t), c)
                for t, c in question_type_counts.items() if c > 0
            )
        else:
            type_desc = "\u3001".join(type_names)

        grade_desc = "\u9002\u7528\u5e74\u7ea7\uff1a{}\n".format(grade) if grade else ""
        is_senior = (stage_category == "senior")

        major_count = 0
        if question_type_counts:
            major_count = sum(c for c in question_type_counts.values() if c > 0)
        reading_sub_qty = "3-4" if is_senior else "5"

        # RAG references
        ref_texts = []
        if use_rag:
            ref_texts = await ExamAgent._fetch_rag_references(
                db, teacher_id, stage_category,
                title=title, knowledge_points=knowledge_points,
                question_types=question_types,
            )

        system_prompt = (
            "You are a professional English exam paper generator AI.\n"
            "Requirements:\n"
            "1. Question difficulty should be appropriate for the given level and grade\n"
            "2. Output exactly the specified number of questions, no more, no less\n"
            "3. Each question must include a question type label\n"
            "4. Each question must include a standard answer and detailed explanation\n"
            "5. Multiple choice questions must have 4 options (A/B/C/D)\n"
            "6. Writing questions must include scoring criteria\n"
            "7. Quotation marks in stems must be escaped with backslash"
        )

        if ref_texts:
            ref_text = "\n\n".join(
                "[Reference {}]\n{}".format(i + 1, r[:500])
                for i, r in enumerate(ref_texts)
            )
            system_prompt += "\n\nBelow are reference questions from your previously uploaded exams; use them as reference for difficulty and format:\n" + ref_text

        if additional_references:
            system_prompt += "\n\nSupplementary reference:\n" + additional_references[:3000]

        system_prompt += "\n\nPlease strictly follow the JSON format with a 'questions' array, total_score field."

        user_prompt = (
            "Generate an English exam paper:\n"
            "Title: {title}\n"
            "{grade_desc}"
            "Knowledge points: {kps}\n"
            "Types and counts: {type_desc}\n"
            "Difficulty: {difficulty}\n"
            "Duration: {duration} minutes\n\n"
            "Total major questions: {major_count} (each reading passage counts as 1 major question), total score: 100.\n"
            "Each reading passage must contain {reading_sub_qty} sub-questions."
        ).format(
            title=title,
            grade_desc=grade_desc,
            kps=", ".join(knowledge_points),
            type_desc=type_desc,
            difficulty=difficulty_names.get(difficulty, "\u4e2d\u7b49"),
            duration=duration_minutes,
            major_count=major_count,
            reading_sub_qty=reading_sub_qty,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = await AIService.chat_completion(
            db, messages, teacher_id,
            timeout_seconds=180.0,
            max_tokens=8192,
        )

        return ExamAgent._extract_json(response)

    async def run(self, **kwargs) -> dict:
        """Execute exam generation."""
        return await self.generate_exam_content(**kwargs)

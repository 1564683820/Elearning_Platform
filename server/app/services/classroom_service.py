"""课堂实时互动服务

管理课堂中的实时互动操作：
- 投票 (vote)
- 答题 (quiz)
- 弹幕 (danmaku)
- 提问 (question)
- 页面同步追踪

当前实现基于 REST API（可通过轮询实现实时效果），
后续可升级为 WebSocket 以获得更好的实时性。
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from datetime import datetime
from app.models.ppt_models import ClassroomSession


class ClassroomService:
    """课堂实时互动服务"""

    @staticmethod
    async def _get_session(db: AsyncSession, session_id: int, teacher_id: int) -> ClassroomSession | None:
        """获取并验证课堂会话"""
        result = await db.execute(
            select(ClassroomSession).where(
                ClassroomSession.id == session_id,
                ClassroomSession.teacher_id == teacher_id,
            )
        )
        session = result.scalar_one_or_none()
        return session

    @staticmethod
    async def _append_interaction(
        db: AsyncSession, session: ClassroomSession,
        key: str, item: dict,
    ) -> dict:
        """向互动数据中追加一条记录"""
        data = dict(session.interaction_data or {})
        if key not in data or not isinstance(data[key], list):
            data[key] = []
        data[key].append(item)
        session.interaction_data = data
        flag_modified(session, "interaction_data")
        await db.commit()
        return item

    # ========== 投票 ==========

    @staticmethod
    async def create_vote(
        db: AsyncSession, teacher_id: int,
        session_id: int, question: str, options: list[str],
    ) -> dict | None:
        """创建课堂投票"""
        session = await ClassroomService._get_session(db, session_id, teacher_id)
        if not session:
            return None

        vote = {
            "id": f"vote_{len(session.interaction_data.get('votes', []))}_{datetime.now().timestamp()}",
            "type": "vote",
            "question": question,
            "options": [{"label": opt, "count": 0} for opt in options],
            "created_at": datetime.now().isoformat(),
            "status": "active",
        }
        return await ClassroomService._append_interaction(db, session, "votes", vote)

    @staticmethod
    async def submit_vote(
        db: AsyncSession, session_id: int,
        vote_id: str, option_index: int,
    ) -> dict | None:
        """提交投票"""
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return None

        data = dict(session.interaction_data or {})
        votes = data.get("votes", [])
        for vote in votes:
            if vote.get("id") == vote_id and vote.get("status") == "active":
                if 0 <= option_index < len(vote.get("options", [])):
                    vote["options"][option_index]["count"] += 1
                    session.interaction_data = data
                    flag_modified(session, "interaction_data")
                    await db.commit()
                    return vote
        return None

    @staticmethod
    async def get_vote_results(
        db: AsyncSession, session_id: int, vote_id: str,
    ) -> dict | None:
        """获取投票结果"""
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return None

        data = session.interaction_data or {}
        for vote in data.get("votes", []):
            if vote.get("id") == vote_id:
                return vote
        return None

    @staticmethod
    async def close_vote(
        db: AsyncSession, teacher_id: int,
        session_id: int, vote_id: str,
    ) -> dict | None:
        """关闭投票"""
        session = await ClassroomService._get_session(db, session_id, teacher_id)
        if not session:
            return None

        data = dict(session.interaction_data or {})
        for vote in data.get("votes", []):
            if vote.get("id") == vote_id:
                vote["status"] = "closed"
                session.interaction_data = data
                flag_modified(session, "interaction_data")
                await db.commit()
                return vote
        return None

    # ========== 课堂答题 ==========

    @staticmethod
    async def create_quiz(
        db: AsyncSession, teacher_id: int,
        session_id: int, question: str,
        options: list[str], correct_answer: int,
    ) -> dict | None:
        """创建课堂答题"""
        session = await ClassroomService._get_session(db, session_id, teacher_id)
        if not session:
            return None

        quiz = {
            "id": f"quiz_{len(session.interaction_data.get('quizzes', []))}_{datetime.now().timestamp()}",
            "type": "quiz",
            "question": question,
            "options": options,
            "correct_answer": correct_answer,
            "answers": [],
            "created_at": datetime.now().isoformat(),
        }
        return await ClassroomService._append_interaction(db, session, "quizzes", quiz)

    @staticmethod
    async def submit_quiz_answer(
        db: AsyncSession, session_id: int,
        quiz_id: str, selected: int, user_id: int | None = None,
    ) -> dict | None:
        """提交答题答案（通过 user_id 防重复）"""
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return None

        data = dict(session.interaction_data or {})
        for quiz in data.get("quizzes", []):
            if quiz.get("id") == quiz_id:
                # 防重复：检查该学生是否已经答过
                if user_id is not None:
                    for ans in quiz.get("answers", []):
                        if ans.get("student_id") == user_id:
                            return {"duplicate": True}

                is_correct = selected == quiz.get("correct_answer")
                answer = {
                    "selected": selected,
                    "is_correct": is_correct,
                    "timestamp": datetime.now().isoformat(),
                }
                if user_id is not None:
                    answer["student_id"] = user_id
                quiz["answers"].append(answer)
                session.interaction_data = data
                flag_modified(session, "interaction_data")
                await db.commit()
                return {"is_correct": is_correct, "correct_answer": quiz["correct_answer"]}
        return None

    @staticmethod
    async def get_quiz_results(
        db: AsyncSession, session_id: int, quiz_id: str,
    ) -> dict | None:
        """获取答题统计（不暴露正确答案）"""
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return None

        data = session.interaction_data or {}
        for quiz in data.get("quizzes", []):
            if quiz.get("id") == quiz_id:
                answers = quiz.get("answers", [])
                # 统计每个选项被选次数
                option_counts = [0] * len(quiz.get("options", []))
                correct_count = 0
                for a in answers:
                    sel = a.get("selected", -1)
                    if 0 <= sel < len(option_counts):
                        option_counts[sel] += 1
                    if a.get("is_correct"):
                        correct_count += 1
                return {
                    "question": quiz["question"],
                    "options": quiz["options"],
                    "option_counts": option_counts,
                    "total_answers": len(answers),
                    "correct_count": correct_count,
                }
        return None

    # ========== 弹幕 ==========

    @staticmethod
    async def send_danmaku(
        db: AsyncSession, session_id: int,
        content: str, student_name: str = "",
    ) -> dict | None:
        """发送弹幕"""
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return None

        danmaku = {
            "id": f"dan_{datetime.now().timestamp()}",
            "student_name": student_name,
            "content": content[:200],  # 限制弹幕长度
            "timestamp": datetime.now().isoformat(),
        }
        return await ClassroomService._append_interaction(db, session, "danmaku", danmaku)

    @staticmethod
    async def get_danmaku(
        db: AsyncSession, session_id: int,
        since_id: str = "", limit: int = 50,
    ) -> list:
        """获取弹幕列表（支持增量拉取）"""
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return []

        data = session.interaction_data or {}
        danmaku_list = data.get("danmaku", [])

        if since_id:
            filtered = []
            found = False
            for d in reversed(danmaku_list):
                if d.get("id") == since_id:
                    found = True
                    break
                filtered.insert(0, d)
            return filtered[:limit]
        return danmaku_list[-limit:]

    # ========== 提问 ==========

    @staticmethod
    async def ask_question(
        db: AsyncSession, session_id: int,
        question: str, student_name: str = "",
    ) -> dict | None:
        """学生提问"""
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return None

        q = {
            "id": f"q_{datetime.now().timestamp()}",
            "student_name": student_name,
            "question": question,
            "status": "pending",  # pending/answered/dismissed
            "answer": "",
            "timestamp": datetime.now().isoformat(),
        }
        return await ClassroomService._append_interaction(db, session, "questions", q)

    @staticmethod
    async def answer_question(
        db: AsyncSession, teacher_id: int,
        session_id: int, question_id: str, answer: str,
    ) -> dict | None:
        """教师回答问题"""
        session = await ClassroomService._get_session(db, session_id, teacher_id)
        if not session:
            return None

        data = dict(session.interaction_data or {})
        for q in data.get("questions", []):
            if q.get("id") == question_id:
                q["status"] = "answered"
                q["answer"] = answer
                session.interaction_data = data
                flag_modified(session, "interaction_data")
                await db.commit()
                return q
        return None

    # ========== 页面同步 ==========

    @staticmethod
    async def sync_page(
        db: AsyncSession, teacher_id: int,
        session_id: int, page_index: int,
    ) -> dict | None:
        """同步当前播放页"""
        session = await ClassroomService._get_session(db, session_id, teacher_id)
        if not session:
            return None

        session.current_page = page_index
        page_log = {
            "page": page_index,
            "timestamp": datetime.now().isoformat(),
        }
        await ClassroomService._append_interaction(db, session, "page_log", page_log)
        return {"current_page": page_index}

    @staticmethod
    async def get_current_page(
        db: AsyncSession, session_id: int,
    ) -> dict | None:
        """获取当前页（供学生端轮询）"""
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return None
        return {"current_page": session.current_page}

    @staticmethod
    async def get_active_quizzes(
        db: AsyncSession, session_id: int,
    ) -> list[dict]:
        """获取课堂中所有活跃答题（供学生端查看）"""
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return []

        data = session.interaction_data or {}
        quizzes = data.get("quizzes", [])
        active = []
        for q in quizzes:
            active.append({
                "id": q.get("id"),
                "question": q.get("question"),
                "options": q.get("options"),
                "correct_answer": q.get("correct_answer"),
                "created_at": q.get("created_at"),
                "total_answers": len(q.get("answers", [])),
            })
        return active

    @staticmethod
    async def get_quiz_result_for_student(
        db: AsyncSession, session_id: int, quiz_id: str,
    ) -> dict | None:
        """学生端查看答题统计（不含正确答案）"""
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return None

        data = session.interaction_data or {}
        for quiz in data.get("quizzes", []):
            if quiz.get("id") == quiz_id:
                answers = quiz.get("answers", [])
                option_counts = [0] * len(quiz.get("options", []))
                correct_count = 0
                for a in answers:
                    sel = a.get("selected", -1)
                    if 0 <= sel < len(option_counts):
                        option_counts[sel] += 1
                    if a.get("is_correct"):
                        correct_count += 1
                return {
                    "question": quiz["question"],
                    "options": quiz["options"],
                    "option_counts": option_counts,
                    "total_answers": len(answers),
                    "correct_count": correct_count,
                }
        return None

    # ========== 幻灯片练习题答题记录 ==========

    @staticmethod
    async def record_slide_answer(
        db: AsyncSession, teacher_id: int,
        session_id: int, page_index: int,
        question_index: int, selected: int, correct: bool,
    ) -> dict | None:
        """记录幻灯片上练习题的答题结果"""
        session = await ClassroomService._get_session(db, session_id, teacher_id)
        if not session:
            return None

        answer = {
            "id": f"sa_{page_index}_{question_index}_{datetime.now().timestamp()}",
            "page_index": page_index,
            "question_index": question_index,
            "selected": selected,
            "correct": correct,
            "timestamp": datetime.now().isoformat(),
        }
        return await ClassroomService._append_interaction(db, session, "slide_answers", answer)

    # ========== 会话状态 ==========

    @staticmethod
    async def pause_classroom(
        db: AsyncSession, teacher_id: int, session_id: int,
    ) -> dict | None:
        """暂停课堂"""
        session = await ClassroomService._get_session(db, session_id, teacher_id)
        if not session:
            return None
        session.status = "paused"
        await db.commit()
        return {"session_id": session_id, "status": "paused"}

    @staticmethod
    async def resume_classroom(
        db: AsyncSession, teacher_id: int, session_id: int,
    ) -> dict | None:
        """恢复课堂"""
        session = await ClassroomService._get_session(db, session_id, teacher_id)
        if not session:
            return None
        session.status = "active"
        await db.commit()
        return {"session_id": session_id, "status": "active"}

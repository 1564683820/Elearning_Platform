import unittest
from contextlib import ExitStack
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from app.api.deps import get_current_teacher_id
from app.api.v1.exam import router
from app.api.v1.teaching_assistant import router as assistant_router
from app.db.database import Base, get_db
from app.models.exam_models import ExamGradingLog, ExamSubmission, TeacherExam
from app.models.chat import ChatConversation, ChatMessage
from app.models.scan_models import ExamScanRecord
from app.models.stats import UserDocument
from app.models.user import User
from app.services.embedding_service import EmbeddingService
from app.services.exam_knowledge import exam_question_chunks, find_exam_knowledge, read_exam_knowledge
from app.services.exam_knowledge_dates import parse_exam_period
from app.services.teaching_assistant_service import TeachingAssistantService
from scripts.reconcile_exam_question_index import reconcile_exam


class ExamKnowledgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(lambda db: Base.metadata.create_all(
                db, tables=[TeacherExam.__table__, ExamSubmission.__table__, User.__table__,
                            ExamScanRecord.__table__, ExamGradingLog.__table__],
            ))
        questions = [{"question_number": 8, "type": "choice", "answer": "B", "stem": "Example question"}]
        async with self.sessions() as db:
            db.add_all([
                TeacherExam(id=101, teacher_id=1, class_id=0, title="八年级 · 10 月随堂测", questions=questions),
                TeacherExam(id=102, teacher_id=1, class_id=2, title="单元巩固卷", questions=questions),
                TeacherExam(id=103, teacher_id=2, class_id=0, title="其他教师试卷", questions=questions),
                ExamSubmission(id=10, exam_id=101, exam_number="0001", score=0, grading_status="omr_done",
                               answers={"8": "A"}, updated_at=datetime(2026, 10, 1)),
                ExamSubmission(id=11, exam_id=101, exam_number="0001", score=2, grading_status="teacher_reviewed",
                               answers={"8": "A"}, ai_grade_detail=[{"question_number": 8, "user_answer": "B"}],
                               updated_at=datetime(2026, 10, 2)),
                ExamSubmission(id=12, exam_id=101, exam_number="0002", score=0, adjusted_score=1,
                               grading_status="manual_done", answers={}),
                ExamSubmission(id=13, exam_id=101, exam_number="0003", score=0, grading_status="ai_done",
                               answers=[{"question_index": 0, "answer": "AB"}]),
                ExamSubmission(id=14, exam_id=101, exam_number="0004", score=2, grading_status="pending",
                               answers={"8": "B"}),
                ExamSubmission(id=15, exam_id=101, score=2, grading_status="omr_done", answers={"8": "B"}),
                ExamGradingLog(id=17, submission_id=11, grader_type="teacher", grader_id=1, action="teacher_review"),
            ])
            await db.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_current_scores_exclude_pending_and_duplicate_identities(self):
        async with self.sessions() as db:
            result = await read_exam_knowledge(db, 1, 101, 8)
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["average"], 1.0)
        question = result["questions"][0]
        self.assertEqual(question["correct"], 1)
        self.assertEqual(question["distribution"], {"B": 1, "空白": 1, "无效填涂": 1})
        self.assertNotIn("0001", str(result))

    async def test_ownership_scope_and_context(self):
        async with self.sessions() as db:
            self.assertIsNone(await read_exam_knowledge(db, 1, 103, 8))
            ambiguous = await find_exam_knowledge(db, 1, None, "第 8 题正确率", [])
            self.assertIn("确认卷名", ambiguous["clarification"])
            self.assertNotIn("其他教师试卷", str(ambiguous))
            named = await find_exam_knowledge(db, 1, None, "10 月随堂测第 8 题错在哪？", [])
            scoped = await find_exam_knowledge(db, 1, 2, "第 8 题正确率", [])
            recent = await find_exam_knowledge(db, 1, None, "最近哪些题最容易错？", [])
            follow_up = await find_exam_knowledge(db, 1, None, "那道题的正确率呢？", [
                {"role": "user", "content": "10 月随堂测第 8 题如何？"},
                {"role": "assistant", "content": "有数据。"},
            ])
        self.assertEqual(named["exams"][0]["count"], 3)
        self.assertEqual(scoped["exams"][0]["id"], "102")
        self.assertEqual([exam["id"] for exam in recent["exams"]], ["101"])
        self.assertEqual(follow_up["exams"][0]["questions"][0]["number"], 8)
        source = TeachingAssistantService._format_sources({"exam_knowledge": named})[0]
        self.assertEqual((source["type"], source["id"], source["question_number"]), ("exam_result", "101", 8))
        self.assertEqual(source["exam_stats"], {
            "confirmed": 3, "correct": 1, "updated_at": named["exams"][0]["updated_at"], "leading_wrong": None,
        })

    async def test_recent_exams_rank_by_current_confirmed_activity(self):
        async with self.sessions.begin() as db:
            for submission_id in range(10, 16):
                (await db.get(ExamSubmission, submission_id)).updated_at = datetime(2026, 9, 1)
            template = (await db.get(TeacherExam, 101)).questions
            for offset in range(6):
                exam_id = 110 + offset
                db.add(TeacherExam(id=exam_id, teacher_id=1, class_id=0, title=f"专项练习 {offset}",
                                   questions=template, created_at=datetime(2026, 10, 6 - offset)))
                db.add(ExamSubmission(id=30 + offset, exam_id=exam_id, exam_number=f"00{offset}",
                                      score=2, grading_status="teacher_reviewed", answers={"8": "B"},
                                      updated_at=datetime(2026, 10, 18 + offset)))
            db.add_all([
                TeacherExam(id=140, teacher_id=1, class_id=2, title="未关联学生的较新试卷", questions=template),
                ExamSubmission(id=43, exam_id=140, exam_number="888", score=2, grading_status="teacher_reviewed",
                               answers={}, updated_at=datetime(2026, 11, 1)),
                ExamSubmission(id=44, exam_id=110, exam_number="pending", score=2, grading_status="pending",
                               answers={}, updated_at=datetime(2026, 11, 2)),
                ExamSubmission(id=45, exam_id=110, exam_number="removed", score=2, grading_status="paper_withdrawn",
                               answers={}, updated_at=datetime(2026, 11, 3)),
                ExamSubmission(id=46, exam_id=103, exam_number="foreign", score=2, grading_status="teacher_reviewed",
                               answers={}, updated_at=datetime(2026, 11, 4)),
            ])
        async with self.sessions() as db:
            result = await find_exam_knowledge(db, 1, None, "最近哪些题最容易错？", [])
            numbered = await find_exam_knowledge(db, 1, None, "最近批改的第8题正确率", [])
        self.assertEqual([exam["id"] for exam in result["exams"]], ["115", "114", "113", "112", "111"])
        self.assertEqual([exam["count"] for exam in result["exams"]], [1] * 5)
        self.assertEqual(numbered["titles"], [exam["title"] for exam in result["exams"]])

    async def test_dated_statistics_apply_beijing_boundaries_after_current_result_filter(self):
        async with self.sessions.begin() as db:
            (await db.get(ExamSubmission, 12)).updated_at = datetime(2026, 9, 30, 16)
            (await db.get(ExamSubmission, 13)).updated_at = datetime(2026, 10, 1, 15, 59)
            db.add(ExamSubmission(id=26, exam_id=101, exam_number="0026", score=2, grading_status="teacher_reviewed",
                                  answers={"8": "B"}, updated_at=datetime(2026, 10, 1, 16)))
        async with self.sessions() as db:
            question = "10 月随堂测在2026-10-01第8题正确率？"
            result = await find_exam_knowledge(db, 1, None, question, [])
            dated = result["exams"][0]
            source = TeachingAssistantService._format_sources({"exam_knowledge": result})[0]
            self.assertEqual((dated["count"], dated["questions"][0]["correct"]), (2, 0))
            self.assertEqual((source["date_from"], source["date_to"]), ("2026-10-01", "2026-10-01"))

            contextual = await find_exam_knowledge(db, 1, None, "那道题错在哪？", [
                {"role": "user", "content": "10 月随堂测昨天第8题正确率？", "created_at": datetime(2026, 10, 2)},
                {"role": "assistant", "content": "已查到。"},
            ])
            self.assertEqual(contextual, result)
            changed_period = await find_exam_knowledge(db, 1, None, "那2026年10月1日呢？", [
                {"role": "user", "content": "10 月随堂测2026年10月2日第8题正确率？"},
                {"role": "assistant", "content": "已查到。"},
            ])
            self.assertEqual(changed_period, result)
            by_date = await find_exam_knowledge(db, 1, None, "2026年10月1日至10月1日批改的试卷均分？", [])
            self.assertEqual([exam["id"] for exam in by_date["exams"]], ["101"])
            self.assertEqual(by_date["exams"][0]["average"], 0.5)
            invalid = await find_exam_knowledge(db, 1, None, "10 月随堂测2026-10-03到2026-10-01正确率", [])
            self.assertIn("确认批改日期", invalid["clarification"])
            multi = await find_exam_knowledge(db, 1, None, "10 月随堂测本周与上周的正确率", [])
            self.assertTrue(multi["invalid_period"])

        at = datetime(2026, 11, 22, 17, tzinfo=timezone.utc)
        week = parse_exam_period("上周成绩", at=at)
        self.assertEqual((week.start, week.end), (date(2026, 11, 16), date(2026, 11, 22)))
        rolling = parse_exam_period("最近 7 天成绩", at=at)
        self.assertEqual((rolling.start, rolling.end), (date(2026, 11, 17), date(2026, 11, 23)))
        self.assertEqual(parse_exam_period("上个月成绩", at=at).end, date(2026, 10, 31))

    async def test_home_availability_uses_current_results_for_authenticated_teacher(self):
        app = FastAPI()
        app.include_router(assistant_router, prefix="/api/v1")

        async def session():
            async with self.sessions() as db:
                yield db

        teacher_id = 1
        app.dependency_overrides[get_db] = session
        app.dependency_overrides[get_current_teacher_id] = lambda: teacher_id
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1/") as client:
            endpoint = "teaching-assistant/exam-knowledge/availability"
            own = await client.get(endpoint)
            self.assertEqual(own.json()["data"], {"has_confirmed_results": True})
            teacher_id = 2
            async with self.sessions.begin() as db:
                db.add(ExamSubmission(id=47, exam_id=103, exam_number="0001", score=2,
                                      grading_status="pending", answers={"8": "B"}))
            other = await client.get(endpoint)
            self.assertEqual(other.json()["data"], {"has_confirmed_results": False})
            async with self.sessions.begin() as db:
                (await db.get(ExamSubmission, 47)).grading_status = "teacher_reviewed"
            confirmed = await client.get(endpoint)
            self.assertEqual(confirmed.json()["data"], {"has_confirmed_results": True})
            async with self.sessions.begin() as db:
                (await db.get(ExamSubmission, 47)).grading_status = "paper_withdrawn"
            withdrawn = await client.get(endpoint)
            self.assertEqual(withdrawn.json()["data"], {"has_confirmed_results": False})

    async def test_reply_evidence_uses_unambiguous_wrong_option_and_authoritative_counts(self):
        async with self.sessions.begin() as db:
            for submission_id, number in ((21, "0006"), (22, "0007")):
                db.add(ExamSubmission(id=submission_id, exam_id=101, exam_number=number, score=0,
                                      grading_status="omr_done", answers={"8": "C"}))
        async with self.sessions() as db:
            result = await find_exam_knowledge(db, 1, None, "10 月随堂测第 8 题错在哪？", [])
        source = TeachingAssistantService._format_sources({"exam_knowledge": result})[0]
        self.assertEqual(source["exam_stats"], {
            "confirmed": 5, "correct": 1, "updated_at": result["exams"][0]["updated_at"],
            "leading_wrong": {"option": "C", "count": 2},
        })
        self.assertNotIn("0006", str(source))

        result["exams"][0]["questions"][0]["distribution"] = {"B": 1, "A": 2, "C": 2}
        tied = TeachingAssistantService._format_sources({"exam_knowledge": result})[0]
        self.assertIsNone(tied["exam_stats"]["leading_wrong"])

    async def test_named_comparison_keeps_each_exam_and_its_question_source(self):
        async with self.sessions.begin() as db:
            second = await db.get(TeacherExam, 102)
            second.questions = [*second.questions, {
                "question_number": 6, "type": "choice", "answer": "A", "stem": "Second question",
            }]
            db.add(ExamSubmission(id=25, exam_id=102, student_id=25, exam_number="0025", score=2,
                                  grading_status="teacher_reviewed", answers={"8": "B", "6": "C"}))
        async with self.sessions() as db:
            question = "对比10 月随堂测第8题和单元巩固卷第6题的正确率"
            result = await find_exam_knowledge(db, 1, None, question, [])
            follow_up = await find_exam_knowledge(db, 1, None, "那两份卷的正确率呢？", [
                {"role": "user", "content": question}, {"role": "assistant", "content": "已列出两卷数据。"},
            ])
            common = await find_exam_knowledge(db, 1, None, "第8题正确率，比较单元巩固卷和10 月随堂测", [])
            next_question = await find_exam_knowledge(db, 1, None, "那两份卷第8题的正确率呢？", [
                {"role": "user", "content": question}, {"role": "assistant", "content": "已列出两卷数据。"},
            ])
        sources = TeachingAssistantService._format_sources({"exam_knowledge": result})
        self.assertEqual([(s["id"], s["question_number"]) for s in sources], [("101", 8), ("102", 6)])
        self.assertEqual([s["exam_stats"]["confirmed"] for s in sources], [3, 1])
        self.assertEqual([s["exam_stats"]["correct"] for s in sources], [1, 0])
        self.assertNotIn("0025", str(result))
        self.assertEqual(follow_up, result)
        self.assertEqual([(r["id"], r["questions"][0]["number"]) for r in common["exams"]], [("102", 8), ("101", 8)])
        self.assertEqual([(r["id"], r["questions"][0]["number"]) for r in next_question["exams"]], [("101", 8), ("102", 8)])

    async def test_title_only_reply_recovers_question_without_reopening_unrelated_search(self):
        async with self.sessions() as db:
            recent = [{"role": "user", "content": "第8题正确率？"},
                      {"role": "assistant", "content": "有多份符合条件的试卷，请确认卷名。"},
                      {"role": "user", "content": "10 月随堂测"}]
            answer = await find_exam_knowledge(db, 1, None, "10 月随堂测", recent)
            self.assertEqual([(exam["id"], exam["questions"][0]["number"]) for exam in answer["exams"]], [("101", 8)])
            self.assertIsNone(await find_exam_knowledge(db, 1, None, "10 月随堂测", []))
            self.assertIsNone(await find_exam_knowledge(db, 1, None, "其他教师试卷", recent))
            self.assertIsNone(await find_exam_knowledge(db, 1, None, "为10 月随堂测写一份通知", recent))

    async def test_shared_chat_clarifies_and_uses_sql_evidence_in_streamed_followup(self):
        async with self.engine.begin() as connection:
            for model in (ChatConversation, ChatMessage, UserDocument):
                await connection.execute(CreateTable(model.__table__))
        app = FastAPI()
        app.include_router(assistant_router, prefix="/api/v1")
        app.include_router(router, prefix="/api/v1")

        async def session():
            async with self.sessions() as db:
                yield db
                await db.commit()

        app.dependency_overrides[get_db] = session
        app.dependency_overrides[get_current_teacher_id] = lambda: 1
        prefix = "app.services.teaching_assistant_service."

        async def tokens():
            yield "第 8 题有 1 份答对，样本共 3 份。"

        with ExitStack() as mocks:
            for target, result in (
                ("IntentClassifier.classify", {"intent": "general_chat"}),
                ("MemoryService.get_relevant_memories", []),
                ("TeachingAssistantService._multi_source_search", {}),
                ("TeachingAssistantService._load_active_skill_prompts", {}),
                ("TeachingAssistantService._update_conversation_summary", None),
                ("TeachingAssistantService._generate_suggestions", []),
            ):
                mocks.enter_context(patch(prefix + target, return_value=result))
            model = mocks.enter_context(patch(prefix + "AIService.chat_completion", side_effect=lambda *_a, **_kw: tokens()))
            async with (
                AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1/") as web,
                AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1/") as h5,
            ):
                created = await web.post("teaching-assistant/sessions", json={})
                self.assertEqual(created.status_code, 200, created.text)
                conversation_id = created.json()["data"]["id"]
                payload = {"conversation_id": conversation_id, "message": "第8题正确率？"}
                clarifier = await web.post("teaching-assistant/chat", json={**payload, "request_id": "ambiguity-web"})
                self.assertEqual(clarifier.status_code, 200, clarifier.text)
                answer = clarifier.json()["data"]["content"]
                self.assertIn("确认卷名", answer)
                self.assertIn("10 月随堂测", answer)
                self.assertIn("单元巩固卷", answer)
                self.assertNotIn("其他教师试卷", answer)
                self.assertEqual(clarifier.json()["data"]["sources"], [])
                model.assert_not_awaited()

                response = await h5.post("teaching-assistant/chat/stream", json={
                    "conversation_id": conversation_id, "message": "10 月随堂测", "request_id": "named-followup-h5",
                })
                self.assertIn("event: done", response.text)
                self.assertIn("event: sources", response.text)
                self.assertIn("10 月随堂测 · 第 8 题统计", response.text)
                model.assert_awaited_once()
                self.assertIn('"correct": 1', model.await_args.args[1][0]["content"])

                history = await web.get(f"teaching-assistant/sessions/{conversation_id}/messages?latest=true")
                source = history.json()["data"]["items"][-1]["sources"][0]
                self.assertEqual((source["id"], source["question_number"]), ("101", 8))
                details = await h5.get(f"teacher/exam/{source['id']}/grading-knowledge",
                                       params={"question_number": source["question_number"]})
                self.assertEqual(details.status_code, 200, details.text)
                self.assertEqual(details.json()["data"]["questions"][0]["correct"], 1)
                second = await h5.post("teaching-assistant/chat/stream", json={**payload, "request_id": "ambiguity-h5"})
                self.assertIn("event: done", second.text)
                self.assertIn("确认卷名", second.text)
                model.assert_awaited_once()

    async def test_statistics_route_rechecks_ownership(self):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        async def session():
            async with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = session
        app.dependency_overrides[get_current_teacher_id] = lambda: 1
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            own = await client.get("/api/v1/teacher/exam/101/grading-knowledge?question_number=8")
            other = await client.get("/api/v1/teacher/exam/103/grading-knowledge?question_number=8")
            missing = await client.get("/api/v1/teacher/exam/101/grading-knowledge?question_number=12")
            date_query = "?date_from=2026-10-02&date_to=2026-10-02"
            ranged = await client.get("/api/v1/teacher/exam/101/grading-knowledge" + date_query)
            ranged_question = await client.get("/api/v1/teacher/exam/101/grading-knowledge" + date_query + "&question_number=8")
            ranged_foreign = await client.get("/api/v1/teacher/exam/103/grading-knowledge" + date_query)
            incomplete = await client.get("/api/v1/teacher/exam/101/grading-knowledge?date_from=2026-10-02")
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.json()["data"]["questions"][0]["correct"], 1)
        self.assertEqual((other.status_code, missing.status_code), (404, 404))
        self.assertEqual((ranged.status_code, ranged_question.status_code, ranged_foreign.status_code, incomplete.status_code),
                         (200, 200, 404, 422))
        self.assertEqual(ranged.json()["data"]["count"], 1)
        self.assertEqual(ranged_question.json()["data"]["date_from"], "2026-10-02")

    async def test_structured_stem_locates_exam_without_title_and_keeps_context(self):
        async with self.sessions() as db:
            exam = await db.get(TeacherExam, 101)
            exam.questions = [{**exam.questions[0], "stem": "When did the train leave?"}]
            await db.commit()
            question = "When did the train leave 这道题正确率是多少？"
            with patch.object(EmbeddingService, "hybrid_search", new_callable=AsyncMock) as search:
                result = await find_exam_knowledge(db, 1, None, question, [])
                follow_up = await find_exam_knowledge(db, 1, None, "那道题错在哪？", [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": "有数据。"},
                ])
            search.assert_not_awaited()
        self.assertEqual(result["exams"][0]["id"], "101")
        self.assertEqual(follow_up, result)
        self.assertEqual(result["exams"][0]["questions"][0]["correct"], 1)

    async def test_vector_candidates_require_current_teacher_class_and_content(self):
        question = "那道考查铁路列车启程时间的题正确率是多少？"
        async with self.sessions() as db:
            exams = [await db.get(TeacherExam, exam_id) for exam_id in (101, 102, 103)]
            own, other_class, foreign = [exam_question_chunks(exam)[0] for exam in exams]
            stale = {**own, "chunk_id": "old-version"}
            with patch.dict("os.environ", {"EXAM_QUESTION_VECTOR_SEARCH": "1"}), patch.object(
                EmbeddingService, "hybrid_search", new_callable=AsyncMock,
                return_value=[stale, foreign, other_class, own],
            ) as search:
                result = await find_exam_knowledge(db, 1, 0, question, [])
                self.assertEqual(search.await_args.kwargs["source_type"], "exam_question")
                self.assertIn("user_id == 1 and class_id == 0", search.await_args.kwargs["extra_filter"])
                self.assertEqual(result["exams"][0]["id"], "101")
                self.assertEqual(result["exams"][0]["count"], 3)
                self.assertNotIn("0001", str(result))
                ambiguous = await find_exam_knowledge(db, 1, None, question, [])
                self.assertIn("匹配到多道题", ambiguous["clarification"])
                exams[0].questions = [{**exams[0].questions[0], "stem": "A changed question"}]
                await db.commit()
                outdated = await find_exam_knowledge(db, 1, 0, question, [])
                self.assertEqual(outdated["exams"], [])

    async def test_index_reconciliation_preserves_old_rows_until_new_rows_are_readable(self):
        async with self.sessions() as db:
            exam = await db.get(TeacherExam, 101)
            current = exam_question_chunks(exam)[0]["chunk_id"]
            old = [{"id": 1, "chunk_id": "retired"}]
            with patch("scripts.reconcile_exam_question_index._query", return_value=old) as query, patch.object(
                EmbeddingService, "index_chunks_batch", new_callable=AsyncMock, return_value=1,
            ) as index, patch.object(EmbeddingService, "delete_by_expr", return_value=True) as delete:
                self.assertEqual(await reconcile_exam(db, exam, apply=False), (1, 1))
                index.assert_not_awaited()
                delete.assert_not_called()
                with self.assertRaisesRegex(RuntimeError, "尚不可读"):
                    await reconcile_exam(db, exam, apply=True)
                delete.assert_not_called()

                query.side_effect = [old, old + [{"id": 2, "chunk_id": current}]]
                self.assertEqual(await reconcile_exam(db, exam, apply=True), (1, 1))
                self.assertEqual(index.await_args.args[2][0]["chunk_id"], current)
                self.assertTrue(delete.call_args.args[1].endswith("and id in [1]"))

    async def test_grading_records_share_effective_score_and_show_history_without_class(self):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        async def session():
            async with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = session
        app.dependency_overrides[get_current_teacher_id] = lambda: 1
        root = "/api/v1/teacher/exam"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            listed = await client.get(f"{root}/101/grading-records?search=0001")
            confirmed = await client.get(f"{root}/101/grading-records?status=confirmed&page_size=1")
            detail = await client.get(f"{root}/101/grading-records/11")
            missing_photo = await client.get(f"{root}/101/grading-records/11/photo")
            cross_exam = await client.get(f"{root}/102/grading-records/11")
            forbidden = await client.get(f"{root}/103/grading-records")
        self.assertEqual(listed.status_code, 200)
        result = listed.json()["data"]
        self.assertEqual((result["confirmed"], result["pending"]), (3, 2))
        self.assertEqual([(item["id"], item["status"]) for item in result["items"]], [
            ("11", "confirmed"), ("10", "historical"),
        ])
        page = confirmed.json()["data"]
        self.assertEqual((page["total"], len(page["items"])), (3, 1))
        item = detail.json()["data"]
        self.assertEqual(item["questions"][0]["marked"], "B")
        self.assertEqual(item["history"][0]["action"], "teacher_review")
        self.assertEqual((missing_photo.status_code, cross_exam.status_code, forbidden.status_code), (404, 404, 404))

    async def test_grading_photo_accepts_only_linked_server_scan(self):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        async def session():
            async with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = session
        app.dependency_overrides[get_current_teacher_id] = lambda: 1
        async with self.sessions() as db:
            entry = await db.get(ExamSubmission, 11)
            entry.scan_record_id = 18
            db.add(ExamScanRecord(id=18, exam_id=101, teacher_id=1, scan_image_url="/static/scans/101/1000_1.png"))
            forged = await db.get(ExamSubmission, 14)
            forged.scan_image_url = "/static/scans/101/2000_1.png"
            db.add(ExamScanRecord(id=19, exam_id=101, teacher_id=2, scan_image_url=forged.scan_image_url))
            await db.commit()

        with TemporaryDirectory() as temporary:
            local = Path(temporary) / "app" / "uploads" / "scans" / "101"
            local.mkdir(parents=True)
            (local / "1000_1.png").write_bytes(b"synthetic scan fixture")
            (local / "2000_1.png").write_bytes(b"other scan fixture")
            with patch("app.services.exam_records.SERVER_DIR", Path(temporary)):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    photo = await client.get("/api/v1/teacher/exam/101/grading-records/11/photo")
                    other_photo = await client.get("/api/v1/teacher/exam/101/grading-records/14/photo")
        self.assertEqual(photo.status_code, 200)
        self.assertEqual(photo.content, b"synthetic scan fixture")
        self.assertEqual(photo.headers["cache-control"], "private, no-store")
        self.assertEqual(other_photo.status_code, 404)

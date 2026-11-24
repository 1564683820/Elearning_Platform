"""Real SQL transactions and actual LangGraph execution; external tools are deterministic.

SQLite tests do not establish MySQL locking or Redis/Milvus integration correctness.
"""
import copy
import unittest
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.database import Base
from app.models.teaching_task import TeachingTask, TeachingTaskOutbox
from app.models.exam_models import TeacherExam, ExamSubmission
from app.models.class_models import Class, ClassTeacher, ClassStudent
from app.models.stats import UserDocument
from app.services.teaching_task_service import TeachingTaskService
from app.services.teaching_agent import TeachingTools, build_graph, MissingEvidence
from app.schemas.teaching_task import validate_artifact
from app.teaching_worker import execute, claim, save_state, relay, LostLease
import httpx
from fastapi import FastAPI
from app.api.v1.teaching_tasks import router
from app.api.deps import get_current_teacher_id
from app.db.database import get_db


def state_fixture():
    return {'config': {'question_count': 2, 'duration_minutes': 20},
        'analysis': {'topics': [{'knowledge_point': '过去时', 'wrong': 3, 'observations': 4}]},
        'citations': [{'id': 'C1', 'document_id': '9', 'page': 1, 'version': 'test', 'snippet': '过去时'}]}


def artifact_fixture():
    return {'title': '过去时巩固', 'lesson': [{'title': '情境教学', 'minutes': 20, 'activity': '复习过去时并练习。'}],
        'total_score': 10, 'questions': [{'type': 'choice', 'stem': f'Yesterday I {i} __ to school.',
            'options': ['went', 'go', 'goes', 'going'], 'answer': 'A', 'score': 5,
            'explanation': 'Yesterday 表示过去时间。', 'knowledge_point': '过去时', 'citation_ids': ['C1']}
            for i in range(2)]}


class FakeTools:
    calls = []
    fail_once = False
    def __init__(self, db=None, task=None):
        pass
    async def authorize(self):
        pass
    async def analyze(self, state):
        self.calls.append('analyze')
        return {'analysis': state_fixture()['analysis']}
    async def retrieve(self, state):
        self.calls.append('retrieve')
        if self.fail_once:
            type(self).fail_once = False
            raise RuntimeError('simulated provider failure')
        return {'citations': state_fixture()['citations']}
    async def plan(self, state):
        self.calls.append('plan')
        return {'plan': state['config']}
    async def generate(self, state):
        self.calls.append('generate')
        return {'artifact': artifact_fixture()}


class TeachingWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        tables = [TeachingTask.__table__, TeachingTaskOutbox.__table__, TeacherExam.__table__,
            ExamSubmission.__table__, Class.__table__, ClassTeacher.__table__, ClassStudent.__table__, UserDocument.__table__]
        async with self.engine.begin() as connection:
            await connection.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        async with self.sessions() as db:
            db.add_all([Class(id=8, name='合成班级', invite_code='TEST8', created_by=7),
                ClassTeacher(id=1, class_id=8, teacher_id=7),
                TeachingTask(id=9007199254740993, teacher_id=7, class_id=8, objective='巩固过去时',
                    status='queued', checkpoint={'config': state_fixture()['config']})])
            await db.commit()
        FakeTools.calls, FakeTools.fail_once = [], False

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def task(self, db):
        return await db.get(TeachingTask, 9007199254740993)

    async def ready(self, status='awaiting_review'):
        async with self.sessions() as db:
            task = await self.task(db)
            task.status, task.checkpoint = status, state_fixture()
            task.artifact, task.artifact_version = artifact_fixture(), 1
            await db.commit()

    async def test_workflow_persists_every_node_and_duplicate_delivery_does_not_regenerate(self):
        await execute(9007199254740993, self.sessions, FakeTools)
        await execute(9007199254740993, self.sessions, FakeTools)
        async with self.sessions() as db:
            task = await self.task(db)
            self.assertEqual(task.status, 'awaiting_review')
            self.assertEqual(task.artifact_version, 1)
            self.assertEqual(len(task.checkpoint['traces']), 6)
        self.assertEqual(FakeTools.calls, ['analyze', 'retrieve', 'plan', 'generate'])

    async def test_http_create_run_conflict_cancel_and_string_identifiers(self):
        app = FastAPI()
        app.include_router(router, prefix='/api/v1')
        async def database():
            async with self.sessions() as db:
                try:
                    yield db
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_teacher_id] = lambda: 7
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            created = await client.post('/api/v1/teaching-tasks', json={'class_id': '8', 'objective': '巩固过去时'})
            self.assertEqual(created.status_code, 201)
            task_id = created.json()['data']['id']
            self.assertIsInstance(task_id, str)
            self.assertEqual(created.json()['data']['class_id'], '8')
            path = f'/api/v1/teaching-tasks/{task_id}'
            self.assertEqual((await client.post(path+'/run')).status_code, 200)
            self.assertEqual((await client.post(path+'/run')).status_code, 409)
            self.assertEqual((await client.post(path+'/approve', json={'version': 1})).status_code, 409)
            self.assertEqual((await client.post(path+'/cancel')).json()['data']['status'], 'cancelled')
            app.dependency_overrides[get_current_teacher_id] = lambda: 99
            self.assertEqual((await client.get(path)).status_code, 404)

    async def test_transient_model_failure_has_exactly_two_automatic_retries(self):
        class TimeoutTools(FakeTools):
            async def generate(self, state):
                self.calls.append('generate')
                raise httpx.ConnectTimeout('simulated timeout')
        for _ in range(4):
            await execute(9007199254740993, self.sessions, TimeoutTools)
        self.assertEqual(FakeTools.calls.count('generate'), 3)
        self.assertEqual(FakeTools.calls.count('analyze'), 1)
        async with self.sessions() as db:
            task = await self.task(db)
            self.assertEqual(task.status, 'failed')
            self.assertEqual(task.attempts, 3)

    async def test_class_permission_revoked_during_generation_discards_model_result(self):
        class RevokedTools(FakeTools):
            revoked = False
            async def authorize(self):
                if self.revoked:
                    raise PermissionError('revoked')
            async def generate(self, state):
                self.revoked = True
                return {'artifact': artifact_fixture()}
        await execute(9007199254740993, self.sessions, RevokedTools)
        async with self.sessions() as db:
            task = await self.task(db)
            self.assertEqual(task.status, 'failed')
            self.assertEqual(task.error_code, 'access_revoked')
            self.assertEqual(task.artifact, {})

    async def test_retry_resumes_successful_analysis_after_worker_failure(self):
        FakeTools.fail_once = True
        await execute(9007199254740993, self.sessions, FakeTools)
        async with self.sessions() as db:
            task = await self.task(db)
            self.assertEqual(task.status, 'failed')
            await TeachingTaskService.command(db, task, 'retry')
            await db.commit()
        await execute(9007199254740993, self.sessions, FakeTools)
        self.assertEqual(FakeTools.calls.count('analyze'), 1)
        async with self.sessions() as db:
            self.assertEqual((await self.task(db)).status, 'awaiting_review')

    async def test_expired_worker_lease_can_be_reclaimed_and_old_owner_fenced(self):
        first = await claim(9007199254740993, 'old', self.sessions)
        self.assertIsNotNone(first)
        self.assertIsNone(await claim(first.id, 'new', self.sessions))
        async with self.sessions() as db:
            task = await self.task(db)
            task.lease_until = datetime.utcnow() - timedelta(seconds=1)
            await db.commit()
        self.assertIsNotNone(await claim(first.id, 'new', self.sessions))
        with self.assertRaises(LostLease):
            await save_state(first.id, 'old', state_fixture(), sessions=self.sessions)

    async def test_killed_worker_process_resumes_persisted_sql_checkpoint(self):
        with tempfile.TemporaryDirectory(prefix='elearning-worker-') as directory:
            database, marker = Path(directory)/'worker.sqlite', Path(directory)/'started'
            engine = create_async_engine('sqlite+aiosqlite:///' + database.as_posix())
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as connection:
                await connection.run_sync(lambda c: Base.metadata.create_all(c,
                    tables=[TeachingTask.__table__, TeachingTaskOutbox.__table__]))
            async with sessions() as db:
                db.add(TeachingTask(id=9007199254740993, teacher_id=7, class_id=8, objective='合成恢复测试',
                    status='queued', checkpoint={'config': state_fixture()['config']}))
                await db.commit()
            process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('worker_crash_probe.py')),
                str(database), str(marker)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(200):
                    if marker.exists() or process.poll() is not None:
                        break
                    await asyncio.sleep(.05)
                self.assertTrue(marker.exists(), 'child worker did not reach generation')
                process.kill()
                await asyncio.to_thread(process.wait, timeout=5)
                async with sessions() as db:
                    task = await db.get(TeachingTask, 9007199254740993)
                    self.assertEqual(task.checkpoint['completed'], ['analyze', 'retrieve', 'plan'])
                    task.lease_until = datetime.now() - timedelta(days=1)
                    await db.commit()
                FakeTools.calls = []
                await execute(9007199254740993, sessions, FakeTools)
                self.assertEqual(FakeTools.calls, ['generate'])
                async with sessions() as db:
                    self.assertEqual((await db.get(TeachingTask, 9007199254740993)).status, 'awaiting_review')
            finally:
                if process.poll() is None:
                    process.kill()
                    await asyncio.to_thread(process.wait, timeout=5)
                await engine.dispose()

    async def test_cancel_fences_in_flight_model_result(self):
        await claim(9007199254740993, 'worker', self.sessions)
        async with self.sessions() as db:
            await TeachingTaskService.command(db, await self.task(db), 'cancel')
            await db.commit()
        with self.assertRaises(LostLease):
            await save_state(9007199254740993, 'worker', state_fixture(), sessions=self.sessions)

    async def test_teacher_edits_invalidate_approval_and_stale_requests_are_rejected(self):
        await self.ready()
        async with self.sessions() as db:
            task = await self.task(db)
            await TeachingTaskService.command(db, task, 'approve', 1)
            artifact = artifact_fixture()
            artifact['title'] = '教师修订练习'
            await TeachingTaskService.command(db, task, 'artifact', 1, artifact)
            self.assertEqual(task.status, 'awaiting_review')
            self.assertIsNone(task.approved_version)
            for version in (1, 2):
                with self.assertRaises(HTTPException) as caught:
                    await TeachingTaskService.command(db, task, 'publish', version)
                self.assertEqual(caught.exception.status_code, 409)

    async def test_repeated_publish_returns_same_exam_and_uses_existing_publisher(self):
        await self.ready()
        async with self.sessions() as db:
            task = await self.task(db)
            await TeachingTaskService.command(db, task, 'approve', 1)
            await TeachingTaskService.command(db, task, 'publish', 1)
            exam_id = task.published_exam_id
            await db.commit()
        # New session models an API process restart / retried request.
        async with self.sessions() as db:
            task = await self.task(db)
            await TeachingTaskService.command(db, task, 'publish', 1)
            self.assertEqual(task.published_exam_id, exam_id)
            self.assertEqual((await db.execute(select(func.count()).select_from(TeacherExam))).scalar(), 1)
            self.assertEqual((await db.get(TeacherExam, exam_id)).status, 'published')

    async def test_foreign_teacher_and_revoked_membership_cannot_read_task(self):
        async with self.sessions() as db:
            with self.assertRaises(HTTPException):
                await TeachingTaskService.owned(db, 9007199254740993, 99)
            membership = await db.get(ClassTeacher, 1)
            await db.delete(membership)
            await db.commit()
            with self.assertRaises(HTTPException):
                await TeachingTaskService.owned(db, 9007199254740993, 7)

    async def test_redis_outage_retains_transactional_outbox(self):
        async with self.sessions() as db:
            task = await self.task(db)
            task.status = 'created'
            await TeachingTaskService.command(db, task, 'run')
            await db.commit()
        redis = AsyncMock()
        redis.xadd.side_effect = RedisConnectionError('offline')
        with self.assertRaises(RedisConnectionError):
            await relay(redis, 'test:tasks', self.sessions)
        async with self.sessions() as db:
            row = (await db.execute(select(TeachingTaskOutbox))).scalar_one()
            self.assertIsNone(row.delivered_at)
            self.assertEqual((await self.task(db)).status, 'queued')

    async def test_missing_evidence_waits_for_input_instead_of_fabricating(self):
        class EmptyTools(FakeTools):
            async def retrieve(self, state):
                raise MissingEvidence('no_verified_retrieval_evidence')
        await execute(9007199254740993, self.sessions, EmptyTools)
        async with self.sessions() as db:
            task = await self.task(db)
            self.assertEqual(task.status, 'awaiting_input')
            self.assertEqual(task.artifact, {})
            self.assertEqual(task.error_code, 'no_verified_retrieval_evidence')
            await TeachingTaskService.command(db, task, 'retry')
            self.assertEqual(task.checkpoint, {'config': state_fixture()['config']})

    async def test_validation_correction_is_bounded(self):
        class BadTools(FakeTools):
            async def generate(self, state):
                self.calls.append('generate')
                return {'artifact': {}}
        saved = []
        async def save(state):
            saved.append(copy.deepcopy(state))
        final = await build_graph(BadTools(), save).ainvoke({'config': state_fixture()['config']})
        self.assertEqual(FakeTools.calls.count('generate'), 3)
        self.assertEqual(final['status'], 'awaiting_input')
        self.assertEqual(final['corrections'], 3)

    async def test_retrieval_filters_foreign_documents_before_vector_search(self):
        async with self.sessions() as db:
            db.add_all([UserDocument(id=9, user_id=7, class_id=8, filename='本班', file_type='txt',
                storage_key='test', parse_status=2, parsed_text='过去时用于过去。\fYesterday went.'),
                UserDocument(id=10, user_id=99, class_id=8, filename='其他教师', file_type='txt',
                storage_key='test', parse_status=2, parsed_text='foreign'),
                UserDocument(id=11, user_id=7, class_id=88, filename='其他班级', file_type='txt',
                storage_key='test', parse_status=2, parsed_text='foreign class')])
            await db.commit()
            with patch('app.services.teaching_agent.EmbeddingService.hybrid_search', AsyncMock(return_value=[
                {'source_id': 9, 'content': 'Yesterday went.'}, {'source_id': 10, 'content': 'foreign'},
                {'source_id': 11, 'content': 'foreign class'}, {'source_id': 9, 'content': 'stale content'}])) as search:
                result = await TeachingTools(db, await self.task(db)).retrieve(state_fixture())
            self.assertEqual(search.call_args.kwargs['extra_filter'], 'source_id in [9]')
            self.assertEqual(len(result['citations']), 1)
            self.assertEqual(result['citations'][0]['page'], 2)

    async def test_actual_analysis_uses_only_current_class_students(self):
        async with self.sessions() as db:
            db.add_all([ClassStudent(id=1, class_id=8, student_id=20),
                TeacherExam(id=40, teacher_id=7, class_id=8, title='合成考试', questions=[{
                    'knowledge_point': '过去时', 'score': 5}], status='done'),
                ExamSubmission(id=50, exam_id=40, student_id=20, answers=[], grading_status='teacher_reviewed',
                    ai_grade_detail=[{'score': 0}]),
                ExamSubmission(id=51, exam_id=40, student_id=99, answers=[], grading_status='ai_done',
                    ai_grade_detail=[{'score': 0}])])
            await db.commit()
            result = await TeachingTools(db, await self.task(db)).analyze(state_fixture())
            self.assertEqual(result['analysis']['submission_count'], 1)
            self.assertEqual(result['analysis']['topics'][0]['wrong'], 1)


class ArtifactValidationTests(unittest.TestCase):
    def test_bad_counts_scores_duplicates_citations_and_coverage_are_rejected(self):
        mutations = [lambda a: a.update(total_score=99),
            lambda a: a['questions'].pop(),
            lambda a: a['questions'][1].update(stem=a['questions'][0]['stem']),
            lambda a: a['questions'][0].update(citation_ids=['invented']),
            lambda a: a['questions'][0].update(knowledge_point='无统计依据'),
            lambda a: a['lesson'][0].update(minutes=19),
            lambda a: a['questions'][0].update(answer='E')]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                artifact = artifact_fixture()
                mutate(artifact)
                with self.assertRaises(ValueError):
                    validate_artifact(artifact, state_fixture())

"""Synthetic seed only; refuses legacy databases and existing demo accounts.

Set TEACHING_DEMO_PASSWORD privately in the process environment before running this script.
Optional --index uses the configured Embedding API (paid) and demo Milvus database.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, text
from app.core.config import get_settings
from app.core.security import pwd_context
from app.db.database import async_session
from app.models.user import User
from app.models.class_models import Class, ClassTeacher, ClassStudent
from app.models.exam_models import TeacherExam, ExamSubmission
from app.models.stats import UserDocument
from app.services.embedding_service import EmbeddingService

PAGES = [
    ('一般过去时', '一般过去时描述过去发生的动作。yesterday、last week 常用作时间标志。规则动词过去式通常加 ed，不规则动词需要单独记忆，例如 go 的过去式是 went。否定句使用 did not 后接动词原形，疑问句使用 Did 加主语和动词原形。例句：She visited the museum yesterday. Did she visit the museum?'),
    ('现在完成时', '现在完成时的结构是 have 或 has 加过去分词，用于过去行为对现在产生的影响。since 后接时间起点，for 后接时间段。already 常用于肯定句，yet 常用于否定句和疑问句。例句：I have lived here for three years. She has just finished her homework.'),
    ('比较级', '比较级用于两者之间的比较，常与 than 连用。短形容词通常加 er，长形容词前加 more。good 的比较级为 better，bad 的比较级为 worse。much 可以修饰比较级，不能用 very 修饰。例句：This book is more interesting than that one.'),
    ('定语从句', '定语从句修饰名词或代词。先行词指人时可用 who，指物时可用 which，that 可以指人或物。关系词在从句中作主语时不能省略。例句：The boy who is reading is my friend. The book that I bought yesterday is useful.'),
    ('被动语态', '被动语态的基本结构是 be 加过去分词，强调动作的承受者。一般现在时为 am、is、are 加过去分词，一般过去时为 was、were 加过去分词。动作执行者可以通过 by 引出。例句：English is spoken in many countries. The window was cleaned yesterday.'),
]


def assert_demo():
    settings = get_settings()
    if settings.MYSQL_HOST not in ('127.0.0.1', 'localhost', '::1') or (settings.MYSQL_DATABASE, settings.WORDS_DATABASE, settings.MILVUS_DATABASE) != (
        'elearning_agent_dev', 'elearning_agent_words_dev', 'elearning_agent_demo'):
        raise RuntimeError('Only the isolated teaching demo databases are allowed')
    return settings


async def seed():
    assert_demo()
    password = os.environ.get('TEACHING_DEMO_PASSWORD', '')
    if len(password) < 12:
        raise RuntimeError('Set TEACHING_DEMO_PASSWORD to a private password of at least 12 characters')
    async with async_session() as db:
        version = (await db.execute(text('SELECT version_num FROM alembic_version'))).scalar()
        if version != 'agent_0001':
            raise RuntimeError('Apply the independent demo migration first')
        if (await db.execute(select(User.id).where(User.account.like('demo_%')).limit(1))).first():
            raise RuntimeError('Demo accounts already exist; refusing to overwrite data')
        hashed = pwd_context.hash(password)
        for i in range(2):
            teacher, classroom, document = 70001+i, 80001+i, 90001+i
            db.add(User(id=teacher, openid=f'synthetic_teacher_{i}', account=f'demo_teacher_{i+1}',
                nickname=f'演示教师{i+1}', password_hash=hashed, role='teacher'))
            db.add(Class(id=classroom, name=f'合成演示班级{i+1}', invite_code=f'AGENTDEMO{i+1}',
                created_by=teacher, stage=2, student_count=2))
            db.add(ClassTeacher(id=81001+i, class_id=classroom, teacher_id=teacher))
            for j in range(2):
                student = 71001+i*2+j
                db.add(User(id=student, openid=f'synthetic_student_{i}_{j}', account=f'demo_student_{i*2+j+1}',
                    nickname=f'合成学生{i*2+j+1}', password_hash=hashed, role='student'))
                db.add(ClassStudent(id=82001+i*2+j, class_id=classroom, student_id=student))
            db.add(UserDocument(id=document, user_id=teacher, class_id=classroom, filename='自编英语复习材料.txt',
                file_type='txt', storage_key=f'demo/{document}', parse_status=2, vector_status=0,
                parsed_text='\f'.join(f'{title}\n{content}' for title, content in PAGES), doc_category='textbook'))
            for exam_number in range(2):
                exam_id = 100001+i*2+exam_number
                questions = [{'type': 'choice', 'stem': f'Yesterday she {n} __ the museum.',
                    'options': ['visited', 'visits', 'visit', 'visiting'], 'answer': 'A',
                    'score': 5, 'knowledge_point': PAGES[0][0], 'explanation': 'yesterday 表示过去。'} for n in range(3)]
                db.add(TeacherExam(id=exam_id, teacher_id=teacher, class_id=classroom,
                    title=f'合成历史考试{exam_number+1}', questions=questions, total_score=15, status='done',
                    grade='七年级', published_at=datetime.now(), submission_count=2))
                for j in range(2):
                    db.add(ExamSubmission(id=110001+i*4+exam_number*2+j, exam_id=exam_id,
                        student_id=71001+i*2+j, answers=[{'question_index': n, 'answer': 'B'} for n in range(3)],
                        score=0, max_score=15, adjusted_score=0, submitted_at=datetime.now(),
                        grading_status='teacher_reviewed', ai_grade_detail=[{'score': 0, 'max_score': 5,
                            'is_correct': False, 'comment': '需要复习过去时'} for _ in range(3)]))
        await db.commit()
    print('Seeded 2 synthetic teachers, 2 classes, 4 students, 4 exams, 8 graded submissions, 2 paginated materials.')


async def index():
    assert_demo()
    async with async_session() as db:
        documents = (await db.execute(select(UserDocument).where(UserDocument.id.in_([90001, 90002])))).scalars().all()
        if len(documents) != 2:
            raise RuntimeError('Seed materials first')
        for document in documents:
            if document.vector_status == 2:
                continue
            chunks = [{'content': page, 'source_type': 'doc_textbook', 'source_id': document.id,
                'class_id': document.class_id, 'doc_title': document.filename, 'doc_category': 'textbook',
                'chunk_id': f'{document.id}_p{number}', 'level': 2, 'chunk_order': number}
                for number, page in enumerate(document.parsed_text.split('\f'), 1)]
            count = await EmbeddingService.index_chunks_batch(db, EmbeddingService.TEACHER_DOCUMENTS,
                chunks, user_id=document.user_id)
            if count != len(chunks):
                raise RuntimeError('Indexing did not complete; SQL material status remains unindexed')
            document.vector_status, document.chunk_count = 2, count
        await db.commit()
    print('Synthetic paginated materials indexed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', action='store_true', help='Index existing demo materials with configured services')
    args = parser.parse_args()
    asyncio.run(index() if args.index else seed())

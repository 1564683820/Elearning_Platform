# -*- coding: utf-8 -*-
"""检查数据库迁移状态"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from sqlalchemy import text
from app.db.database import async_session, engine

async def check():
    try:
        async with engine.connect() as conn:
            r = await conn.execute(text("SELECT 1 FROM wrong_question_book LIMIT 0"))
            print("[OK] wrong_question_book 表存在")
    except Exception as e:
        print(f"[FAIL] wrong_question_book 表不存在 ({str(e)[:50]})")

    try:
        async with engine.connect() as conn:
            r = await conn.execute(text("SELECT 1 FROM exam_scan_record LIMIT 0"))
            print("[OK] exam_scan_record 表存在")
    except Exception as e:
        print(f"[FAIL] exam_scan_record 表不存在 ({str(e)[:50]})")

    try:
        async with engine.connect() as conn:
            r = await conn.execute(text("SELECT scan_image_url FROM exam_submission LIMIT 0"))
            print("[OK] exam_submission 扩展字段存在")
    except Exception as e:
        print(f"[FAIL] exam_submission 缺少扫描批卷扩展字段 ({str(e)[:50]})")

    try:
        async with engine.connect() as conn:
            r = await conn.execute(text("SELECT id, title, status, class_id FROM teacher_exam WHERE status IN ('published','grading','done') LIMIT 5"))
            exams = r.all()
            print(f"\n已发布试卷: {len(exams)} 个")
            for e in exams:
                r2 = await conn.execute(text("SELECT answer_sheet_config IS NOT NULL and answer_sheet_config!='null' FROM teacher_exam WHERE id=:id"),{"id":e[0]})
                config = r2.scalar()
                print(f"  ID={e[0]} '{e[1]}' status={e[2]} config={'YES' if config else 'NO'}")
    except Exception as e:
        print(f"检查试卷失败: {e}")

loop = asyncio.ProactorEventLoop()
asyncio.set_event_loop(loop)
try:
    loop.run_until_complete(check())
finally:
    loop.close()

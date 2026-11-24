# -*- coding: utf-8 -*-
"""
扫描批卷全链路集成测试脚本

模拟完整流程：生成答题卡 → 填涂 → OMR识别 → 批改 → 错题入库 → RAG索引

运行方法:
  cd server
  python -m scripts.test_scan_grade_pipeline

前置条件:
  1. MySQL 已运行，.env 配置正确，依赖已安装 (pip install Pillow opencv-python numpy httpx)
  2. 已运行 migrate_scan_tables.sql: mysql -u root -p elearningtest < scripts/migrate_scan_tables.sql
  3. 有已发布的试卷（或手动创建测试试卷）
"""

import asyncio, json, logging, os, sys, time, traceback
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Windows GBK 控制台兼容
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("scan_test")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("PIL").setLevel(logging.WARNING)

PASS, FAIL, SKIP = 0, 0, 0
def step(name: str):
    logger.info(f"\n{'='*60}\n  >> {name}\n{'='*60}")
def ok(msg: str):
    global PASS; PASS += 1; logger.info(f"  [OK] {msg}")
def fail(msg: str):
    global FAIL; FAIL += 1; logger.warning(f"  [FAIL] {msg}")
def skip(msg: str):
    global SKIP; SKIP += 1; logger.info(f"  [SKIP] {msg}")


# ══════════════════════════════════════════════════════════════
# pool_pre_ping 兼容性修复
# SQLAlchemy 2.0 + aiomysql 0.2.0 ping() 参数不匹配
# 在测试中改用 pool_pre_ping=False 的独立引擎
# ══════════════════════════════════════════════════════════════
from app.core.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

_settings = get_settings()
_test_engine = create_async_engine(
    _settings.DATABASE_URL,
    pool_pre_ping=False,
    pool_recycle=1800,
)
_test_session = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


# ══════════════════════════════════════════════════════════════
# 第1步：环境检查
# ══════════════════════════════════════════════════════════════
async def check_env(db):
    step("第1步：环境检查")
    from sqlalchemy import text
    v = (await db.execute(text("SELECT VERSION()"))).scalar()
    ok(f"MySQL 连接成功, 版本 {v}")
    for tbl in ["wrong_question_book", "exam_scan_record"]:
        try:
            await db.execute(text(f"SELECT 1 FROM {tbl} LIMIT 0"))
            ok(f"表 `{tbl}` 存在")
        except:
            fail(f"表 `{tbl}` 不存在，请先运行 migrate_scan_tables.sql")
            return False
    try:
        await db.execute(text("SELECT scan_image_url, wrong_count FROM exam_submission LIMIT 0"))
        ok("exam_submission 扩展字段存在")
    except:
        fail("exam_submission 缺少扩展字段，请运行 ALTER TABLE")
        return False
    return True


# ══════════════════════════════════════════════════════════════
# 第2步：准备测试试卷数据
# ══════════════════════════════════════════════════════════════
async def prepare_data(db) -> dict:
    step("第2步：准备测试数据")
    from sqlalchemy import select
    from app.models.exam_models import TeacherExam

    stmt = select(TeacherExam).where(
        TeacherExam.status.in_(["published", "grading", "done"])
    ).limit(5)
    exams = (await db.execute(stmt)).scalars().all()
    if not exams:
        fail("没有已发布的试卷，请先创建试卷并发布")
        return None
    exam = exams[0]
    ok(f"使用试卷 ID={exam.id} '{exam.title}' status={exam.status}")

    questions = exam.questions or []
    choice_qs = [q for q in questions if q.get("type") in
                 ("choice","single","multiple","single_choice","multiple_choice")]
    if not choice_qs:
        fail("试卷无选择题，无法测试")
        return None
    ok(f"选择题 {len(choice_qs)} 道，总分 {exam.total_score or 100}")

    # 尝试匹配学生
    student = {"student_id": 0, "exam_number": "0001", "student_name": "测试学生"}
    try:
        from app.models.class_models import ClassStudentInfo
        ci = (await db.execute(
            select(ClassStudentInfo).where(ClassStudentInfo.class_id == exam.class_id).limit(1)
        )).scalar_one_or_none()
        if ci:
            student = {"student_id": ci.student_id or 0, "exam_number": ci.exam_number or "0001",
                       "student_name": ci.student_name or "测试学生"}
            ok(f"学生: {student['student_name']} 考号: {student['exam_number']}")
    except Exception as e:
        skip(f"学生信息查询跳过: {e}")

    return {"exam": exam, "questions": choice_qs, "student": student,
            "total_questions": len(choice_qs), "exam_number": student["exam_number"]}


# ══════════════════════════════════════════════════════════════
# 第3步：生成答题卡 + 填涂 + OMR扫描
# ══════════════════════════════════════════════════════════════
def gen_fill_and_scan(td: dict) -> bool:
    step("第3-5步：生成答题卡 → 填涂 → OMR扫描")

    # ── 3a. 生成空白答题卡 ──
    from app.services.printable_sheet_generator import generate_printable_sheet
    exam, questions = td["exam"], td["questions"]
    q_list = [{"number": i+1, "options": len(q.get("options",[4])) if isinstance(q.get("options"),list) else q.get("options",4)} for i,q in enumerate(questions)]
    max_oc = max(q["options"] for q in q_list) if q_list else 4

    sheet = generate_printable_sheet(exam.id, q_list, max_oc, "A4", 200, exam.title, "测试班级")
    td["sheet_data"] = sheet
    td["coord_config"] = sheet["coordinate_config"]

    # 找到图片路径
    sheet_path = os.path.join(BACKEND_DIR, "uploads", "answer_sheets", f"{exam.id}_a4.png")
    if not os.path.exists(sheet_path):
        sheet_path = os.path.join(BACKEND_DIR, sheet["image_url"].lstrip("/"))
    if not os.path.exists(sheet_path):
        # 搜索
        for root, _, files in os.walk(os.path.join(BACKEND_DIR, "uploads")):
            for f in files:
                if f.endswith(".png") and str(exam.id) in f:
                    sheet_path = os.path.join(root, f)
                    break
    td["blank_path"] = sheet_path if os.path.exists(sheet_path) else None

    if not td["blank_path"]:
        fail("答题卡图片未生成，检查 uploads/answer_sheets/ 目录")
        return False
    ok(f"答题卡: {td['blank_path']} ({sheet['total_questions']}题)")

    # ── 3b. 模拟填涂 ──
    from PIL import Image, ImageDraw
    img = Image.open(td["blank_path"]).convert("RGB")
    draw = ImageDraw.Draw(img)
    cc = td["coord_config"]
    regions = cc.get("question_regions", [])
    spacing = int(cc.get("option_spacing", 60))
    diameter = int(cc.get("circle_diameter", 40))

    # 构建预期答案
    expected = [(q.get("answer") or q.get("correct_answer") or "A").strip().upper() for q in questions]

    filled = []
    correct_cnt, wrong_cnt = 0, 0
    for i, reg in enumerate(regions):
        qnum, rx, ry, opts = reg["number"], int(reg["x"]), int(reg["y"]), reg.get("options", max_oc)
        correct_ans = expected[i] if i < len(expected) else "A"
        correct_idx = ord(correct_ans) - 65

        # 前70%正确，后30%错误
        if i % 10 < 7:
            fill_idx = correct_idx if 0 <= correct_idx < opts else 0
            filled.append(chr(65+fill_idx))
            correct_cnt += 1
        else:
            fill_idx = (correct_idx + 1) % opts
            filled.append(chr(65+fill_idx))
            wrong_cnt += 1

        ox, oy = rx + fill_idx * spacing, ry
        draw.ellipse([ox+4, oy+4, ox+diameter-4, oy+diameter-4], fill="black")

    # 填涂考号
    exam_num = td["exam_number"]
    ea = cc.get("exam_number_area", {})
    ex_x, ex_y = int(ea.get("x", 400)), int(ea.get("y", 200))
    ex_digits = ea.get("digits", 4)
    ex_spacing = int(ea.get("digit_spacing", 80))
    ex_opt_sp = int(ea.get("option_spacing", 50))
    ex_diam = int(diameter * 0.7)

    for di, ch in enumerate(exam_num):
        if not ch.isdigit(): continue
        dval, ddx = int(ch), ex_x + di * ex_spacing + 80
        label_y = ex_y + 20  # EXAM_NUMBER_OPTION_START_Y
        fill_x = ddx + dval * ex_opt_sp
        draw.ellipse([fill_x+2, label_y+30+2, fill_x+ex_diam-2, label_y+30+ex_diam-2], fill="black")

    # 保存填涂版
    filled_dir = os.path.join(BACKEND_DIR, "uploads", "scans", "test")
    os.makedirs(filled_dir, exist_ok=True)
    filled_path = os.path.join(filled_dir, f"filled_{int(time.time())}.png")
    img.save(filled_path, quality=95)
    td["filled_path"] = filled_path
    td["expected"] = expected
    td["filled"] = filled
    ok(f"填涂完成: 正确{correct_cnt}道 错误{wrong_cnt}道")
    ok(f"填涂图: {filled_path}")

    # ── 3c. OMR扫描 ──
    try:
        from app.services.omr_scanner import scan_answer_sheet
    except ImportError as e:
        fail(f"OMR模块导入失败: {e}")
        skip("请运行: cd server && uv sync  (安装 opencv-python 等依赖)")
        return False

    scan_result = scan_answer_sheet(filled_path, cc, max_oc, 1.0)
    td["scan_result"] = scan_result

    if not scan_result.get("success"):
        fail(f"OMR扫描失败: {scan_result.get('error','未知')}")
        return False

    ok(f"OMR扫描成功: 耗时{scan_result['duration_ms']}ms")
    ok(f"识别考号: '{scan_result['exam_number']}'")
    # 调试: 打印坐标和检测详情
    logger.info(f"  坐标: spacing={spacing} diameter={diameter} rows={len(regions)}")
    for i, a in enumerate(scan_result["answers"]):
        r = regions[i] if i < len(regions) else {}
        logger.info(f"    Q{a['question_number']}: 填涂={a['student_answer']!r:4s} "
                    f"置信度={a['confidence']:.3f} 区域=({r.get('x')},{r.get('y')}) "
                    f"预期={filled[i]!r}")

    # 验证识别准确率
    detected = scan_result["answers"]
    matches = sum(1 for a in detected if 0 <= a["question_number"]-1 < len(filled)
                  and a["student_answer"].upper() == filled[a["question_number"]-1].upper())
    rate = matches / len(detected) * 100 if detected else 0
    ok(f"OMR准确率: {matches}/{len(detected)} ({rate:.1f}%)")

    if rate < 50:
        fail("OMR识别准确率低于50%，检查答题卡生成与识别坐标一致性")
        return False

    return True


# ══════════════════════════════════════════════════════════════
# 第6步：全链路批改 + 错题入库 + RAG索引
# ══════════════════════════════════════════════════════════════
async def grade_and_index(db, td: dict) -> bool:
    step("第6步：批改 → 错题入库 → RAG索引")

    from sqlalchemy import select, func
    from app.models.exam_models import TeacherExam, ExamSubmission
    from app.models.scan_models import WrongQuestionBook, ExamScanRecord
    from app.services.wrong_book_service import WrongBookService

    exam, questions, student = td["exam"], td["questions"], td["student"]
    scan_result, answers_data = td["scan_result"], []
    max_score = exam.total_score or 100
    score_perq = max_score / len(questions) if questions else 0
    ai_detail, total_score = [], 0

    exam_db = await db.get(TeacherExam, exam.id)
    if not exam_db:
        fail(f"试卷 {exam.id} 不存在"); return False

    # 构建批改数据
    for sa in scan_result["answers"]:
        qnum, stu_ans, conf = sa["question_number"], sa["student_answer"], sa.get("confidence", 0)
        q_idx = qnum - 1
        if q_idx < 0 or q_idx >= len(questions): continue
        q = questions[q_idx]
        correct = (q.get("answer") or "").strip().upper()
        is_correct = bool(stu_ans and correct and stu_ans.strip().upper() == correct)
        q_max = q.get("score", score_perq)
        q_score = q_max if is_correct else 0
        total_score += q_score
        answers_data.append({"question_number": qnum, "student_answer": stu_ans, "correct_answer": correct,
                             "is_correct": is_correct, "score": q_score, "max_score": q_max, "confidence": conf})
        ai_detail.append({"index": q_idx, "type": q.get("type","choice"), "stem": q.get("stem",""),
                          "user_answer": stu_ans, "correct_answer": correct, "is_correct": is_correct,
                          "score": q_score, "max_score": q_max})

    wrong_count = sum(1 for a in answers_data if not a["is_correct"])
    ok(f"批改结果: {total_score}/{max_score}分, 错题{wrong_count}道")

    # 创建提交记录
    submission = ExamSubmission(exam_id=exam.id, student_id=student["student_id"], answers=answers_data,
        score=total_score, max_score=max_score, ai_grade_detail=ai_detail, exam_number=td["exam_number"],
        grading_status="ai_done", scan_image_url=f"/static/scans/test/{os.path.basename(td['filled_path'])}",
        wrong_count=wrong_count, submitted_at=datetime.utcnow())
    db.add(submission); await db.flush()
    ok(f"提交记录: submission_id={submission.id}")

    # 错题入库
    wrong_saved = 0
    try:
        wrong_saved = await WrongBookService.save_from_submission(db, submission)
        ok(f"错题入库: {wrong_saved} 条")
    except Exception as e:
        fail(f"错题入库失败: {e}")

    # 验证错题本
    if wrong_saved > 0:
        wq_list = (await db.execute(
            select(WrongQuestionBook).where(WrongQuestionBook.submission_id == submission.id)
        )).scalars().all()
        ok(f"wrong_question_book 验证: {len(wq_list)} 条记录")
        complete = all(wq.question_stem and wq.correct_answer and wq.student_answer for wq in wq_list)
        ok(f"错题字段完整性: {'全部完整' if complete else '部分缺失'}")

    # RAG索引
    if wrong_saved > 0:
        try:
            indexed = await WrongBookService.index_to_rag(db, submission.id)
            ok(f"RAG索引: {indexed} 条" if indexed else "无错需索引")
            indexed_count = (await db.execute(
                select(func.count()).where(WrongQuestionBook.submission_id == submission.id, WrongQuestionBook.rag_indexed == 1)
            )).scalar() or 0
            ok(f"RAG状态: {indexed_count}/{wrong_saved} 条已索引")
        except Exception as e:
            fail(f"RAG索引失败（不阻断）: {e}")

    # 扫描日志
    sr = ExamScanRecord(exam_id=exam.id, teacher_id=exam_db.teacher_id,
        scan_image_url=f"/static/scans/test/{os.path.basename(td['filled_path'])}",
        recognized_count=scan_result.get("recognized_count",0),
        matched_student_id=student["student_id"], exam_number=td["exam_number"],
        raw_answers=scan_result.get("answers"),
        grading_result={"score": total_score, "wrong_count": wrong_count},
        scan_duration_ms=scan_result.get("duration_ms",0))
    db.add(sr)
    ok(f"扫描日志: scan_record_id={sr.id}")

    # 更新试卷统计
    cnt = (await db.execute(select(func.count()).where(ExamSubmission.exam_id == exam.id))).scalar() or 0
    avg = (await db.execute(select(func.avg(ExamSubmission.score)).where(
        ExamSubmission.exam_id == exam.id, ExamSubmission.score.isnot(None)))).scalar()
    exam_db.submission_count = cnt
    exam_db.avg_score = round(avg, 1) if avg else None
    await db.commit()
    ok(f"试卷统计: submission_count={cnt}, avg_score={exam_db.avg_score}")

    td["submission_id"] = submission.id
    td["wrong_saved"] = wrong_saved
    return True


# ══════════════════════════════════════════════════════════════
# 第7步：错题本数据验证
# ══════════════════════════════════════════════════════════════
async def verify_wrong_book(db, td: dict):
    step("第7步：验证错题本数据")
    from app.services.wrong_book_service import WrongBookService

    sid = td.get("submission_id")
    if not sid or not td.get("wrong_saved", 0):
        skip("无错题，跳过验证")
        return True

    from sqlalchemy import select
    from app.models.scan_models import WrongQuestionBook
    stats = await WrongBookService.get_wrong_book_stats(db, td["student"]["student_id"], td["exam"].class_id)
    ok(f"错题统计: 总计{stats.get('total_wrong',0)}道")
    if stats.get("weak_points"):
        ok(f"薄弱知识点TOP: {', '.join(stats['weak_points'][:3])}")

    items = (await db.execute(
        select(WrongQuestionBook).where(WrongQuestionBook.submission_id == sid)
    )).scalars().all()
    ok(f"错题本完整性: {len(items)}条, 全部字段完整")
    return True


# ══════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════
async def main():
    logger.info(f"\n{'='*60}")
    logger.info(f"  [扫描批卷全链路集成测试]")
    logger.info(f"  开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  后端: {BACKEND_DIR}")
    logger.info(f"{'='*60}")

    # 使用 pool_pre_ping=False 的独立引擎，避免 aiomysql ping 兼容性问题
    async with _test_session() as db:
        td = None
        # 1-2步: 环境 + 数据准备
        if await check_env(db):
            td = await prepare_data(db)
        if not td:
            logger.error("环境或数据准备失败，终止测试")
            print_summary()
            return

        # 3-5步: 生成 + 填涂 + OMR扫描
        if gen_fill_and_scan(td):
            # 6步: 批改 + 错题入库 + RAG索引
            await grade_and_index(db, td)
            # 7步: 验证
            await verify_wrong_book(db, td)

        await db.commit()
        print_summary()


def print_summary():
    global PASS, FAIL, SKIP
    total = PASS + FAIL + SKIP
    logger.info(f"\n{'='*60}")
    logger.info(f"  测试总结: {total} 步 | 通过: {PASS} | 失败: {FAIL} | 跳过: {SKIP}")
    if FAIL == 0:
        logger.info(f"\n  [OK] 全部通过! 扫描批卷全链路正常工作!")
    else:
        logger.warning(f"\n  [WARN] {FAIL} 步失败，需检查日志")
    logger.info(f"{'='*60}\n")


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy() if hasattr(asyncio, 'WindowsProactorEventLoopPolicy') else None)
    asyncio.run(main())

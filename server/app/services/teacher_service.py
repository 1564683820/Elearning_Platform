# 教师端业务逻辑服务
# 班级管理、数据统计、权限校验
import io
import logging
import secrets
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete as sa_delete
from app.models.user import User
from app.models.class_models import Class, ClassStudent, ClassTeacher, ClassStudentInfo
from app.models.exam_models import ExamSubmission, TeacherExam
from app.models.quiz import WrongQuestion, UserQuizLog
from app.models.stats import UserDailyStat, LearningBehaviorLog
from app.schemas.teacher import (
    ClassCreate, ClassOut, ClassDashboard, StudentOut, StudentDetail,
    StudentInfoItem, StudentInfoUploadResult, AIQueryResponse,
    StudentExamMistakesOut, StudentExamResult, WrongQuestionItem,
)


def _generate_invite_code() -> str:
    """生成8位邀请码（字母+数字）"""
    return secrets.token_hex(4).upper()


class TeacherService:
    """教师端核心服务：班级管理、数据统计"""

    @staticmethod
    async def create_class(
        db: AsyncSession, teacher_id: int, body: ClassCreate
    ) -> ClassOut:
        """教师创建班级，自动生成唯一邀请码"""
        invite_code = _generate_invite_code()
        cls = Class(
            name=body.name,
            description=body.description,
            stage=body.stage,
            invite_code=invite_code,
            created_by=teacher_id,
        )
        db.add(cls)
        await db.flush()
        await db.refresh(cls)  # 强制加载所有 server_default 属性

        # 自动将教师添加为班级教师
        ct = ClassTeacher(class_id=cls.id, teacher_id=teacher_id, role="teacher")
        db.add(ct)
        await db.flush()

        return ClassOut.model_validate(cls)

    @staticmethod
    async def list_my_classes(
        db: AsyncSession, teacher_id: int
    ) -> list[ClassOut]:
        """获取教师管理的所有班级"""
        stmt = (
            select(Class)
            .join(ClassTeacher, ClassTeacher.class_id == Class.id)
            .where(ClassTeacher.teacher_id == teacher_id)
            .order_by(Class.created_at.desc())
        )
        result = await db.execute(stmt)
        classes = result.scalars().all()
        return [ClassOut.model_validate(c) for c in classes]

    @staticmethod
    async def get_class_detail(
        db: AsyncSession, class_id: int, teacher_id: int, is_admin: bool = False
    ) -> ClassOut | None:
        """获取单个班级详情，校验教师权限"""
        cls = await TeacherService._verify_class_ownership(db, class_id, teacher_id, is_admin)
        return ClassOut.model_validate(cls) if cls else None

    @staticmethod
    async def update_class(
        db: AsyncSession, class_id: int, teacher_id: int, body: dict,
        is_admin: bool = False,
    ) -> ClassOut | None:
        """更新班级信息"""
        cls = await TeacherService._verify_class_ownership(db, class_id, teacher_id, is_admin)
        if not cls:
            return None
        for key, value in body.items():
            if hasattr(cls, key) and value is not None:
                setattr(cls, key, value)
        await db.flush()
        await db.refresh(cls)  # 确保更新后的 server_default 属性已加载
        return ClassOut.model_validate(cls)

    @staticmethod
    async def regenerate_invite_code(
        db: AsyncSession, class_id: int, teacher_id: int, is_admin: bool = False
    ) -> str:
        """重新生成班级邀请码"""
        cls = await TeacherService._verify_class_ownership(db, class_id, teacher_id, is_admin)
        if not cls:
            raise ValueError("班级不存在或无权限")
        cls.invite_code = _generate_invite_code()
        await db.flush()
        return cls.invite_code

    @staticmethod
    async def delete_class(
        db: AsyncSession, class_id: int, teacher_id: int, is_admin: bool = False
    ) -> None:
        """删除班级及其关联记录（ClassStudent + ClassTeacher）"""
        cls = await TeacherService._verify_class_ownership(db, class_id, teacher_id, is_admin)
        if not cls:
            raise ValueError("班级不存在或无权限")

        # 删除班级学生关联
        await db.execute(
            sa_delete(ClassStudent).where(ClassStudent.class_id == class_id)
        )

        # 删除班级教师关联
        await db.execute(
            sa_delete(ClassTeacher).where(ClassTeacher.class_id == class_id)
        )

        # 删除班级本身
        await db.delete(cls)
        await db.flush()

    @staticmethod
    async def get_class_students(
        db: AsyncSession, class_id: int, teacher_id: int,
        words_db: AsyncSession | None = None,
        is_admin: bool = False,
    ) -> list[StudentOut]:
        """获取班级学生列表及学习数据概要"""
        cls = await TeacherService._verify_class_ownership(db, class_id, teacher_id, is_admin)
        if not cls:
            return []

        stmt = (
            select(
                ClassStudent.id,
                ClassStudent.student_id,
                User.nickname,
                ClassStudent.joined_at,
            )
            .join(User, User.id == ClassStudent.student_id)
            .where(ClassStudent.class_id == class_id)
            .order_by(ClassStudent.joined_at.desc())
        )
        result = await db.execute(stmt)
        rows = result.all()

        students = []
        for row in rows:
            # 查询每个学生的统计数据（单词题数：题型 1,2）
            word_count = await db.execute(
                select(func.count()).where(
                    and_(
                        UserQuizLog.user_id == row.student_id,
                        UserQuizLog.question_type.in_([1, 2]),
                    )
                )
            )
            quiz_count = await db.execute(
                select(func.count()).where(
                    UserQuizLog.user_id == row.student_id
                )
            )
            correct_count = await db.execute(
                select(func.count()).where(
                    and_(
                        UserQuizLog.user_id == row.student_id,
                        UserQuizLog.is_correct == 1,
                    )
                )
            )
            days = await db.execute(
                select(func.count()).where(
                    UserDailyStat.user_id == row.student_id
                )
            )

            total_q = quiz_count.scalar() or 0
            total_c = correct_count.scalar() or 0
            students.append(StudentOut(
                id=row.id,
                student_id=row.student_id,
                nickname=row.nickname or "未知",
                joined_at=row.joined_at,
                total_words=word_count.scalar() or 0,
                total_training=total_q,
                avg_accuracy=round(total_c / total_q * 100, 1) if total_q > 0 else 0.0,
                study_days=days.scalar() or 0,
            ))
        return students

    @staticmethod
    async def remove_student(
        db: AsyncSession, class_id: int, student_id: int, teacher_id: int,
        is_admin: bool = False,
    ) -> bool:
        """从班级移除学生"""
        await TeacherService._verify_class_ownership(db, class_id, teacher_id, is_admin)
        stmt = select(ClassStudent).where(
            ClassStudent.class_id == class_id,
            ClassStudent.student_id == student_id,
        )
        result = await db.execute(stmt)
        cs = result.scalar_one_or_none()
        if not cs:
            return False
        await db.delete(cs)

        # 更新班级学生计数
        cls = await db.get(Class, class_id)
        if cls and cls.student_count > 0:
            cls.student_count -= 1
        await db.flush()
        return True

    @staticmethod
    async def get_class_dashboard(
        db: AsyncSession, class_id: int, teacher_id: int,
        words_db: AsyncSession | None = None,
        is_admin: bool = False,
    ) -> ClassDashboard:
        """获取班级数据看板"""
        cls = await TeacherService._verify_class_ownership(db, class_id, teacher_id, is_admin)
        if not cls:
            raise ValueError("班级不存在或无权限")

        # 获取班级学生ID列表
        stmt = select(ClassStudent.student_id).where(
            ClassStudent.class_id == class_id
        )
        result = await db.execute(stmt)
        student_ids = [r[0] for r in result.all()]
        student_count = len(student_ids)

        if student_count == 0:
            return ClassDashboard(
                class_id=class_id, class_name=cls.name, student_count=0
            )

        # 总单词题数（题型 1=选择填空, 2=选择翻译）
        word_total = await db.execute(
            select(func.count()).where(
                and_(
                    UserQuizLog.user_id.in_(student_ids),
                    UserQuizLog.question_type.in_([1, 2]),
                )
            )
        )
        # 总做题数
        quiz_total = await db.execute(
            select(func.count()).where(
                UserQuizLog.user_id.in_(student_ids)
            )
        )
        # 正确数
        correct_total = await db.execute(
            select(func.count()).where(
                and_(
                    UserQuizLog.user_id.in_(student_ids),
                    UserQuizLog.is_correct == 1,
                )
            )
        )
        total_q = quiz_total.scalar() or 0
        total_c = correct_total.scalar() or 0

        # 今日活跃人数
        today = datetime.now().date()
        active_today = await db.execute(
            select(func.count(func.distinct(LearningBehaviorLog.user_id))).where(
                and_(
                    LearningBehaviorLog.user_id.in_(student_ids),
                    func.date(LearningBehaviorLog.created_at) == today,
                )
            )
        )

        # 高频错题TOP5
        mistakes = await db.execute(
            select(WrongQuestion.knowledge_point, func.count().label("cnt"))
            .where(
                and_(
                    WrongQuestion.user_id.in_(student_ids),
                    WrongQuestion.knowledge_point.isnot(None),
                )
            )
            .group_by(WrongQuestion.knowledge_point)
            .order_by(func.count().desc())
            .limit(5)
        )
        top_mistakes = [
            {"knowledge_point": m[0], "count": m[1]} for m in mistakes.all()
        ]

        return ClassDashboard(
            class_id=class_id,
            class_name=cls.name,
            student_count=student_count,
            total_words=word_total.scalar() or 0,
            total_quiz=total_q,
            avg_accuracy=round(total_c / total_q * 100, 1) if total_q > 0 else 0.0,
            active_today=active_today.scalar() or 0,
            top_mistakes=top_mistakes,
        )

    @staticmethod
    async def get_student_detail(
        db: AsyncSession, class_id: int, student_id: int, teacher_id: int,
        words_db: AsyncSession | None = None,
        is_admin: bool = False,
    ) -> StudentDetail:
        """获取单个学生详细学习数据"""
        await TeacherService._verify_class_ownership(db, class_id, teacher_id, is_admin)

        user = await db.get(User, student_id)
        if not user:
            raise ValueError("学生不存在")

        # 加入天数
        cs = await db.execute(
            select(ClassStudent).where(
                ClassStudent.class_id == class_id,
                ClassStudent.student_id == student_id,
            )
        )
        cs_row = cs.scalar_one_or_none()
        joined_days = (
            (datetime.now().date() - cs_row.joined_at.date()).days
            if cs_row and cs_row.joined_at
            else 0
        )

        # 总单词题数（题型 1=选择填空, 2=选择翻译）
        word_total = await db.execute(
            select(func.count()).where(
                and_(
                    UserQuizLog.user_id == student_id,
                    UserQuizLog.question_type.in_([1, 2]),
                )
            )
        )
        # 做题数
        quiz_total = await db.execute(
            select(func.count()).where(UserQuizLog.user_id == student_id)
        )
        correct_total = await db.execute(
            select(func.count()).where(
                and_(
                    UserQuizLog.user_id == student_id,
                    UserQuizLog.is_correct == 1,
                )
            )
        )
        total_q = quiz_total.scalar() or 0
        total_c = correct_total.scalar() or 0

        # 各分类正确率
        cat_stmt = (
            select(
                WrongQuestion.category,
                func.count().label("total"),
                func.sum(WrongQuestion.mastered == 0).label("wrong"),
            )
            .where(
                and_(
                    WrongQuestion.user_id == student_id,
                    WrongQuestion.category.isnot(None),
                )
            )
            .group_by(WrongQuestion.category)
        )
        cat_result = await db.execute(cat_stmt)
        category_breakdown = []
        for row in cat_result.all():
            t = row.total or 0
            w = row.wrong or 0
            category_breakdown.append({
                "category": row.category,
                "total": t,
                "wrong": w,
                "accuracy": round((t - w) / t * 100, 1) if t > 0 else 0,
            })

        # 薄弱知识点
        weak = await db.execute(
            select(WrongQuestion.knowledge_point, func.count().label("cnt"))
            .where(
                and_(
                    WrongQuestion.user_id == student_id,
                    WrongQuestion.knowledge_point.isnot(None),
                    WrongQuestion.mastered == 0,
                )
            )
            .group_by(WrongQuestion.knowledge_point)
            .order_by(func.count().desc())
            .limit(10)
        )
        weakness_points = [
            {"knowledge_point": w[0], "count": w[1]} for w in weak.all()
        ]

        return StudentDetail(
            student_id=student_id,
            nickname=user.nickname or "未知",
            joined_days=joined_days,
            total_words=word_total.scalar() or 0,
            total_training=total_q,
            avg_accuracy=round(total_c / total_q * 100, 1) if total_q > 0 else 0.0,
            category_breakdown=category_breakdown,
            weakness_points=weakness_points,
        )

    @staticmethod
    async def ai_query(
        db: AsyncSession, class_id: int, question: str, teacher_id: int
    ) -> AIQueryResponse:
        """AI 自然语言查询：将教师口语问题转为数据分析结果"""
        from app.services.rag_service import RAGService

        answer = await RAGService.generate_nl_query_answer(
            db, class_id, question, teacher_id
        )
        return AIQueryResponse(
            answer=answer,
            data={"class_id": class_id, "question": question},
        )

    @staticmethod
    async def ai_query_stream(db: AsyncSession, class_id: int, question: str, teacher_id: int):
        """AI 自然语言查询 — SSE 流式版本"""
        from app.services.rag_service import RAGService

        async for event in RAGService.generate_nl_query_answer_stream(
            db, class_id, question, teacher_id
        ):
            yield event

    # ========== 学生信息 Excel 导入 ==========

    @staticmethod
    async def import_students_from_excel(
        db: AsyncSession, class_id: int, teacher_id: int,
        file_bytes: bytes, is_admin: bool = False,
        teacher_account: str = "",
    ) -> StudentInfoUploadResult:
        """解析 Excel 并导入学生信息，跳过重复考号，同时自动创建学生账号并入班"""
        await TeacherService._verify_class_ownership(db, class_id, teacher_id, is_admin)

        import openpyxl
        from app.core.security import hash_password
        logger.info(f"Excel upload: class_id={class_id}, received {len(file_bytes)} bytes, "
                     f"first 12 bytes={file_bytes[:12]!r}, teacher_account='{teacher_account}'")

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
        ws = wb.active
        if ws is None:
            raise ValueError("Excel 文件中没有工作表")

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise ValueError("Excel 文件为空")

        # 自动识别表头列：找包含"序号/姓名/考号"关键字的列
        header = rows[0]
        col_map: dict[str, int] = {}
        keywords = {"序号": "number", "姓名": "name", "考号": "exam"}
        for i, cell in enumerate(header):
            if cell is None:
                continue
            val = str(cell).strip()
            for kw, key in keywords.items():
                if kw in val:
                    col_map[key] = i
                    break

        # 如果没识别到，按前3列顺序：序号、姓名、考号
        if len(col_map) < 3:
            col_map = {"number": 0, "name": 1, "exam": 2}

        # 查询已有考号 → ClassStudentInfo 映射
        existing_result = await db.execute(
            select(ClassStudentInfo).where(
                ClassStudentInfo.class_id == class_id
            )
        )
        existing_infos: list[ClassStudentInfo] = list(existing_result.scalars().all())
        existing_exam_nums: set[str] = set(info.exam_number for info in existing_infos)
        # exam_number → ClassStudentInfo 映射，用于后续补建 User/ClassStudent
        exam_num_to_info: dict[str, ClassStudentInfo] = {
            info.exam_number: info for info in existing_infos
        }

        # 查询已有学生账号映射（account -> User 对象），用于去重和更新
        existing_account_result = await db.execute(
            select(User).where(User.role == "student")
        )
        existing_student_users: list[User] = list(existing_account_result.scalars().all())
        account_to_user: dict[str, User] = {}
        openid_to_user: dict[str, User] = {}
        for u in existing_student_users:
            if u.account:
                account_to_user[u.account] = u
            if u.openid:
                openid_to_user[u.openid] = u

        imported_count = 0
        skipped_count = 0
        imported_items: list[StudentInfoItem] = []

        for row_idx, row in enumerate(rows[1:], start=2):
            try:
                number_val = row[col_map["number"]]
                name_val = row[col_map["name"]]
                exam_val = row[col_map["exam"]]
            except IndexError:
                continue

            # 空行跳过
            if number_val is None or name_val is None or exam_val is None:
                continue

            student_number = int(number_val)
            student_name = str(name_val).strip()
            exam_number = str(exam_val).strip()
            if not student_name or not exam_number:
                continue

            # 如果 exam_number 已存在，仍需要确保 User + ClassStudent 记录存在（兼容旧数据）
            if exam_number in existing_exam_nums:
                existing_info = exam_num_to_info.get(exam_number)
                if existing_info:
                    # 确保学生有 User 和 ClassStudent 记录
                    account_prefix = teacher_account if teacher_account else f"c{class_id}"
                    student_account = f"{account_prefix}{existing_info.student_number:04d}"
                    fake_openid_guess = f"auto_{account_prefix}_{existing_info.student_number}"
                    existing_user = account_to_user.get(student_account) or openid_to_user.get(fake_openid_guess)
                    if not existing_user:
                        # 需要创建 User
                        student_user = User(
                            openid=fake_openid_guess,
                            account=student_account,
                            nickname=existing_info.student_name,
                            username=existing_info.student_name,
                            password_hash=hash_password("123456"),
                            role="student",
                            stage=0,
                        )
                        db.add(student_user)
                        await db.flush()
                        account_to_user[student_account] = student_user
                        openid_to_user[fake_openid_guess] = student_user
                        existing_user = student_user
                    # 确保 ClassStudent 关联存在
                    existing_cs = await db.execute(
                        select(ClassStudent).where(
                            ClassStudent.class_id == class_id,
                            ClassStudent.student_id == existing_user.id,
                        )
                    )
                    if not existing_cs.scalar_one_or_none():
                        cs = ClassStudent(
                            class_id=class_id,
                            student_id=existing_user.id,
                        )
                        db.add(cs)
                skipped_count += 1
                continue

            # 1. 创建或更新 ClassStudentInfo
            #    先查是否已存在相同 exam_number（安全网）
            existing_info = await db.execute(
                select(ClassStudentInfo).where(
                    ClassStudentInfo.class_id == class_id,
                    ClassStudentInfo.exam_number == exam_number,
                )
            )
            info = existing_info.scalar_one_or_none()
            if info:
                # 更新已有花名册记录
                info.student_number = student_number
                info.student_name = student_name
            else:
                info = ClassStudentInfo(
                    class_id=class_id,
                    student_number=student_number,
                    student_name=student_name,
                    exam_number=exam_number,
                )
                db.add(info)
            existing_exam_nums.add(exam_number)

            # 2. 学生账号管理（创建或更新 + 加入班级）
            # 若无 teacher_account，用 class_id 作为账号前缀
            account_prefix = teacher_account if teacher_account else f"c{class_id}"
            student_account = f"{account_prefix}{student_number:04d}"
            fake_openid_guess = f"auto_{account_prefix}_{student_number}"
            created_account = ""

            # 2a. 查找已有 User（按 account 或 openid 匹配）
            existing_user = account_to_user.get(student_account) or openid_to_user.get(fake_openid_guess)

            if existing_user:
                # 已有的学生账号 → 更新昵称/用户名，确保加入班级
                existing_user.nickname = student_name
                existing_user.username = student_name
                # 更新 password_hash（重置密码）
                existing_user.password_hash = hash_password("123456")

                # 检查是否已在该班级
                existing_cs = await db.execute(
                    select(ClassStudent).where(
                        ClassStudent.class_id == class_id,
                        ClassStudent.student_id == existing_user.id,
                    )
                )
                if not existing_cs.scalar_one_or_none():
                    cs = ClassStudent(
                        class_id=class_id,
                        student_id=existing_user.id,
                    )
                    db.add(cs)
                created_account = student_account
            else:
                # 新学生 → 创建账号
                student_user = User(
                    openid=fake_openid_guess,
                    account=student_account,
                    nickname=student_name,
                    username=student_name,
                    password_hash=hash_password("123456"),
                    role="student",
                    stage=0,
                )
                db.add(student_user)
                await db.flush()  # 获取 student_user.id

                # 加入班级
                cs = ClassStudent(
                    class_id=class_id,
                    student_id=student_user.id,
                )
                db.add(cs)

                # 更新本地缓存，避免同一批后续行重复创建
                account_to_user[student_account] = student_user
                openid_to_user[fake_openid_guess] = student_user
                created_account = student_account

            imported_count += 1
            imported_items.append(StudentInfoItem(
                student_number=student_number,
                student_name=student_name,
                exam_number=exam_number,
                created_account=created_account,
            ))

        await db.flush()

        # 更新班级学生计数
        cls_obj = await db.get(Class, class_id)
        if cls_obj:
            cs_count = await db.scalar(
                select(func.count()).select_from(ClassStudent).where(
                    ClassStudent.class_id == class_id
                )
            )
            cls_obj.student_count = cs_count or 0

        return StudentInfoUploadResult(
            total=len(rows) - 1,
            imported=imported_count,
            skipped=skipped_count,
            items=imported_items,
        )

    @staticmethod
    async def list_student_info(
        db: AsyncSession, class_id: int, teacher_id: int,
        is_admin: bool = False,
    ) -> list[StudentInfoItem]:
        """获取班级已导入的学生信息列表（含自动创建的登录账号）"""
        await TeacherService._verify_class_ownership(db, class_id, teacher_id, is_admin)

        # 1. 查班级学生花名册
        result = await db.execute(
            select(ClassStudentInfo)
            .where(ClassStudentInfo.class_id == class_id)
            .order_by(ClassStudentInfo.student_number)
        )
        items = result.scalars().all()
        if not items:
            return []

        # 2. 获取教师账号，用于推导学生账号命名
        teacher = await db.get(User, teacher_id)
        teacher_account = teacher.account if teacher and teacher.account else ""
        import logging
        logging.getLogger(__name__).info(
            f"list_student_info: class_id={class_id}, teacher_id={teacher_id}, "
            f"teacher_account='{teacher_account}', student_count={len(items)}"
        )

        # 3. 批量查询已创建的学生账号
        #    兼容：教师账号前缀 或 class_id 前缀（无教师账号时）
        account_prefix = teacher_account if teacher_account else f"c{class_id}"
        potential_accounts = set()
        for item in items:
            potential_accounts.add(f"{account_prefix}{item.student_number:04d}")
            potential_accounts.add(f"{account_prefix}{item.student_number:03d}")
        user_result = await db.execute(
            select(User.account).where(User.account.in_(list(potential_accounts)))
        )
        existing_accounts: set[str] = set(user_result.scalars().all())

        def _find_account(item) -> str:
            a4 = f"{account_prefix}{item.student_number:04d}"
            if a4 in existing_accounts:
                return a4
            a3 = f"{account_prefix}{item.student_number:03d}"
            return a3 if a3 in existing_accounts else ""

        return [
            StudentInfoItem(
                student_number=item.student_number,
                student_name=item.student_name,
                exam_number=item.exam_number,
                created_account=_find_account(item),
            )
            for item in items
        ]

    @staticmethod
    async def delete_student_info(
        db: AsyncSession, class_id: int, teacher_id: int,
        is_admin: bool = False,
    ) -> None:
        """清空班级已导入的学生信息"""
        await TeacherService._verify_class_ownership(db, class_id, teacher_id, is_admin)
        await db.execute(
            sa_delete(ClassStudentInfo).where(ClassStudentInfo.class_id == class_id)
        )
        await db.flush()

    # ========== 学生考试错题(OCR批卷) ==========

    @staticmethod
    async def get_student_exam_mistakes(
        db: AsyncSession, class_id: int, exam_number: str,
        teacher_id: int, is_admin: bool = False,
    ) -> StudentExamMistakesOut:
        """获取某学生（按考号）在班级所有考试中的错题"""
        await TeacherService._verify_class_ownership(db, class_id, teacher_id, is_admin)

        # 先找到学生信息
        result = await db.execute(
            select(ClassStudentInfo).where(
                ClassStudentInfo.class_id == class_id,
                ClassStudentInfo.exam_number == exam_number,
            )
        )
        student = result.scalar_one_or_none()
        if not student:
            raise ValueError("未找到该考号的学生信息")

        # 查询该班级所有考试中该考号的提交记录
        submissions = await db.execute(
            select(
                ExamSubmission, TeacherExam.title,
            )
            .join(TeacherExam, TeacherExam.id == ExamSubmission.exam_id)
            .where(
                ExamSubmission.exam_number == exam_number,
                TeacherExam.class_id == class_id,
                ExamSubmission.grading_status.in_(["ai_done", "teacher_reviewed"]),
            )
            .order_by(ExamSubmission.submitted_at.desc())
        )
        rows = submissions.all()

        exams_results: list[StudentExamResult] = []
        total_wrong = 0

        for sub, exam_title in rows:
            wrong_questions = []
            grade_detail = sub.ai_grade_detail or []

            for q in grade_detail:
                q_max = q.get("max_score", 0)
                q_score = q.get("score", 0) or 0
                is_correct = q.get("is_correct", False)

                # 判断是否为错题：非正确 或 得分不足70%
                if not is_correct or (q_max > 0 and q_score < q_max * 0.7):
                    wrong_questions.append(WrongQuestionItem(
                        question_index=q.get("index", 0),
                        question_type=q.get("type", ""),
                        stem=q.get("stem", ""),
                        user_answer=q.get("user_answer", ""),
                        correct_answer=q.get("correct_answer", ""),
                        max_score=q_max,
                        score=q_score,
                        ai_comment=q.get("ai_comment", ""),
                    ))

            total_wrong += len(wrong_questions)
            exams_results.append(StudentExamResult(
                exam_id=sub.exam_id,
                exam_title=exam_title,
                total_score=sub.score or 0,
                max_score=sub.max_score or 0,
                grading_status=sub.grading_status,
                submitted_at=sub.submitted_at,
                wrong_questions=wrong_questions,
            ))

        return StudentExamMistakesOut(
            student_number=student.student_number,
            student_name=student.student_name,
            exam_number=student.exam_number,
            exam_count=len(exams_results),
            total_wrong=total_wrong,
            exams=exams_results,
        )

    @staticmethod
    async def _verify_class_ownership(
        db: AsyncSession, class_id: int, teacher_id: int, is_admin: bool = False
    ) -> Class | None:
        """校验教师是否为班级的管理者（admin 跳过校验）"""
        if is_admin:
            return await db.get(Class, class_id)
        ct = await db.execute(
            select(ClassTeacher).where(
                ClassTeacher.class_id == class_id,
                ClassTeacher.teacher_id == teacher_id,
            )
        )
        if not ct.scalar_one_or_none():
            raise ValueError("无权操作该班级")
        return await db.get(Class, class_id)

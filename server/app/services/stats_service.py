import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.dialects.mysql import insert
from app.models.stats import UserDailyStat
from app.models.quiz import UserQuizLog, WrongQuestion
from app.schemas.common import DashboardStats, DailyStatOut
from app.utils.redis_client import get_redis, RedisCache
from datetime import date, timedelta


class StatsService:

    @staticmethod
    async def increment_quiz_stat(db: AsyncSession, user_id: int, is_correct: bool):
        """在调用方事务中原子更新当天做题统计，不单独提交。"""
        await StatsService._increment_daily(
            db, user_id, quiz_count=1, quiz_correct=int(is_correct))

    @staticmethod
    async def increment_word_stat(db: AsyncSession, user_id: int, is_review: bool = False):
        """更新每日统计（学习单词后调用）"""
        field = 'words_reviewed' if is_review else 'words_learned'
        await StatsService._increment_daily(db, user_id, **{field: 1})

    @staticmethod
    async def _increment_daily(db: AsyncSession, user_id: int, **deltas):
        # uk_user_date 已约束 (user_id, stat_date)，由 MySQL 串行处理同一行累加。
        statement = insert(UserDailyStat).values(
            user_id=user_id, stat_date=date.today(), **deltas)
        statement = statement.on_duplicate_key_update(**{
            field: getattr(UserDailyStat, field) + delta
            for field, delta in deltas.items()
        })
        await db.execute(statement)
        await db.flush()

        redis = await get_redis()
        cache = RedisCache(redis)
        # 无读取方的 daily hash 不再写入，避免把未提交计数发布到 Redis。
        await cache.delete(f"stats:dashboard:{user_id}")

    # 单词题型：1=选择填空, 2=选择翻译
    WORD_QUESTION_TYPES = [1, 2]

    @staticmethod
    async def get_dashboard(db: AsyncSession, user_id: int, words_db: AsyncSession | None = None) -> DashboardStats:
        """首页看板数据 — 缓存 5 分钟"""
        redis = await get_redis()
        cache = RedisCache(redis)

        cache_key = f"stats:dashboard:{user_id}"
        cached = await cache.get_json(cache_key)
        if cached is not None:
            return DashboardStats(**cached)

        today = date.today()
        week_ago = today - timedelta(days=6)

        # 今日单词题数（题型 1,2）
        word_today_result = await db.execute(
            select(func.count()).where(
                and_(
                    UserQuizLog.user_id == user_id,
                    UserQuizLog.question_type.in_(StatsService.WORD_QUESTION_TYPES),
                    func.date(UserQuizLog.created_at) == today,
                )
            )
        )
        words_learned_today = word_today_result.scalar() or 0

        # 本周单词题数
        word_week_result = await db.execute(
            select(func.count()).where(
                and_(
                    UserQuizLog.user_id == user_id,
                    UserQuizLog.question_type.in_(StatsService.WORD_QUESTION_TYPES),
                    func.date(UserQuizLog.created_at) >= week_ago,
                    func.date(UserQuizLog.created_at) <= today,
                )
            )
        )
        words_learned_week = word_week_result.scalar() or 0

        # 总单词题数
        total_words_result = await db.execute(
            select(func.count()).where(
                and_(
                    UserQuizLog.user_id == user_id,
                    UserQuizLog.question_type.in_(StatsService.WORD_QUESTION_TYPES),
                )
            )
        )
        total_words = total_words_result.scalar() or 0

        # 总做题数（所有题型）
        total_result = await db.execute(
            select(func.count()).where(UserQuizLog.user_id == user_id)
        )
        total_quiz_count = total_result.scalar() or 0

        correct_result = await db.execute(
            select(func.count()).where(
                UserQuizLog.user_id == user_id,
                UserQuizLog.is_correct == 1,
            )
        )
        correct_count = correct_result.scalar() or 0

        quiz_accuracy = round(correct_count / total_quiz_count * 100, 1) if total_quiz_count > 0 else 0

        data = DashboardStats(
            words_learned_today=words_learned_today,
            words_learned_week=words_learned_week,
            quiz_accuracy=quiz_accuracy,
            total_words=total_words,
            total_quiz_count=total_quiz_count,
        )

        await cache.set_json(cache_key, data.model_dump(), ex=300)
        return data

    @staticmethod
    async def get_daily_stats(
        db: AsyncSession, user_id: int, start_date: str = "", end_date: str = ""
    ) -> list[DailyStatOut]:
        """按日统计 — 缓存 10 分钟"""
        redis = await get_redis()
        cache = RedisCache(redis)

        cache_key = f"stats:daily_list:{user_id}:{start_date}:{end_date}"
        cached = await cache.get_json(cache_key)
        if cached is not None:
            return [DailyStatOut(**item) for item in cached]

        stmt = select(UserDailyStat).where(UserDailyStat.user_id == user_id)
        if start_date:
            stmt = stmt.where(UserDailyStat.stat_date >= start_date)
        if end_date:
            stmt = stmt.where(UserDailyStat.stat_date <= end_date)

        stmt = stmt.order_by(UserDailyStat.stat_date.desc()).limit(30)
        result = await db.execute(stmt)
        stats = result.scalars().all()

        items = [
            DailyStatOut(
                stat_date=str(s.stat_date),
                words_learned=s.words_learned,
                words_reviewed=s.words_reviewed,
                quiz_count=s.quiz_count,
                quiz_correct=s.quiz_correct,
                study_minutes=s.study_minutes,
            )
            for s in stats
        ]

        await cache.set_json(cache_key, [item.model_dump() for item in items], ex=600)
        return items

    @staticmethod
    async def get_weekly_stats(db: AsyncSession, user_id: int) -> dict:
        """按周统计 — 缓存 10 分钟"""
        redis = await get_redis()
        cache = RedisCache(redis)

        cache_key = f"stats:weekly:{user_id}"
        cached = await cache.get_json(cache_key)
        if cached is not None:
            return cached

        today = date.today()
        week_ago = today - timedelta(days=6)

        result = await db.execute(
            select(UserDailyStat).where(
                UserDailyStat.user_id == user_id,
                UserDailyStat.stat_date >= week_ago,
                UserDailyStat.stat_date <= today,
            ).order_by(UserDailyStat.stat_date.asc())
        )
        daily_stats = result.scalars().all()

        total_learned = sum(s.words_learned for s in daily_stats)
        total_reviewed = sum(s.words_reviewed for s in daily_stats)
        total_quiz = sum(s.quiz_count for s in daily_stats)
        total_correct = sum(s.quiz_correct for s in daily_stats)
        total_minutes = sum(s.study_minutes for s in daily_stats)

        data = {
            "words_learned": total_learned,
            "words_reviewed": total_reviewed,
            "quiz_count": total_quiz,
            "quiz_correct": total_correct,
            "study_minutes": total_minutes,
            "accuracy": round(total_correct / total_quiz * 100, 1) if total_quiz > 0 else 0,
            "daily_breakdown": [
                {"date": str(s.stat_date), "words_learned": s.words_learned, "quiz_count": s.quiz_count}
                for s in daily_stats
            ],
        }

        await cache.set_json(cache_key, data, ex=600)
        return data

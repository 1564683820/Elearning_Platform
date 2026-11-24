# 情景记忆视频生成服务
# 将单词情景文段转为视频，配套TTS配音和字幕
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.services.ai_service import AIService
from app.services.embedding_service import EmbeddingService
from app.core.config import get_settings

settings = get_settings()


class VideoService:
    """视频生成服务：管理视频生成任务的状态流转和资源管理"""

    @staticmethod
    async def generate_scene_video(
        db: AsyncSession,
        user_id: int,
        scenario_id: int,
        words: list[str],
        content: str,
    ) -> dict:
        """根据情景文段生成视频任务

        参数: db - 数据库会话
        user_id - 用户ID
        scenario_id - 情景文段ID
        words - 关联单词列表
        content - 文段文字内容

        返回: 包含视频任务ID和状态信息的字典，status=1表示已创建任务
        """
        from app.models.chat import ScenarioPassage

        # 查询已有情景文段
        result = await db.execute(
            select(ScenarioPassage).where(ScenarioPassage.id == scenario_id, ScenarioPassage.user_id == user_id)
        )
        scenario = result.scalar_one_or_none()
        if not scenario:
            raise ValueError("情景文段不存在")

        # 标记视频状态为生成中
        scenario.video_status = 1

        # 组装视频信息
        title = f"情景记忆 - {', '.join(words[:5])}{'...' if len(words) > 5 else ''}"
        video_info = {
            "scenario_id": scenario_id,
            "title": title,
            "words": words,
            "text": content,
            "status": "pending",  # pending/processing/completed/failed
        }

        await db.flush()
        return {
            "task_id": scenario_id,
            "title": title,
            "status": 1,
            "video_url": scenario.video_url or "",
        }

    @staticmethod
    async def get_video_status(db: AsyncSession, user_id: int, scenario_id: int) -> dict:
        """查询视频生成状态

        参数: db - 数据库会话
        user_id - 用户ID
        scenario_id - 情景文段ID

        返回: 视频状态信息
        """
        from app.models.chat import ScenarioPassage

        result = await db.execute(
            select(ScenarioPassage).where(ScenarioPassage.id == scenario_id, ScenarioPassage.user_id == user_id)
        )
        scenario = result.scalar_one_or_none()
        if not scenario:
            raise ValueError("情景文段不存在")

        return {
            "scenario_id": scenario.id,
            "video_url": scenario.video_url or "",
            "video_status": scenario.video_status,  # 0=未生成,1=生成中,2=已完成,3=失败
            "content": scenario.content,
        }

    @staticmethod
    async def list_user_videos(
        db: AsyncSession, user_id: int, page: int = 1, page_size: int = 20
    ) -> dict:
        """获取用户的情景记忆视频列表

        参数: db - 数据库会话
        user_id - 用户ID
        page - 页码，从1开始
        page_size - 每页数量，默认20

        返回: 视频列表分页数据
        """
        from app.models.chat import ScenarioPassage

        stmt = select(ScenarioPassage).where(
            ScenarioPassage.user_id == user_id,
        )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(ScenarioPassage.created_at.desc()).offset(offset).limit(page_size)
        result = await db.execute(stmt)
        scenarios = result.scalars().all()

        items = []
        for s in scenarios:
            items.append({
                "id": s.id,
                "content": s.content,
                "word_ids": s.word_ids,
                "video_url": s.video_url or "",
                "video_status": s.video_status,
                "passage_type": s.passage_type,
                "created_at": str(s.created_at),
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

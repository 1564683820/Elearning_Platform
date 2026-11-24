"""
长期记忆管理服务 — 教学助手的记忆层

支持四种记忆类型：
- preference: 教学偏好、关注领域（长期）
- topic_summary: 反复讨论的知识点总结（中期）
- class_note: 对某班级的观察记录（长期）
- teaching_style: 教学风格偏好（长期）
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_, and_, delete

from app.models.teacher_memory import TeacherMemory
from app.models.chat import ChatMessage
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

# 记忆容量上限
MAX_MEMORIES_PER_TEACHER = 200

# 衰减配置
DECAY_DAYS = 30          # 30天未访问触发的衰减
DECAY_FACTOR = 0.9       # 衰减因子
MIN_IMPORTANCE = 0.1     # 淘汰阈值

# 记忆提取 Prompt
MEMORY_EXTRACT_PROMPT = """你是一个教育领域的记忆提取助手。分析以下教师与教学助手的对话，判断是否有值得长期记忆的信息。

## 记忆类型说明
- **preference**: 教师的教学偏好、对某些教学方法的倾向、关注的特定领域
  - 例如：教师提到"我喜欢用情景法教语法"、"我对阅读教学特别关注"
- **topic_summary**: 教师反复讨论或特别关注的知识点/教学主题总结
  - 例如：教师多次询问"定语从句"相关内容，可以总结"该教师近期重点教授定语从句"
- **class_note**: 教师对某班级的观察、评价、教学策略
  - 例如："三班的学生语法基础较弱"、"二班的学生互动积极"
- **teaching_style**: 教师的教学风格、课堂管理方式等偏好
  - 例如："教师倾向于互动式教学"、"喜欢用游戏方式活跃课堂"

## 输出格式（严格JSON数组）
[
  {
    "type": "preference|topic_summary|class_note|teaching_style",
    "key": "简短的关键词（中文，不超过20字）",
    "value": "完整的记忆内容（不超过200字）",
    "importance": 0.5,
    "keywords": ["触发关键词1", "触发关键词2"]
  }
]

如果没有值得记忆的信息，返回空数组 []。

对话：
{dialogue_summary}"""


class MemoryService:
    """教学助手长期记忆管理"""

    @staticmethod
    async def get_relevant_memories(
        db: AsyncSession,
        teacher_id: int,
        query: str,
        limit: int = 5,
    ) -> list[TeacherMemory]:
        """获取与当前查询相关的长期记忆

        匹配策略：先按 trigger_keywords 关键词匹配，再按 importance 排序补全
        """
        if not teacher_id or not query:
            return []

        query_lower = query.lower()

        # 获取该教师所有活跃记忆
        result = await db.execute(
            select(TeacherMemory)
            .where(TeacherMemory.teacher_id == teacher_id)
            .order_by(desc(TeacherMemory.importance))
            .limit(MAX_MEMORIES_PER_TEACHER)
        )
        all_memories = result.scalars().all()

        if not all_memories:
            return []

        # 关键词匹配评分
        scored: list[tuple[TeacherMemory, float]] = []
        for mem in all_memories:
            score = mem.importance * 0.5  # 基础分 = 重要性加权

            # trigger_keywords 匹配加分
            keywords = mem.trigger_keywords or []
            if isinstance(keywords, list):
                for kw in keywords:
                    if kw.lower() in query_lower:
                        score += 0.3
                        break

            # memory_key + memory_value 全文匹配加分
            key_lower = (mem.memory_key or "").lower()
            value_lower = (mem.memory_value or "").lower()[:200]
            if any(word in key_lower or word in value_lower for word in query_lower.split()[:5]):
                score += 0.2

            # memory_type 加分
            type_boost = {
                "class_note": 0.1,
                "topic_summary": 0.15,
                "preference": 0.05,
                "teaching_style": 0.05,
            }
            score += type_boost.get(mem.memory_type, 0)

            scored.append((mem, score))

        # 按综合评分排序，取 top_k
        scored.sort(key=lambda x: x[1], reverse=True)
        top = [mem for mem, _ in scored[:limit]]

        # 更新访问计数（异步非阻塞）
        try:
            for mem in top:
                mem.access_count = (mem.access_count or 0) + 1
                mem.last_accessed_at = datetime.now()
        except Exception:
            pass

        return top

    @staticmethod
    async def upsert_memory(
        db: AsyncSession,
        teacher_id: int,
        memory_type: str,
        memory_key: str,
        memory_value: str,
        importance: float = 0.5,
        keywords: list[str] | None = None,
    ) -> TeacherMemory:
        """创建或更新记忆（容量控制）"""
        # 检查是否已存在相同的 teacher_id + memory_type + memory_key
        result = await db.execute(
            select(TeacherMemory).where(
                TeacherMemory.teacher_id == teacher_id,
                TeacherMemory.memory_type == memory_type,
                TeacherMemory.memory_key == memory_key,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # 更新已有记忆
            existing.memory_value = memory_value
            existing.importance = importance
            existing.trigger_keywords = keywords or existing.trigger_keywords
            existing.last_accessed_at = datetime.now()
            return existing

        # 容量控制
        count = await db.execute(
            select(func.count(TeacherMemory.id)).where(
                TeacherMemory.teacher_id == teacher_id,
            )
        )
        total = count.scalar() or 0
        if total >= MAX_MEMORIES_PER_TEACHER:
            # 淘汰最低 importance 的记忆
            await db.execute(
                delete(TeacherMemory)
                .where(
                    TeacherMemory.teacher_id == teacher_id,
                )
                .order_by(TeacherMemory.importance.asc())
                .limit(total - MAX_MEMORIES_PER_TEACHER + 1)
            )

        # 创建新记忆
        mem = TeacherMemory(
            teacher_id=teacher_id,
            memory_type=memory_type,
            memory_key=memory_key,
            memory_value=memory_value,
            importance=importance,
            trigger_keywords=keywords or [],
        )
        db.add(mem)
        await db.flush()
        await db.refresh(mem)
        return mem

    @staticmethod
    async def auto_create_from_conversation(
        db: AsyncSession,
        teacher_id: int,
        conversation_id: int,
    ) -> list[TeacherMemory]:
        """从最近对话中自动提取长期记忆

        Args:
            db: 数据库会话
            teacher_id: 教师ID
            conversation_id: 会话ID
        Returns:
            新创建的记忆列表
        """
        # 获取对话的最近消息
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(20)
        )
        messages = result.scalars().all()
        messages.reverse()

        if len(messages) < 2:
            return []

        # 构建对话摘要
        dialogue_lines = []
        for m in messages:
            role_name = "教师" if m.role == "user" else "教学助手"
            content = m.content[:300] if m.content else ""
            dialogue_lines.append(f"{role_name}: {content}")

        dialogue_text = "\n".join(dialogue_lines)
        if len(dialogue_text) > 3000:
            dialogue_text = dialogue_text[-3000:]

        prompt = MEMORY_EXTRACT_PROMPT.format(dialogue_summary=dialogue_text)

        try:
            raw = await AIService.chat_completion(
                db, [{"role": "user", "content": prompt}],
                user_id=teacher_id, max_tokens=1024,
            )
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            items = json.loads(text)
            if not isinstance(items, list):
                return []

            created = []
            for item in items:
                if not isinstance(item, dict) or not item.get("type") or not item.get("key"):
                    continue
                mem = await MemoryService.upsert_memory(
                    db=db,
                    teacher_id=teacher_id,
                    memory_type=item["type"],
                    memory_key=item["key"][:128],
                    memory_value=item.get("value", "")[:1000],
                    importance=float(item.get("importance", 0.5)),
                    keywords=item.get("keywords", []),
                )
                created.append(mem)

            return created
        except Exception as e:
            logger.warning(f"自动记忆提取失败: {e}")
            return []

    @staticmethod
    async def decay_memories(db: AsyncSession):
        """衰减与淘汰 — 30天未访问的记忆重要性衰减，低于阈值删除"""
        cutoff = datetime.now() - timedelta(days=DECAY_DAYS)

        # 查询长时间未访问的记忆
        result = await db.execute(
            select(TeacherMemory).where(
                or_(
                    TeacherMemory.last_accessed_at.is_(None),
                    TeacherMemory.last_accessed_at < cutoff,
                )
            )
        )
        stale = result.scalars().all()

        for mem in stale:
            # 衰减
            mem.importance = (mem.importance or 0.5) * DECAY_FACTOR
            if mem.importance < MIN_IMPORTANCE:
                await db.delete(mem)

        logger.info(f"记忆衰减完成: {len(stale)} 条处理")

    @staticmethod
    async def list_memories(
        db: AsyncSession,
        teacher_id: int,
        memory_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """获取教师的长期记忆列表"""
        stmt = select(TeacherMemory).where(TeacherMemory.teacher_id == teacher_id)
        if memory_type:
            stmt = stmt.where(TeacherMemory.memory_type == memory_type)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(desc(TeacherMemory.importance))
        stmt = stmt.order_by(desc(TeacherMemory.created_at)).offset(offset).limit(page_size)
        result = await db.execute(stmt)
        memories = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(m.id),
                    "memory_type": m.memory_type,
                    "memory_key": m.memory_key,
                    "memory_value": m.memory_value,
                    "importance": m.importance,
                    "trigger_keywords": m.trigger_keywords,
                    "access_count": m.access_count,
                    "created_at": m.created_at.isoformat() if m.created_at else "",
                    "updated_at": m.updated_at.isoformat() if m.updated_at else "",
                }
                for m in memories
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def delete_memory(
        db: AsyncSession,
        memory_id: int,
        teacher_id: int,
    ) -> bool:
        """删除指定记忆"""
        result = await db.execute(
            select(TeacherMemory).where(
                TeacherMemory.id == memory_id,
                TeacherMemory.teacher_id == teacher_id,
            )
        )
        mem = result.scalar_one_or_none()
        if not mem:
            return False
        await db.delete(mem)
        return True

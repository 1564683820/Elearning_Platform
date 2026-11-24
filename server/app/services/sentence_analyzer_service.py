"""
句子角色分析服务

功能:
- 将教材页面原始文本拆分为结构化分句
- AI 识别每句话的说话角色（speaker）
- 输出格式化的 sentences_json

典型输出:
[
  {"en": "Hello, I'm Mike.", "cn": "你好，我是迈克。", "speaker": "mike"},
  {"en": "Hi, I'm Amy.", "cn": "你好，我是艾米。", "speaker": "amy"},
  {"en": "Nice to meet you!", "cn": "很高兴认识你！", "speaker": "narrator"}
]
"""
import json
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.textbook_models import TextbookPage
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

# 系统提示词：引导 AI 分析课文分句及其说话的"角色"
_SENTENCE_ANALYZER_SYSTEM_PROMPT = """你是一个儿童英语教材编辑。请分析以下英语课文，完成两项任务：

1. 将课文拆分为完整的英文句子（按 . ! ? 等结尾标点分割）
2. 识别每句话的说话角色（speaker）:
   - 如果句子前有角色名冒号标记（如 "Mike: Hello"），speaker 取该角色名的英文小写
   - 如果上下文能推断出说话角色，如对话交替出现，按 Mike → Amy → Mike 模式分配
   - 如果是旁白/描述/标题/非对话内容，speaker 设为 "narrator"
   - 如果是教材页面标题或习题说明等非课文内容，speaker 设为 "narrator"

请返回 JSON 数组格式（不要包含其他文字）:
[
  {"en": "英文原句", "cn": "中文翻译", "speaker": "角色名小写"},
  {"en": "...", "cn": "...", "speaker": "..."}
]

注意事项:
- cn 字段为中文翻译（简洁通顺即可）
- speaker 使用英文小写，不含空格
- 每句都要有完整的中文翻译
- 如果无法确认角色，设为 "narrator"
- 对话场景中交替出现的句子，合理推断 speaker"""


class SentenceAnalyzerService:
    """句子角色分析服务：将原始文本拆分为带说话角色的结构化分句"""

    @staticmethod
    async def analyze_page_text(
        db: AsyncSession,
        page_id: int,
        user_id: int = 0,
    ) -> list[dict]:
        """分析指定页面的课文文本，返回结构化分句列表

        参数:
            db: 数据库会话
            page_id: 教材页面 ID
            user_id: 用户 ID

        返回:
            list[dict]: 结构化分句 [{en, cn, speaker}, ...]
        """
        from sqlalchemy import select
        stmt = select(TextbookPage).where(TextbookPage.id == page_id)
        result = await db.execute(stmt)
        page = result.scalar_one_or_none()

        if not page:
            logger.warning("页面不存在: page_id=%s", page_id)
            return []

        return await SentenceAnalyzerService.analyze_text(
            db=db,
            text=page.text_content or "",
            page_context={
                "version": page.textbook_version,
                "grade": page.grade,
                "unit": page.unit_number,
                "page_number": page.page_number,
            },
            user_id=user_id,
        )

    @staticmethod
    async def analyze_text(
        db: AsyncSession,
        text: str,
        page_context: Optional[dict] = None,
        user_id: int = 0,
    ) -> list[dict]:
        """分析原始文本，返回结构化分句

        参数:
            db: 数据库会话
            text: 原始课文文本
            page_context: 页面上下文（版本/年级/单元等）
            user_id: 用户 ID

        返回:
            list[dict]: [{en, cn, speaker}, ...]
        """
        if not text or not text.strip():
            logger.warning("文本为空，无法分析分句")
            return []

        # 构建包含上下文信息的 prompt
        context_str = ""
        if page_context:
            context_str = (
                f"教材版本: {page_context.get('version', '')}\n"
                f"年级: {page_context.get('grade', '')}\n"
                f"单元: {page_context.get('unit', '')}\n"
                f"页码: {page_context.get('page_number', '')}\n\n"
            )

        user_prompt = f"""{context_str}课文内容:
{text[:2000]}

请分析以上课文拆分为分句并标注说话角色。"""

        try:
            ai_result = await AIService.chat_completion(
                db=db,
                messages=[
                    {"role": "system", "content": _SENTENCE_ANALYZER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                user_id=user_id,
                stream=False,
            )
            sentences = _parse_ai_sentences(ai_result)
            logger.info(
                "分句分析完成: text_len=%s, sentences=%s",
                len(text), len(sentences),
            )
            return sentences

        except Exception as e:
            logger.error("分句分析失败: %s", e, exc_info=True)
            # 回退：简单按标点拆分，全部标记为 narrator
            return _fallback_split(text)

    @staticmethod
    async def analyze_and_save(
        db: AsyncSession,
        page_id: int,
        user_id: int = 0,
    ) -> dict:
        """分析页面分句并持久化到数据库

        参数:
            db: 数据库会话
            page_id: 教材页面 ID
            user_id: 用户 ID

        返回:
            dict: {success, sentences_count, page_id}
        """
        from sqlalchemy import select, update

        # 获取页面
        stmt = select(TextbookPage).where(TextbookPage.id == page_id)
        result = await db.execute(stmt)
        page = result.scalar_one_or_none()

        if not page:
            return {"success": False, "error": "页面不存在", "page_id": page_id}

        # 分析分句
        sentences = await SentenceAnalyzerService.analyze_page_text(
            db, page_id, user_id
        )

        if not sentences:
            return {
                "success": False,
                "error": "分句分析结果为空",
                "page_id": page_id,
            }

        # 持久化到数据库
        page.sentences_json = sentences
        await db.flush()

        logger.info(
            "分句已持久化: page_id=%s, sentences=%s",
            page_id, len(sentences),
        )
        return {
            "success": True,
            "page_id": page_id,
            "sentences_count": len(sentences),
            "sentences": sentences,
        }


# ========== 内部工具 ==========


def _parse_ai_sentences(ai_response: str) -> list[dict]:
    """解析 AI 返回的分句 JSON"""
    try:
        content = ai_response
        if isinstance(ai_response, dict):
            content = (
                ai_response.get("content", "")
                or ai_response.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

        if isinstance(content, str):
            # 提取 JSON 数组
            start = content.find("[")
            end = content.rfind("]")
            if start >= 0 and end > start:
                content = content[start: end + 1]
            parsed = json.loads(content)
        else:
            parsed = json.loads(json.dumps(content))

        if not isinstance(parsed, list):
            logger.warning("AI 返回不是数组: %s", type(parsed))
            return []

        # 验证每个条目
        validated = []
        for item in parsed:
            if isinstance(item, dict) and item.get("en"):
                validated.append({
                    "en": item.get("en", ""),
                    "cn": item.get("cn", ""),
                    "speaker": item.get("speaker", "narrator"),
                })
        return validated

    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning("解析分句 JSON 失败: %s", e)
        return []


def _fallback_split(text: str) -> list[dict]:
    """回退方案：按标点简单拆分，全部 speaker=narrator"""
    if not text:
        return []
    parts = text.replace("\n", " ").strip()
    # 按 . ! ? 分割
    import re
    sentences = re.findall(r'[^.!?]+[.!?]+', parts)
    if not sentences:
        sentences = [parts]
    return [
        {"en": s.strip(), "cn": "", "speaker": "narrator"}
        for s in sentences if s.strip()
    ]

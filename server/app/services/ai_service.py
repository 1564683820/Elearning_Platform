import asyncio
import httpx
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import get_settings
from app.models.user import UserApiKey
from app.core.security import decrypt_text
from app.utils.redis_client import get_redis, RedisCache
from app.schemas.common import QuestionOut

logger = logging.getLogger(__name__)
settings = get_settings()

# API 配置缓存 TTL（30 分钟）
API_CONFIG_CACHE_TTL = 1800


# 进程内配置缓存 {cache_key: (api_key, api_base, model, expire_at)}
_in_process_api_config_cache: dict[str, tuple[str, str, str, float]] = {}
# 保护进程缓存的异步锁
_api_config_lock = asyncio.Lock()

# 全局并发 LLM 操作信号量 — 限制同时进行的 AI 调用数，防止资源耗尽
# 设为 5 意味着最多 5 个 LLM 调用同时进行，其他排队等待
CONCURRENT_LLM_SEMAPHORE = asyncio.Semaphore(5)


class AIService:
    """统一的 AI 服务层，支持用户自定义 Key 和平台默认 Key"""

    @staticmethod
    async def _get_api_config(
        db: AsyncSession | None,
        user_id: int | None,
        key_type: str = "llm",
    ) -> tuple[str, str, str]:
        """获取 API 配置：(api_key, api_base, model_name) — 两级缓存（进程内 + Redis）

        db 可以传 None 表示只使用缓存/默认配置（适用于 SSE 等场景）。
        """
        cache_key = f"api:config:{user_id}:{key_type}"
        now = __import__('time').time()

        # 1. 进程内缓存（最快，不受 Redis 影响）
        cached = _in_process_api_config_cache.get(cache_key)
        if cached is not None and cached[3] > now:
            return cached[0], cached[1], cached[2]

        # 如果没有 DB，只能返回默认配置
        if db is None:
            api_key, api_base, model = settings.LLM_API_KEY, settings.LLM_API_BASE, settings.LLM_MODEL
            return api_key, api_base, model

        async with _api_config_lock:
            # 二次检查：锁内再检查一次缓存，避免多个协程同时查库
            cached = _in_process_api_config_cache.get(cache_key)
            if cached is not None and cached[3] > now:
                return cached[0], cached[1], cached[2]

            redis = await get_redis()
            cache = RedisCache(redis)

            # 2. Redis 缓存
            if redis is not None:
                cached_redis = await cache.get_json(cache_key)
                if cached_redis is not None:
                    _in_process_api_config_cache[cache_key] = (
                        cached_redis["api_key"], cached_redis["api_base"], cached_redis["model"],
                        now + API_CONFIG_CACHE_TTL,
                    )
                    return cached_redis["api_key"], cached_redis["api_base"], cached_redis["model"]

            # 3. 查库
            result = await db.execute(
                select(UserApiKey).where(
                    UserApiKey.user_id == user_id,
                    UserApiKey.key_type == key_type,
                    UserApiKey.is_valid == 1,
                )
            )
            key_record = result.scalar_one_or_none()

            if key_record and key_record.encrypted_key:
                api_key = decrypt_text(key_record.encrypted_key)
                api_base = key_record.api_base or settings.LLM_API_BASE
                model = key_record.model_name or settings.LLM_MODEL
            elif key_type == "llm":
                api_key, api_base, model = settings.LLM_API_KEY, settings.LLM_API_BASE, settings.LLM_MODEL
            elif key_type == "multimodal":
                api_key, api_base, model = settings.MULTIMODAL_API_KEY, settings.MULTIMODAL_API_BASE, settings.MULTIMODAL_MODEL
            elif key_type == "embedding":
                api_key, api_base, model = settings.EMBEDDING_API_KEY, settings.EMBEDDING_API_BASE, settings.EMBEDDING_MODEL
            else:
                api_key, api_base, model = settings.LLM_API_KEY, settings.LLM_API_BASE, settings.LLM_MODEL

            # 4. 写入两级缓存
            if redis is not None:
                await cache.set_json(
                    cache_key,
                    {"api_key": api_key, "api_base": api_base, "model": model},
                    ex=API_CONFIG_CACHE_TTL,
                )
            _in_process_api_config_cache[cache_key] = (api_key, api_base, model, now + API_CONFIG_CACHE_TTL)

            return api_key, api_base, model

    @staticmethod
    async def prefetch_api_config(
        db: AsyncSession,
        user_id: int,
        key_type: str = "llm",
    ) -> tuple[str, str, str]:
        """预先获取并缓存 API 配置（用于 SSE 场景，LLM 调用期间不需要持有 DB 连接）

        返回 (api_key, api_base, model) 元组。
        """
        return await AIService._get_api_config(db, user_id, key_type)

    @staticmethod
    async def self_test() -> str:
        """自检方法：验证服务正常启动"""
        return "AIService OK"

    @staticmethod
    async def chat_completion(
        db: AsyncSession | None = None,
        messages: list[dict] | None = None,
        user_id: int | None = None,
        stream: bool = False,
        key_type: str = "llm",
        timeout_seconds: float = 120.0,
        max_tokens: int | None = None,
        api_config: tuple[str, str, str] | None = None,
        telemetry: dict | None = None,
        require_complete_stream: bool = False,
    ) -> str | object:
        """LLM 聊天补全 — 含限流检查 + 全局并发控制

        Args:
            db: 数据库会话（为 None 时仅使用缓存默认配置）
            messages: 消息列表
            user_id: 用户 ID
            stream: 是否流式
            key_type: API 类型
            timeout_seconds: 超时时间
            max_tokens: 最大 token 数
            api_config: 预获取的 (api_key, api_base, model) 元组，用于 SSE 场景避免持有 DB 连接
        """
        # 全局并发限流：使用信号量限制同时进行的 LLM 调用数
        async with CONCURRENT_LLM_SEMAPHORE:
            # 限流检查
            if user_id:
                from app.core.middleware.rate_limit import AIRateLimiter
                await AIRateLimiter.check_rate_limit(user_id)

            # 使用预获取配置 或 动态获取
            if api_config is not None:
                api_key, api_base, model = api_config
            else:
                api_key, api_base, model = settings.LLM_API_KEY, settings.LLM_API_BASE, settings.LLM_MODEL
                if user_id and db is not None:
                    api_key, api_base, model = await AIService._get_api_config(db, user_id, key_type)

            if not api_key:
                raise ValueError("未配置 API Key，请在设置中配置")

            print(f"[AI DEBUG] 实际调用配置 | api_base={api_base} model={model} user_id={user_id}", flush=True)
            logger.info(
                "AI 调用 | model=%s api_base=%s messages=%d 条 user_id=%s timeout=%s max_tokens=%s",
                model, api_base, len(messages), user_id, timeout_seconds, max_tokens,
            )

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.3,
                "stream": stream,
            }
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens

            if stream:
                return AIService._stream_response(api_base, headers, payload, timeout_seconds, require_complete_stream)

            # 非流式调用
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds, connect=15.0)) as client:
                print(f"[AI] 开始调用 LLM | model={model} | api_base={api_base}", flush=True)
                resp = await client.post(f"{api_base}/chat/completions", headers=headers, json=payload)
                elapsed = resp.elapsed.total_seconds()
                print(f"[AI] LLM 响应 | status={resp.status_code} | elapsed={elapsed:.1f}s", flush=True)
                if resp.status_code != 200:
                    if telemetry is not None and resp.status_code in (429, 500, 502, 503, 504):
                        resp.raise_for_status()
                    raise ValueError(f"AI 服务调用失败: {resp.status_code} {resp.text[:200]}")

                data = resp.json()
                if telemetry is not None:
                    telemetry.update(model=model, usage=data.get('usage'), latency_ms=round(elapsed * 1000),
                                     cost=None)  # Provider billing is not inferred from token counts.
                content = data["choices"][0]["message"]["content"]
                finish_reason = data["choices"][0].get("finish_reason", "unknown")
                # 空内容时记录详细调试信息
                if not content or content.strip() == "":
                    logger.warning(
                        "AI 返回空内容 | model=%s finish_reason=%s "
                        "usage=%s response_id=%s 前200字符=%s",
                        model, finish_reason,
                        data.get("usage", {}),
                        data.get("id", "N/A"),
                        resp.text[:200] if resp.text else "",
                    )
                return content

    @staticmethod
    async def _stream_response(api_base: str, headers: dict, payload: dict, timeout_seconds: float, require_complete: bool = False):
        """SSE 流式响应生成器 — 内部管理 httpx 客户端生命周期"""
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds, connect=15.0)) as client:
            async with client.stream("POST", f"{api_base}/chat/completions", headers=headers, json=payload) as resp:
                if require_complete:
                    resp.raise_for_status()
                completed = False
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            completed = True
                            break
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices") or []
                            if not choices:
                                continue
                            choice = choices[0]
                            completed = completed or bool(choice.get("finish_reason"))
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
                if require_complete and not completed:
                    raise ValueError("模型响应在结束前断开")

    @staticmethod
    async def get_embedding(db: AsyncSession, text: str, user_id: int | None = None) -> list[float]:
        """获取单条文本向量"""
        result = await AIService.get_embeddings_batch(db, [text], user_id)
        return result[0]

    @staticmethod
    async def get_embeddings_batch(
        db: AsyncSession,
        texts: list[str],
        user_id: int | None = None,
    ) -> list[list[float]]:
        """批量获取文本向量 — 一次 HTTP 请求嵌入多条文本

        Args:
            texts: 文本列表
            user_id: 用户 ID
        Returns:
            向量列表，与 texts 顺序一致
        """
        if not texts:
            return []

        if user_id:
            from app.core.middleware.rate_limit import AIRateLimiter
            await AIRateLimiter.check_rate_limit(user_id)

        api_key, api_base, model = settings.EMBEDDING_API_KEY, settings.EMBEDDING_API_BASE, settings.EMBEDDING_MODEL
        if user_id and db:
            api_key, api_base, model = await AIService._get_api_config(db, user_id, "embedding")

        if not api_key:
            raise ValueError("未配置 Embedding API Key")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # 如果文本数量超过 64 条，分批处理（大多数嵌入 API 有输入长度限制）
        batch_size = 64
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            payload = {
                "model": model,
                "input": batch if len(batch) > 1 else batch[0],
            }
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(f"{api_base}/embeddings", headers=headers, json=payload)
                if resp.status_code != 200:
                    raise ValueError(f"Embedding 调用失败: {resp.status_code}")
                data = resp.json()
                # data["data"] 按输入顺序返回
                batch_embeddings = [item["embedding"] for item in data["data"]]
                all_embeddings.extend(batch_embeddings)

        return all_embeddings

    @staticmethod
    async def generate_quiz_questions(
        db: AsyncSession, user_id: int,
        question_types: list[int], stage: int, count: int,
        options_mode: str = "multiple_choice",
    ) -> list[QuestionOut]:
        """AI 动态生成训练题目

        Args:
            options_mode: "multiple_choice"（选择题型, 含 options）或 "fill_in"（填空/开放题型, 含 reference）
        """
        stage_names = {
            1: "小学", 2: "初中", 3: "高中", 4: "四六级",
        }
        type_desc = {
            1: "选择填空题", 2: "选择翻译题", 3: "听力选择题",
            4: "短语语法题", 5: "句子翻译题", 6: "阅读理解题", 7: "听力训练题",
            8: "句子翻译(中译英填空)", 9: "作文写作",
        }
        stage_name = stage_names.get(stage, f"阶段{stage}")

        if options_mode == "fill_in":
            prompt = AIService._build_fill_in_prompt(question_types, stage_name, count)
        else:
            types_str = "、".join([type_desc.get(t, f"题型{t}") for t in question_types])
            prompt = (
                f"请为{stage_name}阶段的学生生成{count}道英语训练题目。"
                f"题型包括：{types_str}。\n"
                f"请严格按JSON数组格式返回，每个题目格式为：\n"
                f'[{{"type": 类型编号, "content": {{"stem": "题干", "options": ["A选项", "B选项", "C选项", "D选项"], '
                f'"correct": 正确选项索引, "explanation": "解析"}}}}]\n'
                f"只返回JSON，不要其他内容。"
            )

        messages = [{"role": "user", "content": prompt}]
        response = await AIService.chat_completion(
            db, messages, user_id,
            max_tokens=4096 if options_mode == "fill_in" else None,
        )

        try:
            text = response.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            questions_data = json.loads(text)

            result = []
            for i, q in enumerate(questions_data[:count]):
                result.append(QuestionOut(
                    id=-(i + 1),
                    type=q.get("type", question_types[0] if question_types else 1),
                    stage=stage,
                    difficulty=q.get("difficulty", 1),
                    content=q.get("content", {}),
                ))
            return result
        except (json.JSONDecodeError, KeyError):
            return []

    @staticmethod
    def _build_fill_in_prompt(question_types: list[int], stage_name: str, count: int) -> str:
        """构造填空/开放题的 AI prompt"""
        parts = []
        for t in question_types:
            if t == 8:
                parts.append(
                    f"【句子翻译题（中译英）】\n"
                    f"- 生成{count}道中译英填空题\n"
                    f"- 每道题给出一个中文句子，让学生翻译成英文\n"
                    f"- 参考翻译要准确、自然，适合{stage_name}学生水平\n"
                    f"- 注意句子的多样性和实用性\n"
                    f"- JSON格式：{{\"type\": 8, \"content\": {{\"stem\": \"请翻译以下句子：\\n[中文句子]\", "
                    f"\"reference\": \"[参考英文翻译]\", \"type_hint\": \"sentence_translate\", "
                    f"\"knowledge_point\": \"[涉及知识点]\"}}}}"
                )
            elif t == 9:
                parts.append(
                    f"【作文写作题】\n"
                    f"- 生成{count}道英语作文题，适合{stage_name}学生\n"
                    f"- 题型包括：书信、报道、故事续写、介绍说明、议论文等，要多样化\n"
                    f"- 给出明确的写作背景和要求（中文），包括字数要求\n"
                    f"- 提供一篇参考范文（英文），长度 80-200 词\n"
                    f"- JSON格式：{{\"type\": 9, \"content\": {{\"stem\": \"写作要求：\\n[写作背景和要求]\", "
                    f"\"reference\": \"参考范文：\\n[英文范文]\", \"type_hint\": \"writing\", "
                    f"\"knowledge_point\": \"[写作类型]\"}}}}"
                )

        return (
            f"请为{stage_name}阶段的学生生成英语训练题目，严格按以下要求。\n\n"
            + "\n\n".join(parts)
            + "\n\n请严格按JSON数组格式返回所有题目，只返回JSON，不要其他内容。"
        )

    # ═══════════════════════════════════════════════════════════
    # 新训练体系 — AI 生成方法
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def generate_reading_passage(
        db: AsyncSession, user_id: int,
        stage: int, difficulty: str = "中级",
    ) -> dict:
        """AI 生成一篇英文文章 + 5 道阅读理解选择题

        Returns:
            {
                "title": str,
                "content": str,          # 英文文章全文
                "content_cn": str,       # 中文翻译
                "questions": [
                    {
                        "stem": "题干",
                        "options": ["A", "B", "C", "D"],
                        "correct": int,  # 正确选项索引
                        "explanation": "解析",
                    }
                ],
                "word_count": int,
                "difficulty": str,
            }
        """
        stage_names = {
            1: "小学", 2: "初中",
            3: "高中", 4: "四六级",
        }
        stage_name = stage_names.get(stage, f"阶段{stage}")

        prompt = (
            f"请为{stage_name}阶段（{difficulty}难度）的英语学习者生成一篇英文阅读文章。\n\n"
            f"要求：\n"
            f"1. 文章主题不限，内容有趣、有教育意义，长度 200-400 词\n"
            f"2. 难度要符合{stage_name}学生的词汇量和语法水平\n"
            f"3. 文章后附带 5 道阅读理解选择题\n"
            f"4. 每题 4 个选项，只有一个正确答案\n"
            f"5. 题目要测试主旨理解、细节把握、推理判断、词义猜测等不同能力\n\n"
            f"必须严格按以下 JSON 格式返回，不要其他内容：\n"
            f'{{\n'
            f'  "title": "文章标题（英文）",\n'
            f'  "content": "英文文章全文",\n'
            f'  "content_cn": "中文翻译",\n'
            f'  "questions": [\n'
            f'    {{\n'
            f'      "stem": "第1题题干",\n'
            f'      "options": ["A选项", "B选项", "C选项", "D选项"],\n'
            f'      "correct": 0,\n'
            f'      "explanation": "解析"\n'
            f'    }},\n'
            f'    ...（共5题）\n'
            f'  ]\n'
            f'}}'
        )

        messages = [{"role": "user", "content": prompt}]
        response = await AIService.chat_completion(db, messages, user_id, max_tokens=4096)

        try:
            text = response.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            data["word_count"] = len(data.get("content", "").split())
            return data
        except (json.JSONDecodeError, KeyError):
            # 降级：返回一个默认提示
            return {
                "title": "Reading Passage",
                "content": "AI generation failed. Please try again.",
                "content_cn": "AI 生成失败，请重试。",
                "questions": [],
                "word_count": 0,
                "difficulty": difficulty,
            }

    @staticmethod
    async def generate_translation_paragraph(
        db: AsyncSession, user_id: int,
        stage: int,
    ) -> dict:
        """AI 生成一段中文段落供翻译练习（时政/文化/科技等主题）

        Returns:
            {
                "stem": "中文段落（待翻译）",
                "topic": "主题名称",
                "key_vocab": ["关键词1", "关键词2"],
                "reference": "参考答案（英文翻译）",
                "hints": "翻译提示",
            }
        """
        stage_names = {
            1: "小学", 2: "初中",
            3: "高中", 4: "四六级",
        }
        stage_name = stage_names.get(stage, f"阶段{stage}")
        topics = ["时政新闻", "传统文化", "社会热点", "科技发展", "环境保护", "健康生活", "教育学习"]

        prompt = (
            f"请为{stage_name}阶段的英语学习者生成一段中译英翻译练习。\n\n"
            f"要求：\n"
            f"1. 从以下主题中随机选一个：{'、'.join(topics)}\n"
            f"2. 生成一段 80-150 字的中文段落，语言地道、信息丰富\n"
            f"3. 难度适中，包含 3-5 个有价值的英文关键词/短语\n"
            f"4. 提供高质量的英文参考翻译\n"
            f"5. 提供简短翻译提示（包括重点词汇的译法说明）\n\n"
            f"必须严格按以下 JSON 格式返回，不要其他内容：\n"
            f'{{\n'
            f'  "stem": "中文段落",\n'
            f'  "topic": "主题",\n'
            f'  "key_vocab": ["核心词汇1", "核心词汇2", "核心词汇3"],\n'
            f'  "reference": "英文参考翻译",\n'
            f'  "hints": "翻译提示"\n'
            f'}}'
        )

        messages = [{"role": "user", "content": prompt}]
        response = await AIService.chat_completion(db, messages, user_id, max_tokens=4096)

        try:
            text = response.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except (json.JSONDecodeError, KeyError):
            return {
                "stem": "请将以下中文翻译成英文：\n人工智能正在改变我们的生活方式。从智能手机到自动驾驶汽车，AI技术已经渗透到日常生活的方方面面。",
                "topic": "科技发展",
                "key_vocab": ["人工智能", "自动驾驶", "渗透"],
                "reference": "Artificial intelligence is changing our way of life. From smartphones to self-driving cars, AI technology has permeated every aspect of daily life.",
                "hints": '注意"人工智能"译为 artificial intelligence (AI)；"渗透"可用 permeate 或 penetrate。',
            }

    @staticmethod
    async def generate_essay_prompt(
        db: AsyncSession, user_id: int,
        stage: int,
    ) -> dict:
        """AI 生成作文题目/情景

        Returns:
            {
                "stem": "作文要求（中文）",
                "topic": "写作类型/主题",
                "word_limit": "词数要求",
                "reference": "参考范文（英文）",
                "key_points": ["写作要点1", "写作要点2"],
            }
        """
        stage_names = {
            1: "小学", 2: "初中",
            3: "高中", 4: "四六级",
        }
        stage_name = stage_names.get(stage, f"阶段{stage}")

        # 根据阶段决定写作类型
        if stage == 1:
            types = ["描述人物", "描述动物", "介绍家庭", "我的学校", "我最喜欢的季节"]
        elif stage == 2:
            types = ["书信", "日记", "介绍中国节日", "环保倡议", "我最喜欢的运动"]
        else:
            types = ["议论文", "报道", "建议信", "图表描述", "故事续写", "观点对比"]

        type_desc = "、".join(types)

        prompt = (
            f"请为{stage_name}阶段的英语学习者生成一篇英语作文题目。\n\n"
            f"要求：\n"
            f"1. 写作类型从以下中选择：{type_desc}\n"
            f"2. 用中文给出明确的写作背景和要求\n"
            f"3. 给出词数要求（适合{stage_name}水平）\n"
            f"4. 提供一篇高质量的英文参考范文\n"
            f"5. 列出 2-3 个写作要点/建议\n\n"
            f"必须严格按以下 JSON 格式返回，不要其他内容：\n"
            f'{{\n'
            f'  "stem": "写作背景和要求（中文）",\n'
            f'  "topic": "写作类型",\n'
            f'  "word_limit": "词数要求，如 120-180 词",\n'
            f'  "reference": "参考范文（英文，符合词数要求）",\n'
            f'  "key_points": ["写作要点1", "写作要点2", "写作要点3"]\n'
            f'}}'
        )

        messages = [{"role": "user", "content": prompt}]
        response = await AIService.chat_completion(db, messages, user_id, max_tokens=4096)

        try:
            text = response.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except (json.JSONDecodeError, KeyError):
            return {
                "stem": "假设你是李华，你的英国笔友Tom对中国春节很感兴趣。请你给他写一封信，介绍中国春节的传统习俗和庆祝方式。",
                "topic": "书信",
                "word_limit": "100-150 词",
                "reference": "Dear Tom,\n\nI'm glad to hear that you're interested in the Spring Festival. It is the most important traditional festival in China. During the Spring Festival, families gather together for a reunion dinner on New Year's Eve. People decorate their houses with red lanterns and couplets. Children receive red envelopes with lucky money. Fireworks light up the night sky. The festival lasts for 15 days, ending with the Lantern Festival.\n\nI hope this helps you understand our Spring Festival better. If you have any questions, please let me know.\n\nBest wishes,\nLi Hua",
                "key_points": ["开门见山，表达高兴心情", "详细介绍 2-3 个春节传统", "结尾邀请对方进一步交流"],
            }

    @staticmethod
    async def score_translation(
        db: AsyncSession, user_id: int,
        source_text: str, user_answer: str, reference: str,
    ) -> dict:
        """AI 评估翻译质量并打分（百分制）

        Returns:
            {
                "score": int,           # 0-100 分
                "reference": str,       # 参考答案（AI 润色版）
                "feedback": str,        # 评语（优点 + 改进点）
                "mistakes": [           # 主要错误
                    {"detail": "错误描述", "suggestion": "改进建议"}
                ],
                "suggestions": str,     # 整体提升建议
            }
        """
        prompt = (
            f"你是一位专业的英语翻译评分老师。请评估以下翻译作业的质量。\n\n"
            f"【原文（中文）】\n{source_text}\n\n"
            f"【学生的英文翻译】\n{user_answer}\n\n"
            f"【参考翻译】\n{reference}\n\n"
            f"请从以下维度评估：\n"
            f"1. 准确性（40%）：是否准确传达了原文意思，有无漏译、误译\n"
            f"2. 语法正确性（25%）：语法是否规范，时态、语态、句式是否正确\n"
            f"3. 词汇恰当性（20%）：用词是否准确、地道\n"
            f"4. 表达流畅度（15%）：行文是否自然、连贯\n\n"
            f"必须严格按以下 JSON 格式返回（得分合理，不要过高也不要过低）：\n"
            f'{{\n'
            f'  "score": 75,\n'
            f'  "reference": "英文参考答案（可以比参考翻译更好或与之不同的版本）",\n'
            f'  "feedback": "整体评语，指出优点和主要问题",\n'
            f'  "mistakes": [\n'
            f'    {{"detail": "错误1描述", "suggestion": "改进建议"}},\n'
            f'    {{"detail": "错误2描述", "suggestion": "改进建议"}}\n'
            f'  ],\n'
            f'  "suggestions": "整体提升建议"\n'
            f'}}'
        )

        messages = [{"role": "user", "content": prompt}]
        response = await AIService.chat_completion(db, messages, user_id, max_tokens=4096)

        from app.services.grading_result import parse_grade_result
        return parse_grade_result(response)

    @staticmethod
    async def score_essay(
        db: AsyncSession, user_id: int,
        essay_topic: str, user_answer: str, reference: str,
    ) -> dict:
        """AI 评估英语作文并打分（百分制）

        Returns:
            {
                "score": int,           # 0-100 分
                "reference": str,       # 参考范文
                "feedback": str,        # 整体评语
                "dimensions": {         # 各维度得分
                    "content": int,     # 内容完整性 0-25
                    "organization": int, # 结构组织 0-25
                    "language": int,    # 语言表达 0-25
                    "grammar": int,     # 语法准确性 0-25
                },
                "suggestions": str,     # 改进建议
            }
        """
        prompt = (
            f"你是一位专业的英语作文评分老师。请评估以下英语作文的质量。\n\n"
            f"【作文题目】\n{essay_topic}\n\n"
            f"【学生作文】\n{user_answer}\n\n"
            f"【参考范文】\n{reference}\n\n"
            f"请从以下维度评估（总分 100）：\n"
            f"1. 内容完整性（25分）：是否扣题，内容是否充实\n"
            f"2. 结构组织（25分）：段落结构是否清晰，逻辑是否连贯\n"
            f"3. 语言表达（25分）：词汇丰富度、句式多样性\n"
            f"4. 语法准确性（25分）：语法错误数量、时态语态等\n\n"
            f"必须严格按以下 JSON 格式返回：\n"
            f'{{\n'
            f'  "score": 78,\n'
            f'  "reference": "参考范文（可以优化后的版本）",\n'
            f'  "feedback": "整体评语，指出优点和不足",\n'
            f'  "dimensions": {{\n'
            f'    "content": 20,\n'
            f'    "organization": 18,\n'
            f'    "language": 22,\n'
            f'    "grammar": 18\n'
            f'  }},\n'
            f'  "suggestions": "具体改进建议"\n'
            f'}}'
        )

        messages = [{"role": "user", "content": prompt}]
        response = await AIService.chat_completion(db, messages, user_id, max_tokens=4096)

        from app.services.grading_result import parse_grade_result
        return parse_grade_result(response)

    @staticmethod
    async def generate_scenario(
        db: AsyncSession, user_id: int,
        words: list[str], passage_type: str = "story", stage: int = 0
    ) -> str:
        """AI生成情景文段"""
        stage_names = {
            1: "小学", 2: "初中",
            3: "高中", 4: "四六级",
        }
        stage_hint = ""
        if stage:
            stage_name = stage_names.get(stage, "")
            if stage == 1:
                stage_hint = "内容要简单易懂，适合小学生。"
            elif stage == 2:
                stage_hint = "内容可以适当增加难度，适合初中生。"
            elif stage >= 3:
                stage_hint = "内容可以涉及高级词汇和复杂句式。"

        type_desc = {
            "story": "一个有趣的故事",
            "rap": "一段顺口溜/说唱",
            "news": "一篇新闻报道",
            "rhyme": "一段押韵的诗歌",
        }

        # 根据文段类型附加特定要求
        type_specific = {
            "story": "要有逻辑性和画面感，自然地融入所有单词",
            "rap": "要押韵、有节奏感、朗朗上口，便于记忆，句式尽量工整",
            "news": "要像真实的新闻报道，有标题和段落结构",
            "rhyme": "要押韵工整，有诗歌的节奏感和意境",
        }
        specific = type_specific.get(passage_type, "文段要连贯、有逻辑、便于记忆")

        system_prompt = (
            "你是一位英语单词记忆专家。用户会给你一组英语单词，请为这些单词创作一段文段，"
            "帮助用户通过上下文快速记忆单词。"
        )

        prompt = (
            f"请用以下单词生成{type_desc.get(passage_type, '一段文字')}：{', '.join(words)}\n"
            f"要求：\n"
            f"1. 全文必须用**英文**撰写，给定的单词在英文中用 **单词** 标记（如 **apple**）\n"
            f"2. {specific}\n"
            f"3. {stage_hint}\n"
            f"4. 文段长度 100-150 词\n"
            f"5. 在英文文段下方，空一行后附上对应的**中文翻译**\n"
            f"6. 中文翻译中，单词对应的译文也用 **译文** 标记加粗凸显（如 **苹果**）\n"
            f"7. 中文翻译中不需要标题和额外说明\n"
            f"8. 输出格式：\n"
            f"   [英文文段，单词用**标记]\n"
            f"   （空行）\n"
            f"   [中文翻译，对应译文也用**标记]"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        return await AIService.chat_completion(db, messages, user_id)

    @staticmethod
    async def translate_text(
        db: AsyncSession, text: str,
        source_lang: str = "auto", target_lang: str = "auto",
        user_id: int | None = None,
    ) -> dict:
        """AI翻译"""
        if source_lang == "auto" or target_lang == "auto":
            if any('\u4e00' <= c <= '\u9fff' for c in text):
                source_lang, target_lang = "zh", "en"
            else:
                source_lang, target_lang = "en", "zh"

        lang_names = {"zh": "中文", "en": "英文"}

        prompt = (
            f"请将以下{lang_names.get(source_lang, source_lang)}文本翻译成{lang_names.get(target_lang, target_lang)}：\n\n"
            f"{text}\n\n"
            f"要求：\n"
            f"1. 翻译准确、自然\n"
            f"2. 只返回翻译结果，不要其他内容"
        )

        messages = [{"role": "user", "content": prompt}]
        translated = await AIService.chat_completion(db, messages, user_id)

        return {
            "source_text": text,
            "translated_text": translated.strip(),
            "source_lang": source_lang,
            "target_lang": target_lang,
        }

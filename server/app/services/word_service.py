from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, case, and_
from app.models.word import DictWord, DictWordRoot, DictRoot, WordSynonym, Favorite, UserWordProgress
from app.schemas.common import WordOut, WordDetail, WordListQuery, PaginatedData
from app.utils.redis_client import get_redis, RedisCache, cache_get_or_set
from datetime import datetime

# 缓存版本号 — 修改筛选逻辑后递增，以踢掉旧缓存
CACHE_VERSION = "v10"

# ═══════════════════════════════════════════════════════════
# 学习阶段 → tag 关键字映射（精简为四个阶段）
# 1=小学（BNC 词频范围）, 2=初中（中考）, 3=高中（高考）, 4=四六级（四六级）
# ═══════════════════════════════════════════════════════════
STAGE_TAG_MAP: dict[int, list[str]] = {
    2: ["zk"],           # 中考 → 初中
    3: ["gk"],           # 高考 → 高中
    4: ["cet4", "cet6"], # 四六级
}

# BNC 词频范围：小学阶段（无考试标签，用 BNC 排名标识）
_BNC_RANGES: dict[int, int] = {1: 2000}


def _apply_stage_filter(stmt, stage: int):
    """
    按 tag 字段或 BNC 词频范围进行阶段筛选。
    所有基础过滤条件（正则、质量指标等）不受 stage 参数影响，始终生效。
    """
    # 基础过滤：排除词缀、化学名、短语、编号等非标准词汇
    stmt = stmt.where(
        func.REGEXP_LIKE(DictWord.word, '[a-zA-Z]')       # 必须有英文字母
    ).where(
        ~func.REGEXP_LIKE(DictWord.word, '^[0-9]')        # 不以数字开头
    ).where(
        ~DictWord.word.like("-%")                          # 不以 - 开头
    ).where(
        func.REGEXP_LIKE(DictWord.word, '^[a-zA-Z]')       # 必须以字母开头
    ).where(
        ~DictWord.word.like("% %")                         # 不含空格（排除多词短语）
    ).where(
        ~DictWord.word.like("%/%")                         # 不含斜杠（排除 a/b 类组合词）
    )

    # 专业领域标签过滤：从翻译字段中排除地名、人名、化学、医学术语等
    DOMAIN_TAGS = [
        '[地名]', '[人名]', '[化]', '[化学]', '[无化]', '[有化]',
        '[医]', '[法]', '[经]', '[计]',
        '[数]', '[物]', '[生化]', '[生物]', '[地质]', '[气象]',
        '[药]', '[网络]', '[机]', '[电]', '[电子]', '[交]', '[军]',
    ]
    for tag in DOMAIN_TAGS:
        stmt = stmt.where(~DictWord.translation.like(f"%{tag}%"))

    # 排除大写开头的专有名词（地名、人名、品牌名等）
    # 使用 REGEXP_LIKE 的 'c' 参数实现大小写敏感匹配
    stmt = stmt.where(~func.REGEXP_LIKE(DictWord.word, '^[A-Z]', 'c'))

    # ═══════════════════════════════════════════════════════════
    # 化学名词后缀过滤：排除以典型化学命名后缀结尾且不被任何质量指标
    # 标记的词汇（如 -ane 烷烃、-ene 烯烃、-ol 醇、-ide 化合物等）。
    # 遍历多个前缀长度以避免切到短单词的非化学含义。
    # 如果单词有 collins/oxford/bnc 指标，仍视为合格保留。
    # ═══════════════════════════════════════════════════════════
    CHEMIC_SUFFIXES = ["ane", "ene", "ol", "ide", "yne", "oic"]
    chem_conditions = []
    for suf in CHEMIC_SUFFIXES:
        # -ane: length>=4 → "ane"→prefix "" (已由 {3,} 兜住)
        # 要求前缀至少 2 个字母，避免 "ane" 本身、one/ole 等误伤
        chem_conditions.append(
            func.REGEXP_LIKE(
                DictWord.word,
                rf"^[a-z]{{2,}}{suf}$",
                "c",
            )
        )
    if chem_conditions:
        # 仅在单词无任何质量指标时执行化学后缀排除
        stmt = stmt.where(
            or_(
                or_(  # 有质量指标的豁免
                    DictWord.collins > 0,
                    DictWord.bnc > 0,
                    DictWord.oxford == 1,
                    and_(DictWord.frq > 0, DictWord.frq < 30000),
                ),
                and_(  # 无质量指标 且 不是化学后缀 → 保留
                    ~or_(*chem_conditions),
                ),
            )
        )

    # ═══════════════════════════════════════════════════════════
    # 质量门槛：排除低频词和生僻词。
    # dict_word 中 98.7% 的词 frq=0（无频率数据）。
    # 必须至少满足一项实质性质量指标：
    #   - 柯林斯星级 > 0（常见词评级）
    #   - BNC 排名 > 0 且 < 20000（语料库前 2 万词）
    #   - 牛津核心词标记
    #   - 有词频数据且 frq < 30000（排除极低频）
    # 注意：tag!=''（如 cet4/cet6）不作为独立质量指标，因为大量
    # 低频词也带有考试标签，仅靠 tag 无法过滤。
    # ═══════════════════════════════════════════════════════════
    stmt = stmt.where(
        or_(
            DictWord.collins > 0,
            and_(DictWord.bnc > 0, DictWord.bnc < 20000),
            DictWord.oxford == 1,
            and_(DictWord.frq > 0, DictWord.frq < 30000),
        )
    )

    # ═══════════════════════════════════════════════════════════
    # 阶段筛选：按 tag 字段或 BNC 词频范围匹配学习阶段
    # stage 1-4  BNC 基础阶段（启蒙～小五）：按 BNC 排名范围过滤
    # stage 5-10 考试阶段：按 tag LIKE 匹配考试标签关键字
    # ═══════════════════════════════════════════════════════════
    if stage > 0:
        if stage <= 4:
            limit_bnc = _BNC_RANGES.get(stage)
            if limit_bnc:
                stmt = stmt.where(
                    and_(DictWord.bnc > 0, DictWord.bnc <= limit_bnc)
                )
        else:
            tag_keywords = STAGE_TAG_MAP.get(stage)
            if tag_keywords:
                tag_conditions = [
                    DictWord.tag.like(f"%{kw}%") for kw in tag_keywords
                ]
                stmt = stmt.where(or_(*tag_conditions))

    return stmt


class WordService:

    @staticmethod
    async def list_words(db: AsyncSession, query: WordListQuery) -> PaginatedData[WordOut]:
        """单词列表（分页、搜索、阶段筛选、标签筛选）— 搜索结果缓存 1h"""
        redis = await get_redis()
        cache = RedisCache(redis)

        cache_key = f"word:{CACHE_VERSION}:list:{query.search}:{query.stage}:{query.tag}:{query.sort_by}:{query.page}:{query.page_size}"

        async def _query_db():
            stmt = select(DictWord)

            if query.search:
                search_lower = query.search.lower()
                search_pattern = f"%{search_lower}%"
                stmt = stmt.where(
                    or_(
                        DictWord.word.like(search_pattern),
                        DictWord.sw.like(search_pattern),
                        DictWord.translation.like(search_pattern),
                    )
                )

            # 按考试标签（tag）字段直接筛选，如 cet4/cet6/zk/gk
            if query.tag:
                stmt = stmt.where(DictWord.tag.like(f"%{query.tag}%"))

            # 按学习阶段对应的 tag 关键字或 BNC 范围进行阶段筛选
            stmt = _apply_stage_filter(stmt, query.stage)

            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await db.execute(count_stmt)).scalar() or 0

            offset = (query.page - 1) * query.page_size

            # 按 sort_by 字段排序
            if not query.search:
                stmt = stmt.where(DictWord.translation != "")

            if query.sort_by == "asc":
                stmt = stmt.order_by(DictWord.word.asc())
            elif query.sort_by == "desc":
                stmt = stmt.order_by(DictWord.word.desc())
            elif query.sort_by == "random":
                stmt = stmt.order_by(func.rand())
            else:
                # 默认：按词频 + 柯林斯星级排序（重要度）
                stmt = stmt.order_by(
                    case((DictWord.frq == 0, 1), else_=0),
                    DictWord.frq.asc(),
                    DictWord.collins.desc(),
                )
            stmt = stmt.offset(offset).limit(query.page_size)
            result = await db.execute(stmt)
            words = result.scalars().all()

            total_pages = (total + query.page_size - 1) // query.page_size
            return {
                "items": [WordOut.model_validate(w).model_dump() for w in words],
                "total": total,
                "page": query.page,
                "page_size": query.page_size,
                "total_pages": total_pages,
            }

        data = await cache_get_or_set(cache, cache_key, _query_db, ex=3600)
        return PaginatedData(**data)

    @staticmethod
    async def get_word_detail(db: AsyncSession, word_id: int, user_id: int | None = None, main_db: AsyncSession | None = None) -> WordDetail:
        """单词详情（含词根、近义词、学习进度）— 缓存 24h（基础部分），进度不缓存
        db:     单词库 session（elearnword）
        main_db: 主库 session（elearningtest），用于查询 Favorite 表"""

        redis = await get_redis()
        cache = RedisCache(redis)

        base_cache_key = f"word:detail:{word_id}"

        async def _query_base():
            result = await db.execute(select(DictWord).where(DictWord.id == word_id))
            word = result.scalar_one_or_none()
            if not word:
                raise ValueError("单词不存在")

            # 词根关联（通过 dict_word_root + dict_root）
            root_result = await db.execute(
                select(DictWordRoot, DictRoot)
                .join(DictRoot, DictWordRoot.root_id == DictRoot.id)
                .where(DictWordRoot.word_id == word_id)
                .order_by(DictWordRoot.position)
            )
            roots = [
                {"root": r.root, "root_type": r.root_type, "meaning": r.meaning, "position": wr.position}
                for wr, r in root_result.all()
            ]

            # 近义词
            syn_result = await db.execute(
                select(WordSynonym).where(WordSynonym.word_id == word_id)
            )
            synonyms = [
                {"synonym_word": s.synonym_word, "tag": s.tag,
                 "usage_desc": s.usage_desc, "example": s.example}
                for s in syn_result.scalars().all()
            ]

            # idiom / 金句等来自 detail_json
            idiom = None
            if word.detail_json and isinstance(word.detail_json, dict):
                idiom = word.detail_json.get("idiom")

            return {
                "id": word.id,
                "word": word.word,
                "phonetic": word.phonetic,
                "pos": word.pos,
                "translation": word.translation,
                "definition": word.definition,
                "collins": word.collins,
                "oxford": word.oxford,
                "tag": word.tag,
                "bnc": word.bnc,
                "frq": word.frq,
                "sw": word.sw,
                "exchange": word.exchange,
                "audio_url": word.audio_url,
                "detail_json": word.detail_json,
                "roots": roots,
                "synonyms": synonyms,
                "idiom": idiom,
            }

        base_data = await cache_get_or_set(cache, base_cache_key, _query_base, ex=86400)

        # 用户学习进度（实时查库）
        progress = None
        if user_id:
            prog_result = await db.execute(
                select(UserWordProgress).where(
                    UserWordProgress.user_id == user_id,
                    UserWordProgress.word_id == word_id,
                )
            )
            prog = prog_result.scalar_one_or_none()
            is_favorite = False
            # Favorite 表在主库（elearningtest），需使用 main_db session 查询
            if main_db is not None:
                from app.schemas.common import FAVORITE_TYPE_WORD
                fav_result = await main_db.execute(
                    select(Favorite).where(
                        Favorite.user_id == user_id,
                        Favorite.target_type == FAVORITE_TYPE_WORD,
                        Favorite.target_id == word_id,
                    )
                )
                is_favorite = fav_result.scalar_one_or_none() is not None

            if prog or is_favorite:
                progress = {
                    "mastery_level": prog.mastery_level if prog else 0,
                    "review_count": prog.review_count if prog else 0,
                    "is_favorite": is_favorite,
                }

        return WordDetail(**base_data, progress=progress)

    @staticmethod
    async def get_word_by_name(db: AsyncSession, word_text: str, user_id: int | None = None, main_db: AsyncSession | None = None) -> WordDetail:
        """按单词文本获取详情 — 先查缓存 ID 映射"""
        redis = await get_redis()
        cache = RedisCache(redis)

        id_cache_key = f"word:name_id:{word_text.lower()}"
        word_id = await cache.get_json(id_cache_key)

        if word_id is None:
            result = await db.execute(select(DictWord.id).where(DictWord.word == word_text))
            row = result.scalar_one_or_none()
            if not row:
                raise ValueError(f"未找到单词: {word_text}")
            word_id = row
            await cache.set_json(id_cache_key, word_id, ex=86400)

        return await WordService.get_word_detail(db, word_id, user_id, main_db)

    @staticmethod
    async def record_progress(db: AsyncSession, user_id: int, word_id: int, mastery_level: int) -> dict:
        """记录学习进度"""
        result = await db.execute(
            select(UserWordProgress).where(
                UserWordProgress.user_id == user_id,
                UserWordProgress.word_id == word_id,
            )
        )
        progress = result.scalar_one_or_none()

        if progress:
            progress.mastery_level = mastery_level
            progress.review_count += 1
            progress.last_reviewed_at = datetime.now()
        else:
            progress = UserWordProgress(
                user_id=user_id,
                word_id=word_id,
                mastery_level=mastery_level,
                review_count=1,
                last_reviewed_at=datetime.now(),
            )
            db.add(progress)

        await db.flush()

        # 失效缓存
        redis = await get_redis()
        cache = RedisCache(redis)
        await cache.delete(f"word:detail:{word_id}")

        return {"mastery_level": progress.mastery_level, "review_count": progress.review_count}

    @staticmethod
    async def get_daily_words(db: AsyncSession, stage: int, limit: int = 20) -> list[WordOut]:
        """今日推荐单词列表 — 按 tag 关键字筛选阶段"""
        redis = await get_redis()
        cache = RedisCache(redis)

        cache_key = f"word:{CACHE_VERSION}:daily:{stage}:{limit}"

        async def _query_db():
            stmt = select(DictWord).where(DictWord.translation != "")
            stmt = _apply_stage_filter(stmt, stage)
            stmt = stmt.order_by(
                case((DictWord.frq == 0, 1), else_=0),
                DictWord.frq.asc(),
                DictWord.collins.desc(),
            ).limit(limit)
            result = await db.execute(stmt)
            return [WordOut.model_validate(w).model_dump() for w in result.scalars().all()]

        data = await cache_get_or_set(cache, cache_key, _query_db, ex=86400)
        return [WordOut(**item) for item in data]

    @staticmethod
    async def get_neighbor_word_id(db: AsyncSession, word_id: int, direction: str, stage: int = 0) -> int | None:
        """获取相邻单词ID"""
        result = await db.execute(select(DictWord).where(DictWord.id == word_id))
        current = result.scalar_one_or_none()
        if not current:
            return None

        if direction == "prev":
            stmt = (
                select(DictWord.id)
                .where(DictWord.frq < current.frq)
                .order_by(DictWord.frq.desc())
                .limit(1)
            )
        else:
            stmt = (
                select(DictWord.id)
                .where(DictWord.frq > current.frq)
                .order_by(DictWord.frq.asc())
                .limit(1)
            )

        stmt = _apply_stage_filter(stmt, stage)

        neighbor = (await db.execute(stmt)).scalar_one_or_none()
        return neighbor

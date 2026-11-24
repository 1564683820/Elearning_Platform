# 教材点读 Service
# 提供:
# - 教材版本/年级/单元/页面层级查询
# - 页面内容 + 单词详情
# - CDN URL 生成与缓存
# - 阅读进度记录
import re
import json
from datetime import date
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.models.textbook_models import TextbookUnit, TextbookPage
from app.models.word import DictWord


# 教材点读服务：处理教材层级查询、页面内容获取、单词查询、阅读进度
class TextbookService:

    # 获取可用的教材版本列表（基于已入库的教材数据去重）
    @staticmethod
    async def list_versions(db: AsyncSession) -> list[dict]:
        stmt = (
            select(TextbookUnit.textbook_version)
            .distinct()
            .order_by(TextbookUnit.textbook_version)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [{"version": v, "name": _VERSION_NAMES.get(v, v)} for v in rows]

    # 获取某版本下的年级列表
    @staticmethod
    async def list_grades(db: AsyncSession, version: str) -> list[dict]:
        stmt = (
            select(TextbookUnit.grade)
            .where(TextbookUnit.textbook_version == version)
            .distinct()
            .order_by(TextbookUnit.grade)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [{"grade": g, "name": f"第 {g} 年级" if g.isdigit() else g} for g in rows]

    # 获取某版本某年级下的学期列表
    @staticmethod
    async def list_semesters(db: AsyncSession, version: str, grade: str) -> list[dict]:
        stmt = (
            select(TextbookUnit.semester)
            .where(and_(
                TextbookUnit.textbook_version == version,
                TextbookUnit.grade == grade,
            ))
            .distinct()
            .order_by(TextbookUnit.semester)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [{"semester": s, "name": f"{s}学期"} for s in rows]

    # 获取某版本某年级某学期下的单元列表
    @staticmethod
    async def list_units(
        db: AsyncSession,
        version: str,
        grade: str,
        semester: str = "上",
    ) -> list[dict]:
        stmt = (
            select(TextbookUnit)
            .where(and_(
                TextbookUnit.textbook_version == version,
                TextbookUnit.grade == grade,
                TextbookUnit.semester == semester,
            ))
            .order_by(TextbookUnit.sort_order)
        )
        result = await db.execute(stmt)
        units = result.scalars().all()
        return [
            {
                "id": u.id,
                "unit_number": u.unit_number,
                "title": u.title,
                "sub_title": u.sub_title or "",
                "cover_image": u.cover_image or "",
                "page_start": u.page_start,
                "page_end": u.page_end,
                "page_count": u.page_end - u.page_start + 1,
            }
            for u in units
        ]

    # 获取某单元下的页面列表（精简版，含缩略图和状态标记）
    @staticmethod
    async def list_pages(
        db: AsyncSession,
        version: str,
        grade: str,
        unit_number: str,
        semester: str = "上",
        cdn_base: str = "",
    ) -> list[dict]:
        stmt = (
            select(TextbookPage)
            .where(and_(
                TextbookPage.textbook_version == version,
                TextbookPage.grade == grade,
                TextbookPage.unit_number == unit_number,
                TextbookPage.semester == semester,
                TextbookPage.is_active == 1,
            ))
            .order_by(TextbookPage.page_number)
        )
        result = await db.execute(stmt)
        pages = result.scalars().all()
        return [
            {
                "id": p.id,
                "page_number": p.page_number,
                "image_thumbnail": _cdn_url(cdn_base, p.image_thumbnail or p.image_url or ""),
                "has_audio": bool(p.audio_url),
                "has_animation": bool(p.animation_url),
                "word_count": len(p.words_json) if p.words_json else 0,
            }
            for p in pages
        ]

    # 获取页面完整内容（含分句、单词详情、音频URL、角色动画映射）
    @staticmethod
    async def get_page_detail(
        db: AsyncSession,
        page_id: int,
        cdn_base: str = "",
        words_db: AsyncSession | None = None,
    ) -> Optional[dict]:
        stmt = select(TextbookPage).where(TextbookPage.id == page_id, TextbookPage.is_active == 1)
        result = await db.execute(stmt)
        page = result.scalar_one_or_none()
        if not page:
            return None

        # 单词详情补充（查询 DictWord 获取音标/释义）
        words_detail = None
        if page.words_json:
            words_detail = []
            for w in page.words_json:
                word_text = w.get("word", "")
                detail = await _lookup_word(db, word_text, words_db)
                words_detail.append({
                    "word": word_text,
                    "phonetic": w.get("phonetic") or (detail.phonetic if detail else ""),
                    "translation": w.get("translation") or (detail.translation if detail else ""),
                    "definition": detail.definition if detail else "",
                    "audio_url": _cdn_url(cdn_base, w.get("audio_url", "")),
                })

        # 解析 sentences_json 提取角色动画映射，并为每个句子的 animation_url 添加 CDN 前缀
        sentences = page.sentences_json or []
        character_animations = {}
        if sentences:
            for s in sentences:
                s_anim = s.get("animation_url", "") or ""
                s_speaker = s.get("speaker", "") or ""
                if s_anim and s_speaker:
                    character_animations[s_speaker] = _cdn_url(cdn_base, s_anim)
                # 为每个句子的 animation_url/audio_url 添加 CDN 前缀
                if s_anim:
                    s["animation_url"] = _cdn_url(cdn_base, s_anim)
                s_audio = s.get("audio_url", "") or ""
                if s_audio:
                    s["audio_url"] = _cdn_url(cdn_base, s_audio)

        return {
            "id": page.id,
            "page_number": page.page_number,
            "text_content": page.text_content,
            "sentences": sentences,
            "image_url": _cdn_url(cdn_base, page.image_url),
            "image_thumbnail": _cdn_url(cdn_base, page.image_thumbnail or page.image_url),
            "animation_url": _cdn_url(cdn_base, page.animation_url),
            "background_anim_url": _cdn_url(cdn_base, page.background_anim_url),
            "audio_url": _cdn_url(cdn_base, page.audio_url),
            "audio_duration": page.audio_duration or 0,
            "words": words_detail or [],
            "has_exercises": bool(page.exercises_json),
            "character_animations": character_animations,
        }

    # 按页码获取页面内容（通过版本/年级/学期/单元号/页码定位）
    @staticmethod
    async def get_page_by_number(
        db: AsyncSession,
        version: str,
        grade: str,
        unit_number: str,
        page_number: int,
        semester: str = "上",
        cdn_base: str = "",
        words_db: AsyncSession | None = None,
    ) -> Optional[dict]:
        stmt = select(TextbookPage).where(and_(
            TextbookPage.textbook_version == version,
            TextbookPage.grade == grade,
            TextbookPage.unit_number == unit_number,
            TextbookPage.semester == semester,
            TextbookPage.page_number == page_number,
            TextbookPage.is_active == 1,
        ))
        result = await db.execute(stmt)
        page = result.scalar_one_or_none()
        if not page:
            return None
        return await TextbookService.get_page_detail(db, page.id, cdn_base, words_db)

    # 获取上一页和下一页的 ID（用于翻页导航）
    @staticmethod
    async def get_adjacent_pages(
        db: AsyncSession,
        page_id: int,
    ) -> dict:
        stmt = select(TextbookPage).where(TextbookPage.id == page_id)
        result = await db.execute(stmt)
        page = result.scalar_one_or_none()
        if not page:
            return {"prev_id": None, "next_id": None, "total": 0}

        # 查找当前单元的所有页面，定位当前页的相邻页
        stmt_all = (
            select(TextbookPage.id, TextbookPage.page_number)
            .where(and_(
                TextbookPage.textbook_version == page.textbook_version,
                TextbookPage.grade == page.grade,
                TextbookPage.unit_number == page.unit_number,
                TextbookPage.semester == page.semester,
                TextbookPage.is_active == 1,
            ))
            .order_by(TextbookPage.page_number)
        )
        result_all = await db.execute(stmt_all)
        all_pages = result_all.all()

        prev_id = None
        next_id = None
        for i, (pid, pnum) in enumerate(all_pages):
            if pid == page_id:
                if i > 0:
                    prev_id = all_pages[i - 1][0]
                if i < len(all_pages) - 1:
                    next_id = all_pages[i + 1][0]
                break

        return {
            "prev_id": prev_id,
            "next_id": next_id,
            "current_page": page.page_number,
            "total": len(all_pages),
        }

    # 查询单词详情（音标/释义/例句）
    @staticmethod
    async def search_word(
        db: AsyncSession,
        word: str,
        words_db: AsyncSession | None = None,
    ) -> Optional[dict]:
        detail = await _lookup_word(db, word, words_db)
        if not detail:
            return None
        return {
            "word": detail.word,
            "phonetic": detail.phonetic or "",
            "translation": detail.translation or "",
            "definition": detail.definition or "",
            "exchange": detail.exchange or "",
        }

    # 记录用户阅读进度（简化版，记录当前阅读的页面）
    @staticmethod
    async def save_reading_progress(
        db: AsyncSession,
        user_id: int,
        page_id: int,
    ) -> dict:
        return {"user_id": user_id, "page_id": page_id, "saved": True}

    # 获取用户阅读进度（当前简化实现，完整版需建专门的进度表）
    @staticmethod
    async def get_reading_progress(
        db: AsyncSession,
        user_id: int,
        version: str,
        grade: str,
    ) -> Optional[dict]:
        return None


# ========== 内部工具 ==========

# 教材版本名称映射
_VERSION_NAMES = {
    "PEP": "人教版PEP",
    "PEP-3": "人教版PEP三年级起点",
    "FLTRP": "外研社",
}

# 年级名称映射
_GRADE_NAMES = {
    "3": "三年级",
    "4": "四年级",
    "5": "五年级",
    "6": "六年级",
}


# 生成完整的资源 URL（图片/音频等）
# 处理三种情况:
#   1. 外部 URL (http/https) → 原样返回
#   2. CDN 已配置 → 拼接 CDN 域名
#   3. 本地开发 (cdn_base 为空) → 拼接本地服务器地址
# 同时兼容旧数据：自动补全 /uploads/ 前缀
def _cdn_url(cdn_base: str, path: str, server_host: str = "http://127.0.0.1:8000") -> str:
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/uploads/"):
        path = f"/uploads/{path.lstrip('/')}"
    if cdn_base:
        return f"{cdn_base.rstrip('/')}/{path.lstrip('/')}"
    return f"{server_host.rstrip('/')}{path}"


# 查询词典（优先使用 words_db，回退到 db）
# 参数: word - 待查询的单词文本
# 返回: DictWord 对象，未找到返回 None
async def _lookup_word(db: AsyncSession, word: str, words_db: AsyncSession | None = None) -> Optional[DictWord]:
    _db = words_db or db
    stmt = select(DictWord).where(DictWord.word == word.lower().strip())
    result = await _db.execute(stmt)
    return result.scalar_one_or_none()

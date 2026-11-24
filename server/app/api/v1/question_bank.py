# -*- coding: utf-8 -*-
# 教师端 — 题库管理 API 路由
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from app.db.database import get_db
from app.api.deps import get_current_teacher_id
from app.models.quiz import QuestionBank
from app.schemas.common import ResponseData, PaginatedData, PaginatedResponse
from app.services.quiz_service import QuizService
from datetime import datetime

router = APIRouter(prefix="/question-bank", tags=["教师端-题库"])


# ===== 请求/响应模型 =====

class QuestionBankOut(BaseModel):
    id: int
    type: int
    stage: int
    difficulty: int
    content: dict
    source: str = ""
    is_active: int = 1
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TypeStatItem(BaseModel):
    type_id: int
    type_name: str
    count: int


class AIGenerateRequest(BaseModel):
    qtype: str  # "reading" / "translation" / "essay" / "vocabulary" / "grammar"
    stage: int = 2  # 默认初中
    count: int = 5
    difficulty: str = "中级"


# 题型名称映射
TYPE_NAMES = {
    1: "选择填空（词汇）",
    2: "选择翻译",
    3: "听力选择",
    4: "短语语法",
    5: "句子翻译",
    6: "阅读理解",
    7: "听力训练",
    8: "句子翻译（填空）",
    9: "作文写作",
}

_TRAINING_TYPE_NAMES = {
    "vocabulary": "单词词汇",
    "grammar": "短语语法",
    "reading": "阅读理解",
    "translation": "句子翻译",
    "essay": "作文写作",
}


# ===== 接口 =====

@router.get("/stats", response_model=ResponseData[dict])
async def get_question_bank_stats(
    stage: int = Query(0, description="学习阶段 0=全部"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取各题型题目数量统计"""
    query = select(QuestionBank.type, func.count().label("cnt")).where(
        QuestionBank.is_active == 1
    )
    if stage > 0:
        query = query.where(QuestionBank.stage == stage)
    query = query.group_by(QuestionBank.type).order_by(QuestionBank.type)

    result = await db.execute(query)
    rows = result.all()

    stats = []
    total = 0
    for type_id, cnt in rows:
        stats.append({
            "type_id": type_id,
            "type_name": TYPE_NAMES.get(type_id, f"未知({type_id})"),
            "count": cnt,
        })
        total += cnt

    # 按训练分类汇总（与小程序端对齐）
    category_stats = {}
    type_to_category = QuizService._TYPE_CATEGORY_MAP
    for type_id, cnt in rows:
        cat = type_to_category.get(type_id, "vocabulary")
        category_stats[cat] = category_stats.get(cat, 0) + cnt

    return ResponseData(data={
        "total": total,
        "by_type": stats,
        "by_category": [
            {"category": k, "name": _TRAINING_TYPE_NAMES.get(k, k), "count": v}
            for k, v in sorted(category_stats.items())
        ],
    })


@router.get("/list", response_model=ResponseData[PaginatedData[QuestionBankOut]])
async def list_question_bank(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type_id: int = Query(0, description="题型筛选 0=全部"),
    stage: int = Query(0, description="学习阶段 0=全部"),
    difficulty: int = Query(0, description="难度 0=全部"),
    keyword: str = Query("", description="搜索关键词"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """题库列表（分页）"""
    conditions = [QuestionBank.is_active == 1]
    if type_id > 0:
        conditions.append(QuestionBank.type == type_id)
    if stage > 0:
        conditions.append(QuestionBank.stage == stage)
    if difficulty > 0:
        conditions.append(QuestionBank.difficulty == difficulty)

    # 计数
    count_stmt = select(func.count()).select_from(QuestionBank).where(*conditions)
    total = (await db.execute(count_stmt)).scalar() or 0

    # 查列表
    stmt = (
        select(QuestionBank)
        .where(*conditions)
        .order_by(QuestionBank.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    # 关键词过滤（在 content JSON 中搜索）
    if keyword:
        keyword_lower = keyword.lower()
        filtered = []
        for q in items:
            content_str = str(q.content or {}).lower()
            if keyword_lower in content_str:
                filtered.append(q)
        items = filtered
        total = len(filtered)

    total_pages = max(1, (total + page_size - 1) // page_size)

    return ResponseData(data=PaginatedData(
        items=[QuestionBankOut.model_validate(q) for q in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    ))


@router.get("/{question_id}", response_model=ResponseData[QuestionBankOut])
async def get_question_detail(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """题目详情"""
    result = await db.execute(
        select(QuestionBank).where(QuestionBank.id == question_id)
    )
    qb = result.scalar_one_or_none()
    if not qb:
        raise HTTPException(status_code=404, detail="题目不存在")
    return ResponseData(data=QuestionBankOut.model_validate(qb))


@router.delete("/{question_id}", response_model=ResponseData[dict])
async def delete_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """删除题目（软删除 is_active=0）"""
    result = await db.execute(
        select(QuestionBank).where(QuestionBank.id == question_id)
    )
    qb = result.scalar_one_or_none()
    if not qb:
        raise HTTPException(status_code=404, detail="题目不存在")
    qb.is_active = 0
    await db.flush()
    return ResponseData(data={"id": question_id, "deleted": True})


# AI 题型映射（1=词汇/选择填空, 4=语法, 6=阅读, 8=翻译填空, 9=作文）
_AI_QTYPE_TO_BANK_TYPE = {
    "vocabulary": 1,
    "grammar": 4,
    "reading": 6,
    "translation": 8,
    "essay": 9,
}


@router.post("/ai-generate", response_model=ResponseData[dict])
async def ai_generate_questions(
    body: AIGenerateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """AI 生成更多题目并入库（批量生成）"""
    bank_type = _AI_QTYPE_TO_BANK_TYPE.get(body.qtype)
    if not bank_type:
        raise HTTPException(status_code=400, detail=f"不支持的题型: {body.qtype}")

    from app.services.ai_service import AIService

    results = []
    for i in range(body.count):
        try:
            if body.qtype == "reading":
                item = await AIService.generate_reading_passage(
                    db, teacher_id, body.stage, body.difficulty
                )
                if item:
                    content = {
                        "article_title": item.get("title", ""),
                        "article_content": item.get("content", ""),
                        "content_cn": item.get("content_cn", ""),
                        "word_count": item.get("word_count", 0),
                        "difficulty": body.difficulty,
                        "questions": item.get("questions", []),
                    }
                    qb = QuestionBank(
                        stage=body.stage, type=bank_type, difficulty=2,
                        content=content, source="teacher_ai_generate",
                    )
                    db.add(qb)
                    await db.flush()
                    results.append({"index": i, "id": qb.id, "title": item.get("title", "")})
            elif body.qtype == "translation":
                item = await AIService.generate_translation_paragraph(
                    db, teacher_id, body.stage
                )
                if item:
                    content = {
                        "stem": item.get("stem", ""),
                        "topic": item.get("topic", ""),
                        "key_vocab": item.get("key_vocab", []),
                        "reference": item.get("reference", ""),
                        "hints": item.get("hints", ""),
                    }
                    qb = QuestionBank(
                        stage=body.stage, type=bank_type, difficulty=2,
                        content=content, source="teacher_ai_generate",
                    )
                    db.add(qb)
                    await db.flush()
                    results.append({"index": i, "id": qb.id, "title": content.get("topic", "")[:50]})
            elif body.qtype == "essay":
                item = await AIService.generate_essay_prompt(
                    db, teacher_id, body.stage
                )
                if item:
                    content = {
                        "stem": item.get("stem", ""),
                        "topic": item.get("topic", ""),
                        "word_limit": item.get("word_limit", ""),
                        "reference": item.get("reference", ""),
                        "key_points": item.get("key_points", []),
                    }
                    qb = QuestionBank(
                        stage=body.stage, type=bank_type, difficulty=2,
                        content=content, source="teacher_ai_generate",
                    )
                    db.add(qb)
                    await db.flush()
                    results.append({"index": i, "id": qb.id, "title": content.get("topic", "")[:50]})
            else:
                # vocabulary / grammar: 直接走 generate_quiz_questions
                ai_items = await AIService.generate_quiz_questions(
                    db, teacher_id, [bank_type], body.stage, 1,
                    options_mode="multiple_choice",
                )
                if ai_items:
                    qb = QuestionBank(
                        stage=body.stage, type=bank_type, difficulty=2,
                        content=ai_items[0].content if hasattr(ai_items[0], 'content') else {},
                        source="teacher_ai_generate",
                    )
                    db.add(qb)
                    await db.flush()
                    results.append({"index": i, "id": qb.id, "title": str(ai_items[0].content.get("stem", ""))[:50]})
        except Exception as e:
            results.append({"index": i, "id": None, "error": str(e)})
            continue

    return ResponseData(data={
        "qtype": body.qtype,
        "requested_count": body.count,
        "generated_count": len([r for r in results if r.get("id")]),
        "results": results,
    })

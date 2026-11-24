from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.api.deps import get_current_user_id
from app.services.quiz_service import QuizService
from app.services.grading_result import InvalidAIGradeError
from app.schemas.common import (
    ResponseData, QuizGenerateRequest, QuestionOut,
    QuizSubmitRequest, QuizSubmitResponse,
)

router = APIRouter(prefix="/quiz", tags=["训练"])


@router.post("/generate", response_model=ResponseData[list[QuestionOut]])
async def generate_questions(
    body: QuizGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """生成训练题目"""
    result = await QuizService.generate_questions(db, body, user_id)
    return ResponseData(data=result)


@router.post("/submit", response_model=ResponseData[QuizSubmitResponse])
async def submit_answer(
    body: QuizSubmitRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """提交答案"""
    result = await QuizService.submit_answer(db, user_id, body)
    return ResponseData(data=result)


@router.get("/mistakes", response_model=ResponseData[dict])
async def list_mistakes(
    question_type: int = Query(0, description="题型 1=单词,2=语法"),
    mastered: int | None = Query(None, description="是否已掌握 0/1"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """错题本列表"""
    result = await QuizService.get_mistakes(db, user_id, question_type, mastered, page, page_size)
    return ResponseData(data=result)


@router.post("/mistakes/{mistake_id}/review", response_model=ResponseData[dict])
async def review_mistake(
    mistake_id: int,
    mastered: bool = True,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """错题复习 - 标记掌握/未掌握"""
    result = await QuizService.review_mistake(db, user_id, mistake_id, mastered)
    return ResponseData(data=result)


@router.get("/stats", response_model=ResponseData[dict])
async def quiz_stats(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """训练统计数据"""
    result = await QuizService.get_quiz_stats(db, user_id)
    return ResponseData(data=result)


# ===== 新训练体系 — AI 驱动端点 =====


@router.post("/reading/generate", response_model=ResponseData[dict])
async def reading_generate(
    stage: int = 2,  # 默认初中
    difficulty: str = "中级",
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """AI 生成阅读文章 + 5 道选择题（阅读理解模式）"""
    result = await QuizService.generate_reading(db, user_id, stage, difficulty)
    return ResponseData(data=result)


@router.post("/translation/generate", response_model=ResponseData[dict])
async def translation_generate(
    stage: int = 2,  # 默认初中
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """AI 生成翻译练习（翻译模式 - 生成中文段落）"""
    result = await QuizService.generate_translation(db, user_id, stage)
    return ResponseData(data=result)


class FetchAIQuestionRequest(BaseModel):
    qtype: str  # "reading" / "translation" / "essay"
    stage: int = 2  # 默认初中
    difficulty: str = "中级"


@router.post("/ai-question/fetch", response_model=ResponseData[dict])
async def fetch_ai_question(
    body: FetchAIQuestionRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """从题库获取 AI 生成题目，全部答过则 AI 生成新题并入库"""
    result = await QuizService.fetch_ai_question(
        db, user_id, body.qtype, body.stage, body.difficulty
    )
    return ResponseData(data=result)


class TranslationScoreRequest(BaseModel):
    source_text: str
    user_answer: str
    reference: str
    question_id: int = 0


@router.post("/translation/score", response_model=ResponseData[dict])
async def translation_score(
    body: TranslationScoreRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """AI 评分翻译练习"""
    try:
        result = await QuizService.score_translation(
            db, user_id, body.source_text, body.user_answer, body.reference,
            question_id=body.question_id,
        )
    except InvalidAIGradeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return ResponseData(data=result)


@router.post("/essay/generate", response_model=ResponseData[dict])
async def essay_generate(
    stage: int = 2,  # 默认初中
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """AI 生成作文题目（作文模式）"""
    result = await QuizService.generate_essay(db, user_id, stage)
    return ResponseData(data=result)


class EssayScoreRequest(BaseModel):
    essay_topic: str
    user_answer: str
    reference: str
    question_id: int = 0


@router.post("/essay/score", response_model=ResponseData[dict])
async def essay_score(
    body: EssayScoreRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """AI 评分英语作文"""
    try:
        result = await QuizService.score_essay(
            db, user_id, body.essay_topic, body.user_answer, body.reference,
            question_id=body.question_id,
        )
    except InvalidAIGradeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return ResponseData(data=result)

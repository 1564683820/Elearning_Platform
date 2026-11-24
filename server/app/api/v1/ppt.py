"""AI 备课 PPT + 课堂互动 API 路由"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.db.database import get_db
from app.core.paths import UPLOADS_DIR
from app.api.deps import get_current_teacher_id, get_current_user_id
from app.services.ai_service import AIService
from app.services.ppt_service import PPTService
from app.services.ppt_theme_service import PPTThemeService
from app.services.ppt_html_renderer import PPTHtmlRenderer
from app.models.ppt_models import LessonPPT, ClassroomSession
from app.models.ppt_theme_models import PptVersion
from app.utils.json_utils import safe_json_dumps
from app.schemas.ppt import (
    LESSON_TYPES,
    PPTGenerateRequest, PPTUpdateRequest, PPTRegenerateOutlineRequest,
    PPTRegeneratePageRequest, ClassroomStartRequest,
    ClassroomVoteRequest, ClassroomQuizRequest,
    ClassroomDanmakuRequest, ClassroomQuestionRequest,
    PPTGenerateResult, PPTOutlineItem, PPTDetail, PPTListItem,
    ThemeItem, ThemeDetail, ThemeCreate, ThemeUpdate,
    PptVersionItem, PptVersionDetail, PptExportOut,
    ClassroomSessionOut, ClassroomReportOut,
    SlideAnswerRequest,
    PPTGenerateOutlineRequest, PPTGenerateOutlineResponse,
    PPTGenerateFromOutlineRequest, PPTOutlineSection,
)
from app.schemas.common import ResponseData, PaginatedData
from app.services.classroom_service import ClassroomService
from app.services.tts_service import TTSService
from app.services.animation_service import AnimationService
from sqlalchemy import select, func, desc
import logging
from typing import Optional, Dict
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teacher/ppt", tags=["教师端-备课PPT"])


# ========== 课型列表 ==========

@router.get("/lesson-types", response_model=ResponseData)
async def list_lesson_types():
    """获取支持的课型列表"""
    types = [{"value": k, "label": v} for k, v in LESSON_TYPES.items()]
    return ResponseData(data=types)


# ========== PPT 生成 ==========

@router.post("/generate", response_model=ResponseData)
async def generate_ppt(
    body: PPTGenerateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """AI 生成完整 PPT（大纲 + 逐页内容）"""
    if body.lesson_type not in LESSON_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的课型: {body.lesson_type}，可选: {list(LESSON_TYPES.keys())}",
        )
    try:
        # 预获取 API 配置，AI 调用期间不持有 DB 连接
        api_config = await AIService.prefetch_api_config(db, teacher_id)
        result = await PPTService.generate_ppt(
            db=db,
            teacher_id=teacher_id,
            title=body.title,
            lesson_type=body.lesson_type,
            subject=body.subject,
            grade=body.grade,
            class_id=body.class_id,
            slide_count=body.slide_count,
            knowledge_points=body.knowledge_points,
            stage_category=body.stage_category,
            use_rag=body.use_rag,
            additional_references=body.additional_references,
            theme_name=body.theme_name,
            synthesize_audio=getattr(body, 'synthesize_audio', None),
            layout_intent=getattr(body, 'layout_intent', 'auto') or 'auto',
            transition_type=getattr(body, 'transition_type', 'slide') or 'slide',
            transition_duration=getattr(body, 'transition_duration', 400) or 400,
            layout_overrides=getattr(body, 'layout_overrides', None),
            spec_lock=getattr(body, 'spec_lock', None),
            api_config=api_config,
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate-outline", response_model=ResponseData)
async def generate_ppt_outline(
    body: PPTGenerateOutlineRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """教学助手：AI 生成 PPT 大纲（章节 + 子主题）"""
    try:
        api_config = await AIService.prefetch_api_config(db, teacher_id)
        result = await PPTService.generate_outline(
            title=body.title,
            lesson_type=body.lesson_type,
            subject=body.subject,
            grade=body.grade,
            knowledge_points=body.knowledge_points,
            api_config=api_config,
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate-from-outline", response_model=ResponseData)
async def generate_ppt_from_outline(
    body: PPTGenerateFromOutlineRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """教学助手：基于用户确认的大纲 + 主题，生成完整 PPT"""
    if body.lesson_type not in LESSON_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的课型: {body.lesson_type}，可选: {list(LESSON_TYPES.keys())}",
        )
    try:
        api_config = await AIService.prefetch_api_config(db, teacher_id)
        result = await PPTService.generate_from_outline(
            db=db,
            teacher_id=teacher_id,
            title=body.title,
            lesson_type=body.lesson_type,
            subject=body.subject,
            grade=body.grade,
            knowledge_points=body.knowledge_points,
            sections=[s.model_dump() for s in body.sections],
            theme_name=body.theme_name,
            stage_category=body.stage_category,
            synthesize_audio=getattr(body, 'synthesize_audio', None),
            api_config=api_config,
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate-stream")
async def generate_ppt_stream(
    body: PPTGenerateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """SSE 流式生成 PPT（含音频合成进度），返回 text/event-stream"""
    from fastapi.responses import StreamingResponse

    if body.lesson_type not in LESSON_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的课型: {body.lesson_type}，可选: {list(LESSON_TYPES.keys())}",
        )

    async def event_generator():
        async for event in PPTService.generate_ppt_stream(
            db=db, teacher_id=teacher_id,
            title=body.title, lesson_type=body.lesson_type,
            subject=body.subject, grade=body.grade,
            class_id=body.class_id, slide_count=body.slide_count,
            knowledge_points=body.knowledge_points, stage_category=body.stage_category,
            use_rag=body.use_rag, additional_references=body.additional_references,
            theme_name=body.theme_name,
            synthesize_audio=getattr(body, 'synthesize_audio', None),
            layout_intent=getattr(body, 'layout_intent', 'auto') or 'auto',
            transition_type=getattr(body, 'transition_type', 'slide') or 'slide',
            transition_duration=getattr(body, 'transition_duration', 400) or 400,
            layout_overrides=getattr(body, 'layout_overrides', None),
            spec_lock=getattr(body, 'spec_lock', None),
        ):
            yield f"data: {safe_json_dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ========== PPT CRUD ==========

@router.get("/list", response_model=ResponseData)
async def list_ppts(
    status: Optional[str] = Query(None, description="筛选状态"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取教师的 PPT 列表"""
    result = await PPTService.list_ppts(db, teacher_id, status, page, page_size)
    return ResponseData(data=result)


@router.get("/{ppt_id}", response_model=ResponseData)
async def get_ppt(
    ppt_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取单个 PPT 详情（html_content 为空时自动渲染并保存）"""
    result = await PPTService.get_ppt(db, ppt_id, teacher_id)
    if not result:
        raise HTTPException(status_code=404, detail="PPT 不存在")

    # 自动渲染空 html_content，保存到数据库供后续复用
    if not result.get("html_content"):
        raw_pages = result.get("pages_json")
        print(f"[ppt] get_ppt ppt_id={ppt_id} html_content 为空, pages_json 类型={type(raw_pages).__name__}, 预览={str(raw_pages)[:200]}", flush=True)
        pages_list = _ensure_pages_list(raw_pages)
        print(f"[ppt] get_ppt ppt_id={ppt_id} _ensure_pages_list 返回 {len(pages_list)} 页", flush=True)
        if pages_list:
            try:
                # Phase 3.5: 从 spec_lock 提取 visual_style
                spec_lock_data = result.get("spec_lock", {})
                vs = ""
                if isinstance(spec_lock_data, dict):
                    vs = spec_lock_data.get("visual_style", "")
                elif isinstance(spec_lock_data, str):
                    try:
                        sl = json.loads(spec_lock_data)
                        vs = sl.get("visual_style", "") if isinstance(sl, dict) else ""
                    except (json.JSONDecodeError, TypeError):
                        pass
                html_content = await PPTHtmlRenderer.render_from_db(
                    db, pages_list, result["title"],
                    result.get("theme_name", "classic"),
                    visual_style=vs,
                )
                print(f"[ppt] get_ppt ppt_id={ppt_id} render_from_db 返回 html_content 长度={len(html_content) if html_content else 0}", flush=True)
                if html_content:
                    result["html_content"] = html_content
                    # 保存回数据库
                    ppt = (await db.execute(
                        select(LessonPPT).where(LessonPPT.id == ppt_id)
                    )).scalar_one_or_none()
                    if ppt:
                        ppt.html_content = html_content
                        await db.commit()
                        print(f"[ppt] get_ppt ppt_id={ppt_id} HTML 已保存到数据库", flush=True)
            except Exception as e:
                print(f"[ppt] 自动渲染 HTML 失败 ppt_id={ppt_id}: {type(e).__name__}: {e}", flush=True)
                import traceback
                traceback.print_exc()
                # 尝试不带 visual_style 的降级渲染
                try:
                    print(f"[ppt] get_ppt ppt_id={ppt_id} 尝试降级渲染（无 visual_style）", flush=True)
                    html_content = await PPTHtmlRenderer.render_from_db(
                        db, pages_list, result["title"],
                        result.get("theme_name", "classic"),
                        visual_style="",
                    )
                    if html_content:
                        result["html_content"] = html_content
                        print(f"[ppt] get_ppt ppt_id={ppt_id} 降级渲染成功，长度={len(html_content)}", flush=True)
                        ppt = (await db.execute(
                            select(LessonPPT).where(LessonPPT.id == ppt_id)
                        )).scalar_one_or_none()
                        if ppt:
                            ppt.html_content = html_content
                            await db.commit()
                    else:
                        print(f"[ppt] get_ppt ppt_id={ppt_id} 降级渲染也返回空", flush=True)
                except Exception as e2:
                    print(f"[ppt] get_ppt ppt_id={ppt_id} 降级渲染也失败: {type(e2).__name__}: {e2}", flush=True)
                    traceback.print_exc()
        else:
            print(f"[ppt] get_ppt ppt_id={ppt_id} pages_list 为空，跳过渲染。检查数据: pages_json={repr(raw_pages)[:500]}", flush=True)
    return ResponseData(data=result)


@router.put("/{ppt_id}", response_model=ResponseData)
async def update_ppt(
    ppt_id: int,
    body: PPTUpdateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """更新 PPT（标题、课型、页面内容等）"""
    update_data = body.model_dump(exclude_unset=True)
    result = await PPTService.update_ppt(db, ppt_id, teacher_id, update_data)
    if not result:
        raise HTTPException(status_code=404, detail="PPT 不存在")
    return ResponseData(data=result)


@router.post("/{ppt_id}/visual-edits", response_model=ResponseData)
async def save_visual_edits(
    ppt_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """保存可视化编辑结果（文字/位置调整），注入到 pages_json 各页的 _visual_edits 字段中

    请求体格式: { "page_edits": { "0": [{ "tag": "h1", "text": "新标题", "x": 100, "y": 50 }], "1": [...] } }
    """
    import copy
    page_edits = (body or {}).get("page_edits", {})
    if not page_edits:
        raise HTTPException(status_code=400, detail="page_edits 为空")

    # 获取当前 PPT
    ppt = await PPTService.get_ppt(db, ppt_id, teacher_id)
    if not ppt:
        raise HTTPException(status_code=404, detail="PPT 不存在")

    pages_json = ppt.get("pages_json", [])
    if isinstance(pages_json, str):
        pages_json = json.loads(pages_json)
    if not isinstance(pages_json, list):
        raise HTTPException(status_code=400, detail="pages_json 格式异常")

    # 注入 _visual_edits 到各页
    for page_idx_str, edits in page_edits.items():
        try:
            idx = int(page_idx_str)
            if 0 <= idx < len(pages_json) and isinstance(pages_json[idx], dict):
                pages_json[idx]["_visual_edits"] = edits
        except (ValueError, IndexError, TypeError):
            continue

    # 通过已有的 update_ppt 保存（触发版本历史 + HTML 重建）
    result = await PPTService.update_ppt(db, ppt_id, teacher_id, {"pages_json": pages_json})
    if not result:
        raise HTTPException(status_code=404, detail="保存失败")
    return ResponseData(data=result)


@router.delete("/{ppt_id}", response_model=ResponseData)
async def delete_ppt(
    ppt_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """删除 PPT"""
    success = await PPTService.delete_ppt(db, ppt_id, teacher_id)
    if not success:
        raise HTTPException(status_code=404, detail="PPT 不存在")
    return ResponseData(message="删除成功")


@router.post("/{ppt_id}/publish", response_model=ResponseData)
async def publish_ppt(
    ppt_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """发布 PPT（草稿→已发布）"""
    result = await PPTService.update_ppt(db, ppt_id, teacher_id, {"status": "published"})
    if not result:
        raise HTTPException(status_code=404, detail="PPT 不存在")
    return ResponseData(data={"id": ppt_id, "status": "published"})


# ========== 单页重新生成 ==========

@router.post("/{ppt_id}/regenerate-page", response_model=ResponseData)
async def regenerate_page(
    ppt_id: int,
    body: PPTRegeneratePageRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """使用 AI 重新生成 PPT 的某一页"""
    try:
        result = await PPTService.regenerate_page(
            db=db, teacher_id=teacher_id, ppt_id=ppt_id,
            page_index=body.page_index, outline_title=body.outline_title,
            lesson_type=body.lesson_type, subject=body.subject, grade=body.grade,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="PPT 不存在")
        return ResponseData(data={"page_index": body.page_index, "page": result})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== 课堂互动 ==========

@router.post("/classroom/start", response_model=ResponseData)
async def start_classroom(
    body: ClassroomStartRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """开始课堂互动会话"""
    try:
        session = await PPTService.start_classroom(db, teacher_id, body.ppt_id)
        return ResponseData(data=session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/classroom/{session_id}/end", response_model=ResponseData)
async def end_classroom(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """结束课堂并生成报告"""
    result = await PPTService.end_classroom(db, session_id, teacher_id)
    if not result:
        raise HTTPException(status_code=404, detail="课堂会话不存在")
    return ResponseData(data=result)


@router.get("/classroom/{session_id}/report", response_model=ResponseData)
async def get_classroom_report(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取课堂报告"""
    report = await PPTService.get_classroom_report(db, session_id, teacher_id)
    if not report:
        raise HTTPException(status_code=404, detail="课堂会话不存在")
    return ResponseData(data=report)


# ========== 投票 ==========

@router.post("/classroom/{session_id}/vote/create", response_model=ResponseData)
async def create_vote(
    session_id: int,
    body: ClassroomVoteRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """创建课堂投票"""
    result = await ClassroomService.create_vote(db, teacher_id, session_id, body.question, body.options)
    if not result:
        raise HTTPException(status_code=404, detail="课堂会话不存在")
    return ResponseData(data=result)


@router.post("/classroom/{session_id}/vote/submit", response_model=ResponseData)
async def submit_vote(
    session_id: int,
    vote_id: str = Query(..., description="投票ID"),
    option_index: int = Query(..., ge=0, description="选项索引"),
    db: AsyncSession = Depends(get_db),
):
    """提交投票（学生端）"""
    result = await ClassroomService.submit_vote(db, session_id, vote_id, option_index)
    if not result:
        raise HTTPException(status_code=404, detail="投票不存在或已关闭")
    return ResponseData(data=result)


@router.get("/classroom/{session_id}/vote/{vote_id}/results", response_model=ResponseData)
async def get_vote_results(
    session_id: int,
    vote_id: str,
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher_id),
):
    """获取投票结果"""
    result = await ClassroomService.get_vote_results(db, session_id, vote_id)
    if not result:
        raise HTTPException(status_code=404, detail="投票不存在")
    return ResponseData(data=result)


@router.post("/classroom/{session_id}/vote/{vote_id}/close", response_model=ResponseData)
async def close_vote(
    session_id: int,
    vote_id: str,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """关闭投票"""
    result = await ClassroomService.close_vote(db, teacher_id, session_id, vote_id)
    if not result:
        raise HTTPException(status_code=404, detail="投票不存在")
    return ResponseData(data=result)


# ========== 课堂答题 ==========

@router.post("/classroom/{session_id}/quiz/create", response_model=ResponseData)
async def create_quiz(
    session_id: int,
    body: ClassroomQuizRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """创建课堂答题"""
    result = await ClassroomService.create_quiz(db, teacher_id, session_id, body.question, body.options, body.correct_answer)
    if not result:
        raise HTTPException(status_code=404, detail="课堂会话不存在")
    return ResponseData(data=result)


@router.post("/classroom/{session_id}/quiz/submit", response_model=ResponseData)
async def submit_quiz(
    session_id: int,
    quiz_id: str = Query(..., description="答题ID"),
    selected: int = Query(..., ge=0, description="选择的选项索引"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """提交答题（学生端）"""
    result = await ClassroomService.submit_quiz_answer(db, session_id, quiz_id, selected, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="答题不存在")
    if result.get("duplicate"):
        raise HTTPException(status_code=409, detail="你已经回答过这道题了")
    return ResponseData(data=result)


@router.get("/classroom/{session_id}/quiz/{quiz_id}/results", response_model=ResponseData)
async def get_quiz_results(
    session_id: int,
    quiz_id: str,
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher_id),
):
    """获取答题统计（教师端）"""
    result = await ClassroomService.get_quiz_results(db, session_id, quiz_id)
    if not result:
        raise HTTPException(status_code=404, detail="答题不存在")
    return ResponseData(data=result)


# ========== 学生端获取活跃答题 ==========

@router.get("/classroom/{session_id}/active-quizzes", response_model=ResponseData)
async def get_active_quizzes(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取课堂活跃答题列表（学生端）"""
    quizzes = await ClassroomService.get_active_quizzes(db, session_id)
    return ResponseData(data={"quizzes": quizzes})


@router.get("/classroom/{session_id}/quiz/{quiz_id}/student-results", response_model=ResponseData)
async def get_quiz_student_results(
    session_id: int,
    quiz_id: str,
    db: AsyncSession = Depends(get_db),
):
    """学生端查看答题统计"""
    result = await ClassroomService.get_quiz_result_for_student(db, session_id, quiz_id)
    if not result:
        raise HTTPException(status_code=404, detail="答题不存在")
    return ResponseData(data=result)


# ========== 弹幕 ==========

@router.post("/classroom/{session_id}/danmaku", response_model=ResponseData)
async def send_danmaku(
    session_id: int,
    body: ClassroomDanmakuRequest,
    db: AsyncSession = Depends(get_db),
):
    """发送弹幕（学生端）"""
    result = await ClassroomService.send_danmaku(db, session_id, body.content, body.student_name)
    if not result:
        raise HTTPException(status_code=404, detail="课堂会话不存在")
    return ResponseData(data=result)


@router.get("/classroom/{session_id}/danmaku", response_model=ResponseData)
async def get_danmaku(
    session_id: int,
    since_id: str = Query("", description="增量拉取标识"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """获取弹幕列表（支持增量拉取）"""
    data = await ClassroomService.get_danmaku(db, session_id, since_id, limit)
    return ResponseData(data={"items": data, "total": len(data)})


# ========== 提问 ==========

@router.post("/classroom/{session_id}/question", response_model=ResponseData)
async def ask_question(
    session_id: int,
    body: ClassroomQuestionRequest,
    db: AsyncSession = Depends(get_db),
):
    """学生提问"""
    result = await ClassroomService.ask_question(db, session_id, body.question, body.student_name)
    if not result:
        raise HTTPException(status_code=404, detail="课堂会话不存在")
    return ResponseData(data=result)


@router.post("/classroom/{session_id}/question/{question_id}/answer", response_model=ResponseData)
async def answer_question(
    session_id: int,
    question_id: str,
    answer: str = Query(..., description="回答内容"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """教师回答问题"""
    result = await ClassroomService.answer_question(db, teacher_id, session_id, question_id, answer)
    if not result:
        raise HTTPException(status_code=404, detail="问题不存在")
    return ResponseData(data=result)


# ========== 幻灯片练习题答题记录 ==========

@router.post("/classroom/{session_id}/slide-answer", response_model=ResponseData)
async def record_slide_answer(
    session_id: int,
    body: SlideAnswerRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """记录幻灯片上练习题答题结果（从 iframe postMessage 接收）"""
    result = await ClassroomService.record_slide_answer(
        db, teacher_id, session_id,
        body.page_index, body.question_index,
        body.selected, body.correct,
    )
    if not result:
        raise HTTPException(status_code=404, detail="课堂会话不存在")
    return ResponseData(data=result)


# ========== 页面同步 ==========

@router.post("/classroom/{session_id}/page-sync", response_model=ResponseData)
async def sync_page(
    session_id: int,
    page_index: int = Query(..., ge=0, description="页面索引"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """同步当前播放页"""
    result = await ClassroomService.sync_page(db, teacher_id, session_id, page_index)
    if not result:
        raise HTTPException(status_code=404, detail="课堂会话不存在")
    return ResponseData(data=result)


@router.get("/classroom/{session_id}/current-page", response_model=ResponseData)
async def get_current_page(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取当前页（供学生端轮询）"""
    result = await ClassroomService.get_current_page(db, session_id)
    if not result:
        raise HTTPException(status_code=404, detail="课堂会话不存在")
    return ResponseData(data=result)


# ========== 会话状态 ==========

@router.post("/classroom/{session_id}/pause", response_model=ResponseData)
async def pause_classroom(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """暂停课堂"""
    result = await ClassroomService.pause_classroom(db, teacher_id, session_id)
    if not result:
        raise HTTPException(status_code=404, detail="课堂会话不存在")
    return ResponseData(data=result)


@router.post("/classroom/{session_id}/resume", response_model=ResponseData)
async def resume_classroom(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """恢复课堂"""
    result = await ClassroomService.resume_classroom(db, teacher_id, session_id)
    if not result:
        raise HTTPException(status_code=404, detail="课堂会话不存在")
    return ResponseData(data=result)


# ========== 课堂会话列表 ==========

@router.get("/classroom/list", response_model=ResponseData)
async def list_classroom_sessions(
    status: Optional[str] = Query(None, description="筛选状态"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取课堂会话列表"""
    result = await PPTService.list_classroom_sessions(db, teacher_id, status, page, page_size)
    return ResponseData(data=result)


# ========== 主题管理 ==========

@router.get("/themes/list", response_model=ResponseData)
async def list_themes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取主题列表（内置 + 教师自定义）"""
    result = await PPTThemeService.list_themes(db, teacher_id, page, page_size)
    return ResponseData(data=result)


@router.get("/themes/{theme_id}", response_model=ResponseData)
async def get_theme(
    theme_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取主题详情（含完整 CSS）"""
    result = await PPTThemeService.get_theme(db, theme_id)
    if not result:
        raise HTTPException(status_code=404, detail="主题不存在")
    return ResponseData(data=result)


@router.post("/themes", response_model=ResponseData)
async def create_theme(
    body: ThemeCreate,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """创建自定义主题"""
    try:
        result = await PPTThemeService.create_custom_theme(
            db=db, teacher_id=teacher_id,
            name=body.name, display_name=body.display_name,
            css_variables=body.css_variables, css_content=body.css_content,
            description=body.description, preview_color=body.preview_color,
            style_skill=body.style_skill,
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/themes/{theme_id}", response_model=ResponseData)
async def update_theme(
    theme_id: int,
    body: ThemeUpdate,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """更新自定义主题"""
    result = await PPTThemeService.update_theme(
        db, theme_id, teacher_id, body.model_dump(exclude_unset=True)
    )
    if not result:
        raise HTTPException(status_code=404, detail="主题不存在或无权修改")
    return ResponseData(data=result)


@router.delete("/themes/{theme_id}", response_model=ResponseData)
async def delete_theme(
    theme_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """删除自定义主题"""
    success = await PPTThemeService.delete_theme(db, theme_id, teacher_id)
    if not success:
        raise HTTPException(status_code=404, detail="主题不存在或无权删除")
    return ResponseData(message="删除成功")


# ========== 版本历史 ==========

@router.get("/{ppt_id}/versions", response_model=ResponseData)
async def list_versions(
    ppt_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取 PPT 版本历史列表"""
    # 验证 PPT 归属
    ppt = await PPTService.get_ppt(db, ppt_id, teacher_id)
    if not ppt:
        raise HTTPException(status_code=404, detail="PPT 不存在")

    query = select(PptVersion).where(
        PptVersion.ppt_id == ppt_id
    ).order_by(desc(PptVersion.version)).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await db.execute(query)
    versions = result.scalars().all()

    count_q = select(func.count()).select_from(
        select(PptVersion).where(PptVersion.ppt_id == ppt_id).subquery()
    )
    total = (await db.execute(count_q)).scalar() or 0

    items = []
    for v in versions:
        items.append({
            "id": v.id,
            "ppt_id": v.ppt_id,
            "version": v.version,
            "theme_name": v.theme_name or "",
            "change_summary": v.change_summary or "",
            "created_at": v.created_at.isoformat() if v.created_at else "",
        })

    return ResponseData(data={"items": items, "total": total})


@router.get("/{ppt_id}/versions/{version_id}", response_model=ResponseData)
async def get_version(
    ppt_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取指定版本的详情"""
    ppt = await PPTService.get_ppt(db, ppt_id, teacher_id)
    if not ppt:
        raise HTTPException(status_code=404, detail="PPT 不存在")

    result = await db.execute(
        select(PptVersion).where(
            PptVersion.id == version_id,
            PptVersion.ppt_id == ppt_id,
        )
    )
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="版本不存在")

    return ResponseData(data={
        "id": v.id,
        "ppt_id": v.ppt_id,
        "version": v.version,
        "html_content": v.html_content or "",
        "pages_json": v.pages_json or [],
        "theme_name": v.theme_name or "",
        "change_summary": v.change_summary or "",
        "created_at": v.created_at.isoformat() if v.created_at else "",
    })


# ========== PPT 导出 ==========

def _ensure_pages_list(pages_json: any) -> list:
    """确保 pages_json 是 list，兼容数据库返回字符串的情况"""
    if isinstance(pages_json, list):
        return pages_json
    if isinstance(pages_json, dict):
        # 部分数据可能以 dict 包裹 { "pages": [...] } 格式存储
        for key in ("pages", "slides", "data"):
            val = pages_json.get(key)
            if isinstance(val, list):
                return val
        # 无法解析则返回空
        return []
    if isinstance(pages_json, str):
        try:
            parsed = json.loads(pages_json)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                for key in ("pages", "slides", "data"):
                    val = parsed.get(key)
                    if isinstance(val, list):
                        return val
        except (json.JSONDecodeError, TypeError):
            pass
    return []


@router.get("/{ppt_id}/export", response_model=ResponseData)
async def export_ppt(
    ppt_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """导出 PPT 为自包含 HTML"""
    ppt = await PPTService.get_ppt(db, ppt_id, teacher_id)
    if not ppt:
        raise HTTPException(status_code=404, detail="PPT 不存在")

    # 若已有 html_content 则直接返回，否则实时渲染
    html_content = ppt.get("html_content") or ""
    if not html_content:
        try:
            theme_name = ppt.get("theme_name", "classic")
            pages_list = _ensure_pages_list(ppt.get("pages_json", []))
            if not pages_list:
                raise ValueError("PPT 页面数据为空或格式异常")
            # Phase 3.5: 从 spec_lock 提取 visual_style
            spec_lock_data = ppt.get("spec_lock", {})
            vs = ""
            if isinstance(spec_lock_data, dict):
                vs = spec_lock_data.get("visual_style", "")
            html_content = await PPTHtmlRenderer.render_from_db(
                db, pages_list, ppt["title"], theme_name,
                visual_style=vs,
            )
            # 渲染成功后保存到数据库供后续复用
            if html_content:
                db_ppt = (await db.execute(
                    select(LessonPPT).where(LessonPPT.id == ppt_id)
                )).scalar_one_or_none()
                if db_ppt:
                    db_ppt.html_content = html_content
                    await db.commit()
        except Exception as e:
            print(f"[ppt] export_ppt ppt_id={ppt_id} 渲染失败: {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()
            # 返回 500 而非 400（ValueError 会被全局 handler 拦截），确保前端能识别异常
            raise HTTPException(status_code=500, detail=f"PPT 渲染失败: {str(e)}")

    return ResponseData(data={
        "id": ppt["id"],
        "title": ppt["title"],
        "html_content": html_content,
        "theme_name": ppt.get("theme_name", "classic"),
        "slide_count": ppt.get("slide_count", 0),
    })





# ========== PPT 重设主题 ==========

@router.post("/{ppt_id}/retheme", response_model=ResponseData)
async def retheme_ppt(
    ppt_id: int,
    theme_name: str = Query(..., description="目标主题名"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """切换 PPT 主题并重新渲染"""
    result = await PPTService.update_ppt(db, ppt_id, teacher_id, {"theme_name": theme_name})
    if not result:
        raise HTTPException(status_code=404, detail="PPT 不存在或主题不存在")
    return ResponseData(data=result)


# ========== TTS 语音合成（PPT 幻灯片内嵌音频）==========

class TTSRequest(BaseModel):
    text: str
    voice: str = ""

@router.post("/tts", response_model=ResponseData)
async def generate_tts(
    request: TTSRequest,
):
    """为 PPT 幻灯片生成 TTS 音频，返回音频 URL"""
    from app.core.config import get_settings
    settings = get_settings()
    import os, hashlib
    try:
        audio_bytes = await TTSService.synthesize(
            text=request.text,
            voice_type=request.voice or settings.TTS_VOICE,
        )
        if not audio_bytes:
            raise HTTPException(status_code=500, detail="TTS 合成返回空数据")

        text_hash = hashlib.md5(request.text.strip().encode("utf-8")).hexdigest()[:12]
        audio_dir = str(UPLOADS_DIR / "ppt_audio")
        os.makedirs(audio_dir, exist_ok=True)
        filename = f"ppt_audio_lazy_{text_hash}.mp3"
        filepath = os.path.join(audio_dir, filename)
        with open(filepath, "wb") as f:
            f.write(audio_bytes)

        return ResponseData(data={"url": f"/uploads/ppt_audio/{filename}"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS 生成失败: {str(e)}")


# ========== PPT 幻灯片插图生成 ==========

class ImageGenRequest(BaseModel):
    prompt: str
    style: str = ""

@router.post("/generate-image", response_model=ResponseData)
async def generate_slide_image(
    request: ImageGenRequest,
):
    """为 PPT 幻灯片生成插图，返回图片 URL"""
    try:
        url = await AnimationService.generate_image(
            prompt=request.prompt,
            style=request.style or "illustration",
        )
        return ResponseData(data={"url": url})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图片生成失败: {str(e)}")


# ========== 内容分析（Phase 3.1）==========

class ContentAnalysisRequest(BaseModel):
    """内容分析请求"""
    pages: list = Field(..., description="PPT 页面数据列表")


@router.post("/analyze-content", response_model=ResponseData)
async def analyze_ppt_content(
    request: ContentAnalysisRequest,
):
    """分析 PPT 页面数据的内容特征，推荐视觉风格和布局策略

    独立的内容分析端点，供前端在开始生成前预览风格推荐结果。

    返回:
        {
            "profile": {...},          # 内容分析详细数据
            "recommendedStyle": "...",  # 推荐的视觉风格
            "layoutStrategy": {...},    # 布局策略推荐
            "styleCandidates": [...]    # Top-N 风格候选项
        }
    """
    try:
        from app.ppt_generator.analysis.content_analyzer import ContentAnalyzer

        analyzer = ContentAnalyzer()
        profile = analyzer.analyze(request.pages)

        result = {
            "profile": profile.to_dict(),
            "recommendedStyle": analyzer.recommend_style(profile),
            "layoutStrategy": analyzer.recommend_layout_strategy(profile),
            "styleCandidates": [
                {"style": s, "reason": r}
                for s, r in analyzer.generate_style_candidates(profile, top_n=3)
            ],
        }
        logger.info(f"内容分析完成: {profile.describe()}")
        return ResponseData(data=result)
    except Exception as e:
        logger.error(f"内容分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"内容分析失败: {str(e)}")

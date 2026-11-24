"""知识图谱 API 路由 — 6 个端点 + 1 个 SSE 流式端点"""
import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db, async_session
from app.api.deps import get_current_teacher_id
from app.services.ai_service import AIService
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.schemas.knowledge_graph import KGGenerateRequest, KGUpdateRequest
from app.schemas.common import ResponseData
from app.utils.json_utils import safe_json_dumps
from typing import Optional

logger = logging.getLogger("knowledge_graph")

router = APIRouter(prefix="/teacher/ppt/knowledge-graph", tags=["教师端-知识图谱"])


@router.post("/generate", response_model=ResponseData)
async def generate_knowledge_graph(
    body: KGGenerateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """第一阶段：AI 生成知识图谱（章节→知识点树形结构）— 非流式版本"""
    try:
        result = await KnowledgeGraphService.generate_graph(
            db=db,
            teacher_id=teacher_id,
            title=body.title,
            lesson_type=body.lesson_type,
            subject=body.subject,
            grade=body.grade,
            supplement=body.supplement,
            expected_sections=body.expected_sections,
            expected_nodes_per_section=body.expected_nodes_per_section,
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate-sse")
async def generate_knowledge_graph_sse(
    body: KGGenerateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """第一阶段（SSE 流式）：AI 生成知识图谱，通过 Server-Sent Events 推送进度

    优化：在 SSE 生成器启动前预获取 API 配置，LLM 调用期间不持有 DB 连接。
    """
    print(f"[SSE] 知识图谱生成请求开始 | teacher={teacher_id} title={body.title} lesson_type={body.lesson_type}")
    logger.info(
        "[SSE] 知识图谱生成请求开始 | teacher=%s title=%s lesson_type=%s",
        teacher_id, body.title, body.lesson_type,
    )

    # 预获取 API 配置（在 SSE 流启动前，短暂持有 DB 连接）
    try:
        api_config = await AIService.prefetch_api_config(db, teacher_id)
        print(f"[SSE] API 配置预获取成功 | teacher={teacher_id}", flush=True)
    except Exception as e:
        logger.error("[SSE] API 配置预获取失败 | teacher=%s err=%s", teacher_id, e)
        raise HTTPException(status_code=500, detail=f"获取 API 配置失败: {str(e)}")
    # 配置已获取，DB 连接在此释放（Depends(get_db) 自动 close）

    async def event_stream():
        """SSE 事件生成器 — 仅在读写数据库时短暂获取 DB 连接，LLM 调用期间不持有"""
        print("[SSE] event_stream 生成器已创建，准备迭代...", flush=True)
        try:
            step = 0
            # 整体超时 120 秒，防止无限挂起
            async with asyncio.timeout(120):
                async for event in KnowledgeGraphService.generate_graph_stream(
                    teacher_id=teacher_id,
                    title=body.title,
                    lesson_type=body.lesson_type,
                    subject=body.subject,
                    grade=body.grade,
                    supplement=body.supplement,
                    expected_sections=body.expected_sections,
                    expected_nodes_per_section=body.expected_nodes_per_section,
                    api_config=api_config,
                ):
                    event_type = event.get("type", "message")
                    data = safe_json_dumps(event, ensure_ascii=False)  # 大整数转字符串，防止前端精度丢失
                    print(f"[SSE] yield event | type={event_type} progress={event.get('progress')} msg={event.get('message')}", flush=True)
                    yield f"event: {event_type}\ndata: {data}\n\n"
                    await asyncio.sleep(0)
                    if event_type in ("complete", "error"):
                        logger.info(
                            "[SSE] 知识图谱流结束 | type=%s teacher=%s",
                            event_type, teacher_id,
                        )
                    elif event_type == "progress" and step % 2 == 0:
                        logger.info(
                            "[SSE] 知识图谱进度 | teacher=%s progress=%s msg=%s",
                            teacher_id, event.get("progress"), event.get("message"),
                        )
                    step += 1
        except asyncio.TimeoutError:
            print(f"[SSE] 知识图谱流超时 | teacher={teacher_id}", flush=True)
            logger.error("[SSE] 知识图谱流超时 | teacher=%s", teacher_id)
            error_data = safe_json_dumps(
                {"type": "error", "message": "知识图谱生成超时（120秒），请检查 AI 服务状态后重试"},
                ensure_ascii=False,
            )
            yield f"event: error\ndata: {error_data}\n\n"
        except Exception as e:
            print(f"[SSE] 知识图谱流异常 | err={e}", flush=True)
            logger.error(
                "[SSE] 知识图谱流异常 | teacher=%s err=%s",
                teacher_id, str(e), exc_info=True,
            )
            error_data = safe_json_dumps(
                {"type": "error", "message": f"服务器内部错误: {str(e)}"},
                ensure_ascii=False,
            )
            yield f"event: error\ndata: {error_data}\n\n"

    print("[SSE] 返回 StreamingResponse")
    logger.info("[SSE] 返回 StreamingResponse")
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{kg_id:int}", response_model=ResponseData)
async def get_knowledge_graph(
    kg_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取单个知识图谱详情"""
    result = await KnowledgeGraphService.get_graph(db, kg_id, teacher_id)
    if not result:
        raise HTTPException(status_code=404, detail="知识图谱不存在")
    return ResponseData(data=result)


@router.put("/{kg_id}", response_model=ResponseData)
async def update_knowledge_graph(
    kg_id: int,
    body: KGUpdateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """保存知识图谱修改（整树替换），仅 draft 状态可编辑"""
    try:
        result = await KnowledgeGraphService.update_graph(
            db=db, kg_id=kg_id, teacher_id=teacher_id,
            content=body.content,
            title=body.title,
        )
        if not result:
            raise HTTPException(status_code=404, detail="知识图谱不存在")
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{kg_id}/confirm", response_model=ResponseData)
async def confirm_knowledge_graph(
    kg_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """确认锁定知识图谱（draft→confirmed），不可再编辑"""
    try:
        result = await KnowledgeGraphService.confirm_graph(db, kg_id, teacher_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    if not result:
        raise HTTPException(status_code=404, detail="知识图谱不存在")
    return ResponseData(data=result)


@router.post("/{kg_id}/generate-ppt", response_model=ResponseData)
async def generate_ppt_from_graph(
    kg_id: int,
    theme_name: str = Query("classic", description="PPT 主题名称"),
    visual_style: str = Query("", description="视觉风格名称（Phase 3.3）"),
    spec_lock: str = Query("", description="设计规格锁定 JSON 字符串（Phase 3.3）"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """第二阶段：基于已确认的知识图谱生成完整 PPT"""
    parsed_spec_lock = None
    if spec_lock:
        try:
            parsed_spec_lock = json.loads(spec_lock)
        except (json.JSONDecodeError, TypeError):
            pass
    try:
        result = await KnowledgeGraphService.generate_ppt_from_graph(
            db=db, kg_id=kg_id, teacher_id=teacher_id,
            theme_name=theme_name, visual_style=visual_style or None,
            spec_lock=parsed_spec_lock,
        )
        return ResponseData(data=result)
    except ValueError as e:
        import traceback as _tb
        _tb.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        raise HTTPException(status_code=500, detail=f"生成 PPT 时发生未知错误: {type(e).__name__}: {str(e)}")


@router.get("/list", response_model=ResponseData)
async def list_knowledge_graphs(
    status: Optional[str] = Query(None, description="筛选状态: draft/confirmed"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取教师的知识图谱列表"""
    result = await KnowledgeGraphService.list_graphs(
        db, teacher_id, status, page, page_size,
    )
    return ResponseData(data=result)

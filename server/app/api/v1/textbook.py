"""
教材点读 API 路由

提供:
- 教材层级选择：版本 → 年级 → 学期 → 单元 → 页面
- 页面点读：全文、分句、图片、音频
- 单词点读查询
- 阅读进度
- 教材上传/解析/查看/删除
"""
import os
import uuid
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.db.database import get_db, get_words_db
from app.api.deps import get_current_user_id, get_current_teacher_id
from app.schemas.common import ResponseData
from app.services.textbook_service import TextbookService
from app.services.textbook_pdf_service import TextbookPDFService
from app.core.middleware.membership_limit import require_feature
from app.core.config import get_settings
from app.core.paths import UPLOADS_DIR
from app.models.textbook_upload import TextbookUpload
from app.models.textbook_models import TextbookPage, TextbookUnit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/textbook", tags=["教材点读"])
settings = get_settings()
UPLOAD_DIR = str(UPLOADS_DIR / "textbook")


# ========== 教材层级 API ==========

@router.get("/versions", response_model=ResponseData[list])
async def list_versions(
    db: AsyncSession = Depends(get_db),
):
    """获取教材版本列表"""
    versions = await TextbookService.list_versions(db)
    return ResponseData(data=versions)


@router.get("/{version}/grades", response_model=ResponseData[list])
async def list_grades(
    version: str = Path(..., description="教材版本 e.g. PEP"),
    db: AsyncSession = Depends(get_db),
):
    """获取某版本下的年级列表"""
    grades = await TextbookService.list_grades(db, version)
    return ResponseData(data=grades)


@router.get("/{version}/{grade}/semesters", response_model=ResponseData[list])
async def list_semesters(
    version: str = Path(...),
    grade: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """获取某年级下的学期列表"""
    semesters = await TextbookService.list_semesters(db, version, grade)
    return ResponseData(data=semesters)


@router.get("/{version}/{grade}/{semester}/units", response_model=ResponseData[list])
async def list_units(
    version: str = Path(...),
    grade: str = Path(...),
    semester: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """获取某学期下的单元列表"""
    units = await TextbookService.list_units(db, version, grade, semester)
    return ResponseData(data=units)


@router.get("/{version}/{grade}/{semester}/{unit}/pages", response_model=ResponseData[list])
async def list_pages(
    version: str = Path(...),
    grade: str = Path(...),
    semester: str = Path(...),
    unit: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """获取某单元下的页面列表"""
    settings = get_settings()
    cdn_base = getattr(settings, "CDN_BASE_URL", "")
    pages = await TextbookService.list_pages(db, version, grade, unit, semester, cdn_base=cdn_base)
    return ResponseData(data=pages)


# ========== 点读核心 API ==========

@router.get("/page/{page_id}", response_model=ResponseData[dict])
async def get_page_detail(
    page_id: int = Path(..., ge=1),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    words_db: AsyncSession = Depends(get_words_db),
    _=Depends(require_feature("textbook_reading")),
):
    """获取页面完整内容（含分句、单词、音频URL）"""
    settings = get_settings()
    cdn_base = getattr(settings, "CDN_BASE_URL", "")
    detail = await TextbookService.get_page_detail(db, page_id, cdn_base, words_db=words_db)
    if not detail:
        return ResponseData(code=1, message="页面不存在")
    # 记录阅读进度
    await TextbookService.save_reading_progress(db, user_id, page_id)
    return ResponseData(data=detail)


@router.get("/page/{page_id}/navigate", response_model=ResponseData[dict])
async def get_page_navigation(
    page_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
):
    """获取翻页导航（上一页/下一页 ID）"""
    nav = await TextbookService.get_adjacent_pages(db, page_id)
    return ResponseData(data=nav)


@router.get("/page/{version}/{grade}/{semester}/{unit}/{page_number}", response_model=ResponseData[dict])
async def get_page_by_number(
    version: str = Path(...),
    grade: str = Path(...),
    semester: str = Path(...),
    unit: str = Path(...),
    page_number: int = Path(..., ge=1),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    words_db: AsyncSession = Depends(get_words_db),
    _=Depends(require_feature("textbook_reading")),
):
    """按页码获取页面内容"""
    settings = get_settings()
    cdn_base = getattr(settings, "CDN_BASE_URL", "")
    detail = await TextbookService.get_page_by_number(
        db, version, grade, unit, page_number, semester, cdn_base, words_db=words_db
    )
    if not detail:
        return ResponseData(code=1, message="页面不存在")
    await TextbookService.save_reading_progress(db, user_id, detail["id"])
    return ResponseData(data=detail)


# ========== 单词查询 ==========

@router.get("/word/{word}", response_model=ResponseData[dict])
async def search_word(
    word: str = Path(..., description="查询的单词"),
    db: AsyncSession = Depends(get_db),
    words_db: AsyncSession = Depends(get_words_db),
):
    """查询单词详情（音标/释义）"""
    result = await TextbookService.search_word(db, word, words_db=words_db)
    if not result:
        return ResponseData(code=1, message="未找到该单词")
    return ResponseData(data=result)


# ========== TTS 音频 ==========

@router.post("/page/{page_id}/tts", response_model=ResponseData[dict])
async def generate_tts(
    page_id: int = Path(..., ge=1),
    sentence_index: int = Query(-1, description="指定句子索引，-1=全文"),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """即时合成 TTS 音频，返回 audio_url（同时更新 DB 持久化）

    第 1 次调用时调用火山引擎 API 合成，
    后续自动从永久文件缓存读取（零费用）。
    """
    from app.services.tts_service import TTSService
    from app.models.textbook_models import TextbookPage
    import json

    # 1. 合成音频
    result = await TTSService.synthesize_for_page(db, page_id, sentence_index)
    if not result.get("audio_url"):
        return ResponseData(code=1, message=result.get("error", "TTS 合成失败"))

    # 2. 将 audio_url 持久化到数据库（下次前端直接取 sentences_json.audio_url 即可）
    page = await db.get(TextbookPage, page_id)
    if page:
        if sentence_index >= 0 and page.sentences_json:
            # 更新句子级 audio_url → 下次 onTapSentence 直接走第 2 级优先级
            sentences = list(page.sentences_json)
            if sentence_index < len(sentences):
                if isinstance(sentences[sentence_index], dict):
                    sentences[sentence_index] = dict(sentences[sentence_index])
                    sentences[sentence_index]["audio_url"] = result["audio_url"]
                    page.sentences_json = sentences
                    await db.flush()
                    logger.info("已持久化 sentences_json[%s].audio_url = %s",
                                sentence_index, result["audio_url"])
        elif sentence_index == -1 and not page.audio_url:
            # 首次整页合成 → 更新 page.audio_url
            page.audio_url = result["audio_url"]
            await db.flush()
            logger.info("已持久化 page.audio_url = %s", result["audio_url"])

        await db.commit()

    return ResponseData(data=result)


# ========== 分句角色分析 ==========

@router.post("/page/{page_id}/analyze-sentences", response_model=ResponseData[dict])
async def analyze_page_sentences(
    page_id: int = Path(..., ge=1),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """AI 分析页面课文，拆分为分句并识别每个句子的说话角色（speaker）
    
    输出:
      - 更新 page.sentences_json 为结构化分句 [{en, cn, speaker}]
      - 返回分析结果
    """
    from app.services.sentence_analyzer_service import SentenceAnalyzerService

    result = await SentenceAnalyzerService.analyze_and_save(db, page_id, user_id)
    if not result.get("success"):
        return ResponseData(code=1, message=result.get("error", "分句分析失败"))
    
    await db.commit()
    return ResponseData(data=result)


@router.post("/page/{page_id}/batch-analyze-sentences", response_model=ResponseData[dict])
async def batch_analyze_sentences(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """批量分析当前用户所有尚未分句的页面

    遍历所有 page.is_active=1 且 sentences_json 为空的页面，
    逐页调用 AI 进行分句角色分析。
    """
    from app.services.sentence_analyzer_service import SentenceAnalyzerService
    from sqlalchemy import select, and_

    stmt = select(TextbookPage).where(and_(
        TextbookPage.is_active == 1,
        TextbookPage.sentences_json.is_(None),
    )).order_by(TextbookPage.textbook_version, TextbookPage.grade, TextbookPage.unit_number, TextbookPage.page_number)

    result = await db.execute(stmt)
    pages = result.scalars().all()

    total = len(pages)
    succeeded = 0
    failed = 0
    results = []

    for page in pages:
        try:
            r = await SentenceAnalyzerService.analyze_and_save(db, page.id, user_id)
            if r.get("success"):
                succeeded += 1
                results.append({"page_id": page.id, "sentences": r.get("sentences_count", 0)})
            else:
                failed += 1
                results.append({"page_id": page.id, "error": r.get("error", "分析失败")})
        except Exception as e:
            failed += 1
            results.append({"page_id": page.id, "error": str(e)})
            logger.error("批量分句分析异常: page_id=%s, error=%s", page.id, e)

    await db.commit()
    logger.info("批量分句分析完成: total=%s, succeeded=%s, failed=%s", total, succeeded, failed)
    return ResponseData(data={
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    })


# ========== 微动图 ==========

@router.post("/page/{page_id}/animation", response_model=ResponseData[dict])
async def create_animation(
    page_id: int = Path(..., ge=1),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """创建微动图生成任务（异步处理，返回 task_id）"""
    from app.services.animation_service import AnimationService
    task = await AnimationService.create_animation_task(db, page_id, user_id)
    return ResponseData(data=task)


@router.get("/animation/{task_id}/status", response_model=ResponseData[dict])
async def get_animation_status(
    task_id: str = Path(..., description="微动图任务ID"),
):
    """查询微动图生成状态"""
    from app.services.animation_service import AnimationService
    status = await AnimationService.get_animation_status(task_id)
    return ResponseData(data=status)


# ========== 阅读进度 ==========

@router.post("/progress", response_model=ResponseData[dict])
async def save_progress(
    page_id: int = Query(..., ge=1),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """保存阅读进度"""
    result = await TextbookService.save_reading_progress(db, user_id, page_id)
    return ResponseData(data=result)


# ========== 教材上传/解析 ==========

@router.post("/upload", response_model=ResponseData[dict])
async def upload_textbook(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF 教材文件"),
    textbook_version: str = Form("PEP", description="教材版本"),
    grade: str = Form("3", description="年级"),
    semester: str = Form("上", description="学期"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """上传教材 PDF — 立即返回 upload_id，后台异步解析

    解析流程:
      1. 保存 PDF 文件
      2. 后台异步逐页提取文本
      3. 自动检测单元边界（Unit X / 第X单元）
      4. 创建 TextbookPage 记录

    前端轮询: GET /api/v1/textbook/uploads/{upload_id}
    查看解析页: GET /api/v1/textbook/uploads/{upload_id}/pages
    """
    _, ext = os.path.splitext(file.filename or "")
    if ext.lower() != ".pdf":
        raise ValueError("仅支持 PDF 格式文件")

    content = await file.read()
    if len(content) > 200 * 1024 * 1024:
        raise ValueError("文件大小不能超过 200MB")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_key = f"{user_id}/{uuid.uuid4().hex}.pdf"
    file_path = os.path.join(UPLOAD_DIR, file_key)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "wb") as f:
        f.write(content)

    # 创建上传记录
    upload = TextbookUpload(
        user_id=user_id,
        filename=file.filename or "unknown.pdf",
        file_key=file_key,
        file_size=len(content),
        textbook_version=textbook_version,
        grade=grade,
        semester=semester,
        parse_status=0,
    )
    db.add(upload)
    await db.flush()
    await db.refresh(upload)
    await db.commit()

    async def _parse_background():
        """后台解析 PDF + 自动触发分句分析 + 微动图生成"""
        from app.db.database import async_session as get_async_session
        try:
            async with get_async_session() as parse_db:
                result = await TextbookPDFService.parse_and_import(
                    parse_db, upload.id, file_path,
                    textbook_version, grade, semester,
                )
                if result.get("success"):
                    await parse_db.commit()
                    logger.info(
                        f"教材解析完成 | upload_id={upload.id} "
                        f"pages={result.get('created_pages')} units={result.get('created_units')}"
                    )
                    # ── 自动触发：分句角色分析 + 增强微动图生成 ──
                    try:
                        await _auto_trigger_enhancements(
                            parse_db, upload.id,
                            result.get('textbook_version', textbook_version),
                            result.get('grade', grade),
                            result.get('semester', semester),
                        )
                    except Exception as post_e:
                        logger.error(
                            f"自动增强处理异常 upload_id={upload.id}: {post_e}",
                            exc_info=True,
                        )
                else:
                    # 解析失败时 parse_and_import 内部已调用 _mark_upload_error（flush），需要提交
                    await parse_db.commit()
                    logger.warning(f"教材解析失败 upload_id={upload.id}: {result.get('error')}")
        except Exception as e:
            logger.error(f"教材后台解析异常 upload_id={upload.id}: {e}", exc_info=True)
            # 标记失败
            try:
                async with get_async_session() as err_db:
                    up = await err_db.get(TextbookUpload, upload.id)
                    if up:
                        up.parse_status = 3
                        up.error_msg = str(e)[:500]
                        await err_db.commit()
            except Exception:
                pass

    background_tasks.add_task(_parse_background)

    return ResponseData(data={
        "upload_id": upload.id,
        "filename": upload.filename,
        "file_size": upload.file_size,
        "textbook_version": upload.textbook_version,
        "grade": upload.grade,
        "semester": upload.semester,
        "parse_status": 0,
        "message": "教材已上传，正在后台解析",
    })


@router.get("/uploads", response_model=ResponseData[dict])
async def list_textbook_uploads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取当前用户的教材上传记录列表（含动图/音频完成状态）"""
    stmt = (
        select(TextbookUpload)
        .where(TextbookUpload.user_id == user_id)
        .order_by(TextbookUpload.created_at.desc())
    )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    records = result.scalars().all()

    # 批量查询每本教材的动图/音频完成页数
    items = [_upload_to_dict(r) for r in records]
    if records:
        from sqlalchemy import or_
        # 按 (version, grade, semester) 聚合统计
        conditions = []
        for r in records:
            if r.textbook_version:
                conditions.append(
                    and_(
                        TextbookPage.textbook_version == r.textbook_version,
                        TextbookPage.grade == r.grade,
                        TextbookPage.semester == r.semester,
                        TextbookPage.is_active == 1,
                    )
                )
        if conditions:
            # 一次性查询所有相关页面的动画/音频状态
            stats_stmt = (
                select(TextbookPage)
                .where(or_(*conditions))
            )
            stats_result = await db.execute(stats_stmt)
            stats_pages = stats_result.scalars().all()

            # 按 (version, grade, semester) 分组计数
            stats_map = {}
            for sp in stats_pages:
                key = (sp.textbook_version, sp.grade, sp.semester)
                if key not in stats_map:
                    stats_map[key] = {"anim": 0, "audio": 0, "total": 0}
                stats_map[key]["total"] += 1
                if sp.animation_url:
                    stats_map[key]["anim"] += 1
                if sp.audio_url:
                    stats_map[key]["audio"] += 1

            # 填充到返回数据
            for item in items:
                key = (item.get("textbook_version"), item.get("grade"), item.get("semester"))
                stat = stats_map.get(key, {})
                item["animDone"] = stat.get("anim", 0) > 0
                item["audioDone"] = stat.get("audio", 0) > 0
                item["animCount"] = stat.get("anim", 0)
                item["audioCount"] = stat.get("audio", 0)

    return ResponseData(data={
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/uploads/{upload_id}", response_model=ResponseData[dict])
async def get_textbook_upload(
    upload_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取单条上传记录详情"""
    upload = await db.get(TextbookUpload, upload_id)
    if not upload:
        return ResponseData(code=1, message="上传记录不存在")
    if upload.user_id != user_id:
        return ResponseData(code=1, message="无权限查看此上传记录")

    return ResponseData(data=_upload_to_dict(upload))


@router.get("/uploads/{upload_id}/pages", response_model=ResponseData[list])
async def get_upload_pages(
    upload_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取某次上传解析出的页面列表"""
    upload = await db.get(TextbookUpload, upload_id)
    if not upload:
        return ResponseData(code=1, message="上传记录不存在")
    if upload.user_id != user_id:
        return ResponseData(code=1, message="无权限查看此上传记录")

    if upload.parse_status != 2:
        return ResponseData(data=[], message="教材尚未解析完成")

    # 查询该版本/年级/学期下的所有页面
    stmt = (
        select(
            TextbookPage.id,
            TextbookPage.unit_number,
            TextbookPage.page_number,
            TextbookPage.text_content,
            TextbookPage.created_at,
        )
        .where(and_(
            TextbookPage.textbook_version == upload.textbook_version,
            TextbookPage.grade == upload.grade,
            TextbookPage.semester == upload.semester,
            TextbookPage.is_active == 1,
        ))
        .order_by(TextbookPage.unit_number, TextbookPage.page_number)
    )
    result = await db.execute(stmt)
    rows = result.all()

    pages_list = []
    for row in rows:
        pages_list.append({
            "id": row.id,
            "unit_number": row.unit_number,
            "page_number": row.page_number,
            "text_preview": (row.text_content or "")[:200],
            "text_length": len(row.text_content or ""),
            "created_at": row.created_at.isoformat() if row.created_at else "",
        })

    return ResponseData(data=pages_list)


@router.delete("/uploads/{upload_id}", response_model=ResponseData[dict])
async def delete_textbook_upload(
    upload_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """删除上传记录及其解析的页面内容"""
    upload = await db.get(TextbookUpload, upload_id)
    if not upload:
        return ResponseData(code=1, message="上传记录不存在")
    if upload.user_id != user_id:
        return ResponseData(code=1, message="无权限删除此上传记录")

    # 删除关联的页面和空单元
    await TextbookPDFService.delete_pages_for_upload(
        db, upload.id, upload.textbook_version, upload.grade, upload.semester,
    )

    # 删除文件
    file_path = os.path.join(UPLOAD_DIR, upload.file_key)
    if os.path.exists(file_path):
        os.remove(file_path)

    # 删除上传记录
    await db.delete(upload)
    await db.flush()

    return ResponseData(data={"message": "上传记录已删除"})


@router.post("/uploads/{upload_id}/reparse", response_model=ResponseData[dict])
async def reparse_textbook_upload(
    background_tasks: BackgroundTasks,
    upload_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """重新解析已上传的教材 PDF"""
    upload = await db.get(TextbookUpload, upload_id)
    if not upload:
        return ResponseData(code=1, message="上传记录不存在")
    if upload.user_id != user_id:
        return ResponseData(code=1, message="无权限操作")

    file_path = os.path.join(UPLOAD_DIR, upload.file_key)
    if not os.path.exists(file_path):
        return ResponseData(code=1, message="原始文件已丢失，无法重新解析")

    # 先删除旧解析数据
    await TextbookPDFService.delete_pages_for_upload(
        db, upload.id, upload.textbook_version, upload.grade, upload.semester,
    )

    # 重置状态
    upload.parse_status = 0
    upload.total_pages = 0
    upload.parsed_pages = 0
    upload.error_msg = ""
    await db.flush()
    await db.commit()

    async def _reparse_background():
        from app.db.database import async_session as get_async_session
        try:
            async with get_async_session() as parse_db:
                result = await TextbookPDFService.parse_and_import(
                    parse_db, upload.id, file_path,
                    upload.textbook_version, upload.grade, upload.semester,
                )
                if result.get("success"):
                    logger.info(f"教材重新解析完成 upload_id={upload.id}")
                else:
                    logger.warning(f"教材重新解析失败 upload_id={upload.id}: {result.get('error')}")
        except Exception as e:
            logger.error(f"教材后台重新解析异常 upload_id={upload.id}: {e}", exc_info=True)

    background_tasks.add_task(_reparse_background)

    return ResponseData(data={
        "upload_id": upload.id,
        "message": "教材已加入重新解析队列",
    })


# ========== 自动增强处理（分句分析 + 微动图生成）==========


async def _auto_trigger_enhancements(
    db: AsyncSession,
    upload_id: int,
    textbook_version: str,
    grade: str,
    semester: str,
):
    """PDF 解析完成后自动触发：分句角色分析 + 增强微动图生成

    流程:
      1. 查询该上传所有活跃页面
      2. 逐页 AI 分句角色分析（同步，写入 sentences_json）
      3. 逐页串行生成增强微动图（每页立即保存到DB，中断不丢数据）
      4. 受 ANIMATION_BATCH_SIZE 限制，累计生成 N 张动图后停止（默认10张）
    """
    from app.services.sentence_analyzer_service import SentenceAnalyzerService
    from app.services.animation_service import AnimationService

    max_images = settings.ANIMATION_BATCH_SIZE  # 默认10张动图，避免一次生成整本太慢

    # Step 1: 查询页面
    stmt = (
        select(TextbookPage)
        .where(and_(
            TextbookPage.textbook_version == textbook_version,
            TextbookPage.grade == grade,
            TextbookPage.semester == semester,
            TextbookPage.is_active == 1,
            TextbookPage.text_content.isnot(None),
            TextbookPage.text_content != "",
        ))
        .order_by(TextbookPage.unit_number, TextbookPage.page_number)
    )
    result = await db.execute(stmt)
    pages = result.scalars().all()

    if not pages:
        logger.info("自动增强: 无页面可处理 upload_id=%s", upload_id)
        return

    logger.info("自动增强开始: upload_id=%s, total_pages=%s, max_images=%s",
                upload_id, len(pages), max_images)

    sentence_succeeded = 0
    total_images_generated = 0
    pages_completed = 0
    animation_limit_reached = False

    for page in pages:
        # Step 2: 分句角色分析（仅对尚无 sentences_json 的页面）
        if not page.sentences_json:
            try:
                sr = await SentenceAnalyzerService.analyze_and_save(
                    db, page.id, user_id=0,
                )
                if sr.get("success"):
                    sentence_succeeded += 1
                    logger.info(
                        "自动分句完成: page_id=%s, sentences=%s",
                        page.id, sr.get("sentences_count"),
                    )
                else:
                    logger.warning(
                        "自动分句失败: page_id=%s, error=%s",
                        page.id, sr.get("error"),
                    )
            except Exception as e:
                logger.error(
                    "自动分句异常: page_id=%s, error=%s",
                    page.id, e, exc_info=True,
                )

        # Step 3: 微动图生成（串行，按图片张数累计限制）
        if page.image_url and not page.animation_url:
            # 计算本页预计生成图片数（用于预判）
            estimated = _estimate_images_for_page(page)
            if total_images_generated + estimated > max_images and total_images_generated >= max_images:
                animation_limit_reached = True
                logger.info(
                    "微动图已达上限 %s 张（已生成 %s 张），跳过剩余页面: upload_id=%s",
                    max_images, total_images_generated, upload_id,
                )
                break

            # 如果本页会超过上限但仍未达到，传入剩余配额
            page_max_images = max(1, max_images - total_images_generated)

            try:
                task = await AnimationService.create_animation_task(
                    db, page.id, user_id=0, enhanced=True,
                )
                task_id = task.get("task_id", "")
                if task_id:
                    result_info = await _wait_for_animation_completion(task_id, page.id)
                    if result_info.get("success"):
                        image_count = result_info.get("image_count", 0)
                        total_images_generated += image_count
                        pages_completed += 1
                        logger.info("微动图 [%s/%s张]: page_id=%s, 本页%s张",
                                    total_images_generated, max_images, page.id, image_count)

                        # 达到上限立即停止
                        if total_images_generated >= max_images:
                            logger.info("微动图已达上限 %s 张: upload_id=%s",
                                        max_images, upload_id)
                            break
            except Exception as e:
                logger.error(
                    "微动图生成失败: page_id=%s, error=%s",
                    page.id, e, exc_info=True,
                )

    # 提交分句结果
    await db.flush()
    logger.info(
        "自动增强完成: upload_id=%s, sentences=%s, anim_pages=%s, images=%s, limit=%s",
        upload_id, sentence_succeeded, pages_completed,
        total_images_generated, animation_limit_reached,
    )


# ========== 教材批量处理 API ==========


@router.post("/batch/{upload_id}/tts", response_model=ResponseData[dict])
async def batch_generate_tts(
    upload_id: int = Path(..., ge=1),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """批量合成音频：遍历 upload_id 对应版本的所有页面，逐页合成整页音频

    前端可轮询 upload 的 parsed_pages/total_pages 观察进度。
    """
    from app.services.tts_service import TTSService

    upload = await db.get(TextbookUpload, upload_id)
    if not upload:
        return ResponseData(code=1, message="上传记录不存在")
    if upload.user_id != user_id:
        return ResponseData(code=1, message="无权限操作此教材")

    stmt = (
        select(TextbookPage)
        .where(and_(
            TextbookPage.textbook_version == upload.textbook_version,
            TextbookPage.grade == upload.grade,
            TextbookPage.semester == upload.semester,
            TextbookPage.is_active == 1,
        ))
        .order_by(TextbookPage.unit_number, TextbookPage.page_number)
    )
    result = await db.execute(stmt)
    pages = result.scalars().all()

    total = len(pages)
    succeeded = 0
    failed = 0
    results = []

    for page in pages:
        try:
            r = await TTSService.synthesize_for_page(db, page.id, -1)
            if r.get("audio_url"):
                page.audio_url = r["audio_url"]
                await db.flush()
                succeeded += 1
                results.append({
                    "page_id": page.id,
                    "page_number": page.page_number,
                    "audio_url": r["audio_url"],
                    "cached": r.get("cached", False),
                })
            else:
                failed += 1
                results.append({
                    "page_id": page.id,
                    "page_number": page.page_number,
                    "error": r.get("error", "合成失败"),
                })
        except Exception as e:
            failed += 1
            results.append({
                "page_id": page.id,
                "page_number": page.page_number,
                "error": str(e),
            })
            logger.error("批量 TTS 异常: page_id=%s, error=%s", page.id, e)

    upload.parsed_pages = succeeded
    await db.flush()
    logger.info("批量 TTS 完成: upload_id=%s, total=%s, succeeded=%s, failed=%s",
                upload_id, total, succeeded, failed)
    return ResponseData(data={
        "total": total, "succeeded": succeeded, "failed": failed,
        "results": results,
    })


@router.post("/batch/{upload_id}/sentence-analyze", response_model=ResponseData[dict])
async def batch_analyze_sentences(
    upload_id: int = Path(..., ge=1),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """批量 AI 分句分析：遍历 upload_id 对应版本的所有页面，逐页分析并识别说话角色"""
    from app.services.sentence_analyzer_service import SentenceAnalyzerService

    upload = await db.get(TextbookUpload, upload_id)
    if not upload:
        return ResponseData(code=1, message="上传记录不存在")
    if upload.user_id != user_id:
        return ResponseData(code=1, message="无权限操作此教材")

    stmt = (
        select(TextbookPage)
        .where(and_(
            TextbookPage.textbook_version == upload.textbook_version,
            TextbookPage.grade == upload.grade,
            TextbookPage.semester == upload.semester,
            TextbookPage.is_active == 1,
        ))
        .order_by(TextbookPage.unit_number, TextbookPage.page_number)
    )
    result = await db.execute(stmt)
    pages = result.scalars().all()

    total = len(pages)
    succeeded = 0
    failed = 0
    results = []

    for page in pages:
        try:
            r = await SentenceAnalyzerService.analyze_and_save(db, page.id, user_id)
            if r.get("success"):
                succeeded += 1
                results.append({
                    "page_id": page.id,
                    "page_number": page.page_number,
                    "sentences_count": r.get("sentences_count", 0),
                })
            else:
                failed += 1
                results.append({
                    "page_id": page.id, "page_number": page.page_number,
                    "error": r.get("error", "分析失败"),
                })
        except Exception as e:
            failed += 1
            results.append({
                "page_id": page.id, "page_number": page.page_number,
                "error": str(e),
            })
            logger.error("批量分句分析异常: page_id=%s, error=%s", page.id, e)

    await db.flush()
    logger.info("批量分句分析完成: upload_id=%s, total=%s, succeeded=%s, failed=%s",
                upload_id, total, succeeded, failed)
    return ResponseData(data={
        "total": total, "succeeded": succeeded, "failed": failed,
        "results": results,
    })


@router.post("/batch/{upload_id}/animation", response_model=ResponseData[dict])
async def batch_generate_animation(
    upload_id: int = Path(..., ge=1),
    limit: int = Query(
        default=None,
        ge=1,
        description="最多生成动图张数，默认从配置 ANIMATION_BATCH_SIZE 读取（10张）"
    ),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """批量生成微动图：遍历 upload_id 对应版本的所有页面，串行生成并每页即时保存

    按实际生成的动图张数（角色动画+背景动画+整页动画）累计，
    受 limit 参数限制（默认 10 张），避免一次生成整本太慢。
    已完成的页面（含 animation_url）自动跳过。
    每页生成完立即保存到数据库，中断不丢数据。
    """
    from app.services.animation_service import AnimationService

    upload = await db.get(TextbookUpload, upload_id)
    if not upload:
        return ResponseData(code=1, message="上传记录不存在")
    if upload.user_id != user_id:
        return ResponseData(code=1, message="无权限操作此教材")

    max_images = limit if limit is not None else settings.ANIMATION_BATCH_SIZE

    stmt = (
        select(TextbookPage)
        .where(and_(
            TextbookPage.textbook_version == upload.textbook_version,
            TextbookPage.grade == upload.grade,
            TextbookPage.semester == upload.semester,
            TextbookPage.is_active == 1,
            TextbookPage.image_url.isnot(None),
            TextbookPage.image_url != "",
        ))
        .order_by(TextbookPage.unit_number, TextbookPage.page_number)
    )
    result = await db.execute(stmt)
    pages = result.scalars().all()

    total_pages = len(pages)
    total_images_generated = 0
    pages_completed = 0
    pages_skipped = 0
    pages_failed = 0
    results = []

    logger.info("批量微动图开始: upload_id=%s, total_pages=%s, max_images=%s",
                upload_id, total_pages, max_images)

    for page in pages:
        # 跳过已完成的页面
        if page.animation_url:
            pages_skipped += 1
            results.append({
                "page_id": page.id, "page_number": page.page_number,
                "status": "skipped", "message": "已有动画",
            })
            continue

        # 达到图片数上限，停止
        if total_images_generated >= max_images:
            remaining = sum(1 for p in pages if not p.animation_url) - pages_completed
            results.append({
                "status": "limit_reached",
                "message": f"已生成 {total_images_generated} 张动图（上限 {max_images}），剩余 {remaining} 页未处理",
            })
            logger.info("批量微动图达上限: images=%s, limit=%s",
                        total_images_generated, max_images)
            break

        try:
            task = await AnimationService.create_animation_task(
                db, page.id, user_id, enhanced=True,
            )
            task_id = task.get("task_id", "")
            if task_id:
                result_info = await _wait_for_animation_completion(task_id, page.id)
                if result_info.get("success"):
                    image_count = result_info.get("image_count", 0)
                    total_images_generated += image_count
                    pages_completed += 1
                    results.append({
                        "page_id": page.id, "page_number": page.page_number,
                        "status": "completed", "task_id": task_id,
                        "image_count": image_count,
                        "total_images": total_images_generated,
                    })
                    logger.info("批量微动图 [%s/%s张]: page_id=%s, 本页%s张",
                                total_images_generated, max_images, page.id, image_count)
                else:
                    pages_failed += 1
                    results.append({
                        "page_id": page.id, "page_number": page.page_number,
                        "status": "failed", "task_id": task_id,
                        "message": "生成超时或失败",
                    })
            else:
                pages_failed += 1
                results.append({
                    "page_id": page.id, "page_number": page.page_number,
                    "status": "failed", "message": task.get("error", "创建任务失败"),
                })
        except Exception as e:
            pages_failed += 1
            results.append({
                "page_id": page.id, "page_number": page.page_number,
                "status": "error", "error": str(e),
            })
            logger.error("批量动画生成异常: page_id=%s, error=%s", page.id, e)

    logger.info("批量微动图完成: upload_id=%s, total_pages=%s, pages_completed=%s, "
                "images=%s, skipped=%s, failed=%s",
                upload_id, total_pages, pages_completed, total_images_generated,
                pages_skipped, pages_failed)
    return ResponseData(data={
        "total_pages": total_pages, "pages_completed": pages_completed,
        "pages_skipped": pages_skipped, "pages_failed": pages_failed,
        "total_images": total_images_generated, "max_images": max_images,
        "results": results,
    })


@router.get("/batch/{upload_id}/animation/progress", response_model=ResponseData[dict])
async def get_animation_progress(
    upload_id: int = Path(..., ge=1),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询微动图生成进度：哪些页已生成、哪些页待生成

    返回:
      total: 总页面数（有插图的页面）
      completed: 已完成微动图生成的页面数
      pending: 待生成的页面数
      pages: 各页面详情列表
    """
    upload = await db.get(TextbookUpload, upload_id)
    if not upload:
        return ResponseData(code=1, message="上传记录不存在")
    if upload.user_id != user_id:
        return ResponseData(code=1, message="无权限操作此教材")

    stmt = (
        select(TextbookPage)
        .where(and_(
            TextbookPage.textbook_version == upload.textbook_version,
            TextbookPage.grade == upload.grade,
            TextbookPage.semester == upload.semester,
            TextbookPage.is_active == 1,
        ))
        .order_by(TextbookPage.unit_number, TextbookPage.page_number)
    )
    result = await db.execute(stmt)
    pages = result.scalars().all()

    total_with_image = sum(1 for p in pages if p.image_url)
    completed = sum(1 for p in pages if p.image_url and p.animation_url)
    pending = total_with_image - completed

    pages_detail = []
    for p in pages:
        pages_detail.append({
            "page_id": p.id,
            "page_number": p.page_number,
            "unit_number": p.unit_number,
            "has_image": bool(p.image_url),
            "has_animation": bool(p.animation_url),
            "has_sentences": bool(p.sentences_json),
            "animation_url": p.animation_url or "",
            "text_preview": (p.text_content or "")[:100],
        })

    return ResponseData(data={
        "upload_id": upload_id,
        "total_pages": len(pages),
        "total_with_image": total_with_image,
        "completed": completed,
        "pending": pending,
        "percent": round(completed / total_with_image * 100, 1) if total_with_image > 0 else 0,
        "pages": pages_detail,
    })


# ========== 自动增强处理（分句分析 + 微动图生成）==========


async def _async_generate_animation(page_id: int):
    """在独立 session 中执行增强微动图生成"""
    from app.db.database import async_session as get_async_session

    try:
        async with get_async_session() as anim_db:
            from app.services.animation_service import AnimationService
            task = await AnimationService.create_animation_task(
                anim_db, page_id, user_id=0, enhanced=True,
            )
            await anim_db.commit()
            logger.info(
                "自动微动图任务已创建: page_id=%s, task_id=%s",
                page_id, task.get("task_id"),
            )
    except Exception as e:
        logger.error(
            "自动微动图生成失败: page_id=%s, error=%s",
            page_id, e, exc_info=True,
        )


async def _wait_for_animation_completion(task_id: str, page_id: int, timeout_sec: int = 300) -> dict:
    """等待微动图后台任务完成（轮询 Redis 状态）

    参数:
        task_id: 动画任务ID
        page_id: 页面ID（用于日志）
        timeout_sec: 超时秒数（默认5分钟）

    返回:
        {"success": bool, "image_count": int}  — image_count 是该页实际生成的动图张数
    """
    import asyncio

    if not task_id:
        logger.warning("task_id 为空，无法等待动画完成: page_id=%s", page_id)
        return {"success": False, "image_count": 0}

    from app.services.animation_service import AnimationService
    poll_interval = 3  # 每3秒检查一次

    for attempt in range(timeout_sec // poll_interval):
        await asyncio.sleep(poll_interval)
        try:
            status_info = await AnimationService.get_animation_status(task_id)
            status = status_info.get("status", "")
            if status == "completed":
                image_count = status_info.get("image_count", 0)
                logger.info("微动图完成: page_id=%s, task_id=%s, images=%s",
                            page_id, task_id, image_count)
                return {"success": True, "image_count": image_count}
            elif status == "failed":
                logger.warning("微动图失败: page_id=%s, task_id=%s", page_id, task_id)
                return {"success": False, "image_count": 0}
        except Exception as e:
            logger.warning("轮询动画状态异常: task_id=%s, error=%s", task_id, e)

    logger.warning("微动图等待超时: page_id=%s, task_id=%s, timeout=%ss",
                   page_id, task_id, timeout_sec)
    return {"success": False, "image_count": 0}


# ==================== 内部工具 ====================

def _upload_to_dict(upload: TextbookUpload) -> dict:
    """将 TextbookUpload ORM 对象转为字典"""
    return {
        "id": upload.id,
        "filename": upload.filename,
        "file_size": upload.file_size,
        "textbook_version": upload.textbook_version,
        "grade": upload.grade,
        "semester": upload.semester,
        "parse_status": upload.parse_status,
        "total_pages": upload.total_pages,
        "parsed_pages": upload.parsed_pages,
        "error_msg": upload.error_msg or "",
        "created_at": upload.created_at.isoformat() if upload.created_at else "",
        "updated_at": upload.updated_at.isoformat() if upload.updated_at else "",
    }


def _estimate_images_for_page(page: TextbookPage) -> int:
    """估算一个页面可能生成的动图数量

    用于在真正生成前预判是否会超过总配额。
    每页可能的动图: 角色动画(按 sentences 中的 speaker 数) + 背景动画(1) + 整页动画(1)
    """
    count = 0
    # 背景动画：几乎所有页面都有
    count += 1
    # 整页动画：通常有 full_animation_prompt
    count += 1
    # 角色动画：从 sentences_json 数不同的 speaker
    if page.sentences_json:
        speakers = set()
        for s in page.sentences_json:
            if isinstance(s, dict):
                sp = s.get("speaker", "")
                if sp and sp.lower() != "narrator":
                    speakers.add(sp)
        # 每个说话角色可能生成一张动图
        if speakers:
            count += len(speakers)
    return count

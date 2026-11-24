import os
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Query, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.db.database import get_db
from app.api.deps import get_current_user_id, get_current_teacher_id, get_current_user_id_download
from app.models.stats import UserDocument
from app.schemas.common import ResponseData, DocumentOut
from app.core.config import get_settings
from app.core.paths import UPLOADS_DIR
from app.services.document_service import DOC_CATEGORIES, STAGE_CATEGORIES
from app.services.document_scope import PRIVATE_DOCUMENT_CATEGORIES, library_documents
from app.services.document_processor import DocumentProcessor
from app.services.document_progress import get_progress
from app.services.upload_job_manager import (
    create_job, start_job, get_job, update_job_step, set_job_done, set_job_error,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["文档"])
settings = get_settings()

UPLOAD_DIR = str(UPLOADS_DIR)


@router.post("/upload", response_model=ResponseData[DocumentOut])
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_category: str = Form("other", description="文档分类: exam/teaching_plan/courseware/textbook/reference/other"),
    stage_category: str = Form("other", description="学段: preschool/primary/junior/senior/other"),
    doc_tags: str = Form("", description="自定义标签，逗号分隔"),
    class_id: int = Form(0, description="所属班级ID，0=教师私有"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """上传文档（兼容旧接口，自动解析并向量化）"""
    if doc_category not in DOC_CATEGORIES:
        raise ValueError(f"不支持的文档分类: {doc_category}，可选: {', '.join(DOC_CATEGORIES.keys())}")
    if stage_category not in STAGE_CATEGORIES:
        raise ValueError(f"不支持的学段: {stage_category}，可选: {', '.join(STAGE_CATEGORIES.keys())}")

    allowed_types = {".pdf", ".docx", ".doc", ".txt", ".pptx", ".ppt", ".png", ".jpg", ".jpeg"}
    _, ext = os.path.splitext(file.filename or "")
    if ext.lower() not in allowed_types:
        raise ValueError(f"不支持的文件格式: {ext}，请上传 {', '.join(allowed_types)} 文件")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("文件大小不能超过 20MB")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_key = f"{user_id}/{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, file_key)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "wb") as f:
        f.write(content)

    type_map = {
        ".pdf": "pdf", ".pptx": "ppt", ".ppt": "ppt",
        ".docx": "word", ".doc": "word",
        ".txt": "txt", ".png": "image", ".jpg": "image", ".jpeg": "image",
    }
    file_type = type_map.get(ext.lower(), "txt")

    doc = UserDocument(
        user_id=user_id,
        filename=file.filename or "unknown",
        file_type=file_type,
        file_size=len(content),
        storage_key=file_key,
        file_path=file_path,
        parse_status=0,
        doc_category=doc_category,
        stage_category=stage_category,
        doc_tags=doc_tags,
        class_id=class_id if class_id else None,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    # 先提交事务，确保后台任务的新 session 能读到刚插入的记录
    await db.commit()

    async def _process():
        from app.db.database import async_session as get_async_session
        try:
            async with get_async_session() as process_db:
                result = await DocumentProcessor.process_document(
                    process_db, doc.id, user_id, class_id=class_id,
                )
                if result.get("success"):
                    logger.info(f"文档处理完成 doc_id={doc.id} chunks={result.get('chunk_count')}")
                else:
                    logger.warning(f"文档处理异常 doc_id={doc.id}: {result.get('error')}")
        except Exception as e:
            logger.error(f"文档后台处理失败 doc_id={doc.id}: {e}", exc_info=True)

    background_tasks.add_task(_process)

    return ResponseData(data=DocumentOut.model_validate(doc))


@router.post("/upload-async", response_model=ResponseData[dict])
async def upload_document_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_category: str = Form("other", description="文档分类: exam/teaching_plan/courseware/textbook/reference/other"),
    stage_category: str = Form("other", description="学段: preschool/primary/junior/senior/other"),
    doc_tags: str = Form("", description="自定义标签，逗号分隔"),
    class_id: int = Form(0, description="所属班级ID，0=教师私有"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """异步上传文档 — 立即返回 job_id，后台处理，前端轮询进度

    步骤: upload → cleanup → parse → chunk → embed → done
    前端轮询 GET /documents/jobs/{job_id}
    """
    if doc_category not in DOC_CATEGORIES:
        raise ValueError(f"不支持的文档分类: {doc_category}")
    if stage_category not in STAGE_CATEGORIES:
        raise ValueError(f"不支持的学段: {stage_category}")

    allowed_types = {".pdf", ".docx", ".doc", ".txt", ".pptx", ".ppt", ".png", ".jpg", ".jpeg"}
    _, ext = os.path.splitext(file.filename or "")
    if ext.lower() not in allowed_types:
        raise ValueError(f"不支持的文件格式: {ext}")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("文件大小不能超过 20MB")

    # 1. 创建 job（立即返回）
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_key = f"{user_id}/{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, file_key)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    type_map = {
        ".pdf": "pdf", ".pptx": "ppt", ".ppt": "ppt",
        ".docx": "word", ".doc": "word",
        ".txt": "txt", ".png": "image", ".jpg": "image", ".jpeg": "image",
    }
    file_type = type_map.get(ext.lower(), "txt")

    doc = UserDocument(
        user_id=user_id,
        filename=file.filename or "unknown",
        file_type=file_type,
        file_size=len(content),
        storage_key=file_key,
        file_path=file_path,
        parse_status=0,
        doc_category=doc_category,
        stage_category=stage_category,
        doc_tags=doc_tags,
        class_id=class_id if class_id else None,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    # 先提交事务，确保后台任务的新 session 能读到刚插入的记录
    await db.commit()

    # 创建 job
    job_id = await create_job(doc.id)

    async def _async_process():
        from app.db.database import async_session as get_async_session
        import asyncio
        try:
            # step 1: upload — 写入文件
            await update_job_step(job_id, "upload", 100, "done", "文件写入完成")
            with open(file_path, "wb") as f:
                f.write(content)

            await start_job(job_id)
            await update_job_step(job_id, "cleanup", 100, "done", "文件准备就绪")

            async with get_async_session() as process_db:
                result = await DocumentProcessor.process_document(
                    process_db, doc.id, user_id, job_id=job_id, class_id=class_id,
                )
                # 提交事务，确保 parse_status / vector_status 等更新持久化
                await process_db.commit()
                if result.get("success"):
                    logger.info(f"异步处理完成 doc_id={doc.id} job_id={job_id}")
                    await set_job_done(job_id, f"处理完成，入库 {result.get('chunk_count', 0)} 块")
                else:
                    error_msg = result.get("error") or "未知错误"
                    logger.warning(f"异步处理失败 doc_id={doc.id} job_id={job_id}: {error_msg}")
        except Exception as e:
            logger.error(f"异步处理异常 doc_id={doc.id} job_id={job_id}: {e}", exc_info=True)
            await set_job_error(job_id, str(e))

    background_tasks.add_task(_async_process)

    return ResponseData(data={
        "job_id": job_id,
        "doc_id": doc.id,
        "status": "pending",
        "message": "文件已加入异步处理队列",
    })


@router.get("/jobs/{job_id}", response_model=ResponseData[dict])
async def get_job_progress(
    job_id: str,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取异步上传 Job 的实时进度（需认证）"""
    job = await get_job(job_id)
    if job is None:
        return ResponseData(data={
            "status": "unknown",
            "percent": 0,
            "steps": {},
            "message": "Job 不存在或已过期",
        })
    doc_id = job.get("doc_id")
    if not doc_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    await _require_document_owner(db, doc_id, user_id)
    return ResponseData(data=job)


async def _require_document_owner(db: AsyncSession, doc_id: int, user_id: int):
    """Cached progress is not an authorization source; verify the live document."""
    doc = await db.get(UserDocument, doc_id)
    if doc is None or doc.user_id != user_id or doc.doc_category in PRIVATE_DOCUMENT_CATEGORIES:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


# ==================== 原有端点（保持不变）====================

@router.get("/", response_model=ResponseData[dict])
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    doc_category: Optional[str] = Query(None, description="文档分类筛选"),
    stage_category: Optional[str] = Query(None, description="学段筛选"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """文档列表（支持分类/学段筛选）"""
    stmt = select(UserDocument).where(UserDocument.user_id == user_id, library_documents())
    if doc_category:
        stmt = stmt.where(UserDocument.doc_category == doc_category)
    if stage_category:
        stmt = stmt.where(UserDocument.stage_category == stage_category)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    stmt = stmt.order_by(UserDocument.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    docs = result.scalars().all()

    return ResponseData(data={
        "items": [DocumentOut.model_validate(d) for d in docs],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.put("/{doc_id}", response_model=ResponseData[DocumentOut])
async def update_document(
    doc_id: int,
    doc_category: Optional[str] = Form(None, description="文档分类"),
    stage_category: Optional[str] = Form(None, description="学段"),
    doc_tags: Optional[str] = Form(None, description="自定义标签"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(UserDocument).where(UserDocument.id == doc_id, UserDocument.user_id == user_id, library_documents())
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise ValueError("文档不存在")

    if doc_category is not None:
        if doc_category not in DOC_CATEGORIES:
            raise ValueError(f"不支持的文档分类: {doc_category}")
        doc.doc_category = doc_category
    if stage_category is not None:
        if stage_category not in STAGE_CATEGORIES:
            raise ValueError(f"不支持的学段: {stage_category}")
        doc.stage_category = stage_category
    if doc_tags is not None:
        doc.doc_tags = doc_tags

    await db.flush()
    await db.refresh(doc)
    return ResponseData(data=DocumentOut.model_validate(doc))


@router.get("/categories", response_model=ResponseData[dict])
async def list_categories():
    return ResponseData(data={
        "doc_categories": [{"value": k, "label": v} for k, v in DOC_CATEGORIES.items()],
        "stage_categories": [{"value": k, "label": v} for k, v in STAGE_CATEGORIES.items()],
    })


@router.post("/{doc_id}/reprocess", response_model=ResponseData[dict])
async def reprocess_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(UserDocument).where(UserDocument.id == doc_id, UserDocument.user_id == user_id, library_documents())
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    doc.parse_status = 0
    doc.vector_status = 0
    doc.chunk_count = 0
    await db.flush()

    async def _process():
        from app.db.database import async_session as get_async_session
        try:
            async with get_async_session() as process_db:
                # reprocess 时 process_document 会自动从 doc 记录读取 class_id
                result = await DocumentProcessor.process_document(
                    process_db, doc_id, user_id
                )
                if result.get("success"):
                    logger.info(f"文档重处理完成 doc_id={doc_id} chunks={result.get('chunk_count')}")
                else:
                    logger.warning(f"文档重处理失败 doc_id={doc_id}: {result.get('error')}")
        except Exception as e:
            logger.error(f"文档后台重处理失败 doc_id={doc_id}: {e}", exc_info=True)

    background_tasks.add_task(_process)
    return ResponseData(data={"doc_id": doc_id, "status": "processing", "message": "文档已加入处理队列"})


@router.post("/reprocess-all", response_model=ResponseData[dict])
async def reprocess_all_documents(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(UserDocument).where(
            UserDocument.user_id == user_id,
            UserDocument.parse_status.in_([0, 3]),
            library_documents(),
        )
    )
    docs = result.scalars().all()
    if not docs:
        return ResponseData(data={"message": "没有需要重新处理的文档", "count": 0})

    doc_ids = [d.id for d in docs]
    for doc in docs:
        doc.parse_status = 0
        doc.vector_status = 0
        doc.chunk_count = 0
    await db.flush()

    async def _process_all():
        from app.db.database import async_session as get_async_session
        for did in doc_ids:
            try:
                async with get_async_session() as process_db:
                    result = await DocumentProcessor.process_document(
                        process_db, did, user_id
                    )
                    if result.get("success"):
                        logger.info(f"批量重处理完成 doc_id={did}")
                    else:
                        logger.warning(f"批量重处理失败 doc_id={did}: {result.get('error')}")
            except Exception as e:
                logger.error(f"批量重处理异常 doc_id={did}: {e}")

    background_tasks.add_task(_process_all)
    return ResponseData(data={
        "message": f"{len(doc_ids)} 个文档已加入处理队列",
        "count": len(doc_ids),
        "doc_ids": doc_ids,
    })


@router.post("/reindex", response_model=ResponseData[dict])
async def reindex_document(
    doc_id: int = Query(..., description="待重索引的文档 ID"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """对已解析文档重新建立向量索引（不重新提取文本）

    适用于 Milvus 集合重建后，需要为 parse_status=2 但向量丢失的文档重建索引。
    """
    result = await DocumentProcessor.reindex_document(db, doc_id, user_id)
    await db.commit()
    if result.get("success"):
        return ResponseData(data=result)
    else:
        raise HTTPException(status_code=400, detail=result.get("error", "重索引失败"))


@router.post("/reindex-all", response_model=ResponseData[dict])
async def reindex_all_documents(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """批量重索引所有已解析但向量未入库的文档"""
    result = await db.execute(
        select(UserDocument).where(
            UserDocument.user_id == user_id,
            UserDocument.parse_status == 2,
            library_documents(),
            UserDocument.vector_status != 2,
        )
    )
    docs = result.scalars().all()
    if not docs:
        return ResponseData(data={"message": "没有需要重索引的文档", "count": 0})

    doc_ids = [d.id for d in docs]

    async def _reindex_all():
        from app.db.database import async_session as get_async_session
        for did in doc_ids:
            try:
                async with get_async_session() as process_db:
                    result = await DocumentProcessor.reindex_document(
                        process_db, did, user_id
                    )
                    if result.get("success"):
                        logger.info(f"重索引完成 doc_id={did}")
                    else:
                        logger.warning(f"重索引失败 doc_id={did}: {result.get('error')}")
                    await process_db.commit()
            except Exception as e:
                logger.error(f"重索引异常 doc_id={did}: {e}")

    background_tasks.add_task(_reindex_all)
    return ResponseData(data={
        "message": f"{len(doc_ids)} 个文档已加入重索引队列",
        "count": len(doc_ids),
        "doc_ids": doc_ids,
    })


@router.get("/{doc_id}/progress", response_model=ResponseData[dict])
async def get_document_progress(
    doc_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取文档处理实时进度（需认证）"""
    await _require_document_owner(db, doc_id, user_id)
    progress = await get_progress(doc_id)
    if progress is None:
        return ResponseData(data={
            "status": "unknown", "percent": 0, "steps": {},
            "message": "暂无进度信息（可能已过期）",
        })
    return ResponseData(data=progress)


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id_download),
):
    """下载/预览文档（需认证），支持 token 作为 query 参数

    前端可直接用 window.open('/api/v1/documents/123/download?token=xxx')
    打开 PDF / 图片等浏览器支持的文件格式进行预览。
    """
    result = await db.execute(
        select(UserDocument).where(UserDocument.id == doc_id, UserDocument.user_id == user_id, library_documents())
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not doc.file_path or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="文件不存在或已被删除")

    # 根据扩展名确定 Content-Type
    CONTENT_TYPES = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".ppt": "application/vnd.ms-powerpoint",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".txt": "text/plain; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    _, ext = os.path.splitext(doc.file_path)
    media_type = CONTENT_TYPES.get(ext.lower(), "application/octet-stream")

    # content_disposition_type="inline" 让浏览器内联展示
    # filename 参数会自动用 RFC 5987 (UTF-8) 编码中文文件名
    return FileResponse(
        doc.file_path,
        media_type=media_type,
        filename=doc.filename,
        content_disposition_type="inline",
        headers={
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/{doc_id}/text-content")
async def get_document_text(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id_download),
):
    """获取文档提取的文本内容（用于文本预览）

    返回解析后的纯文本内容，支持所有数据类型（PDF/PPTX/DOCX/TXT/图片）。
    对于已解析完成的文档直接返回数据库中的 parsed_text，
    对于未解析的文档尝试实时从文件中提取文本。
    """
    result = await db.execute(
        select(UserDocument).where(UserDocument.id == doc_id, UserDocument.user_id == user_id, library_documents())
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    text = ""

    # 优先从数据库读取已解析的文本
    if doc.parse_status == 2 and doc.parsed_text:
        text = doc.parsed_text
        logger.info(f"文本预览(DB): doc_id={doc_id} {len(text)} 字符")
    elif doc.file_path and os.path.exists(doc.file_path):
        # 未解析或解析失败，尝试实时提取
        logger.info(f"文本预览(实时提取): doc_id={doc_id} type={doc.file_type}")
        try:
            text = await DocumentProcessor._extract_text(
                doc.file_path, doc.file_type, doc.filename, doc.id
            )
        except Exception as e:
            logger.warning(f"实时文本提取失败 doc_id={doc_id}: {e}")
            text = ""

    if not text or not text.strip():
        return {
            "text": "",
            "chars": 0,
            "hint": "该文档暂无可提取的文本内容，请确认文件格式正确" if not text else text,
        }

    return {
        "text": text,
        "chars": len(text),
        "filename": doc.filename,
    }


@router.delete("/{doc_id}", response_model=ResponseData[dict])
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(UserDocument).where(UserDocument.id == doc_id, UserDocument.user_id == user_id, library_documents())
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise ValueError("文档不存在")

    # 清除 Milvus 数据
    try:
        from app.services.embedding_service import EmbeddingService
        EmbeddingService.delete_by_expr(
            EmbeddingService.TEACHER_DOCUMENTS,
            f'source_type like "doc%" and source_id == {doc.id}',
        )
        # 清除父级分块
        from app.services.parent_chunk_store import clear_doc_parents
        await clear_doc_parents(db, doc.id)
    except Exception as e:
        logger.warning(f"清除向量数据失败 doc_id={doc.id}: {e}")

    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    await db.delete(doc)
    await db.flush()
    return ResponseData(data={"message": "文档已删除"})

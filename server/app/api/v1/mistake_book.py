"""
错题本路由 — 提供错题本三类数据的 API 端点
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.api.deps import get_current_user_id
from app.services.mistake_book_service import MistakeBookService
from app.services.pdf_export_service import generate_report_pdf
from app.schemas.common import ResponseData

router = APIRouter(prefix="/mistake-book", tags=["错题本"])


class BatchDeleteRequest(BaseModel):
    ids: list[int]


@router.get("/word-training", response_model=ResponseData)
async def word_training_mistakes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取单词训练错题列表"""
    result = await MistakeBookService.get_word_training_mistakes(db, user_id, page, page_size)
    return ResponseData(data=result)


@router.delete("/word-training/batch", response_model=ResponseData)
async def batch_delete_word_mistakes(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """批量删除单词训练错题"""
    count = await MistakeBookService.batch_delete_word_mistakes(db, user_id, body.ids)
    return ResponseData(data={"deleted": count})


@router.get("/exam-mistakes", response_model=ResponseData)
async def exam_mistakes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取试卷错题列表"""
    result = await MistakeBookService.get_exam_mistakes(db, user_id, page, page_size)
    return ResponseData(data=result)


@router.get("/summary-reports", response_model=ResponseData)
async def summary_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取小e总结报告列表"""
    result = await MistakeBookService.get_summary_reports(db, user_id, page, page_size)
    return ResponseData(data=result)


@router.delete("/summary-reports/batch", response_model=ResponseData)
async def batch_delete_summary_reports(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """批量删除小e总结报告"""
    count = await MistakeBookService.batch_delete_summary_reports(db, user_id, body.ids)
    return ResponseData(data={"deleted": count})


@router.post("/save-summary", response_model=ResponseData)
async def save_summary_report(
    title: str = Query(..., description="报告标题"),
    content: str = Query(..., description="报告内容(Markdown)"),
    exam_name: str = Query("", description="关联考试名称"),
    days: int = Query(0, description="覆盖天数"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """保存小e总结报告"""
    result = await MistakeBookService.save_summary_report(
        db, user_id, title, content, exam_name, days
    )
    return ResponseData(data=result)


@router.get("/summary-reports/{report_id}", response_model=ResponseData)
async def get_report_detail(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取单条总结报告详情"""
    result = await MistakeBookService.get_report_detail(db, user_id, report_id)
    if not result:
        raise HTTPException(status_code=404, detail="报告不存在")
    return ResponseData(data=result)


@router.get("/summary-reports/{report_id}/export")
async def export_report_pdf(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """导出小e总结报告为 PDF 文件"""
    result = await MistakeBookService.get_report_detail(db, user_id, report_id)
    if not result:
        raise HTTPException(status_code=404, detail="报告不存在")

    title = result.get("title") or "小e总结报告"
    content = result.get("content") or ""
    if not content:
        raise HTTPException(status_code=400, detail="报告内容为空，无法导出")

    try:
        pdf_bytes = generate_report_pdf(title, content)
    except Exception as e:
        import traceback, logging
        logging.getLogger(__name__).error("PDF 导出异常:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"PDF 生成失败: {str(e)}")

    filename = f"小e总结_{title[:20]}.pdf"
    # URL-encode 中文文件名用于 Content-Disposition
    from urllib.parse import quote
    encoded = quote(filename)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{encoded}"; filename*=utf-8\'\'{encoded}',
        },
    )

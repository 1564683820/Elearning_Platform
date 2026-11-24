# SVG 在线编辑器 FastAPI 路由
# 提供 SVG 元素编辑、注解管理、撤销、保存回写等 API

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_teacher_id
from app.db.database import get_db
from app.ppt_generator.pptx_editor.editor_state import editor_state
from app.ppt_generator.pptx_editor.editor_service import (
    inline_icons,
    save_all,
    validate_edit_attrs,
)
from app.ppt_generator.pptx_editor.annotations import (
    assign_temp_ids,
    parse_annotations,
)
from app.schemas.common import ResponseData

logger = logging.getLogger("pptx_editor")

router = APIRouter(prefix="/teacher/ppt/{ppt_id}/editor", tags=["教师端-PPT SVG编辑器"])

# 图标库根目录（参考实现路径）
ICONS_DIR = (
    Path(__file__).resolve().parents[4]  # 仓库根目录
    / "docs"
    / "ppt-master-main"
    / "ppt-master-main"
    / "skills"
    / "ppt-master"
    / "templates"
    / "icons"
)

# ---- Pydantic 请求模型 ----


class EditRequest(BaseModel):
    element_id: str = Field(..., max_length=128)
    text: Optional[str] = Field(None, max_length=5000)
    attrs: Optional[dict] = Field(None)
    promote_tspan: Optional[dict] = Field(None)
    changes: list[dict] = Field(default_factory=list)


class AnnotateRequest(BaseModel):
    element_id: str = Field(..., max_length=128)
    annotation: str = Field("", max_length=1000)


# ---- 辅助 ----


async def _ensure_ppt_access(ppt_id: int, db: AsyncSession, teacher_id: int):
    """验证 PPT 归属并返回 ppt 对象"""
    from app.services.ppt_service import PPTService

    ppt = await PPTService.get_ppt(db, ppt_id, teacher_id)
    if not ppt:
        raise HTTPException(status_code=404, detail="PPT 不存在")
    return ppt


async def _generate_svgs_for_editor(
    ppt_id: int, db: AsyncSession, teacher_id: int
) -> dict[int, str]:
    """通过预览管线生成所有幻灯片的 SVG"""
    from app.api.v1.ppt import _run_preview_pipeline

    data = await _run_preview_pipeline(
        ppt_id, teacher_id, db,
        embed_images=True,
        inheritance_mode="flat",
        page_range=None,
    )
    slides = data.get("slides", [])
    # SlideArtifact.index 是 1-based, 存储为 0-based 以便与前端 page 参数对齐
    return {s["index"] - 1: s["svg"] for s in slides}


def _find_elem_by_id(root, element_id: str):
    """在 SVG 树中按 id 查找元素"""
    import xml.etree.ElementTree as ET
    for elem in root.iter():
        if elem.get("id") == element_id:
            return elem
    return None


# ---- 端点 ----


@router.post("/start", response_model=ResponseData)
async def editor_start(
    ppt_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """初始化编辑器：验证 PPT 归属并从预览管线生成所有 SVG"""
    ppt = await _ensure_ppt_access(ppt_id, db, teacher_id)

    pages_json = ppt.get("pages_json", [])
    if isinstance(pages_json, str):
        pages_json = json.loads(pages_json)
    slide_count = len(pages_json)

    svgs = await _generate_svgs_for_editor(ppt_id, db, teacher_id)
    if not svgs:
        raise HTTPException(status_code=500, detail="SVG 生成失败，无有效幻灯片")

    # 构建画布信息
    info = {}
    for idx in svgs:
        info[idx] = {"index": idx}

    editor_state.load_ppt(ppt_id, svgs, info)

    return ResponseData(data={
        "ppt_id": ppt_id,
        "title": ppt.get("title", ""),
        "slide_count": slide_count,
        "loaded_pages": len(svgs),
        "message": f"已加载 {len(svgs)} 页幻灯片 SVG",
    })


@router.get("/slide/{page}", response_model=ResponseData)
async def get_editor_slide(
    ppt_id: int,
    page: int,
    inline_icon: bool = Query(True, description="是否内联图标供浏览器预览"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取指定页可编辑 SVG（已分配临时 ID + 可选图标内联）"""
    await _ensure_ppt_access(ppt_id, db, teacher_id)

    if not editor_state.has_ppt(ppt_id):
        raise HTTPException(status_code=400, detail="请先调用 /start 初始化编辑器")

    svg_content = editor_state.get_svg(ppt_id, page)
    if svg_content is None:
        raise HTTPException(status_code=404, detail=f"第 {page} 页 SVG 不存在")

    import xml.etree.ElementTree as ET

    try:
        tree = ET.fromstring(svg_content.encode("utf-8"))
        root = tree
    except ET.ParseError as exc:
        raise HTTPException(status_code=500, detail=f"SVG 解析失败: {exc}")

    # 分配临时 ID
    assign_temp_ids(root)

    # 提取注解列表供前端参考
    ann_list = parse_annotations(root)

    svg_str = ET.tostring(root, encoding="unicode", short_empty_elements=True)

    # 图标内联（浏览器无法解析 <use data-icon>）
    icon_warnings = []
    if inline_icon:
        svg_str, icon_warnings = inline_icons(svg_str)

    info = editor_state.get_svg_info(ppt_id, page) or {}
    edit_depth = editor_state.get_edit_depth(ppt_id, page)
    annotations = editor_state.get_annotations(ppt_id, page)

    return ResponseData(data={
        "page": page,
        "svg": svg_str,
        "edit_depth": edit_depth,
        "annotations": annotations,
        "existing_annotations": ann_list,
        "icon_inline_warnings": icon_warnings,
        "canvas_width": info.get("width"),
        "canvas_height": info.get("height"),
    })


@router.post("/slide/{page}/edit", response_model=ResponseData)
async def submit_edit(
    ppt_id: int,
    page: int,
    body: EditRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """提交 SVG 元素编辑操作"""
    await _ensure_ppt_access(ppt_id, db, teacher_id)

    if not editor_state.has_ppt(ppt_id):
        raise HTTPException(status_code=400, detail="请先调用 /start 初始化编辑器")

    # 验证
    svg_content = editor_state.get_svg(ppt_id, page)
    if svg_content is None:
        raise HTTPException(status_code=404, detail=f"第 {page} 页 SVG 不存在")

    import xml.etree.ElementTree as ET

    try:
        tree = ET.fromstring(svg_content.encode("utf-8"))
        root = tree
    except ET.ParseError as exc:
        raise HTTPException(status_code=500, detail=f"SVG 解析失败: {exc}")

    # 查找元素获取当前属性集用于校验
    elem = _find_elem_by_id(root, body.element_id)
    existing_attrs = set(elem.attrib.keys()) if elem is not None else set()

    if body.attrs:
        err = validate_edit_attrs(body.attrs, existing_attrs)
        if err:
            raise HTTPException(status_code=400, detail=err)

    # 构建编辑记录
    record: dict = {"element_id": body.element_id}
    if body.text is not None:
        record["text"] = body.text
    if body.attrs:
        record["attrs"] = body.attrs
    if body.promote_tspan:
        record["promote_tspan"] = body.promote_tspan
    if body.changes:
        record["changes"] = body.changes

    editor_state.add_edit(ppt_id, page, record)
    depth = editor_state.get_edit_depth(ppt_id, page)

    return ResponseData(data={
        "element_id": body.element_id,
        "edit_depth": depth,
        "message": "编辑已记录",
    })


@router.post("/slide/{page}/undo", response_model=ResponseData)
async def undo_edit(
    ppt_id: int,
    page: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """撤销幻灯片上最近一次编辑"""
    await _ensure_ppt_access(ppt_id, db, teacher_id)
    if not editor_state.has_ppt(ppt_id):
        raise HTTPException(status_code=400, detail="请先调用 /start 初始化编辑器")

    ok = editor_state.undo_edit(ppt_id, page)
    if not ok:
        return ResponseData(data={"message": "无可撤销的编辑", "edit_depth": 0})

    depth = editor_state.get_edit_depth(ppt_id, page)
    return ResponseData(data={"message": "已撤销", "edit_depth": depth})


@router.post("/slide/{page}/annotate", response_model=ResponseData)
async def set_slide_annotation(
    ppt_id: int,
    page: int,
    body: AnnotateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """设置/更新 SVG 元素注解"""
    await _ensure_ppt_access(ppt_id, db, teacher_id)

    if not editor_state.has_ppt(ppt_id):
        raise HTTPException(status_code=400, detail="请先调用 /start 初始化编辑器")

    svg_content = editor_state.get_svg(ppt_id, page)
    if svg_content is None:
        raise HTTPException(status_code=404, detail=f"第 {page} 页 SVG 不存在")

    # 验证元素存在
    import xml.etree.ElementTree as ET

    try:
        tree = ET.fromstring(svg_content.encode("utf-8"))
        root = tree
    except ET.ParseError as exc:
        raise HTTPException(status_code=500, detail=f"SVG 解析失败: {exc}")

    if _find_elem_by_id(root, body.element_id) is None:
        raise HTTPException(status_code=404, detail=f"元素 {body.element_id} 不存在")

    editor_state.set_annotation(ppt_id, page, body.element_id, body.annotation)
    all_anns = editor_state.get_annotations(ppt_id, page)

    return ResponseData(data={
        "element_id": body.element_id,
        "annotation": body.annotation,
        "annotations": all_anns,
    })


@router.delete("/slide/{page}/annotate/{element_id}", response_model=ResponseData)
async def delete_slide_annotation(
    ppt_id: int,
    page: int,
    element_id: str,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """删除指定 SVG 元素的注解"""
    await _ensure_ppt_access(ppt_id, db, teacher_id)
    if not editor_state.has_ppt(ppt_id):
        raise HTTPException(status_code=400, detail="请先调用 /start 初始化编辑器")

    editor_state.delete_annotation(ppt_id, page, element_id)
    all_anns = editor_state.get_annotations(ppt_id, page)

    return ResponseData(data={
        "element_id": element_id,
        "annotations": all_anns,
    })


@router.post("/save-all", response_model=ResponseData)
async def editor_save_all(
    ppt_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """应用所有待提交编辑 → 重建 PPTX → 更新数据库 pages_json"""
    await _ensure_ppt_access(ppt_id, db, teacher_id)

    if not editor_state.has_ppt(ppt_id):
        raise HTTPException(status_code=400, detail="无可保存内容或编辑器未初始化")

    result = await save_all(ppt_id, db)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "保存失败"))

    return ResponseData(data=result)


@router.get("/state", response_model=ResponseData)
async def get_editor_state(
    ppt_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """查看编辑器当前状态（调试用）"""
    await _ensure_ppt_access(ppt_id, db, teacher_id)

    if not editor_state.has_ppt(ppt_id):
        return ResponseData(data={"active": False, "message": "编辑器未初始化"})

    all_edits = editor_state.get_all_edits(ppt_id)
    summary = {}
    for page_idx, edits in all_edits.items():
        summary[page_idx] = {
            "edit_count": len(edits),
            "annotations": editor_state.get_annotations(ppt_id, page_idx),
        }

    return ResponseData(data={
        "active": True,
        "svg_count": len(editor_state._svgs.get(ppt_id, {})),
        "pages": summary,
    })

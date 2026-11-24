# SVG 编辑器业务逻辑
# 负责 SVG 解析、编辑应用、图标内联、保存回写

import json
import logging
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from app.ppt_generator.pptx_editor.annotations import (
    assign_temp_ids,
    parse_annotations,
    set_annotation,
    set_text,
    set_attributes,
    strip_unused_temp_ids,
)
from app.ppt_generator.pptx_editor.editor_state import editor_state

logger = logging.getLogger("pptx_editor")

# ---- 安全校验 ----

_UNSAFE_COLOR_RE = re.compile(r"[;:@\\]|url\s*\(", re.IGNORECASE)
_SAFE_ATTR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]*$")
_MAX_ATTR_VALUE_LEN = 256
_MAX_EDIT_TEXT_LEN = 5000
_ADDABLE_BATCH_ATTRS = frozenset({
    "fill", "stroke", "opacity",
    "font-size", "font-family", "font-weight", "text-anchor",
    "x", "y",
})


def validate_edit_attrs(attrs: dict, existing_attrs: set[str]) -> Optional[str]:
    """校验编辑属性，非法时返回错误信息"""
    from app.ppt_generator.pptx_editor.annotations import is_editable_attr
    for key, value in attrs.items():
        if not isinstance(key, str) or not _SAFE_ATTR_NAME_RE.match(key):
            return f"invalid attribute name: {key}"
        if not is_editable_attr(key):
            return f"attribute not editable: {key}"
        if key not in existing_attrs and key != "transform" and key not in _ADDABLE_BATCH_ATTRS:
            return f"attribute does not exist on element: {key}"
        if value is None:
            if key not in existing_attrs:
                return f"attribute does not exist on element: {key}"
            continue
        if not isinstance(value, str):
            return f"value must be a string: {key}"
        if len(value) > _MAX_ATTR_VALUE_LEN:
            return f"value too long: {key}"
        if key in ("fill", "stroke", "color", "stop-color", "flood-color", "lighting-color"):
            if len(value) >= _MAX_ATTR_VALUE_LEN or _UNSAFE_COLOR_RE.search(value):
                return f"unsafe color value: {key}"
        if key == "transform" and re.search(r"nan|inf", value, re.IGNORECASE):
            return f"invalid transform value: {key}"
        if any(c in value for c in '<>"'):
            return f"invalid value: {key}"
        if re.search(r"javascript\s*:|data\s*:|url\s*\(", value, re.IGNORECASE):
            return f"unsafe value: {key}"
    return None


def _find_by_id(root: ET.Element, element_id: str) -> Optional[ET.Element]:
    for elem in root.iter():
        if elem.get("id") == element_id:
            return elem
    return None


def _apply_edit_record(root: ET.Element, record: dict) -> tuple[bool, Optional[str]]:
    element_id = record.get("element_id")
    if not isinstance(element_id, str):
        return False, "invalid-record"
    promote = record.get("promote_tspan")
    if promote:
        from app.ppt_generator.pptx_editor.annotations import promote_tspan_to_text
        if not isinstance(promote, dict):
            return False, "invalid-promote"
        ok, reason = promote_tspan_to_text(
            root, element_id,
            str(promote.get("x") or ""),
            str(promote.get("y") or ""),
        )
        if not ok:
            return ok, reason
    if "text" in record:
        ok, reason = set_text(root, element_id, str(record.get("text") or ""))
        if not ok:
            return ok, reason
    attrs = record.get("attrs")
    if attrs:
        ok, reason = set_attributes(root, element_id, attrs)
        if not ok:
            return ok, reason
    return True, None


def _apply_edit_records(root: ET.Element, records: list[dict]) -> tuple[bool, Optional[str]]:
    for record in records:
        ok, reason = _apply_edit_record(root, record)
        if not ok:
            return ok, reason
    return True, None


# ---- 图标内联（浏览器预览用）----

_USE_ICON_PATTERN = re.compile(r'<use\s+[^>]*data-icon="[^"]*"[^>]*/>')


def inline_icons(content: str) -> tuple[str, list[dict]]:
    """将 <use data-icon="..."/> 替换为内联 <g> 用于浏览器预览"""
    from app.ppt_generator.pptx_editor.embed_icons import (
        parse_use_element,
        resolve_icon_path,
        extract_paths_from_icon,
        generate_icon_group,
    )
    warnings: list[dict] = []
    matches = list(_USE_ICON_PATTERN.finditer(content))
    if not matches:
        return content, warnings

    from app.ppt_generator.pptx_editor.editor_routes import ICONS_DIR
    icons_dir = ICONS_DIR

    new_content = content
    for match in reversed(matches):
        use_str = match.group(0)
        icon_name = ""
        try:
            attrs = parse_use_element(use_str)
            icon_name = str(attrs.get("icon") or "")
            if not icon_name:
                warnings.append({"icon": "", "reason": "missing data-icon attribute"})
                continue
            icon_path, _ = resolve_icon_path(icon_name, icons_dir)
            color = str(attrs.get("fill", "#000000"))
            elements, style, base_size = extract_paths_from_icon(icon_path, color)
        except Exception as exc:
            warnings.append({"icon": icon_name, "reason": f"{type(exc).__name__}: {exc}"})
            logger.warning("icon inline failed: name=%r reason=%s", icon_name, exc)
            continue
        if not elements:
            warnings.append({"icon": icon_name, "reason": "no renderable paths in icon"})
            continue
        replacement = generate_icon_group(attrs, elements, style, base_size)
        id_match = re.search(r'\bid="([^"]+)"', use_str)
        if id_match:
            preview_attrs = [
                f'id="{_xml_attr(id_match.group(1))}"',
                f'data-icon="{_xml_attr(icon_name)}"',
            ]
            for key in ("x", "y", "width", "height"):
                if key in attrs:
                    preview_attrs.append(f'data-use-{key}="{_xml_attr(attrs[key])}"')
            if "transform" in attrs:
                preview_attrs.append('data-use-has-transform="1"')
            replacement = replacement.replace(
                "<g ", f'<g {" ".join(preview_attrs)} ', 1,
            )
        new_content = new_content[:match.start()] + replacement + new_content[match.end():]
    return new_content, warnings


def _xml_attr(value: object) -> str:
    return str(value).replace("&", "&amp;").replace('"', "&quot;")


# ---- 保存回写 ----

async def save_all(ppt_id: int, db_session) -> dict:
    """将 PPT 的所有待提交编辑写入 SVG 并重建 PPTX"""
    from app.ppt_generator.pptx_to_svg.converter import convert_pptx_to_svg, ConvertOptions
    from app.ppt_generator.svg_to_pptx.pptx_builder import build_pptx_from_svgs
    from app.services.ppt_service import PPTService

    edits = editor_state.get_all_edits(ppt_id)
    annotations_data = editor_state.get_all_annotations(ppt_id)

    if not edits and not annotations_data:
        return {"status": "ok", "files_modified": [], "message": "无变更需要保存"}

    # 1. 获取原始 SVG，应用编辑和注解
    modified_pages = []
    svg_dict = {}

    for page_idx in sorted(set(list(edits.keys()) + list(annotations_data.keys()))):
        svg_content = editor_state.get_svg(ppt_id, page_idx)
        if svg_content is None:
            continue
        try:
            tree = ET.fromstring(svg_content.encode("utf-8"))
            root = tree
        except ET.ParseError as exc:
            logger.warning("svg parse failed page=%d: %s", page_idx, exc)
            continue

        assign_temp_ids(root)

        # 应用编辑
        page_edits = edits.get(page_idx, [])
        ok, reason = _apply_edit_records(root, page_edits)
        if not ok:
            return {"status": "error", "message": f"第{page_idx + 1}页编辑应用失败: {reason}"}

        # 写入注解
        page_anns = annotations_data.get(page_idx, {})
        old_anns = {a["element_id"]: a["annotation"] for a in parse_annotations(root)}
        for elem in root.iter():
            elem.attrib.pop("data-edit-target", None)
            elem.attrib.pop("data-edit-annotation", None)
        for element_id, annotation_text in page_anns.items():
            set_annotation(root, element_id, annotation_text)
        annotated_ids = set(page_anns.keys())
        strip_unused_temp_ids(root, annotated_ids)

        svg_str = ET.tostring(root, encoding="unicode", xml_declaration=True)
        svg_dict[page_idx] = svg_str
        modified_pages.append(page_idx)

    if not svg_dict:
        return {"status": "ok", "files_modified": [], "message": "无有效 SVG"}

    # 2. 写入临时 SVG 文件并重建 PPTX
    import asyncio
    loop = asyncio.get_event_loop()

    with tempfile.TemporaryDirectory(prefix=f"svg_editor_{ppt_id}_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        svg_files = []
        for page_idx in sorted(svg_dict.keys()):
            fpath = tmp_path / f"slide_{page_idx + 1:04d}.svg"
            fpath.write_text(svg_dict[page_idx], encoding="utf-8")
            svg_files.append(str(fpath))

        # SVG → PPTX
        pptx_out = tmp_path / f"edited_{ppt_id}.pptx"
        try:
            build_pptx_from_svgs(svg_files, str(pptx_out))
        except Exception as exc:
            logger.error("svg_to_pptx failed: %s", exc)
            return {"status": "error", "message": f"PPTX 重建失败: {exc}"}

        # 从新 PPTX 提取 pages_json（回读）
        try:
            options = ConvertOptions(
                embed_images=True, inheritance_mode="flat", keep_hidden=False
            )
            convert_result = await loop.run_in_executor(
                None, convert_pptx_to_svg, pptx_out, None, options,
            )
        except Exception as exc:
            logger.error("pptx_to_svg回读失败: %s", exc)
            return {"status": "error", "message": f"SVG 回读失败: {exc}"}

    # 3. 更新数据库中的 pages_json
    from app.schemas.ppt import PPTUpdateRequest
    try:
        ppt = await PPTService.get_ppt(db_session, ppt_id, None)
        current_pages = ppt.get("pages_json", [])
        if isinstance(current_pages, str):
            current_pages = json.loads(current_pages)
    except Exception:
        current_pages = []

    # 保留原始 JSON 结构，仅增量更新
    updated = False
    for art in convert_result.slides:
        idx = art.index if hasattr(art, "index") else art.page_index
        if 0 <= idx < len(current_pages):
            current_pages[idx]["_editor_svg"] = svg_dict.get(idx)
            updated = True

    if updated:
        await PPTService.update_ppt(
            db_session, ppt_id, None,
            PPTUpdateRequest(pages_json=current_pages),
        )
        await db_session.commit()

    # 4. 清理内存状态
    editor_state.clear_ppt(ppt_id)

    return {
        "status": "ok",
        "files_modified": modified_pages,
        "message": f"已保存并更新 {len(modified_pages)} 页",
    }

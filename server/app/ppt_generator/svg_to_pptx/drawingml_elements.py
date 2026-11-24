"""DrawingML 元素构建器 — 构建 PPTX 幻灯片内容 XML 片段

提供从 SVG 元素到 PowerPoint DrawingML 原语的转换函数。
"""
from typing import Optional, Dict, Any
from .drawingml_styles import (
    build_fill_xml, build_line_xml, build_text_style_xml,
    build_paragraph_xml, build_xfrm_xml, build_gradient_fill_xml,
)
from .drawingml_paths import build_cust_geom_xml
from .drawingml_context import DrawingMLContext
from .drawingml_utils import px_to_emu, escape_xml, extract_float


def build_rect_element(
    ctx: DrawingMLContext,
    x: float, y: float, w: float, h: float,
    fill_color: Optional[str] = None,
    stroke_color: Optional[str] = None,
    stroke_width: float = 0,
    rx: float = 0, ry: float = 0,
    opacity: float = 1.0,
) -> str:
    """构建矩形 DrawingML 元素 (p:sp)

    Args:
        ctx: DrawingML 上下文
        x, y: 左上角坐标 (SVG px)
        w, h: 宽高 (SVG px)
        fill_color: 填充色
        stroke_color: 描边色
        stroke_width: 描边宽
        rx, ry: 圆角半径
        opacity: 透明度

    Returns:
        p:sp XML 片段
    """
    emu_x = px_to_emu(x)
    emu_y = px_to_emu(y)
    emu_w = px_to_emu(w)
    emu_h = px_to_emu(h)

    shape_id = ctx.get_next_shape_id()
    fill_xml = build_fill_xml(ctx.map_color(fill_color), opacity) if fill_color and fill_color != "none" else ""
    line_xml = build_line_xml(ctx.map_color(stroke_color), stroke_width, opacity) if stroke_color and stroke_color != "none" else ""
    xfrm_xml = build_xfrm_xml(emu_x, emu_y, emu_w, emu_h)

    # 圆角矩形 vs 直角矩形
    if rx > 0 or ry > 0:
        prst_geom = f'<a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val {int(rx)}"/></a:avLst></a:prstGeom>'
    else:
        prst_geom = '<a:prstGeom prst="rect"/>'

    return (
        f'<p:sp>'
        f'<p:nvSpPr><p:cNvPr id="{shape_id}" name="{shape_id}"/>'
        f'<p:cNvSpPr txBox="0"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>{xfrm_xml}{prst_geom}{fill_xml}{line_xml}</p:spPr>'
        f'</p:sp>'
    )


def build_text_element(
    ctx: DrawingMLContext,
    x: float, y: float, w: float, h: float,
    text: str,
    font_family: str = "Calibri",
    font_size_pt: float = 18,
    color_hex: str = "000000",
    bold: bool = False,
    italic: bool = False,
    align: str = "left",
    opacity: float = 1.0,
    lang: str = "en-US",
) -> str:
    """构建文本元素 (p:sp 包含 txBody)

    Args:
        ctx: DrawingML 上下文
        x, y: 左上角坐标
        w, h: 文本框大小
        text: 文本内容
        font_family, font_size_pt, color_hex, bold, italic: 文本样式
        align: 对齐方式
        opacity: 透明度

    Returns:
        p:sp XML 片段
    """
    emu_x = px_to_emu(x)
    emu_y = px_to_emu(y)
    emu_w = px_to_emu(w)
    emu_h = px_to_emu(h)

    shape_id = ctx.get_next_shape_id()
    mapped_font = ctx.map_font(font_family)
    mapped_color = ctx.map_color(color_hex)
    xfrm_xml = build_xfrm_xml(emu_x, emu_y, emu_w, emu_h)
    paragraph_xml = build_paragraph_xml(text, mapped_font, font_size_pt, mapped_color, bold, italic, lang=lang)
    body_pr_xml = f'<a:bodyPr wrap="square" rtlCol="0"/>'

    return (
        f'<p:sp>'
        f'<p:nvSpPr><p:cNvPr id="{shape_id}" name="{shape_id}"/>'
        f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>{xfrm_xml}<a:prstGeom prst="rect"/></p:spPr>'
        f'<p:txBody>{body_pr_xml}{paragraph_xml}</p:txBody>'
        f'</p:sp>'
    )


def build_path_element(
    ctx: DrawingMLContext,
    d: str,
    fill_color: Optional[str] = None,
    stroke_color: Optional[str] = None,
    stroke_width: float = 0,
    opacity: float = 1.0,
) -> str:
    """构建路径元素 (p:sp 使用 custGeom)

    Args:
        ctx: DrawingML 上下文
        d: SVG path d 属性
        fill_color: 填充色
        stroke_color: 描边色
        stroke_width: 描边宽
        opacity: 透明度

    Returns:
        p:sp XML 片段
    """
    shape_id = ctx.get_next_shape_id()
    geom_xml = build_cust_geom_xml(d)
    fill_xml = build_fill_xml(ctx.map_color(fill_color), opacity) if fill_color and fill_color != "none" else ""
    line_xml = build_line_xml(ctx.map_color(stroke_color), stroke_width, opacity) if stroke_color and stroke_color != "none" else ""

    return (
        f'<p:sp>'
        f'<p:nvSpPr><p:cNvPr id="{shape_id}" name="{shape_id}"/>'
        f'<p:cNvSpPr txBox="0"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>{geom_xml}{fill_xml}{line_xml}</p:spPr>'
        f'</p:sp>'
    )


def build_circle_element(
    ctx: DrawingMLContext,
    cx: float, cy: float, r: float,
    fill_color: Optional[str] = None,
    stroke_color: Optional[str] = None,
    stroke_width: float = 0,
    opacity: float = 1.0,
) -> str:
    """构建圆形元素 (p:sp 使用椭圆预设)

    Args:
        ctx: DrawingML 上下文
        cx, cy: 圆心坐标
        r: 半径
        fill_color: 填充色
        stroke_color: 描边色
        stroke_width: 描边宽
        opacity: 透明度

    Returns:
        p:sp XML 片段
    """
    x = cx - r
    y = cy - r
    w = r * 2
    h = r * 2

    emu_x = px_to_emu(x)
    emu_y = px_to_emu(y)
    emu_w = px_to_emu(w)
    emu_h = px_to_emu(h)

    shape_id = ctx.get_next_shape_id()
    fill_xml = build_fill_xml(ctx.map_color(fill_color), opacity) if fill_color and fill_color != "none" else ""
    line_xml = build_line_xml(ctx.map_color(stroke_color), stroke_width, opacity) if stroke_color and stroke_color != "none" else ""
    xfrm_xml = build_xfrm_xml(emu_x, emu_y, emu_w, emu_h)

    return (
        f'<p:sp>'
        f'<p:nvSpPr><p:cNvPr id="{shape_id}" name="{shape_id}"/>'
        f'<p:cNvSpPr txBox="0"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>{xfrm_xml}<a:prstGeom prst="ellipse"/>{fill_xml}{line_xml}</p:spPr>'
        f'</p:sp>'
    )


def build_line_element(
    ctx: DrawingMLContext,
    x1: float, y1: float, x2: float, y2: float,
    stroke_color: str = "000000",
    stroke_width: float = 1,
    opacity: float = 1.0,
) -> str:
    """构建线段元素 (p:cxnSp)

    Args:
        ctx: DrawingML 上下文
        x1, y1: 起点坐标
        x2, y2: 终点坐标
        stroke_color: 线条颜色
        stroke_width: 线条宽度
        opacity: 透明度

    Returns:
        p:cxnSp XML 片段
    """
    shape_id = ctx.get_next_shape_id()
    mapped_color = ctx.map_color(stroke_color)
    emu_x = px_to_emu(min(x1, x2))
    emu_y = px_to_emu(min(y1, y2))
    emu_w = px_to_emu(abs(x2 - x1))
    emu_h = px_to_emu(abs(y2 - y1))

    line_xml = build_line_xml(mapped_color, stroke_width, opacity)

    return (
        f'<p:cxnSp>'
        f'<p:nvCxnSpPr><p:cNvPr id="{shape_id}" name="{shape_id}"/>'
        f'<p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr>'
        f'<p:spPr>'
        f'{build_xfrm_xml(emu_x, emu_y, emu_w, emu_h)}'
        f'<a:prstGeom prst="line"/>'
        f'{line_xml}'
        f'</p:spPr>'
        f'</p:cxnSp>'
    )


def build_image_element(
    ctx: DrawingMLContext,
    x: float, y: float, w: float, h: float,
    image_rid: str,
    opacity: float = 1.0,
) -> str:
    """构建图片元素 (p:pic)

    Args:
        ctx: DrawingML 上下文
        x, y: 左上角坐标
        w, h: 图片尺寸
        image_rid: 图片关系的 rId
        opacity: 透明度

    Returns:
        p:pic XML 片段
    """
    emu_x = px_to_emu(x)
    emu_y = px_to_emu(y)
    emu_w = px_to_emu(w)
    emu_h = px_to_emu(h)

    shape_id = ctx.get_next_shape_id()
    alpha_xml = f'<a:alpha val="{int(opacity * 100000)}"/>' if opacity < 1.0 else ""

    return (
        f'<p:pic>'
        f'<p:nvPicPr>'
        f'<p:cNvPr id="{shape_id}" name="{shape_id}"/>'
        f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
        f'<p:nvPr/>'
        f'</p:nvPicPr>'
        f'<p:blipFill>'
        f'<a:blip r:embed="{image_rid}">{alpha_xml}</a:blip>'
        f'<a:stretch><a:fillRect/></a:stretch>'
        f'</p:blipFill>'
        f'<p:spPr>'
        f'{build_xfrm_xml(emu_x, emu_y, emu_w, emu_h)}'
        f'<a:prstGeom prst="rect"/>'
        f'</p:spPr>'
        f'</p:pic>'
    )


def build_group_element(
    ctx: DrawingMLContext,
    x: float, y: float, w: float, h: float,
    child_elements: list,
) -> str:
    """构建组元素 (p:grpSp)

    Args:
        ctx: DrawingML 上下文
        x, y: 组位置
        w, h: 组大小
        child_elements: 子元素 XML 列表

    Returns:
        p:grpSp XML 片段
    """
    emu_x = px_to_emu(x)
    emu_y = px_to_emu(y)
    emu_w = px_to_emu(w)
    emu_h = px_to_emu(h)

    children_xml = "".join(child_elements)

    return (
        f'<p:grpSp>'
        f'<p:nvGrpSpPr>'
        f'<p:cNvPr id="{ctx.get_next_shape_id()}" name="group"/>'
        f'<p:cNvGrpSpPr/><p:nvPr/>'
        f'</p:nvGrpSpPr>'
        f'<p:grpSpPr>'
        f'<a:xfrm>'
        f'<a:off x="{emu_x}" y="{emu_y}"/>'
        f'<a:ext cx="{emu_w}" cy="{emu_h}"/>'
        f'<a:chOff x="0" y="0"/>'
        f'<a:chExt cx="{emu_w}" cy="{emu_h}"/>'
        f'</a:xfrm>'
        f'</p:grpSpPr>'
        f'{children_xml}'
        f'</p:grpSp>'
    )

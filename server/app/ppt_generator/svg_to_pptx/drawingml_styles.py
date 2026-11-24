"""DrawingML 样式映射 — SVG 样式属性 → DrawingML XML"""
from typing import Optional


def build_fill_xml(color_hex: str, opacity: float = 1.0) -> str:
    """构建填充 XML

    Args:
        color_hex: 十六进制颜色 (如 "FF0000")
        opacity: 透明度 (0-1)

    Returns:
        DrawingML solidFill XML 片段
    """
    if not color_hex or color_hex == "none":
        return ""

    opacity_attr = ""
    if opacity < 1.0:
        alpha = int(opacity * 100000)
        opacity_attr = f'<a:alpha val="{alpha}"/>'

    return (
        f'<a:solidFill>'
        f'<a:srgbClr val="{color_hex}">{opacity_attr}</a:srgbClr>'
        f'</a:solidFill>'
    )


def build_gradient_fill_xml(gradient_def: dict) -> str:
    """构建渐变填充 XML

    Args:
        gradient_def: {
            'type': 'linear'|'radial',
            'angle': 0-360,
            'stops': [{'pos': 0-100000, 'color': 'FF0000', 'opacity': 1.0}, ...]
        }

    Returns:
        DrawingML gradFill XML 片段
    """
    grad_type = gradient_def.get("type", "linear")
    angle = gradient_def.get("angle", 0)

    if grad_type == "linear":
        # 转换 SVG 角度为 DrawingML 角度
        # SVG: 0=上, 顺时针; DrawingML: 0=左, 逆时针
        dml_angle = (450 - angle) % 360
        path_xml = f'<a:lin ang="{int(dml_angle * 60000)}" scaled="0"/>'
    elif grad_type == "radial":
        path_xml = '<a:path path="circle"><a:fillToRect l="50000" t="50000" r="50000" b="50000"/></a:path>'
    else:
        path_xml = f'<a:lin ang="0" scaled="0"/>'

    stops_xml_parts = []
    for stop in gradient_def.get("stops", []):
        pos = stop.get("pos", 0)
        color = stop.get("color", "000000")
        opacity = stop.get("opacity", 1.0)
        opacity_attr = ""
        if opacity < 1.0:
            alpha = int(opacity * 100000)
            opacity_attr = f'<a:alpha val="{alpha}"/>'
        stops_xml_parts.append(
            f'<a:gs pos="{pos}">'
            f'<a:srgbClr val="{color}">{opacity_attr}</a:srgbClr>'
            f'</a:gs>'
        )

    stops_xml = "".join(stops_xml_parts)

    return (
        f'<a:gradFill>'
        f'{path_xml}'
        f'<a:gsLst>{stops_xml}</a:gsLst>'
        f'</a:gradFill>'
    )


def build_line_xml(color_hex: str, width_pt: float = 1.0, opacity: float = 1.0) -> str:
    """构建线条 XML

    Args:
        color_hex: 十六进制颜色
        width_pt: 线宽（磅值）
        opacity: 透明度

    Returns:
        DrawingML ln XML 片段
    """
    if not color_hex or color_hex == "none":
        return ""

    w_emu = int(width_pt * 12700)
    fill_xml = build_fill_xml(color_hex, opacity)

    return (
        f'<a:ln w="{w_emu}">'
        f'{fill_xml}'
        f'</a:ln>'
    )


def build_text_style_xml(
    font_family: str = "Calibri",
    font_size_pt: float = 18,
    color_hex: str = "000000",
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
    opacity: float = 1.0,
    lang: str = "en-US",
) -> str:
    """构建文本样式 XML

    Args:
        font_family: 字体名
        font_size_pt: 字号（磅）
        color_hex: 十六进制颜色
        bold, italic, underline: 样式标记
        opacity: 透明度
        lang: 语言标记 (en-US / zh-CN 等)

    Returns:
        DrawingML 文本样式 XML 片段
    """
    sz_hundredths = int(font_size_pt * 100)
    bold_attr = ' b="1"' if bold else ''
    italic_attr = ' i="1"' if italic else ''
    uline_attr = ' u="sng"' if underline else ''
    opacity_attr = ""
    if opacity < 1.0:
        alpha = int(opacity * 100000)
        opacity_attr = f'<a:alpha val="{alpha}"/>'

    return (
        f'<a:rPr lang="{lang}" sz="{sz_hundredths}"{bold_attr}{italic_attr}{uline_attr}>'
        f'<a:solidFill><a:srgbClr val="{color_hex}">{opacity_attr}</a:srgbClr></a:solidFill>'
        f'<a:latin typeface="{font_family}"/>'
        f'<a:ea typeface="{font_family}"/>'
        f'</a:rPr>'
    )


def build_paragraph_xml(
    text: str,
    font_family: str = "Calibri",
    font_size_pt: float = 18,
    color_hex: str = "000000",
    bold: bool = False,
    italic: bool = False,
    align: str = "left",
    space_before: int = 0,
    space_after: int = 0,
    lang: str = "en-US",
) -> str:
    """构建段落 XML

    Args:
        text: 文本内容
        font_family: 字体名
        font_size_pt: 字号（磅）
        color_hex: 十六进制颜色
        bold, italic: 样式标记
        align: 对齐方式
        space_before, space_after: 段落间距
        lang: 语言标记

    Returns:
        DrawingML 段落 XML 片段
    """
    align_map = {"left": "l", "center": "ctr", "right": "r", "justify": "just"}
    dml_align = align_map.get(align, "l")

    style_xml = build_text_style_xml(font_family, font_size_pt, color_hex, bold, italic, lang=lang)
    from .drawingml_utils import escape_xml
    safe_text = escape_xml(text)

    return (
        f'<a:p>'
        f'<a:pPr algn="{dml_align}" spcBef="{space_before}" spcAft="{space_after}"/>'
        f'<a:r>{style_xml}<a:t>{safe_text}</a:t></a:r>'
        f'</a:p>'
    )


def build_xfrm_xml(x: float, y: float, w: float, h: float, rot: float = 0) -> str:
    """构建 2D 变换 XML

    Args:
        x, y: 左上角坐标 (EMU)
        w, h: 宽高 (EMU)
        rot: 旋转角度（60,000 分之一度）

    Returns:
        DrawingML spPr/xfrm XML 片段
    """
    rot_attr = f' rot="{int(rot)}"' if rot else ""
    return (
        f'<a:xfrm{rot_attr}>'
        f'<a:off x="{int(x)}" y="{int(y)}"/>'
        f'<a:ext cx="{int(w)}" cy="{int(h)}"/>'
        f'</a:xfrm>'
    )

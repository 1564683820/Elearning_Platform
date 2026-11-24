"""PPTX 页脚/页码/日期 XML 构建器

为 PPTX 幻灯片添加页脚、页码和日期占位符的 Open XML 定义。
"""

from typing import Optional
from lxml import etree

# 命名空间
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def build_footer_shape_xml(
    text: str = "",
    x_emu: int = 457200,    # 0.5 inch
    y_emu: int = 6400800,   # 7 inch (底部)
    w_emu: int = 1828800,   # 2 inch
    h_emu: int = 370000,    # ~0.4 inch
    font_name: str = "Arial",
    font_size_pt: int = 10,
    color_hex: str = "999999",
    is_center: bool = False,
) -> str:
    """构建页脚文本形状 XML (p:sp)

    Args:
        text: 页脚文本（如公司名、版权信息）
        x_emu, y_emu, w_emu, h_emu: 位置和尺寸 (EMU)
        font_name: 字体名称
        font_size_pt: 字号（磅）
        color_hex: 颜色十六进制（无 #）
        is_center: 是否居中对齐

    Returns:
        p:sp XML 字符串（空字符串表示无页脚）
    """
    if not text:
        return ""

    align_val = "ctr" if is_center else "l"
    sz_hundredths = font_size_pt * 100  # a:sz 使用百分之一磅值

    return (
        f'<p:sp xmlns:p="{NS_P}" xmlns:a="{NS_A}" xmlns:r="{NS_R}">'
        f'<p:nvSpPr>'
        f'<p:cNvPr id="10000" name="Footer Shape"/>'
        f'<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        f'<p:nvPr/>'
        f'</p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm>'
        f'<a:off x="{x_emu}" y="{y_emu}"/>'
        f'<a:ext cx="{w_emu}" cy="{h_emu}"/>'
        f'</a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:noFill/>'
        f'</p:spPr>'
        f'<p:txBody>'
        f'<a:bodyPr rtlCol="0" anchor="ctr"/>'
        f'<a:lstStyle/>'
        f'<a:p>'
        f'<a:pPr algn="{align_val}"/>'
        f'<a:r>'
        f'<a:rPr lang="zh-CN" sz="{sz_hundredths}" dirty="0"'
        f' err="1" smtClean="0">'
        f'<a:solidFill><a:srgbClr val="{color_hex}"/></a:solidFill>'
        f'<a:latin typeface="{font_name}"/>'
        f'<a:ea typeface="{font_name}"/>'
        f'</a:rPr>'
        f'<a:t>{text}</a:t>'
        f'</a:r>'
        f'</a:p>'
        f'</a:txBody>'
        f'</p:sp>'
    )


def build_page_number_shape_xml(
    x_emu: int = 10972800,  # ~12 inch (右下角)
    y_emu: int = 6400800,
    w_emu: int = 914400,    # 1 inch
    h_emu: int = 370000,
    font_name: str = "Arial",
    font_size_pt: int = 10,
    color_hex: str = "999999",
) -> str:
    """构建页码占位符 XML (p:sp 含 fld 字段代码)

    使用 <a:fld> 引用幻灯片编号字段，PowerPoint 会自动填充页码。

    Args:
        x_emu, y_emu, w_emu, h_emu: 位置和尺寸 (EMU)
        font_name, font_size_pt, color_hex: 字体样式

    Returns:
        p:sp XML 字符串
    """
    sz_hundredths = font_size_pt * 100

    return (
        f'<p:sp xmlns:p="{NS_P}" xmlns:a="{NS_A}">'
        f'<p:nvSpPr>'
        f'<p:cNvPr id="10001" name="Page Number"/>'
        f'<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        f'<p:nvPr/>'
        f'</p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm>'
        f'<a:off x="{x_emu}" y="{y_emu}"/>'
        f'<a:ext cx="{w_emu}" cy="{h_emu}"/>'
        f'</a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:noFill/>'
        f'</p:spPr>'
        f'<p:txBody>'
        f'<a:bodyPr rtlCol="0" anchor="ctr"/>'
        f'<a:lstStyle/>'
        f'<a:p>'
        f'<a:pPr algn="r"/>'
        f'<a:r>'
        f'<a:rPr lang="zh-CN" sz="{sz_hundredths}" dirty="0">'
        f'<a:solidFill><a:srgbClr val="{color_hex}"/></a:solidFill>'
        f'<a:latin typeface="{font_name}"/>'
        f'<a:ea typeface="{font_name}"/>'
        f'</a:rPr>'
        f'<a:fld id="SLDNU{hash((x_emu, y_emu))}" type="slidenum">'
        f'<a:t>&lt;number&gt;</a:t>'
        f'</a:fld>'
        f'</a:r>'
        f'</a:p>'
        f'</a:txBody>'
        f'</p:sp>'
    )


def build_date_shape_xml(
    date_text: str = "",
    x_emu: int = 457200,
    y_emu: int = 6400800,
    w_emu: int = 2743200,  # 3 inch
    h_emu: int = 370000,
    font_name: str = "Arial",
    font_size_pt: int = 10,
    color_hex: str = "999999",
) -> str:
    """构建日期文本框 XML (p:sp)

    Args:
        date_text: 日期文本（如 "2026-07-05" 或 "2026年7月"）
        x_emu, y_emu, w_emu, h_emu, font_name, font_size_pt, color_hex: 样式

    Returns:
        p:sp XML 字符串
    """
    if not date_text:
        return ""

    sz_hundredths = font_size_pt * 100

    return (
        f'<p:sp xmlns:p="{NS_P}" xmlns:a="{NS_A}">'
        f'<p:nvSpPr>'
        f'<p:cNvPr id="10002" name="Date"/>'
        f'<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        f'<p:nvPr/>'
        f'</p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm>'
        f'<a:off x="{x_emu}" y="{y_emu}"/>'
        f'<a:ext cx="{w_emu}" cy="{h_emu}"/>'
        f'</a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:noFill/>'
        f'</p:spPr>'
        f'<p:txBody>'
        f'<a:bodyPr rtlCol="0" anchor="ctr"/>'
        f'<a:lstStyle/>'
        f'<a:p>'
        f'<a:pPr algn="l"/>'
        f'<a:r>'
        f'<a:rPr lang="zh-CN" sz="{sz_hundredths}" dirty="0">'
        f'<a:solidFill><a:srgbClr val="{color_hex}"/></a:solidFill>'
        f'<a:latin typeface="{font_name}"/>'
        f'<a:ea typeface="{font_name}"/>'
        f'</a:rPr>'
        f'<a:t>{date_text}</a:t>'
        f'</a:r>'
        f'</a:p>'
        f'</a:txBody>'
        f'</p:sp>'
    )


def build_common_slide_data(
    footer_text: str = "",
    show_page_number: bool = False,
    date_text: str = "",
    slide_width_emu: int = 12192000,
    slide_height_emu: int = 6858000,
    font_name: str = "Arial",
    font_size_pt: int = 10,
    color_hex: str = "999999",
) -> str:
    """构建幻灯片通用装饰元素（页脚 + 页码 + 日期）

    三个元素组合在一起，如需独立控制可单独调用上面的函数。

    Args:
        footer_text: 页脚文本
        show_page_number: 是否显示页码
        date_text: 日期文本
        slide_width_emu, slide_height_emu: 幻灯片尺寸
        font_name, font_size_pt, color_hex: 字体样式

    Returns:
        组合的 XML 片段
    """
    parts = []

    # 左下角：日期
    if date_text:
        parts.append(build_date_shape_xml(
            date_text=date_text,
            x_emu=int(slide_width_emu * 0.04),
            y_emu=int(slide_height_emu * 0.94),
            w_emu=int(slide_width_emu * 0.20),
            font_name=font_name,
            font_size_pt=font_size_pt,
            color_hex=color_hex,
        ))

    # 中下：页脚
    if footer_text:
        parts.append(build_footer_shape_xml(
            text=footer_text,
            x_emu=int(slide_width_emu * 0.35),
            y_emu=int(slide_height_emu * 0.94),
            w_emu=int(slide_width_emu * 0.30),
            is_center=True,
            font_name=font_name,
            font_size_pt=font_size_pt,
            color_hex=color_hex,
        ))

    # 右下：页码
    if show_page_number:
        parts.append(build_page_number_shape_xml(
            x_emu=int(slide_width_emu * 0.88),
            y_emu=int(slide_height_emu * 0.94),
            w_emu=int(slide_width_emu * 0.08),
            font_name=font_name,
            font_size_pt=font_size_pt,
            color_hex=color_hex,
        ))

    return "\n".join(parts)

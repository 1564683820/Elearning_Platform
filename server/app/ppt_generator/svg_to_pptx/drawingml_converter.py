"""SVG DOM → DrawingML 转换分发器

将解析后的 SVG DOM 树转换为 DrawingML p:sp / p:pic / p:grpSp 元素 XML。
"""
import xml.etree.ElementTree as ET
import logging
from typing import List, Optional
from .drawingml_context import DrawingMLContext
from .drawingml_elements import (
    build_rect_element, build_text_element, build_path_element,
    build_circle_element, build_line_element, build_image_element,
    build_group_element,
)
from .drawingml_utils import extract_float

logger = logging.getLogger(__name__)

# SVG 命名空间
SVG_NS = "http://www.w3.org/2000/svg"


def _get_tag_local(tag: str) -> str:
    """获取标签名的本地部分（去除命名空间）"""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


class SVGElementConverter:
    """SVG 元素到 DrawingML 元素的转换器"""

    def __init__(self, ctx: DrawingMLContext, viewbox_width: float = 1280, viewbox_height: float = 720):
        self.ctx = ctx
        self.vb_w = viewbox_width
        self.vb_h = viewbox_height
        self.image_counter = 0

    def convert_element(self, elem: ET.Element) -> Optional[str]:
        """转换单个 SVG 元素为 DrawingML XML"""
        tag = _get_tag_local(elem.tag)
        if tag == "g":
            return self._convert_group(elem)
        elif tag == "rect":
            return self._convert_rect(elem)
        elif tag == "circle":
            return self._convert_circle(elem)
        elif tag == "ellipse":
            return self._convert_ellipse(elem)
        elif tag == "line":
            return self._convert_line(elem)
        elif tag == "polyline" or tag == "polygon":
            return self._convert_polygon(elem, tag == "polygon")
        elif tag == "path":
            return self._convert_path(elem)
        elif tag == "text":
            return self._convert_text(elem)
        elif tag == "image":
            return self._convert_image(elem)
        return None

    def _get_common_attrs(self, elem: ET.Element) -> dict:
        """提取公共属性：fill, stroke, stroke-width, opacity, transform"""
        fill = elem.get("fill")
        stroke = elem.get("stroke")
        sw = extract_float(elem.get("stroke-width", "0"))
        opacity = extract_float(elem.get("opacity", "1.0"))
        fill_opacity = extract_float(elem.get("fill-opacity", "1.0"))
        total_opacity = opacity * fill_opacity
        return {"fill": fill, "stroke": stroke, "stroke_width": sw, "opacity": total_opacity}

    def _convert_rect(self, elem: ET.Element) -> Optional[str]:
        """转换 rect 元素"""
        x = extract_float(elem.get("x", "0"))
        y = extract_float(elem.get("y", "0"))
        w = extract_float(elem.get("width", "0"))
        h = extract_float(elem.get("height", "0"))
        rx = extract_float(elem.get("rx", "0"))
        ry = extract_float(elem.get("ry", "0"))
        attrs = self._get_common_attrs(elem)
        if w <= 0 or h <= 0:
            return None
        return build_rect_element(
            self.ctx, x, y, w, h,
            attrs["fill"], attrs["stroke"],
            attrs["stroke_width"], rx, ry, attrs["opacity"],
        )

    def _convert_circle(self, elem: ET.Element) -> Optional[str]:
        """转换 circle 元素"""
        cx = extract_float(elem.get("cx", "0"))
        cy = extract_float(elem.get("cy", "0"))
        r = extract_float(elem.get("r", "0"))
        attrs = self._get_common_attrs(elem)
        if r <= 0:
            return None
        return build_circle_element(
            self.ctx, cx, cy, r,
            attrs["fill"], attrs["stroke"],
            attrs["stroke_width"], attrs["opacity"],
        )

    def _convert_ellipse(self, elem: ET.Element) -> Optional[str]:
        """转换 ellipse 元素 — 用椭圆预设几何"""
        cx = extract_float(elem.get("cx", "0"))
        cy = extract_float(elem.get("cy", "0"))
        rx = extract_float(elem.get("rx", "0"))
        ry = extract_float(elem.get("ry", "0"))
        attrs = self._get_common_attrs(elem)
        if rx <= 0 or ry <= 0:
            return None
        # 用圆角矩形模拟椭圆（DrawingML 没有椭圆预设）
        x = cx - rx
        y = cy - ry
        w = rx * 2
        h = ry * 2
        return build_rect_element(
            self.ctx, x, y, w, h,
            attrs["fill"], attrs["stroke"],
            attrs["stroke_width"], rx, ry, attrs["opacity"],
        )

    def _convert_line(self, elem: ET.Element) -> Optional[str]:
        """转换 line 元素"""
        x1 = extract_float(elem.get("x1", "0"))
        y1 = extract_float(elem.get("y1", "0"))
        x2 = extract_float(elem.get("x2", "0"))
        y2 = extract_float(elem.get("y2", "0"))
        attrs = self._get_common_attrs(elem)
        return build_line_element(
            self.ctx, x1, y1, x2, y2,
            attrs["stroke"] or "000000",
            max(attrs["stroke_width"], 1),
            attrs["opacity"],
        )

    def _convert_polygon(self, elem: ET.Element, closed: bool) -> Optional[str]:
        """转换 polyline/polygon 元素为 path"""
        points_str = elem.get("points", "")
        if not points_str:
            return None
        attrs = self._get_common_attrs(elem)

        d = "M " + " ".join(p.strip() for p in points_str.replace(",", " ").split())
        if closed:
            d += " Z"

        return build_path_element(
            self.ctx, d,
            attrs["fill"], attrs["stroke"],
            attrs["stroke_width"], attrs["opacity"],
        )

    def _convert_path(self, elem: ET.Element) -> Optional[str]:
        """转换 path 元素"""
        d = elem.get("d", "")
        if not d:
            return None
        attrs = self._get_common_attrs(elem)
        return build_path_element(
            self.ctx, d,
            attrs["fill"], attrs["stroke"],
            attrs["stroke_width"], attrs["opacity"],
        )

    def _detect_has_cjk(self, text: str) -> bool:
        """检测文本是否包含 CJK 字符

        中文字符 Unicode 范围：\u4e00-\u9fff，以及全角符号等
        """
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f' or '\uff00' <= ch <= '\uffef':
                return True
        return False

    def _estimate_text_width(self, text: str, font_size_pt: float, x: float) -> float:
        """估算文本宽度（适配中文）

        中文字符宽度 ~1em，英文字符 ~0.6em
        """
        text_stripped = text.strip()
        if not text_stripped:
            return 0
        cjk_count = sum(1 for ch in text_stripped if '\u4e00' <= ch <= '\u9fff')
        latin_count = len(text_stripped) - cjk_count
        # 中文按 1.0em、英文按 0.6em 估算
        est_w = (cjk_count * font_size_pt * 1.0 + latin_count * font_size_pt * 0.6)
        # 加上边距裕量
        est_w += font_size_pt * 0.5
        return min(est_w, self.vb_w - x)

    def _convert_text(self, elem: ET.Element) -> Optional[str]:
        """转换 text 元素"""
        x = extract_float(elem.get("x", "0"))
        y = extract_float(elem.get("y", "0"))
        text = elem.text or ""
        # 收集所有子文本
        for child in elem:
            if child.text:
                text += child.text
            if child.tail:
                text += child.tail

        if not text.strip():
            return None

        # 提取样式 — 优先使用内联样式
        font_family = elem.get("font-family", "Calibri")
        font_size_str = elem.get("font-size", "18")
        # 处理 "18px" 格式
        font_size_pt = extract_float(font_size_str.replace("px", "").replace("pt", ""))
        if font_size_pt <= 0:
            font_size_pt = 18

        color = elem.get("fill", "#000000")
        bold = elem.get("font-weight", "") in ("bold", "700")
        italic = elem.get("font-style", "") == "italic"
        align = elem.get("text-anchor", "start")
        align_map = {"start": "left", "middle": "center", "end": "right"}
        dml_align = align_map.get(align, "left")
        opacity = extract_float(elem.get("opacity", "1.0"))

        # 检测是否包含中文以确定语言标记
        has_cjk = self._detect_has_cjk(text)
        lang = "zh-CN" if has_cjk else "en-US"

        # 估算文本宽度（适配中文）
        estimated_w = self._estimate_text_width(text, font_size_pt, x)

        return build_text_element(
            self.ctx, x, y - font_size_pt * 0.85, estimated_w, font_size_pt * 1.4,
            text.strip(), font_family, font_size_pt, color,
            bold, italic, dml_align, opacity, lang=lang,
        )

    def _convert_image(self, elem: ET.Element) -> Optional[str]:
        """转换 image 元素（需要外部提供 href→rId 映射）"""
        x = extract_float(elem.get("x", "0"))
        y = extract_float(elem.get("y", "0"))
        w = extract_float(elem.get("width", "0"))
        h = extract_float(elem.get("height", "0"))
        href = elem.get("{http://www.w3.org/1999/xlink}href") or elem.get("href", "")
        if w <= 0 or h <= 0 or not href:
            return None
        return None  # 图片由外部调用者提供 rid

    def _convert_group(self, elem: ET.Element) -> Optional[str]:
        """转换 g（组）元素"""
        child_xmls = []
        for child in elem:
            xml = self.convert_element(child)
            if xml:
                child_xmls.append(xml)

        if not child_xmls:
            return None

        x = extract_float(elem.get("x", "0"))
        y = extract_float(elem.get("y", "0"))

        return build_group_element(
            self.ctx, x, y, self.vb_w, self.vb_h, child_xmls,
        )

    def convert_svg(self, svg_root: ET.Element) -> str:
        """转换整个 SVG 文档为幻灯片内容 XML

        Args:
            svg_root: SVG XML 根元素

        Returns:
            幻灯片内容 XML (p:spTree 内部)
        """
        elements_xml = []

        # 提取 viewBox 尺寸
        vb = svg_root.get("viewBox", f"0 0 {self.vb_w} {self.vb_h}")
        parts = vb.strip().split()
        if len(parts) == 4:
            self.vb_w = float(parts[2])
            self.vb_h = float(parts[3])

        # 处理 SVG 背景
        bg_color = svg_root.get("fill") or svg_root.get("style", "")
        if bg_color and "background" not in bg_color.lower():
            # SVG 自身作为背景
            pass

        # 创建背景矩形（如果 SVG 有背景色）
        if bg_color and bg_color != "none":
            bg_rect = build_rect_element(
                self.ctx, 0, 0, self.vb_w, self.vb_h,
                fill_color=bg_color,
            )
            elements_xml.append(bg_rect)

        # 递归处理所有子元素
        for child in svg_root:
            xml = self.convert_element(child)
            if xml:
                elements_xml.append(xml)

        return "\n".join(elements_xml)


def convert_svg_to_slide_content(svg_xml: str, viewbox_w: float = 1280, viewbox_h: float = 720) -> str:
    """将 SVG XML 字符串转换为幻灯片 DrawingML 内容

    Args:
        svg_xml: SVG XML 字符串
        viewbox_w, viewbox_h: 视口尺寸

    Returns:
        幻灯片内容 XML 字符串 (p:spTree 内部内容)
    """
    try:
        root = ET.fromstring(svg_xml)
    except ET.ParseError as e:
        logger.error(f"SVG 解析错误: {e}")
        return ""

    ctx = DrawingMLContext()
    converter = SVGElementConverter(ctx, viewbox_w, viewbox_h)
    return converter.convert_svg(root)


def convert_svg_file_to_content(svg_path: str, viewbox_w: float = 1280, viewbox_h: float = 720) -> str:
    """读取 SVG 文件并转换为幻灯片内容

    Args:
        svg_path: SVG 文件路径
        viewbox_w, viewbox_h: 视口尺寸

    Returns:
        幻灯片内容 XML 字符串
    """
    import os
    if not os.path.exists(svg_path):
        logger.error(f"SVG 文件不存在: {svg_path}")
        return ""
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_xml = f.read()
    return convert_svg_to_slide_content(svg_xml, viewbox_w, viewbox_h)

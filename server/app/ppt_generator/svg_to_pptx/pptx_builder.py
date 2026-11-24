"""PPTX 包构建器 — 创建 Open XML PPTX 包结构

使用 python-pptx 创建基础 PPTX，然后通过 XML 操作替换幻灯片内容。
Phase 3.4: 增强动画/切换/页脚/母版注入能力。
"""
import os
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from pptx import Presentation
from pptx.util import Emu
from lxml import etree

from .drawingml_converter import convert_svg_to_slide_content
from .drawingml_utils import px_to_emu
from .pptx_animations import build_page_animation_set
from .pptx_footer import build_common_slide_data
from .pptx_master import inject_theme

logger = logging.getLogger(__name__)

# 幻灯片尺寸常量
SLIDE_W_169 = 12192000
SLIDE_H_169 = 6858000

# 命名空间
NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

# p:spTree 模板 — 每张幻灯片的内容容器
SPSLIDE_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
    ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<p:cSld>'
    '<p:spTree>'
    '<p:nvGrpSpPr>'
    '<p:cNvPr id="1" name=""/>'
    '<p:cNvGrpSpPr/>'
    '<p:nvPr/>'
    '</p:nvGrpSpPr>'
    '<p:grpSpPr>'
    '<a:xfrm>'
    '<a:off x="0" y="0"/>'
    '<a:ext cx="0" cy="0"/>'
    '<a:chOff x="0" y="0"/>'
    '<a:chExt cx="0" cy="0"/>'
    '</a:xfrm>'
    '</p:grpSpPr>'
    '{content}'
    '</p:spTree>'
    '</p:cSld>'
    '</p:sld>'
)


class PPTXBuilder:
    """PPTX 构建器 — 将 DrawingML 内容打包为 .pptx 文件

    Phase 3.4 新增能力:
    - 幻灯片切换效果  (p:transition)
    - 元素动画       (p:timing)
    - 页脚/页码/日期 (p:sp shapes)
    - 母版主题注入   (theme.xml 颜色+字体)
    """

    def __init__(self, slide_w_emu: int = SLIDE_W_169, slide_h_emu: int = SLIDE_H_169):
        self.slide_w = slide_w_emu
        self.slide_h = slide_h_emu
        self.slides: List[str] = []               # 每页的 spTree content XML
        self.slide_notes: List[str] = []           # 每页的备注文本
        self.media_files: List[Dict] = []          # 媒体文件
        # Phase 3.4: 新增动画/页脚配置
        self.slide_transitions: List[str] = []     # 每页的 p:transition XML
        self.slide_timings: List[str] = []         # 每页的 p:timing XML
        self.slide_footers: List[str] = []         # 每页的页脚装饰 XML
        # 全局主题配置
        self.theme_colors: Optional[Dict[str, str]] = None
        self.theme_font_major: str = "Arial"
        self.theme_font_minor: str = "Calibri"
        self.theme_font_ea: str = "Microsoft YaHei"

        self.title = "AI Generated Presentation"
        self._image_counter = 0

    def add_slide(
        self,
        svg_content: str,
        notes: str = "",
        animation_config: Optional[Dict] = None,
        footer_config: Optional[Dict] = None,
    ) -> int:
        """添加一页幻灯片

        Args:
            svg_content: SVG XML 或 DrawingML content XML
            notes: 演讲备注文本
            animation_config: 本页动画配置:
                {"transition": {"style":"fade","speed":"medium","direction":"left"},
                 "elements": [{"id":"2","type":"fly-in","trigger":"afterPrevious",...}],
                 "auto_advance_ms": 5000}
            footer_config: 本页页脚配置:
                {"footer_text":"公司名", "show_page_number":True,
                 "date_text":"2026-07-05", "font_name":"Arial",
                 "font_size_pt":10, "color_hex":"999999"}

        Returns:
            幻灯片索引
        """
        # 判断是 SVG XML 还是已有的 DrawingML content
        if svg_content.strip().startswith("<svg") or svg_content.strip().startswith('<?xml'):
            content_xml = convert_svg_to_slide_content(svg_content, 1280, 720)
        else:
            content_xml = svg_content

        self.slides.append(content_xml)
        self.slide_notes.append(notes)

        # Phase 3.4: 处理动画配置
        transition_xml = ""
        timing_xml = ""
        if animation_config:
            transition_xml, timing_xml = build_page_animation_set(animation_config)
        self.slide_transitions.append(transition_xml)
        self.slide_timings.append(timing_xml)

        # Phase 3.4: 处理页脚配置
        footer_xml = ""
        if footer_config:
            footer_xml = build_common_slide_data(
                footer_text=footer_config.get("footer_text", ""),
                show_page_number=footer_config.get("show_page_number", False),
                date_text=footer_config.get("date_text", ""),
                slide_width_emu=self.slide_w,
                slide_height_emu=self.slide_h,
                font_name=footer_config.get("font_name", "Arial"),
                font_size_pt=footer_config.get("font_size_pt", 10),
                color_hex=footer_config.get("color_hex", "999999"),
            )
        self.slide_footers.append(footer_xml)

        return len(self.slides) - 1

    def add_image(self, image_path: str, slide_index: int,
                  x: float, y: float, w: float, h: float) -> str:
        """为指定页面添加图片"""
        self._image_counter += 1
        img_data = {
            "path": image_path,
            "slide": slide_index,
            "x": x, "y": y, "w": w, "h": h,
            "rid": f"rId_img_{self._image_counter}",
        }
        self.media_files.append(img_data)
        return img_data["rid"]

    def build(self, output_path: str) -> str:
        """构建最终的 .pptx 文件

        Phase 3.4 流程:
          创建 python-pptx 基础 → 填充内容 → 注入切换/动画/页脚 → 注入主题

        Args:
            output_path: 输出文件路径

        Returns:
            输出文件路径
        """
        prs = Presentation()
        prs.slide_width = self.slide_w
        prs.slide_height = self.slide_h

        blank_layout = prs.slide_layouts[6]

        for idx, content_xml in enumerate(self.slides):
            slide = prs.slides.add_slide(blank_layout)
            # 1. 替换内容
            self._replace_slide_content(slide, content_xml, idx)
            # 2. 注入切换效果 (p:transition)
            self._apply_transition(slide, idx)
            # 3. 注入元素动画 (p:timing)
            self._apply_timing(slide, idx)
            # 4. 注入页脚/页码/日期
            self._apply_footer(slide, idx)

        # 5. 添加备注
        self._add_notes(prs)

        # 6. 添加媒体文件
        self._add_media(prs)

        # 7. 保存
        prs.save(output_path)

        # 8. 注入配色/字体主题
        if self.theme_colors:
            inject_theme(
                pptx_path=output_path,
                color_map=self.theme_colors,
                font_major=self.theme_font_major,
                font_minor=self.theme_font_minor,
                font_east_asia=self.theme_font_ea,
            )

        logger.info(f"PPTX 已保存: {output_path}")
        return output_path

    # ---- 内部方法 ----

    def _replace_slide_content(self, slide, content_xml: str, slide_idx: int):
        """替换幻灯片的内容 XML"""
        try:
            ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
            slide_elem = slide._element
            sp_tree = slide_elem.find(f"{{{ns}}}cSld/{{{ns}}}spTree")
            if sp_tree is None:
                return

            children_to_remove = []
            for child in sp_tree:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag not in ("nvGrpSpPr", "grpSpPr"):
                    children_to_remove.append(child)
            for child in children_to_remove:
                sp_tree.remove(child)

            if content_xml.strip():
                try:
                    new_content = etree.fromstring(
                        f'<root xmlns:p="{ns}" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                        f'{content_xml}</root>'
                    )
                    for child in new_content:
                        sp_tree.append(child)
                except etree.XMLSyntaxError as e:
                    logger.warning(f"幻灯片 {slide_idx + 1} 内容 XML 解析失败: {e}")
                    self._add_fallback_text(sp_tree, f"Slide {slide_idx + 1}")

        except Exception as e:
            logger.error(f"替换幻灯片 {slide_idx + 1} 内容出错: {e}")

    def _apply_transition(self, slide, idx: int):
        """为幻灯片注入切换效果 (p:transition)"""
        if idx >= len(self.slide_transitions):
            return
        trans_xml = self.slide_transitions[idx]
        if not trans_xml:
            return
        try:
            transition_elem = etree.fromstring(trans_xml)
            slide_elem = slide._element
            slide_elem.append(transition_elem)
        except Exception as e:
            logger.warning(f"幻灯片 {idx + 1} 切换效果注入失败: {e}")

    def _apply_timing(self, slide, idx: int):
        """为幻灯片注入元素动画 (p:timing)"""
        if idx >= len(self.slide_timings):
            return
        timing_xml = self.slide_timings[idx]
        if not timing_xml:
            return
        try:
            timing_elem = etree.fromstring(timing_xml)
            slide_elem = slide._element
            slide_elem.append(timing_elem)
        except Exception as e:
            logger.warning(f"幻灯片 {idx + 1} 动画注入失败: {e}")

    def _apply_footer(self, slide, idx: int):
        """为幻灯片注入页脚装饰（页脚/页码/日期 XML 片段插入 spTree）"""
        if idx >= len(self.slide_footers):
            return
        footer_xml = self.slide_footers[idx]
        if not footer_xml:
            return
        try:
            ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
            slide_elem = slide._element
            sp_tree = slide_elem.find(f"{{{ns}}}cSld/{{{ns}}}spTree")
            if sp_tree is None:
                return
            footer_elem = etree.fromstring(
                f'<root xmlns:p="{ns}" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                f'{footer_xml}</root>'
            )
            for child in footer_elem:
                sp_tree.append(child)
        except Exception as e:
            logger.warning(f"幻灯片 {idx + 1} 页脚注入失败: {e}")

    def _add_fallback_text(self, sp_tree, text: str):
        """添加回退文本元素"""
        fallback_xml = etree.fromstring(
            f'<p:sp xmlns:p="{NS["p"]}" xmlns:a="{NS["a"]}">'
            f'<p:nvSpPr><p:cNvPr id="1" name="fallback"/>'
            f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="914400" y="914400"/>'
            f'<a:ext cx="9144000" cy="685800"/></a:xfrm>'
            f'<a:prstGeom prst="rect"/></p:spPr>'
            f'<p:txBody><a:bodyPr/><a:p><a:r>'
            f'<a:rPr lang="en-US" sz="1800" b="1"/>'
            f'<a:t>{text}</a:t></a:r></a:p></p:txBody>'
            f'</p:sp>'
        )
        sp_tree.append(fallback_xml)

    def _add_notes(self, prs):
        """为幻灯片添加备注"""
        for idx, notes_text in enumerate(self.slide_notes):
            if not notes_text:
                continue
            if idx < len(prs.slides):
                notes_slide = prs.slides[idx].notes_slide
                tf = notes_slide.notes_text_frame
                tf.clear()
                tf.text = notes_text

    def _add_media(self, prs):
        """为幻灯片添加媒体文件"""
        for img in self.media_files:
            img_path = img["path"]
            slide_idx = img["slide"]
            if not os.path.exists(img_path):
                logger.warning(f"图片文件不存在: {img_path}")
                continue
            if slide_idx >= len(prs.slides):
                continue
            slide = prs.slides[slide_idx]
            x_emu = px_to_emu(img["x"])
            y_emu = px_to_emu(img["y"])
            w_emu = px_to_emu(img["w"])
            h_emu = px_to_emu(img["h"])
            try:
                slide.shapes.add_picture(img_path, x_emu, y_emu, w_emu, h_emu)
            except Exception as e:
                logger.warning(f"添加图片失败: {e}")

    # ---- 全局配置方法 ----

    def set_theme(
        self,
        colors: Optional[Dict[str, str]] = None,
        font_major: str = "Arial",
        font_minor: str = "Calibri",
        font_east_asia: str = "Microsoft YaHei",
    ):
        """设置全局主题配色和字体（注入 theme.xml）"""
        self.theme_colors = colors
        self.theme_font_major = font_major
        self.theme_font_minor = font_minor
        self.theme_font_ea = font_east_asia


# ---- 便利函数 ----

def build_pptx_from_svg_files(
    svg_files: List[str],
    output_path: str,
    slide_w_pt: float = 13.333,
    slide_h_pt: float = 7.5,
) -> str:
    """从多个 SVG 文件构建 PPTX"""
    builder = PPTXBuilder(
        slide_w_emu=int(slide_w_pt * 914400),
        slide_h_emu=int(slide_h_pt * 914400),
    )
    for svg_path in svg_files:
        with open(svg_path, "r", encoding="utf-8") as f:
            content = f.read()
        builder.add_slide(content)

    return builder.build(output_path)


def build_pptx_from_slide_contents(
    slide_contents: List[Dict[str, Any]],
    output_path: str,
    slide_w_pt: float = 13.333,
    slide_h_pt: float = 7.5,
) -> str:
    """从幻灯片内容（SVG + 备注 + 媒体 + 动画/页脚配置）构建 PPTX

    slide_contents 支持的新字段:
      - animation: Dict — 本页动画配置
      - footer: Dict — 本页页脚配置
    """
    builder = PPTXBuilder(
        slide_w_emu=int(slide_w_pt * 914400),
        slide_h_emu=int(slide_h_pt * 914400),
    )

    for idx, slide_data in enumerate(slide_contents):
        svg_content = slide_data.get("svg", "")
        notes = slide_data.get("notes", "")
        animation = slide_data.get("animation")
        footer = slide_data.get("footer")
        builder.add_slide(svg_content, notes, animation, footer)

        for img in slide_data.get("images", []):
            builder.add_image(
                img["path"], idx,
                img.get("x", 0), img.get("y", 0),
                img.get("w", 100), img.get("h", 100),
            )

    return builder.build(output_path)

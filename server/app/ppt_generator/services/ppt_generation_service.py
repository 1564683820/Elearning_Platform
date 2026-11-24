"""PPT 生成集成服务 — 桥接 ppt_generator 模块与现有 PPTService"""
import os
import json
import logging
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from app.core.paths import UPLOADS_DIR

from ..svg_to_pptx.pptx_builder import PPTXBuilder
from ..svg_to_pptx.drawingml_converter import convert_svg_to_slide_content
from ..quality.svg_quality_checker import SVGQualityChecker
from ..svg_finalize.finalize_svg import SVGFinalizer
from ..source_to_md.pdf_to_md import PDFConverter
from ..source_to_md.doc_to_md import DOCXConverter
from ..config import DEFAULT_CANVAS, CANVAS_FORMATS
from ..analysis.content_analyzer import ContentAnalyzer

logger = logging.getLogger(__name__)

# 跨平台字体栈 — 优先使用系统美观字体，后降级
FONT_STACK = '"Microsoft YaHei", "PingFang SC", "Noto Sans SC", "HarmonyOS Sans", "Source Han Sans SC", sans-serif'
FONT_STACK_MONO = '"Cascadia Code", "Fira Code", "Consolas", monospace'
# 最大文本行长度保底（避免超长文本溢出卡片）
MAX_TEXT_LENGTH = 120
# 卡片阴影滤镜 ID（用于对话气泡、语法卡片等）
SHADOW_FILTER_ID = 'slide-shadow'

# ========== 全局字号层级体系（按视觉风格可被覆写） ==========
FONT_SCALE = {
    "cover": 48,       # 封面主标题
    "large": 36,       # 章节标题 / 大标题
    "h1": 28,          # 一级标题（默认标题）
    "h2": 22,          # 二级标题（副标题）
    "h3": 18,          # 三级标题（卡片标题）
    "body": 16,        # 正文
    "body_sm": 15,     # 小正文
    "small": 14,       # 辅助文字
    "note": 12,        # 注释 / 页脚
    "code": 13,        # 代码 / 音标
    "icon": 11,        # 图标编号文字
    "meta": 10,        # 极小元信息
}

# 字号角色别名（将通用层级映射到各页面类型的语义角色）
FONT_ROLE_ALIAS = {
    "title_slide":     {"main_title": "cover", "subtitle": "h2", "grade": "small"},
    "objective":       {"header": "h1", "item": "body"},
    "vocabulary":      {"header": "h1", "word": "body_sm", "phonetic": "small", "translation": "small", "example": "small"},
    "dialogue":        {"header": "h1", "speaker": "body_sm", "text": "body", "translation": "small"},
    "grammar":         {"header": "h1", "rule": "body_sm", "example": "small", "explanation": "small"},
    "practice":        {"header": "h1", "stem": "body", "option": "small", "explanation": "small"},
    "interactive":     {"header": "h1", "description": "body", "step": "body_sm"},
    "ai_interaction":  {"header": "h1", "prompt": "body", "question": "body_sm", "hint": "small"},
    "summary":         {"header": "h1", "point": "body_sm", "homework": "body_sm"},
    "catalog":         {"header": "h1", "section": "body"},
    "listening":       {"header": "h1", "audio_text": "body", "question": "body_sm"},
    "speaking":        {"header": "h1", "text": "body", "tips": "small"},
}


# ==================== 视觉风格引擎 ====================

DEFAULT_STYLE = "warm-simple"
STYLE_LIST = [
    "swiss-minimal", "soft-rounded", "editorial", "dark-tech",
    "sketch-notes", "chalkboard", "glassmorphism", "paper-cut", "warm-simple",
]


class VisualStyleEngine:
    """视觉风格引擎 — 根据风格规范生成差异化 SVG 装饰

    管理 9 种视觉风格的形状语言、排版性格、装饰 DNA、留白间距的配置。
    """

    # 风格配置注册表 — 完整 9 种风格
    STYLE_REGISTRY: Dict[str, Dict] = {
        "swiss-minimal": {
            "shape": {"card_radius": 0, "card_border": 1, "shadow": "none",
                       "marker_radius": 2, "marker_width": 4},
            "decoration": {"top_bar": False, "title_marker": True,
                            "bg_decoration": "none", "left_accent": True,
                            "separator": "solid", "show_page_number": True},
            "typography": {
                "title_font": '"Montserrat","SCDream","Microsoft YaHei",sans-serif',
                "body_font": '"Inter","SCDream","Microsoft YaHei",sans-serif',
                "title_weight": "bold", "body_weight": "normal",
                "title_size": 28, "body_size": 15, "note_size": 12,
            },
            "spacing": {"margin": 60, "gap": 14, "card_gap": 12, "line_height": 1.6},
        },
        "soft-rounded": {
            "shape": {"card_radius": 12, "card_border": 0, "shadow": "light",
                       "marker_radius": 13, "marker_width": 6},
            "decoration": {"top_bar": True, "title_marker": True,
                            "bg_decoration": "circle", "left_accent": True,
                            "separator": "none", "show_page_number": False},
            "typography": {
                "title_font": '"Microsoft YaHei","PingFang SC",sans-serif',
                "body_font": '"Microsoft YaHei","PingFang SC",sans-serif',
                "title_weight": "bold", "body_weight": "normal",
                "title_size": 30, "body_size": 16, "note_size": 13,
            },
            "spacing": {"margin": 50, "gap": 12, "card_gap": 10, "line_height": 1.7},
        },
        "editorial": {
            "shape": {"card_radius": 6, "card_border": 1, "shadow": "light",
                       "marker_radius": 4, "marker_width": 4},
            "decoration": {"top_bar": True, "title_marker": True,
                            "bg_decoration": "grid", "left_accent": True,
                            "separator": "dotted", "show_page_number": True},
            "typography": {
                "title_font": '"Georgia","Source Han Serif SC","Microsoft YaHei",serif',
                "body_font": '"Inter","SCDream","Microsoft YaHei",sans-serif',
                "title_weight": "bold", "body_weight": "normal",
                "title_size": 26, "body_size": 15, "note_size": 11,
            },
            "spacing": {"margin": 60, "gap": 16, "card_gap": 14, "line_height": 1.8},
        },
        "dark-tech": {
            "shape": {"card_radius": 8, "card_border": 1, "shadow": "medium",
                       "marker_radius": 8, "marker_width": 5},
            "decoration": {"top_bar": True, "title_marker": True,
                            "bg_decoration": "grid", "left_accent": True,
                            "separator": "glow-dashed", "show_page_number": False},
            "typography": {
                "title_font": '"Montserrat","SCDream","Microsoft YaHei",sans-serif',
                "body_font": '"Inter","Microsoft YaHei","PingFang SC",sans-serif',
                "title_weight": "bold", "body_weight": "300",
                "title_size": 26, "body_size": 14, "note_size": 11,
            },
            "spacing": {"margin": 50, "gap": 10, "card_gap": 8, "line_height": 1.5},
        },
        "sketch-notes": {
            "shape": {"card_radius": 0, "card_border": 0, "shadow": "none",
                       "marker_radius": 12, "marker_width": 5},
            "decoration": {"top_bar": False, "title_marker": True,
                            "bg_decoration": "grid-paper", "left_accent": True,
                            "separator": "wavy", "show_page_number": False},
            "typography": {
                "title_font": '"Comic Sans MS","Ma Shan Zheng","Microsoft YaHei",cursive',
                "body_font": '"Caveat","Microsoft YaHei","PingFang SC",sans-serif',
                "title_weight": "bold", "body_weight": "normal",
                "title_size": 34, "body_size": 17, "note_size": 13,
            },
            "spacing": {"margin": 55, "gap": 16, "card_gap": 14, "line_height": 1.8},
        },
        "chalkboard": {
            "shape": {"card_radius": 6, "card_border": 1, "shadow": "none",
                       "marker_radius": 6, "marker_width": 4},
            "decoration": {"top_bar": False, "title_marker": True,
                            "bg_decoration": "none", "left_accent": True,
                            "separator": "dashed", "show_page_number": False},
            "typography": {
                "title_font": '"Chalkboard SE","Microsoft YaHei","PingFang SC",sans-serif',
                "body_font": '"Chalkboard SE","Microsoft YaHei","PingFang SC",sans-serif',
                "title_weight": "bold", "body_weight": "500",
                "title_size": 30, "body_size": 16, "note_size": 13,
            },
            "spacing": {"margin": 55, "gap": 14, "card_gap": 12, "line_height": 1.7},
        },
        "glassmorphism": {
            "shape": {"card_radius": 10, "card_border": 1, "shadow": "medium",
                       "marker_radius": 10, "marker_width": 5},
            "decoration": {"top_bar": False, "title_marker": True,
                            "bg_decoration": "glow", "left_accent": True,
                            "separator": "glass", "show_page_number": False},
            "typography": {
                "title_font": '"Inter","SCDream","Microsoft YaHei",sans-serif',
                "body_font": '"Inter","SCDream","Microsoft YaHei",sans-serif',
                "title_weight": "bold", "body_weight": "normal",
                "title_size": 28, "body_size": 15, "note_size": 11,
            },
            "spacing": {"margin": 55, "gap": 12, "card_gap": 10, "line_height": 1.6},
        },
        "paper-cut": {
            "shape": {"card_radius": 4, "card_border": 0, "shadow": "medium",
                       "marker_radius": 4, "marker_width": 6},
            "decoration": {"top_bar": True, "title_marker": True,
                            "bg_decoration": "pattern", "left_accent": True,
                            "separator": "dotted", "show_page_number": True},
            "typography": {
                "title_font": '"Noto Serif SC","Source Han Serif SC","SimSun",serif',
                "body_font": '"Microsoft YaHei","PingFang SC",sans-serif',
                "title_weight": "bold", "body_weight": "normal",
                "title_size": 28, "body_size": 15, "note_size": 12,
            },
            "spacing": {"margin": 55, "gap": 14, "card_gap": 12, "line_height": 1.7},
        },
        "warm-simple": {
            "shape": {"card_radius": 8, "card_border": 1, "shadow": "light",
                       "marker_radius": 6, "marker_width": 6},
            "decoration": {"top_bar": True, "title_marker": True,
                            "bg_decoration": "circle", "left_accent": True,
                            "separator": "solid", "show_page_number": False},
            "typography": {
                "title_font": '"SCDream","Microsoft YaHei","PingFang SC",sans-serif',
                "body_font": '"Microsoft YaHei","PingFang SC",sans-serif',
                "title_weight": "bold", "body_weight": "normal",
                "title_size": 28, "body_size": 15, "note_size": 12,
            },
            "spacing": {"margin": 55, "gap": 13, "card_gap": 11, "line_height": 1.6},
        },
    }

    # 页面类型到推荐风格的映射
    STYLE_SELECTION: Dict[str, str] = {
        "catalog": "swiss-minimal",
        "vocabulary": "soft-rounded",
        "dialogue": "soft-rounded",
        "grammar": "swiss-minimal",
        "practice": "editorial",
        "title": "warm-simple",
        "summary": "editorial",
        "objective": "swiss-minimal",
        "interactive": "dark-tech",
        "ai_interaction": "dark-tech",
        "listening": "soft-rounded",
        "speaking": "soft-rounded",
    }

    @classmethod
    def get_style_config(cls, style_name: str) -> Dict:
        """获取风格配置（不存在时返回默认风格）"""
        return cls.STYLE_REGISTRY.get(style_name, cls.STYLE_REGISTRY[DEFAULT_STYLE])

    @classmethod
    def recommend_style(cls, slide_type: str) -> str:
        """根据页面类型推荐视觉风格"""
        return cls.STYLE_SELECTION.get(slide_type, DEFAULT_STYLE)

    @classmethod
    def get_font_stack(cls, style_name: str, font_role: str = "body") -> str:
        """获取风格对应的字体栈

        Args:
            style_name: 风格名称
            font_role: "title" | "body" | "mono"
        """
        style = cls.get_style_config(style_name)
        typo = style["typography"]
        if font_role == "title":
            return typo["title_font"]
        elif font_role == "mono":
            return FONT_STACK_MONO
        return typo["body_font"]

    @classmethod
    def get_title_size(cls, style_name: str) -> int:
        """获取风格对应的标题字号"""
        return cls.get_style_config(style_name)["typography"]["title_size"]

    @classmethod
    def get_body_size(cls, style_name: str) -> int:
        """获取风格对应的正文字号"""
        return cls.get_style_config(style_name)["typography"]["body_size"]

    @classmethod
    def get_margin(cls, style_name: str) -> int:
        """获取风格对应的页面边距"""
        return cls.get_style_config(style_name)["spacing"]["margin"]

    @classmethod
    def get_role_font_size(cls, style_name: str, role: str = "body", page_type: str = "") -> int:
        """获取语义角色的字号（先查 page_type 别名映射，再查 FONT_SCALE）

        Args:
            style_name: 视觉风格名称
            role: 语义角色名（如 header / item / word / stem）
            page_type: 页面类型（用于角色别名映射）

        Returns:
            字号 px 值
        """
        # 查页面类型别名映射
        resolved_role = role
        if page_type:
            alias_map = FONT_ROLE_ALIAS.get(page_type, {})
            resolved_role = alias_map.get(role, role)
        # 查 FONT_SCALE
        size = FONT_SCALE.get(resolved_role)
        if size:
            return size
        # 兜底 fallback
        try:
            return int(resolved_role)
        except (ValueError, TypeError):
            return 16

    @classmethod
    def get_role_font_family(cls, style_name: str, role: str = "body", page_type: str = "") -> str:
        """获取语义角色的字体栈（title 用标题字体，其余用正文字体）

        Args:
            style_name: 视觉风格名称
            role: 语义角色名
            page_type: 页面类型（暂未使用，为扩展预留）

        Returns:
            字体栈字符串
        """
        if role in ("main_title", "header", "h1", "cover"):
            return cls.get_font_stack(style_name, "title")
        return cls.get_font_stack(style_name, "body")

    @classmethod
    def get_gap(cls, style_name: str, gap_adjust: int = 0) -> int:
        """获取风格对应的元素间距"""
        return cls.get_style_config(style_name)["spacing"]["gap"] + gap_adjust

    @classmethod
    def get_card_gap(cls, style_name: str) -> int:
        """获取风格对应的卡片间距"""
        return cls.get_style_config(style_name)["spacing"]["card_gap"]

    @classmethod
    def get_line_height(cls, style_name: str) -> float:
        """获取风格对应的行高"""
        return cls.get_style_config(style_name)["spacing"]["line_height"]

    @classmethod
    def get_card_radius(cls, style_name: str) -> int:
        """获取风格对应的卡片圆角"""
        return cls.get_style_config(style_name)["shape"]["card_radius"]

    @classmethod
    def get_marker_radius(cls, style_name: str) -> int:
        """获取风格对应的标记圆角"""
        return cls.get_style_config(style_name)["shape"]["marker_radius"]

    @classmethod
    def apply_style_decorations(
        cls,
        svg_parts: List[str],
        style_name: str,
        canvas_w: int,
        canvas_h: int,
        colors: Dict,
    ) -> List[str]:
        """根据风格规范添加差异化装饰元素

        Args:
            svg_parts: 现有的 SVG 片段列表（将在适当位置插入装饰）
            style_name: 视觉风格名称
            canvas_w: 画布宽度
            canvas_h: 画布高度
            colors: 主题色字典

        Returns:
            添加装饰后的 SVG 片段列表
        """
        style = cls.get_style_config(style_name)
        deco = style["decoration"]
        shape = style["shape"]

        # === 背景装饰 ===
        bg_type = deco["bg_decoration"]
        if bg_type == "circle":
            # 半透明装饰圆（soft-rounded / warm-simple）
            svg_parts.append(
                f'<circle cx="{canvas_w - 100}" cy="{canvas_h - 100}" r="150" '
                f'fill="{colors["primary"]}" opacity="0.03"/>'
            )
        elif bg_type == "grid":
            # 极淡网格线（editorial / dark-tech）
            svg_parts.append(
                f'<line x1="0" y1="{canvas_h // 2}" x2="{canvas_w}" y2="{canvas_h // 2}" '
                f'stroke="{colors["primary"]}" stroke-width="0.5" opacity="0.02"/>'
                f'<line x1="{canvas_w // 2}" y1="0" x2="{canvas_w // 2}" y2="{canvas_h}" '
                f'stroke="{colors["primary"]}" stroke-width="0.5" opacity="0.02"/>'
            )
        elif bg_type == "grid-paper":
            # 模拟方格纸背景（sketch-notes）
            for gx in range(0, canvas_w, 40):
                svg_parts.append(
                    f'<line x1="{gx}" y1="0" x2="{gx}" y2="{canvas_h}" '
                    f'stroke="{colors["text"]}" stroke-width="0.5" opacity="0.04"/>'
                )
            for gy in range(0, canvas_h, 40):
                svg_parts.append(
                    f'<line x1="0" y1="{gy}" x2="{canvas_w}" y2="{gy}" '
                    f'stroke="{colors["text"]}" stroke-width="0.5" opacity="0.04"/>'
                )
        elif bg_type == "glow":
            # 玻璃拟态光晕背景（glassmorphism）
            svg_parts.append(
                f'<circle cx="80" cy="120" r="180" fill="{colors["primary"]}" opacity="0.12" '
                f'filter="url(#slide-shadow)"/>'
                f'<circle cx="{canvas_w - 80}" cy="{canvas_h - 100}" r="140" '
                f'fill="{colors["secondary"]}" opacity="0.10"/>'
            )
        elif bg_type == "pattern":
            # 剪纸风格纹样（paper-cut）
            svg_parts.append(
                f'<rect x="0" y="0" width="15" height="15" fill="{colors["primary"]}" opacity="0.03" '
                f'stroke="{colors["primary"]}" stroke-width="0.5" opacity="0.05" rx="1"/>'
            )

        # === 顶部装饰条 ===
        if deco["top_bar"]:
            if style_name == "dark-tech":
                # 发光渐变条
                svg_parts.append(
                    f'<defs>'
                    f'<linearGradient id="top-bar-grad" x1="0" y1="0" x2="1" y2="0">'
                    f'<stop offset="0%" stop-color="{colors["primary"]}"/>'
                    f'<stop offset="100%" stop-color="{colors["secondary"]}"/>'
                    f'</linearGradient>'
                    f'</defs>'
                    f'<rect x="0" y="0" width="{canvas_w}" height="5" fill="url(#top-bar-grad)"/>'
                )
            elif style_name == "paper-cut":
                # 传统纹样风格装饰条（重复图案效果）
                svg_parts.append(
                    f'<rect x="0" y="0" width="{canvas_w}" height="5" fill="{colors["primary"]}"/>'
                    f'<rect x="0" y="5" width="{canvas_w}" height="2" fill="{colors["primary"]}" opacity="0.3"/>'
                    f'<rect x="0" y="7" width="{canvas_w}" height="1" fill="{colors["primary"]}" opacity="0.15"/>'
                )
            elif style_name in ("editorial",):
                # 杂志风格极细线
                svg_parts.append(
                    f'<line x1="0" y1="0" x2="{canvas_w}" y2="0" '
                    f'stroke="{colors["primary"]}" stroke-width="2" opacity="0.5"/>'
                )
            else:
                # 默认：5px 主色条
                svg_parts.append(
                    f'<rect x="0" y="0" width="{canvas_w}" height="5" fill="{colors["primary"]}"/>'
                )

        # === 左侧装饰线（颜色/风格可区分） ===
        if deco["left_accent"]:
            if style_name == "dark-tech":
                # 发光装饰线
                svg_parts.append(
                    f'<defs>'
                    f'<linearGradient id="left-accent-grad" x1="0" y1="0" x2="1" y2="0">'
                    f'<stop offset="0%" stop-color="{colors["primary"]}"/>'
                    f'<stop offset="100%" stop-color="{colors["primary"]}" stop-opacity="0"/>'
                    f'</linearGradient>'
                    f'</defs>'
                    f'<rect x="0" y="0" width="4" height="{canvas_h}" '
                    f'fill="url(#left-accent-grad)" opacity="0.15"/>'
                )
            else:
                # 默认浅色装饰线
                svg_parts.append(
                    f'<rect x="0" y="0" width="3" height="{canvas_h}" '
                    f'fill="{colors["primary"]}" opacity="0.08"/>'
                )

        # === 阴影滤镜（根据风格阴影层级） ===
        shadow = shape["shadow"]
        if shadow == "light":
            svg_parts.append(
                f'<defs>'
                f'<filter id="{SHADOW_FILTER_ID}" x="-5%" y="-5%" width="115%" height="115%">'
                f'<feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000" flood-opacity="0.06"/>'
                f'</filter>'
                f'</defs>'
            )
        elif shadow == "medium":
            svg_parts.append(
                f'<defs>'
                f'<filter id="{SHADOW_FILTER_ID}" x="-8%" y="-8%" width="120%" height="120%">'
                f'<feDropShadow dx="0" dy="4" stdDeviation="8" flood-color="#000" flood-opacity="0.15"/>'
                f'</filter>'
                f'</defs>'
            )
        # "none" — 不添加阴影滤镜定义

        return svg_parts


class PPTGenerationService:
    """PPT 生成集成服务

    参考 ppt-master (https://github.com/hugohe3/ppt-master) 架构：
      pages_json -> SVG 渲染（视觉匹配 HTML）-> 质量检查 -> 后处理 -> DrawingML -> PPTX
    """

    # 主题色映射（与 HTML 主题 CSS 变量对应）
    THEME_COLOR_MAP = {
        "classic":  {"primary": "#2d7d46", "secondary": "#7E3AF2", "background": "#FFFFFF",
                     "surface": "#f5faf5", "text": "#1a1a2e", "text_secondary": "#546e7a",
                     "accent": "#ff8f00", "border": "#c8e6c9"},
        "modern":   {"primary": "#1565c0", "secondary": "#e3f2fd", "background": "#FFFFFF",
                     "surface": "#f5f9ff", "text": "#1a1a2e", "text_secondary": "#546e7a",
                     "accent": "#f57c00", "border": "#bbdefb"},
        "vibrant":  {"primary": "#7b1fa2", "secondary": "#f3e5f5", "background": "#FFFFFF",
                     "surface": "#faf5fb", "text": "#1a1a2e", "text_secondary": "#6a1b9a",
                     "accent": "#e65100", "border": "#ce93d8"},
        "minimal":  {"primary": "#37474f", "secondary": "#eceff1", "background": "#FAFAFA",
                     "surface": "#f5f5f5", "text": "#212121", "text_secondary": "#757575",
                     "accent": "#ff6f00", "border": "#e0e0e0"},
        "ocean":    {"primary": "#00695c", "secondary": "#e0f2f1", "background": "#FFFFFF",
                     "surface": "#f5fafa", "text": "#1a1a2e", "text_secondary": "#00796b",
                     "accent": "#ff6f00", "border": "#b2dfdb"},
        "warm":     {"primary": "#e65100", "secondary": "#fbe9e7", "background": "#FFFFFF",
                     "surface": "#fff8f5", "text": "#1a1a2e", "text_secondary": "#bf360c",
                     "accent": "#1565c0", "border": "#ffccbc"},
        "dark":     {"primary": "#6366F1", "secondary": "#1E293B", "background": "#0F172A",
                     "surface": "#1E293B", "text": "#F8FAFC", "text_secondary": "#94A3B8",
                     "accent": "#F59E0B", "border": "#334155"},
    }

    @staticmethod
    def resolve_theme_colors(theme_name: str) -> Dict:
        """根据主题名解析配色方案（供外部调用）"""
        return PPTGenerationService.THEME_COLOR_MAP.get(
            theme_name, PPTGenerationService.THEME_COLOR_MAP["classic"])

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or self._default_output_dir()
        self._current_style_name: str = DEFAULT_STYLE

    def set_style(self, style_name: str):
        """设置当前视觉风格"""
        if style_name in STYLE_LIST:
            self._current_style_name = style_name
        else:
            logger.warning(f"未知风格: {style_name}，使用默认: {DEFAULT_STYLE}")
            self._current_style_name = DEFAULT_STYLE

    def _default_output_dir(self) -> str:
        """默认输出目录"""
        output = UPLOADS_DIR / "ppt_export"
        output.mkdir(parents=True, exist_ok=True)
        return str(output)

    def _get_page_style(self, page: Dict, style_name: Optional[str] = None) -> str:
        """获取页面视觉风格（页面级可按类型推荐）"""
        if style_name:
            return style_name
        slide_type = page.get("type", "content")
        return VisualStyleEngine.recommend_style(slide_type)

    async def generate_from_pages_json(
        self,
        pages_json: List[Dict],
        title: str = "AI 课件",
        theme_colors: Optional[Dict] = None,
        canvas_format: str = "ppt169",
        theme_name: Optional[str] = None,
        visual_style: Optional[str] = None,
        global_animation: Optional[Dict] = None,
        global_footer: Optional[Dict] = None,
    ) -> Dict:
        """从现有 pages_json 生成原生 PPTX

        参考 ppt-master (https://github.com/hugohe3/ppt-master) 架构：
          pages_json -> SVG 渲染（视觉匹配 HTML）-> 质量检查 -> 后处理 -> DrawingML -> PPTX

        Args:
            pages_json: PPT 页面数据列表（现有格式）
            title: PPT 标题
            theme_colors: 主题色（默认使用专业配色）
            canvas_format: 画布格式（默认 16:9）
            theme_name: 主题名称（用于解析主题色，如 classic/modern/vibrant 等）
            visual_style: 视觉风格名称（swiss-minimal/soft-rounded/editorial/dark-tech/...）
            global_animation: 全局动画配置（Override 所有页面的 animation 字段）
            global_footer: 全局页脚配置（全页面统一页脚/页码/日期）

        Returns:
            包含导出信息的 dict
        """
        canvas = CANVAS_FORMATS.get(canvas_format, CANVAS_FORMATS[DEFAULT_CANVAS])
        colors = (theme_colors or
                  (self.resolve_theme_colors(theme_name) if theme_name else None) or
                  self._default_colors())
        output_path = os.path.join(
            self.output_dir,
            f"ai_ppt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx",
        )

        # 设置全局风格（如指定）
        if visual_style:
            self.set_style(visual_style)

        # ===== Phase 3.1: 内容分析 =====
        content_analyzer = ContentAnalyzer()
        content_profile = content_analyzer.analyze(pages_json)
        logger.info(f"[内容分析] {content_profile.describe()}")

        # 如未指定风格，自动推荐
        if not visual_style:
            auto_style = content_analyzer.recommend_style(content_profile)
            logger.info(f"[风格推荐] 自动选择: {auto_style}")
            self.set_style(auto_style)

        # 如未指定布局，记录推荐策略（各页面渲染时使用 layous 字段）
        layout_strategy = content_analyzer.recommend_layout_strategy(content_profile)
        if layout_strategy:
            logger.info(f"[布局推荐] {layout_strategy}")

        builder = PPTXBuilder()

        # Phase 3.4: 从 theme_colors 设置母版主题配色
        if theme_colors or theme_name:
            inject_map = theme_colors or self._default_colors()
            builder.set_theme(colors=inject_map)

        for idx, page in enumerate(pages_json):
            # 确定本页风格（全局风格 > 按类型自动推荐）
            page_style = visual_style or self._get_page_style(page)

            # 应用布局策略（如页面类型在推荐中且未手动指定 layout）
            page_type = page.get("type", "content")
            if page_type in layout_strategy and not page.get("layout"):
                page["layout"] = layout_strategy[page_type]

            # 1. 根据页面数据生成 SVG
            svg_content = self._page_to_svg(page, idx, canvas, colors, page_style)

            # 2. 质量检查
            checker = SVGQualityChecker(
                viewbox_w=float(canvas["viewBox"].split()[2]),
                viewbox_h=float(canvas["viewBox"].split()[3]),
            )
            passed, issues = checker.check_and_report(svg_content)
            if not passed:
                logger.warning(f"第 {idx + 1} 页 SVG 检查未通过，使用回退渲染")
                svg_content = self._fallback_slide(page, idx, canvas, colors)

            # 3. SVG 后处理
            finalizer = SVGFinalizer()
            svg_content = finalizer.process(svg_content)

            # 4. 提取备注和动画/页脚配置
            notes = page.get("notes", "") or page.get("content", {}).get("notes", "")

            # Phase 3.4: 页面级动画/页脚配置（global_animation 优先于 page.animation）
            page_animation = global_animation or page.get("animation")
            page_footer = global_footer or page.get("footer")

            # 5. 添加到构建器（含动画/页脚）
            builder.add_slide(svg_content, notes, page_animation, page_footer)

        # 6. 构建最终 PPTX（含切换/动画/页脚/主题注入）
        output_path = builder.build(output_path)

        # 7. 获取文件信息
        file_size = os.path.getsize(output_path)
        file_name = os.path.basename(output_path)

        return {
            "path": output_path,
            "file_name": file_name,
            "file_url": f"/uploads/ppt_export/{file_name}",
            "slide_count": len(pages_json),
            "file_size": file_size,
            "content_profile": content_profile.to_dict(),
            "recommended_style": self._current_style_name,
            "layout_strategy": layout_strategy,
        }

    def _page_to_svg(
        self, page: Dict, idx: int, canvas: Dict, colors: Dict,
        style_name: Optional[str] = None,
    ) -> str:
        """将单页页面数据转换为 SVG — 视觉匹配 HTML 渲染器

        Args:
            page: 页面数据
            idx: 页面索引
            canvas: 画布格式
            colors: 主题色
            style_name: 视觉风格名称（None 则自动推荐）
        """
        slide_type = page.get("type", "content")
        content = page.get("content", {})
        title = page.get("title", "")

        # 解析风格
        if not style_name:
            style_name = VisualStyleEngine.recommend_style(slide_type)
        self._current_style_name = style_name
        style_config = VisualStyleEngine.get_style_config(style_name)
        title_font = style_config["typography"]["title_font"]
        title_size = style_config["typography"]["title_size"]

        canvas_w = int(canvas["viewBox"].split()[2])
        canvas_h = int(canvas["viewBox"].split()[3])
        margin = VisualStyleEngine.get_margin(style_name)
        content_w = canvas_w - margin * 2

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{canvas["viewBox"]}" '
            f'width="{canvas_w}" height="{canvas_h}">',
            # 背景
            f'<rect width="{canvas_w}" height="{canvas_h}" fill="{colors["background"]}"/>',
        ]

        # 风格化装饰（顶部条、左侧装饰线、背景装饰、阴影滤镜）
        svg_parts = VisualStyleEngine.apply_style_decorations(
            svg_parts, style_name, canvas_w, canvas_h, colors
        )

        # 标题区域 — 左侧带色标的标题栏（匹配 HTML 的 slide-header style="left-border"）
        content_y = 90
        if title and slide_type not in ("title", "listening", "speaking"):
            marker_r = style_config["shape"]["marker_radius"]
            svg_parts.append(
                f'<rect x="{margin}" y="{content_y - 28}" width="{style_config["shape"]["marker_width"]}" height="28" '
                f'rx="{marker_r}" fill="{colors["primary"]}"/>'
            )
            svg_parts.append(
                f'<text x="{margin + 16}" y="{content_y}" font-size="{title_size}" '
                f'font-family=\'{title_font}\' font-weight="bold" fill="{colors["text"]}">'
                f'{self._escape_svg_text(title)}'
                f'</text>'
            )
            content_y += 56
            # 标题下方分隔线（风格可定制）
            sep = style_config["decoration"]["separator"]
            if sep == "dotted":
                svg_parts.append(
                    f'<line x1="{margin}" y1="{content_y - 8}" x2="{margin + content_w}" '
                    f'y2="{content_y - 8}" stroke="{colors["border"]}" stroke-width="1" '
                    f'stroke-dasharray="2,4" opacity="0.4"/>'
                )
            elif sep == "dashed":
                svg_parts.append(
                    f'<line x1="{margin}" y1="{content_y - 8}" x2="{margin + content_w}" '
                    f'y2="{content_y - 8}" stroke="{colors["primary"]}" stroke-width="1" '
                    f'stroke-dasharray="6,4" opacity="0.3"/>'
                )
            elif sep != "none":
                # 默认实线
                svg_parts.append(
                    f'<line x1="{margin}" y1="{content_y - 8}" x2="{margin + content_w}" '
                    f'y2="{content_y - 8}" stroke="{colors["border"]}" stroke-width="1" opacity="0.5"/>'
                )
            content_y += 8

        # 根据 slide_type 渲染内容 — 传入完整 page 以获取更多字段
        svg_parts.extend(self._render_content(slide_type, content, colors, margin, content_y, content_w, canvas_h, canvas_w, page))

        svg_parts.append("</svg>")
        return "\n".join(svg_parts)

    # 布局变体名称常量
    LAYOUT_GRID = "grid"
    LAYOUT_WATERFALL = "waterfall"
    LAYOUT_CARDS = "cards"
    LAYOUT_CHAT = "chat"
    LAYOUT_STAGE = "stage"
    LAYOUT_LIST = "list"
    LAYOUT_TABLE = "table"
    LAYOUT_COMPACT = "compact"
    LAYOUT_FULL = "full"

    # 页间节奏序列 — 避免连续页面使用相同布局
    RHYTHM_SEQUENCE = [
        "anchor", "dense", "breathing", "dense", "breathing",
        "anchor", "dense", "breathing", "dense", "breathing",
    ]

    LAYOUT_VARIANTS = {
        "catalog": [LAYOUT_LIST, LAYOUT_FULL],
        "vocabulary": [LAYOUT_GRID, LAYOUT_WATERFALL, LAYOUT_CARDS],
        "dialogue": [LAYOUT_LIST, LAYOUT_CHAT, LAYOUT_STAGE],
        "objective": [LAYOUT_GRID, LAYOUT_LIST],
        "grammar": [LAYOUT_CARDS, LAYOUT_TABLE],
        "summary": [LAYOUT_LIST, LAYOUT_COMPACT, LAYOUT_FULL],
        "practice": [LAYOUT_LIST, LAYOUT_CARDS],
        "interactive": [LAYOUT_LIST, LAYOUT_CARDS],
        "ai_interaction": [LAYOUT_GRID, LAYOUT_CARDS],
        "listening": [LAYOUT_LIST, LAYOUT_FULL],
        "speaking": [LAYOUT_LIST, LAYOUT_FULL],
    }

    def _get_rhythm(self, idx: int) -> str:
        """根据页面索引获取节奏类型"""
        return self.RHYTHM_SEQUENCE[idx % len(self.RHYTHM_SEQUENCE)]

    def _get_layout_variant(self, slide_type: str, rhythm: str, prev_variants: List[str]) -> str:
        """为页面类型选择合适的布局变体，避免连续重复

        Args:
            slide_type: 页面类型
            rhythm: 页面节奏
            prev_variants: 前几页使用的布局变体列表
        """
        variants = self.LAYOUT_VARIANTS.get(slide_type, ["default"])
        if len(variants) <= 1:
            return variants[0]

        # 排除前 2 页使用的变体
        excluded = set(prev_variants[-2:])
        candidates = [v for v in variants if v not in excluded]
        if not candidates:
            candidates = variants

        # 根据节奏选择：anchor 倾向 grid/full，breathing 倾向 cards/waterfall
        if rhythm == "anchor":
            ordered = [v for v in candidates if v in ("grid", "full", "list")]
            if ordered:
                return ordered[0]
        elif rhythm == "breathing":
            ordered = [v for v in candidates if v in ("cards", "waterfall", "chat")]
            if ordered:
                return ordered[0]
        return candidates[0]

    def _render_content(
        self, slide_type: str, content: Dict, colors: Dict,
        margin: int, start_y: int, content_w: int, canvas_h: int,
        canvas_w: int = 1280, page: Optional[Dict] = None,
        page_idx: int = 0, prev_layouts: Optional[List[str]] = None,
    ) -> List[str]:
        """根据页面类型渲染内容 — 视觉匹配 HTML 渲染器，支持 11 种类型

        Args:
            slide_type: 页面类型
            content: 页面内容数据
            colors: 主题色
            margin: 页面边距
            start_y: 起始 y 坐标
            content_w: 内容宽度
            canvas_h: 画布高度
            canvas_w: 画布宽度
            page: 完整页面数据
            page_idx: 页面索引（用于节奏和布局选择）
            prev_layouts: 前几页使用的布局变体列表
        """
        parts = []
        y = start_y
        page = page or {}
        prev_layouts = prev_layouts or []

        # === 页间节奏控制 ===
        rhythm = self._get_rhythm(page_idx)

        # 根据节奏调整间距
        rhythm_margin_adjust = 0
        rhythm_gap_adjust = 0
        if rhythm == "dense":
            rhythm_margin_adjust = -5
            rhythm_gap_adjust = -3
        elif rhythm == "breathing":
            rhythm_margin_adjust = 8
            rhythm_gap_adjust = 4

        # 选择布局变体
        layout_variant = self._get_layout_variant(slide_type, rhythm, prev_layouts)

        if slide_type == "title":
            parts.extend(self._render_title_slide(page, colors, canvas_h, canvas_w))
        elif slide_type == "objective":
            if layout_variant == self.LAYOUT_GRID:
                parts.extend(self._render_objective_slide(content, colors, margin, y, content_w))
            else:
                parts.extend(self._render_objective_list_slide(content, colors, margin, y, content_w, rhythm_gap_adjust))
        elif slide_type == "vocabulary":
            if layout_variant == self.LAYOUT_WATERFALL:
                parts.extend(self._render_vocabulary_waterfall(content, colors, margin, y, content_w, rhythm_gap_adjust))
            elif layout_variant == self.LAYOUT_CARDS:
                parts.extend(self._render_vocabulary_cards_slide(content, colors, margin, y, content_w, rhythm_gap_adjust))
            else:
                parts.extend(self._render_vocabulary_slide(content, colors, margin, y, content_w))
        elif slide_type == "dialogue":
            if layout_variant == self.LAYOUT_CHAT:
                parts.extend(self._render_dialogue_chat_slide(content, colors, margin, y, content_w, rhythm_gap_adjust))
            elif layout_variant == self.LAYOUT_STAGE:
                parts.extend(self._render_dialogue_stage_slide(content, colors, margin, y, content_w, rhythm_gap_adjust))
            else:
                parts.extend(self._render_dialogue_slide(content, colors, margin, y, content_w))
        elif slide_type == "grammar":
            if layout_variant == self.LAYOUT_TABLE:
                parts.extend(self._render_grammar_table(content, colors, margin, y, content_w, rhythm_gap_adjust))
            else:
                parts.extend(self._render_grammar_slide(content, colors, margin, y, content_w))
        elif slide_type == "practice":
            parts.extend(self._render_practice_slide(content, colors, margin, y, content_w))
        elif slide_type == "summary":
            parts.extend(self._render_summary_slide(content, colors, margin, y, content_w, canvas_h))
        elif slide_type == "interactive":
            parts.extend(self._render_interactive_slide(content, colors, margin, y, content_w))
        elif slide_type == "ai_interaction":
            parts.extend(self._render_ai_interaction_slide(content, colors, margin, y, content_w))
        elif slide_type == "listening":
            parts.extend(self._render_listening_slide(page, content, colors, margin, start_y, content_w))
        elif slide_type == "speaking":
            parts.extend(self._render_speaking_slide(page, content, colors, margin, start_y, content_w))
        elif slide_type == "catalog":
            parts.extend(self._render_catalog_slide(content, colors, margin, y, content_w, canvas_h))
        else:
            items = content.get("items", content.get("content", []))
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str):
                        parts.append(
                            f'<text x="{margin}" y="{y + 12}" font-size="{self._style_size("body", "content")}" '
            f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">'
            f'\u2022 {self._escape_svg_text(item)}</text>')
                        y += 32
        return parts

    # ========== 各类型专用渲染器 ==========

    def _render_title_slide(self, page: Dict, colors: Dict,
                            canvas_h: int, canvas_w: int) -> List[str]:
        """封面渲染 — 按视觉风格提供差异化封面布局"""
        content = page.get("content", {})
        main_title = content.get("main_title", page.get("title", "PPT"))
        subtitle = content.get("subtitle", "")
        grade = content.get("grade", "")
        cx = canvas_w // 2
        cy = canvas_h // 2 - 60
        style_name = self._current_style_name
        parts = []

        if style_name == "swiss-minimal":
            # 极简：纯白背景 + 左对齐大标题 + 极细装饰线
            parts.append(f'<rect x="0" y="0" width="{canvas_w}" height="{canvas_h}" fill="{colors["background"]}"/>')
            parts.append(
                f'<rect x="0" y="0" width="4" height="{canvas_h}" fill="{colors["primary"]}" opacity="0.12"/>'
                f'<text x="100" y="{cy + 20}" font-size="{self._style_size("main_title", "title_slide")}" font-weight="bold" '
                f'font-family=\'{self._style_font("title")}\' fill="{colors["text"]}">'
                f'{self._escape_svg_text(main_title)}</text>'
                f'<line x1="100" y1="{cy + 32}" x2="{100 + 80}" y2="{cy + 32}" '
                f'stroke="{colors["primary"]}" stroke-width="2"/>')
            if subtitle:
                parts.append(
                    f'<text x="100" y="{cy + 70}" font-size="{self._style_size("subtitle", "title_slide")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}">'
                    f'{self._escape_svg_text(subtitle)}</text>')

        elif style_name == "editorial":
            # 杂志风：米白背景 + 居中衬线标题 + 装饰线
            parts.append(f'<rect x="0" y="0" width="{canvas_w}" height="{canvas_h}" fill="#FDFBF7"/>')
            parts.append(
                f'<line x1="{cx - 200}" y1="{cy - 10}" x2="{cx + 200}" y2="{cy - 10}" '
                f'stroke="{colors["primary"]}" stroke-width="1" opacity="0.4"/>'
                f'<text x="{cx}" y="{cy + 30}" font-size="{self._style_size("main_title", "title_slide")}" font-weight="bold" '
                f'font-family=\'{self._style_font("title")}\' fill="{colors["text"]}" text-anchor="middle">'
                f'{self._escape_svg_text(main_title)}</text>'
                f'<line x1="{cx - 200}" y1="{cy + 48}" x2="{cx + 200}" y2="{cy + 48}" '
                f'stroke="{colors["primary"]}" stroke-width="1" opacity="0.4"/>')
            if subtitle:
                parts.append(
                    f'<text x="{cx}" y="{cy + 90}" font-size="{self._style_size("subtitle", "title_slide")}" font-style="italic" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" text-anchor="middle">'
                    f'{self._escape_svg_text(subtitle)}</text>')

        elif style_name == "dark-tech":
            # 暗色科技：渐变背景 + 发光标题 + 几何装饰
            parts.append(f'<rect x="0" y="0" width="{canvas_w}" height="{canvas_h}" fill="{colors["background"]}"/>')
            # 网格背景
            for gx in range(0, canvas_w, 60):
                parts.append(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{canvas_h}" stroke="{colors["border"]}" stroke-width="0.5" opacity="0.15"/>')
            for gy in range(0, canvas_h, 60):
                parts.append(f'<line x1="0" y1="{gy}" x2="{canvas_w}" y2="{gy}" stroke="{colors["border"]}" stroke-width="0.5" opacity="0.15"/>')
            # 装饰光环
            parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="200" fill="none" stroke="{colors["primary"]}" stroke-width="1" opacity="0.08"/>'
                f'<circle cx="{cx}" cy="{cy}" r="140" fill="none" stroke="{colors["primary"]}" stroke-width="0.5" opacity="0.12"/>'
                f'<text x="{cx}" y="{cy + 24}" font-size="{self._style_size("main_title", "title_slide")}" font-weight="bold" '
                f'font-family=\'{self._style_font("title")}\' fill="{colors["text"]}" text-anchor="middle">'
                f'{self._escape_svg_text(main_title)}</text>')
            if subtitle:
                parts.append(
                    f'<text x="{cx}" y="{cy + 70}" font-size="{self._style_size("subtitle", "title_slide")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" text-anchor="middle">'
                    f'{self._escape_svg_text(subtitle)}</text>')

        elif style_name == "sketch-notes":
            # 手绘风：米黄背景 + 手绘感标题 + 模拟下划线
            parts.append(f'<rect x="0" y="0" width="{canvas_w}" height="{canvas_h}" fill="#FFFDF5"/>')
            # 方格纸背景
            for gx in range(0, canvas_w, 40):
                parts.append(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{canvas_h}" stroke="#333" stroke-width="0.5" opacity="0.04"/>')
            for gy in range(0, canvas_h, 40):
                parts.append(f'<line x1="0" y1="{gy}" x2="{canvas_w}" y2="{gy}" stroke="#333" stroke-width="0.5" opacity="0.04"/>')
            # 手写标题 + 双下划线
            parts.append(
                f'<text x="{cx}" y="{cy + 10}" font-size="{self._style_size("main_title", "title_slide")}" font-weight="bold" '
                f'font-family=\'{self._style_font("title")}\' fill="{colors["text"]}" text-anchor="middle">'
                f'{self._escape_svg_text(main_title)}</text>'
                f'<line x1="{cx - 180}" y1="{cy + 24}" x2="{cx + 180}" y2="{cy + 24}" '
                f'stroke="{colors["primary"]}" stroke-width="2" opacity="0.6"/>'
                f'<line x1="{cx - 160}" y1="{cy + 30}" x2="{cx + 160}" y2="{cy + 30}" '
                f'stroke="{colors["primary"]}" stroke-width="1.5" opacity="0.4"/>')
            if subtitle:
                parts.append(
                    f'<text x="{cx}" y="{cy + 72}" font-size="{self._style_size("subtitle", "title_slide")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" text-anchor="middle">'
                    f'{self._escape_svg_text(subtitle)}</text>')

        elif style_name == "chalkboard":
            # 黑板：深绿背景 + 粉笔白字 + 粉笔装饰
            bg_color = "#2D5016"
            parts.append(f'<rect x="0" y="0" width="{canvas_w}" height="{canvas_h}" fill="{bg_color}"/>')
            # 粉笔边框
            parts.append(
                f'<rect x="30" y="30" width="{canvas_w - 60}" height="{canvas_h - 60}" rx="6" '
                f'fill="none" stroke="#F5F5F0" stroke-width="1" opacity="0.3" stroke-dasharray="8,4"/>'
                f'<text x="{cx}" y="{cy + 20}" font-size="{self._style_size("main_title", "title_slide")}" font-weight="bold" '
                f'font-family=\'{self._style_font("title")}\' fill="#F5F5F0" text-anchor="middle">'
                f'{self._escape_svg_text(main_title)}</text>')
            if subtitle:
                parts.append(
                    f'<text x="{cx}" y="{cy + 70}" font-size="{self._style_size("subtitle", "title_slide")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="#FFEAA7" text-anchor="middle" opacity="0.9">'
                    f'{self._escape_svg_text(subtitle)}</text>')
            # 粉笔星星装饰
            parts.append(
                f'<text x="60" y="100" font-size="18" fill="#FFB3B3" opacity="0.4">\u2606</text>'
                f'<text x="{canvas_w - 80}" y="{canvas_h - 60}" font-size="14" fill="#FFEAA7" opacity="0.3">\u2605</text>')

        elif style_name == "glassmorphism":
            # 玻璃拟态：渐变背景 + 毛玻璃卡片
            parts.append(f'<rect x="0" y="0" width="{canvas_w}" height="{canvas_h}" fill="{colors["background"]}"/>')
            parts.append(
                f'<circle cx="100" cy="150" r="220" fill="{colors["primary"]}" opacity="0.08" filter="url(#{SHADOW_FILTER_ID})"/>'
                f'<circle cx="{canvas_w - 80}" cy="{canvas_h - 100}" r="180" fill="{colors["secondary"]}" opacity="0.06"/>')
            # 半透明玻璃卡片
            parts.append(
                f'<rect x="{cx - 300}" y="{cy - 80}" width="600" height="220" rx="16" '
                f'fill="rgba(255,255,255,0.12)" stroke="rgba(255,255,255,0.25)" stroke-width="1" '
                f'filter="url(#{SHADOW_FILTER_ID})"/>'
                f'<text x="{cx}" y="{cy + 10}" font-size="{self._style_size("main_title", "title_slide")}" font-weight="bold" '
                f'font-family=\'{self._style_font("title")}\' fill="{colors["text"]}" text-anchor="middle">'
                f'{self._escape_svg_text(main_title)}</text>')
            if subtitle:
                parts.append(
                    f'<text x="{cx}" y="{cy + 60}" font-size="{self._style_size("subtitle", "title_slide")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" text-anchor="middle">'
                    f'{self._escape_svg_text(subtitle)}</text>')

        elif style_name == "paper-cut":
            # 剪纸：传统色 + 层叠效果 + 纹样
            bg_c = colors.get("primary", "#D4322F")
            parts.append(f'<rect x="0" y="0" width="{canvas_w}" height="{canvas_h}" fill="{bg_c}"/>')
            # 层叠装饰框
            parts.append(
                f'<rect x="50" y="50" width="{canvas_w - 100}" height="{canvas_h - 100}" rx="4" '
                f'fill="none" stroke="#FFFFFF" stroke-width="1" opacity="0.15"/>'
                f'<rect x="60" y="60" width="{canvas_w - 120}" height="{canvas_h - 120}" rx="4" '
                f'fill="none" stroke="#FFFFFF" stroke-width="0.5" opacity="0.1"/>'
                f'<text x="{cx}" y="{cy + 10}" font-size="{self._style_size("main_title", "title_slide")}" font-weight="bold" '
                f'font-family=\'{self._style_font("title")}\' fill="#FFFFFF" text-anchor="middle">'
                f'{self._escape_svg_text(main_title)}</text>')
            if subtitle:
                parts.append(
                    f'<text x="{cx}" y="{cy + 65}" font-size="{self._style_size("subtitle", "title_slide")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="#FFFFFF" text-anchor="middle" opacity="0.8">'
                    f'{self._escape_svg_text(subtitle)}</text>')

        else:
            # 默认（warm-simple / soft-rounded）：纯色背景 + 装饰圆 + 居中文字
            parts.append(f'<rect x="0" y="0" width="{canvas_w}" height="{canvas_h}" fill="{colors["primary"]}"/>')
            parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{min(canvas_w, canvas_h) // 3}" '
                f'fill="none" stroke="#FFFFFF" stroke-width="1" opacity="0.1"/>'
                f'<circle cx="{cx}" cy="{cy}" r="{min(canvas_w, canvas_h) // 5}" '
                f'fill="none" stroke="#FFFFFF" stroke-width="1" opacity="0.15"/>'
                f'<circle cx="{canvas_w - 80}" cy="80" r="120" fill="#FFFFFF" opacity="0.06"/>'
                f'<circle cx="80" cy="{canvas_h - 80}" r="100" fill="#FFFFFF" opacity="0.04"/>'
                f'<text x="{cx}" y="{cy + 20}" font-size="{self._style_size("main_title", "title_slide")}" font-weight="bold" '
                f'font-family=\'{self._style_font("title")}\' fill="#FFFFFF" text-anchor="middle">'
                f'{self._escape_svg_text(main_title)}</text>')
            if subtitle:
                parts.append(
                    f'<text x="{cx}" y="{cy + 70}" font-size="{self._style_size("subtitle", "title_slide")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="#FFFFFF" text-anchor="middle" opacity="0.85">'
                    f'{self._escape_svg_text(subtitle)}</text>')

        if grade:
            parts.append(
                f'<text x="{cx}" y="{cy + 110}" font-size="{self._style_size("grade", "title_slide")}" '
                f'font-family=\'{self._style_font("body")}\' fill="#FFFFFF" text-anchor="middle" opacity="0.6">'
                f'{self._escape_svg_text(grade)}</text>')
        return parts

    def _render_objective_slide(self, content: Dict, colors: Dict,
                                 margin: int, y: int, content_w: int) -> List[str]:
        """学习目标 — 双列网格卡片（匹配 HTML objective-grid）"""
        parts = []
        items = content.get("items", [])
        col_count, gap = 2, 12
        card_w = (content_w - gap) // col_count
        card_h = 44
        for i, item in enumerate(items[:8]):
            col, row = i % col_count, i // col_count
            cx = margin + col * (card_w + gap)
            cy = y + row * (card_h + gap)
            parts.append(
                f'<rect x="{cx}" y="{cy}" width="{card_w}" height="{card_h}" '
                f'rx="6" fill="{colors["surface"]}" stroke="{colors["border"]}" '
                f'stroke-width="1"/>'
                f'<circle cx="{cx + 16}" cy="{cy + card_h // 2}" r="12" fill="{colors["primary"]}"/>'
                f'<text x="{cx + 16}" y="{cy + card_h // 2 + 5}" font-size="{self._style_size("icon", "objective")}" '
                f'fill="#FFF" text-anchor="middle">{i + 1}</text>'
                f'<text x="{cx + 36}" y="{cy + card_h // 2 + 5}" font-size="{self._style_size("item", "objective")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">{self._escape_svg_text(item)}</text>')
        return parts

    def _render_vocabulary_slide(self, content: Dict, colors: Dict,
                                  margin: int, y: int, content_w: int) -> List[str]:
        """词汇展示 — 网格卡片（匹配 HTML vocab-grid）"""
        parts = []
        words = content.get("words", [])
        col_count, gap = 3, 10
        card_w = (content_w - gap * 2) // col_count
        card_h = 85
        for i, w in enumerate(words[:9]):
            col, row = i % col_count, i // col_count
            cx = margin + col * (card_w + gap)
            cy = y + row * (card_h + gap)
            word_text, pho = w.get("word", ""), w.get("phonetic", "")
            trans, ex = w.get("translation", ""), w.get("example", "")
            parts.append(
                f'<rect x="{cx}" y="{cy}" width="{card_w}" height="{card_h}" rx="6" '
                f'fill="{colors["surface"]}" stroke="{colors["border"]}" stroke-width="1"/>'
                f'<rect x="{cx}" y="{cy}" width="{card_w}" height="3" rx="1.5" '
                f'fill="{colors["primary"]}"/>'
                f'<text x="{cx + 10}" y="{cy + 22}" font-size="{self._style_size("word", "vocabulary")}" font-weight="bold" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">{self._escape_svg_text(word_text)}</text>')
            if pho:
                parts.append(
                    f'<text x="{cx + 10}" y="{cy + 38}" font-size="{self._style_size("phonetic", "vocabulary")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}">{self._escape_svg_text(pho)}</text>')
            parts.append(
                f'<text x="{cx + 10}" y="{cy + 56}" font-size="{self._style_size("translation", "vocabulary")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">{self._escape_svg_text(trans)}</text>')
            if ex:
                parts.append(
                    f'<text x="{cx + 10}" y="{cy + 74}" font-size="{self._style_size("example", "vocabulary")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" opacity="0.8">'
                    f'{self._escape_svg_text(ex[:40])}</text>')
        return parts

    def _render_dialogue_slide(self, content: Dict, colors: Dict,
                                margin: int, y: int, content_w: int) -> List[str]:
        """对话练习 — 卡片式气泡（匹配 HTML dialogue-cards）"""
        parts = []
        for i, d in enumerate(content.get("dialogues", [])[:6]):
            speaker, text = d.get("speaker", "A"), d.get("text", "")
            trans = d.get("translation", "")
            is_a = speaker.upper() in ("A", "T", "TEACHER")
            bc = colors["primary"] if is_a else colors["secondary"]
            cx = margin if is_a else margin + 60
            cw = content_w - 60
            # 对话气泡带阴影效果
            parts.append(
                f'<rect x="{cx}" y="{y}" width="{cw}" height="50" rx="8" '
                f'fill="{colors["surface"]}" filter="url(#{SHADOW_FILTER_ID})"/>'
                f'<rect x="{cx}" y="{y}" width="{cw}" height="50" rx="8" '
                f'fill="{bc}" opacity="0.06"/>'
                f'<rect x="{cx}" y="{y}" width="4" height="50" rx="2" fill="{bc}" opacity="0.7"/>'
                f'<text x="{cx + 14}" y="{y + 16}" font-size="{self._style_size("speaker", "dialogue")}" font-weight="bold" '
                f'font-family=\'{self._style_font("body")}\' fill="{bc}">{self._escape_svg_text(speaker)}</text>'
                f'<text x="{cx + 14}" y="{y + 36}" font-size="{self._style_size("text", "dialogue")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">{self._escape_svg_text(text)}</text>')
            y += 52
            if trans:
                parts.append(
                    f'<text x="{cx + 14}" y="{y}" font-size="{self._style_size("translation", "dialogue")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" opacity="0.8">'
                    f'{self._escape_svg_text(trans)}</text>')
                y += 18
        return parts

    def _render_grammar_slide(self, content: Dict, colors: Dict,
                               margin: int, y: int, content_w: int) -> List[str]:
        """语法讲解 — 带边框卡片（匹配 HTML grammar-card-boxed）"""
        parts = []
        for pt in content.get("points", [])[:4]:
            rule, example = pt.get("rule", ""), pt.get("example", "")
            expl = pt.get("explanation", "")
            extra = 22 if expl else 0
            ch = 64 + extra
            # 语法卡片带阴影效果
            parts.append(
                f'<rect x="{margin}" y="{y}" width="{content_w}" height="{ch}" '
                f'rx="8" fill="{colors["surface"]}" filter="url(#{SHADOW_FILTER_ID})"/>'
                f'<rect x="{margin}" y="{y}" width="{content_w}" height="{ch}" '
                f'rx="8" fill="none" stroke="{colors["primary"]}" stroke-width="1.5"/>'
                f'<rect x="{margin + 12}" y="{y + 10}" width="40" height="18" rx="4" '
                f'fill="{colors["primary"]}" opacity="0.12"/>'
                f'<text x="{margin + 32}" y="{y + 24}" font-size="{self._style_size("icon", "grammar")}" font-weight="bold" '
                f'fill="{colors["primary"]}" text-anchor="middle">\u89c4\u5219</text>'
                f'<text x="{margin + 60}" y="{y + 24}" font-size="{self._style_size("rule", "grammar")}" font-weight="bold" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">{self._escape_svg_text(rule)}</text>'
                f'<text x="{margin + 14}" y="{y + 48}" font-size="{self._style_size("example", "grammar")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}">'
                f'\u4f8b\u53e5: {self._escape_svg_text(example)}</text>')
            if expl:
                parts.append(
                    f'<text x="{margin + 14}" y="{y + ch - 8}" font-size="{self._style_size("explanation", "grammar")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" opacity="0.8">'
                    f'{self._escape_svg_text(expl)}</text>')
            y += ch + 12
        return parts

    def _render_practice_slide(self, content: Dict, colors: Dict,
                                margin: int, y: int, content_w: int) -> List[str]:
        """课堂练习 — 题号 + 选项（匹配 HTML practice questions）"""
        parts = []
        for qi, q in enumerate(content.get("questions", [])[:3]):
            stem, options = q.get("stem", ""), q.get("options", [])
            expl = q.get("explanation", "")
            parts.append(
                f'<rect x="{margin}" y="{y}" width="26" height="20" rx="4" '
                f'fill="{colors["primary"]}" opacity="0.12"/>'
                f'<text x="{margin + 13}" y="{y + 15}" font-size="{self._style_size("icon", "practice")}" font-weight="bold" '
                f'fill="{colors["primary"]}" text-anchor="middle">'
                f'\u7b2c{qi + 1}\u9898</text>')
            y += 28
            parts.append(
                f'<text x="{margin}" y="{y}" font-size="{self._style_size("stem", "practice")}" font-weight="bold" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">{self._escape_svg_text(stem)}</text>')
            y += 26
            for oi, opt in enumerate(options[:4]):
                parts.append(
                    f'<rect x="{margin}" y="{y}" width="{content_w}" height="22" rx="4" '
                    f'fill="{colors["surface"]}" opacity="0.4"/>'
                    f'<text x="{margin + 8}" y="{y + 16}" font-size="{self._style_size("option", "practice")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">'
                    f'{chr(65 + oi)}. {self._escape_svg_text(opt)}</text>')
                y += 24
            if expl:
                y += 4
                parts.append(
                    f'<text x="{margin}" y="{y}" font-size="{self._style_size("explanation", "practice")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["accent"]}" opacity="0.8">'
                    f'[\u89e3\u6790] {self._escape_svg_text(expl)}</text>')
                y += 16
            y += 10
        return parts

    def _render_summary_slide(self, content: Dict, colors: Dict,
                               margin: int, y: int, content_w: int,
                               canvas_h: int) -> List[str]:
        """总结 — 要点 + 课后作业框（匹配 HTML summary）"""
        parts = []
        parts.append(
            f'<text x="{margin}" y="{y}" font-size="{self._style_size("point", "summary")}" font-weight="bold" '
            f'font-family=\'{self._style_font("body")}\' fill="{colors["primary"]}">\u672c\u8bfe\u91cd\u70b9</text>')
        y += 28
        for kp in content.get("key_points", [])[:7]:
            parts.append(
                f'<rect x="{margin}" y="{y - 3}" width="6" height="6" rx="3" '
                f'fill="{colors["primary"]}" opacity="0.7"/>'
                f'<text x="{margin + 16}" y="{y + 3}" font-size="{self._style_size("point", "summary")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">{self._escape_svg_text(kp)}</text>')
            y += 26
        hw = content.get("homework", "")
        if hw:
            y = max(y + 14, canvas_h - 90)
            parts.append(
                f'<rect x="{margin}" y="{y}" width="{content_w}" height="44" '
                f'rx="6" fill="{colors["surface"]}" stroke="{colors["accent"]}" '
                f'stroke-width="1" stroke-dasharray="3,2"/>'
                f'<text x="{margin + 14}" y="{y + 27}" font-size="{self._style_size("homework", "summary")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">'
                f'\u8bfe\u540e\u4f5c\u4e1a  {self._escape_svg_text(hw)}</text>')
        return parts

    def _render_catalog_slide(self, content: Dict, colors: Dict,
                               margin: int, y: int, content_w: int,
                               canvas_h: int) -> List[str]:
        """目录 — 编号章节列表，作为课程导航"""
        parts = []
        sections = content.get("sections", [])
        # 标题标识
        parts.append(
            f'<text x="{margin}" y="{y}" font-size="{self._style_size("section", "catalog")}" font-weight="bold" '
            f'font-family=\'{self._style_font("body")}\' fill="{colors["primary"]}">\u672c\u8bfe\u5bfc\u822a</text>')
        y += 34
        # 用红线作为内容区装饰
        parts.append(
            f'<line x1="{margin}" y1="{y}" x2="{margin + content_w}" y2="{y}" '
            f'stroke="{colors["primary"]}" stroke-width="2" opacity="0.25"/>')
        y += 20
        # 左侧竖线装饰
        line_x = margin + 36
        parts.append(
            f'<line x1="{line_x}" y1="{y}" x2="{line_x}" y2="{y + len(sections) * 44 + 16}" '
            f'stroke="{colors["accent"]}" stroke-width="2" opacity="0.3" stroke-dasharray="4,3"/>')
        for i, sec in enumerate(sections[:8]):
            cy = y + i * 44
            # 编号圆
            parts.append(
                f'<circle cx="{line_x}" cy="{cy + 10}" r="10" '
                f'fill="{colors["accent"]}" opacity="0.15"/>'
                f'<text x="{line_x}" y="{cy + 14}" font-size="{self._style_size("icon", "catalog")}" font-weight="bold" '
                f'fill="{colors["accent"]}" text-anchor="middle">{i + 1}</text>'
                # 章节文本
                f'<text x="{line_x + 24}" y="{cy + 14}" font-size="{self._style_size("section", "catalog")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">'
                f'{self._escape_svg_text(sec)}</text>')
        return parts

    def _render_interactive_slide(self, content: Dict, colors: Dict,
                                   margin: int, y: int, content_w: int) -> List[str]:
        """互动活动 — 徽标 + 描述 + 编号步骤（匹配 HTML interactive）"""
        parts = []
        at = content.get("activity_type", "activity")
        steps, desc = content.get("steps", []), content.get("description", "")
        label = {"game": "\u6e38\u620f", "vote": "\u6295\u7968",
                 "roleplay": "\u89d2\u8272", "discussion": "\u8ba8\u8bba"}.get(at, "\u4e92\u52a8")
        parts.append(
            f'<rect x="{margin}" y="{y}" width="72" height="26" rx="13" '
            f'fill="{colors["primary"]}" opacity="0.12"/>'
            f'<text x="{margin + 36}" y="{y + 18}" font-size="{self._style_size("icon", "interactive")}" font-weight="bold" '
            f'fill="{colors["primary"]}" text-anchor="middle">{label}</text>')
        y += 36
        if desc:
            parts.append(
                f'<text x="{margin}" y="{y}" font-size="{self._style_size("description", "interactive")}" font-weight="bold" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">{self._escape_svg_text(desc)}</text>')
            y += 28
        for i, s in enumerate(steps[:5]):
            parts.append(
                f'<circle cx="{margin + 12}" cy="{y + 8}" r="12" fill="{colors["accent"]}"/>'
                f'<text x="{margin + 12}" y="{y + 13}" font-size="{self._style_size("icon", "interactive")}" font-weight="bold" '
                f'fill="#FFF" text-anchor="middle">{i + 1}</text>'
                f'<text x="{margin + 34}" y="{y + 13}" font-size="{self._style_size("step", "interactive")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">{self._escape_svg_text(s)}</text>')
            y += 32
        return parts

    def _render_ai_interaction_slide(self, content: Dict, colors: Dict,
                                      margin: int, y: int, content_w: int) -> List[str]:
        """人机互动页 — 提示语 + 卡片提问（匹配 HTML ai_interaction）"""
        parts = []
        prompt_text = content.get("prompt", "你对今天学的内容有什么疑问吗？")
        questions = content.get("questions", [])
        cx = margin + content_w // 2
        parts.append(
            f'<text x="{cx}" y="{y + 10}" font-size="{self._style_size("prompt", "ai_interaction")}" font-weight="500" '
            f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}" text-anchor="middle" opacity="0.9">'
            f'{self._escape_svg_text(prompt_text)}</text>')
        y += 48
        col_cnt, gap = 2, 10
        cw = (content_w - gap) // col_cnt
        ch = 50
        for i, q in enumerate(questions[:6]):
            col, row = i % col_cnt, i // col_cnt
            qx, qy = margin + col * (cw + gap), y + row * (ch + gap)
            question, hint = q.get("question", ""), q.get("hint", "")
            parts.append(
                f'<rect x="{qx}" y="{qy}" width="{cw}" height="{ch}" rx="8" '
                f'fill="{colors["surface"]}" stroke="{colors["border"]}" stroke-width="1"/>'
                f'<rect x="{qx}" y="{qy}" width="3" height="{ch}" rx="1.5" fill="{colors["primary"]}"/>'
                f'<text x="{qx + 14}" y="{qy + 20}" font-size="{self._style_size("question", "ai_interaction")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">{self._escape_svg_text(question)}</text>')
            if hint:
                parts.append(
                    f'<text x="{qx + 14}" y="{qy + 38}" font-size="{self._style_size("hint", "ai_interaction")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" opacity="0.8">'
                    f'{self._escape_svg_text(hint)}</text>')
            parts.append(
                f'<text x="{qx + cw - 10}" y="{qy + ch - 8}" font-size="{self._style_size("icon", "ai_interaction")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["primary"]}" text-anchor="end" opacity="0.6">'
                f'\u25b6 \u54a8\u8be2AI</text>')
        if questions:
            y2 = y + ((len(questions) - 1) // col_cnt + 1) * (ch + gap) + 20
            parts.append(
                f'<text x="{cx}" y="{y2}" font-size="{self._style_size("hint", "ai_interaction")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" text-anchor="middle" opacity="0.7">'
                f'\u70b9\u51fb\u95ee\u9898\u5411 AI \u63d0\u95ee</text>')
        return parts

    def _render_listening_slide(self, page: Dict, content: Dict, colors: Dict,
                                 margin: int, y: int, content_w: int) -> List[str]:
        """听力练习页 — 播放器 + 展开文本 + 题目（匹配 HTML listening）"""
        parts = []
        audio_text = content.get("audio_text", page.get("audio_text", ""))
        subtitle = content.get("subtitle", page.get("subtitle", ""))
        questions = content.get("questions", page.get("questions", []))
        # 播放器栏
        parts.append(
            f'<rect x="{margin}" y="{y}" width="{content_w}" height="40" rx="8" '
            f'fill="{colors["surface"]}" stroke="{colors["border"]}" stroke-width="1"/>'
            f'<rect x="{margin}" y="{y}" width="4" height="40" rx="2" '
            f'fill="{colors["primary"]}" opacity="0.5"/>'
            f'<text x="{margin + 18}" y="{y + 26}" font-size="{self._style_size("small", "listening")}" font-weight="bold" '
            f'font-family=\'{self._style_font("body")}\' fill="{colors["primary"]}">\u25b6 \u64ad\u653e\u97f3\u9891</text>'
            f'<text x="{margin + content_w - 14}" y="{y + 26}" font-size="{self._style_size("icon", "listening")}" '
            f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" text-anchor="end" opacity="0.7">'
            f'\u25bc \u67e5\u770b\u539f\u6587</text>')
        y += 52
        if audio_text:
            parts.append(
                f'<rect x="{margin}" y="{y}" width="{content_w}" height="50" rx="6" '
                f'fill="{colors["surface"]}" stroke="{colors["border"]}" stroke-width="1" stroke-dasharray="3,2"/>'
                f'<text x="{margin + 14}" y="{y + 18}" font-size="{self._style_size("audio_text", "listening")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">{self._escape_svg_text(audio_text[:80])}</text>')
            if subtitle:
                parts.append(
                    f'<text x="{margin + 14}" y="{y + 38}" font-size="{self._style_size("note", "listening")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}">{self._escape_svg_text(subtitle)}</text>')
            y += 58
        # 题目
        if questions:
            parts.append(
                f'<text x="{margin}" y="{y}" font-size="{self._style_size("question", "listening")}" font-weight="bold" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["primary"]}">\u542c\u529b\u7406\u89e3\u9898</text>')
            y += 24
            for qi, q in enumerate(questions[:3]):
                stem = q.get("stem", "")
                options = q.get("options", [])
                parts.append(
                    f'<text x="{margin}" y="{y}" font-size="{self._style_size("question", "listening")}" font-weight="bold" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">{qi + 1}. {self._escape_svg_text(stem)}</text>')
                y += 22
                for oi, opt in enumerate(options[:4]):
                    parts.append(
                        f'<text x="{margin + 16}" y="{y}" font-size="{self._style_size("note", "listening")}" '
                        f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">'
                        f'{chr(65 + oi)}. {self._escape_svg_text(opt)}</text>')
                    y += 20
                y += 6
        return parts

    def _render_speaking_slide(self, page: Dict, content: Dict, colors: Dict,
                                margin: int, y: int, content_w: int) -> List[str]:
        """口语跟读页 — 播放器 + 文本 + 翻译 + 提示（匹配 HTML speaking）"""
        parts = []
        text = content.get("text", page.get("text", ""))
        translation = content.get("translation", page.get("translation", ""))
        tips = content.get("tips", page.get("tips", ""))
        # 播放器栏
        parts.append(
            f'<rect x="{margin}" y="{y}" width="{content_w}" height="40" rx="8" '
            f'fill="{colors["surface"]}" stroke="{colors["border"]}" stroke-width="1"/>'
            f'<rect x="{margin}" y="{y}" width="4" height="40" rx="2" '
            f'fill="{colors["primary"]}" opacity="0.5"/>'
            f'<text x="{margin + 18}" y="{y + 26}" font-size="{self._style_size("small", "speaking")}" font-weight="bold" '
            f'font-family=\'{self._style_font("body")}\' fill="{colors["primary"]}">\u25b6 \u64ad\u653e\u793a\u8303\u6717\u8bfb</text>'
            f'<text x="{margin + content_w - 14}" y="{y + 26}" font-size="{self._style_size("icon", "speaking")}" '
            f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" text-anchor="end" opacity="0.7">'
            f'\u25bc \u67e5\u770b\u539f\u6587</text>')
        y += 52
        if text:
            parts.append(
                f'<text x="{margin}" y="{y}" font-size="{self._style_size("text", "speaking")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">{self._escape_svg_text(text[:100])}</text>')
            y += 28
        if translation:
            parts.append(
                f'<text x="{margin}" y="{y}" font-size="{self._style_size("tips", "speaking")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}">{self._escape_svg_text(translation)}</text>')
            y += 24
        if tips:
            y += 6
            parts.append(
                f'<rect x="{margin}" y="{y}" width="{content_w}" height="36" rx="6" '
                f'fill="{colors["surface"]}" stroke="{colors["accent"]}" stroke-width="1" opacity="0.6"/>'
                f'<text x="{margin + 14}" y="{y + 24}" font-size="{self._style_size("tips", "speaking")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">\u53d1\u97f3\u63d0\u793a: {self._escape_svg_text(tips)}</text>')
        return parts

    # ==================== 布局变体渲染器 ====================

    def _render_objective_list_slide(
        self, content: Dict, colors: Dict,
        margin: int, y: int, content_w: int,
        gap_adjust: int = 0,
    ) -> List[str]:
        """学习目标 — 纵向列表布局（适用于 breathing 节奏）

        每个目标为带编号圆标的独立行，视觉清晰。
        """
        parts = []
        items = content.get("items", [])
        gap = 14 + gap_adjust
        icon_size = 24
        for i, item in enumerate(items[:8]):
            cy = y + i * (icon_size + gap)
            # 编号图标
            parts.append(
                f'<circle cx="{margin + icon_size // 2}" cy="{cy + icon_size // 2}" '
                f'r="{icon_size // 2}" fill="{colors["primary"]}" opacity="0.12"/>'
                f'<text x="{margin + icon_size // 2}" y="{cy + icon_size // 2 + 1}" '
                f'font-size="{self._style_size("meta", "objective")}" font-weight="bold" fill="{colors["primary"]}" '
                f'text-anchor="middle">{i + 1}</text>'
                # 勾选标记
                f'<circle cx="{margin + icon_size + 14}" cy="{cy + icon_size // 2}" '
                f'r="6" fill="none" stroke="{colors["primary"]}" stroke-width="1.5" opacity="0.4"/>'
                # 文本
                f'<text x="{margin + icon_size + 28}" y="{cy + icon_size // 2 + 5}" '
                f'font-size="{self._style_size("item", "objective")}" font-family=\'{self._style_font("body")}\' '
                f'fill="{colors["text"]}">{self._escape_svg_text(item)}</text>'
            )
        return parts

    def _render_vocabulary_waterfall(
        self, content: Dict, colors: Dict,
        margin: int, y: int, content_w: int,
        gap_adjust: int = 0,
    ) -> List[str]:
        """词汇展示 — 瀑布流布局（错落排列，增强视觉动感）

        交替行的卡片带偏移量，营造错落节奏感。
        """
        parts = []
        words = content.get("words", [])
        col_count, gap = 3, 10
        card_w = (content_w - gap * 2) // col_count
        card_h = 90
        offsets = [0, 18, 0, 22, 5]  # 交替偏移制造错落感

        for i, w in enumerate(words[:9]):
            col, row = i % col_count, i // col_count
            col_offset = offsets[row % len(offsets)]
            cx = margin + col * (card_w + gap)
            cy = y + row * (card_h + gap) + col_offset

            word_text, pho = w.get("word", ""), w.get("phonetic", "")
            trans, ex = w.get("translation", ""), w.get("example", "")

            # 卡片背景 — 带细微旋转
            rotation = (col_offset // 4) * (1 if col % 2 == 0 else -1)
            parts.append(
                f'<g transform="rotate({rotation}, {cx + card_w // 2}, {cy + card_h // 2})">'
                f'<rect x="{cx}" y="{cy}" width="{card_w}" height="{card_h}" rx="8" '
                f'fill="{colors["surface"]}" stroke="{colors["border"]}" stroke-width="1" '
                f'filter="url(#{SHADOW_FILTER_ID})"/>'
                # 顶部色条
                f'<rect x="{cx}" y="{cy}" width="{card_w}" height="3" rx="1.5" '
                f'fill="{colors["primary"]}"/>'
                # 单词
                f'<text x="{cx + 10}" y="{cy + 22}" font-size="15" font-weight="bold" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">'
                f'{self._escape_svg_text(word_text)}</text>'
                f'</g>'
            )
            if pho:
                parts.append(
                    f'<text x="{cx + 10}" y="{cy + 38}" font-size="{self._style_size("phonetic", "vocabulary")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}">'
                    f'{self._escape_svg_text(pho)}</text>'
                )
            parts.append(
                f'<text x="{cx + 10}" y="{cy + 56}" font-size="{self._style_size("translation", "vocabulary")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">'
                f'{self._escape_svg_text(trans)}</text>'
            )
            if ex:
                parts.append(
                    f'<text x="{cx + 10}" y="{cy + 76}" font-size="{self._style_size("example", "vocabulary")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" opacity="0.8">'
                    f'{self._escape_svg_text(ex[:35])}</text>'
                )
        return parts

    def _render_vocabulary_cards_slide(
        self, content: Dict, colors: Dict,
        margin: int, y: int, content_w: int,
        gap_adjust: int = 0,
    ) -> List[str]:
        """词汇展示 — 大卡片水平布局（更宽的字卡，适合少数重点词汇）

        每个单词占满整行，卡片高度增加，展示更详细信息。
        """
        parts = []
        words = content.get("words", [])
        gap = 8 + gap_adjust
        card_h = 80

        for i, w in enumerate(words[:6]):
            cy = y + i * (card_h + gap)
            word_text, pho = w.get("word", ""), w.get("phonetic", "")
            trans, ex = w.get("translation", ""), w.get("example", "")

            # 左侧色块 + 主词
            parts.append(
                f'<rect x="{margin}" y="{cy}" width="{content_w}" height="{card_h}" rx="8" '
                f'fill="{colors["surface"]}" stroke="{colors["border"]}" stroke-width="1" '
                f'filter="url(#{SHADOW_FILTER_ID})"/>'
                # 左侧粗色块
                f'<rect x="{margin}" y="{cy}" width="6" height="{card_h}" rx="3" '
                f'fill="{colors["primary"]}" opacity="0.6"/>'
                # 大号单词
                f'<text x="{margin + 24}" y="{cy + 32}" font-size="{self._style_size("word", "vocabulary")}" font-weight="bold" '
                f'font-family=\'{self._style_font("title")}\' fill="{colors["text"]}">'
                f'{self._escape_svg_text(word_text)}</text>'
            )
            if pho:
                parts.append(
                    f'<text x="{margin + 24}" y="{cy + 52}" font-size="{self._style_size("phonetic", "vocabulary")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}">'
                    f'/ {self._escape_svg_text(pho)} /</text>'
                )
            # 翻译 — 右侧或中间
            parts.append(
                f'<text x="{margin + content_w - 20}" y="{cy + 32}" font-size="{self._style_size("translation", "vocabulary")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["primary"]}" '
                f'text-anchor="end">{self._escape_svg_text(trans)}</text>'
            )
            if ex:
                parts.append(
                    f'<text x="{margin + 24}" y="{cy + 68}" font-size="{self._style_size("example", "vocabulary")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" opacity="0.7">'
                    f'\u4f8b: {self._escape_svg_text(ex[:50])}</text>'
                )
        return parts

    def _render_dialogue_chat_slide(
        self, content: Dict, colors: Dict,
        margin: int, y: int, content_w: int,
        gap_adjust: int = 0,
    ) -> List[str]:
        """对话练习 — 聊天气泡布局（类似微信/即时通讯风格）

        每条对话：圆形头像 + 发言者名称 + 气泡正文 + 翻译。
        """
        parts = []
        dialogues = content.get("dialogues", [])[:6]
        gap = 6 + gap_adjust
        avatar_r = 16

        for i, d in enumerate(dialogues):
            speaker, text = d.get("speaker", "A"), d.get("text", "")
            trans = d.get("translation", "")
            is_a = speaker.upper() in ("A", "T", "TEACHER")
            is_left = is_a  # 发言者 A/老师居左，B/学生居右

            # 头像
            av_x = margin if is_left else margin + content_w - avatar_r * 2
            av_color = colors["primary"] if is_left else colors["accent"]
            # 消息气泡
            bubble_max_w = int(content_w * 0.65)
            bubble_x = margin + avatar_r * 2 + 8 if is_left else margin + content_w - avatar_r * 2 - 8 - bubble_max_w
            bubble_color = colors["surface"] if is_left else colors["primary"] + "0.08"

            parts.append(
                # 头像
                f'<circle cx="{av_x + avatar_r}" cy="{y + avatar_r}" r="{avatar_r}" '
                f'fill="{av_color}" opacity="0.15"/>'
                f'<text x="{av_x + avatar_r}" y="{y + avatar_r + 4}" font-size="{self._style_size("icon", "dialogue")}" '
                f'font-weight="bold" fill="{av_color}" text-anchor="middle">'
                f'{speaker[0].upper()}</text>'
                # 发言者名称
                f'<text x="{bubble_x if is_left else bubble_x + bubble_max_w}" '
                f'y="{y - 4}" font-size="{self._style_size("meta", "dialogue")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" '
                f'text-anchor="{"start" if is_left else "end"}">{speaker}</text>'
                # 气泡正文
                f'<rect x="{bubble_x}" y="{y + 4}" width="{bubble_max_w}" height="28" rx="8" '
                f'fill="{bubble_color}" stroke="{colors["border"]}" stroke-width="0.5"/>'
                f'<text x="{bubble_x + 10}" y="{y + 24}" font-size="{self._style_size("text", "dialogue")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">'
                f'{self._escape_svg_text(text)}</text>'
            )
            y += 40

            if trans:
                trans_x = bubble_x + 10 if is_left else bubble_x + bubble_max_w - 10
                parts.append(
                    f'<text x="{trans_x}" y="{y}" font-size="{self._style_size("translation", "dialogue")}" '
                    f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}" '
                    f'text-anchor="{"start" if is_left else "end"}" opacity="0.7">'
                    f'{self._escape_svg_text(trans)}</text>'
                )
                y += 18

            y += gap

        return parts

    def _render_dialogue_stage_slide(
        self, content: Dict, colors: Dict,
        margin: int, y: int, content_w: int,
        gap_adjust: int = 0,
    ) -> List[str]:
        """对话练习 — 舞台分屏布局（左右对比，适合角色扮演）

        将对话分为左侧发言人和右侧发言人两列展示。
        """
        parts = []
        dialogues = content.get("dialogues", [])[:6]
        gap = 6 + gap_adjust

        # 中间分隔线
        mid_x = margin + content_w // 2
        parts.append(
            f'<line x1="{mid_x}" y1="{y - 10}" x2="{mid_x}" y2="{y + 180}" '
            f'stroke="{colors["border"]}" stroke-width="1" stroke-dasharray="3,3" opacity="0.5"/>'
        )

        left_dialogues = []
        right_dialogues = []
        for d in dialogues:
            speaker = d.get("speaker", "A")
            if speaker.upper() in ("A", "T", "TEACHER"):
                left_dialogues.append(d)
            else:
                right_dialogues.append(d)

        half_w = content_w // 2 - 20
        item_h = 44

        # 左侧：发言者 A
        for i, d in enumerate(left_dialogues[:4]):
            text = d.get("text", "")
            trans = d.get("translation", "")
            cy = y + i * (item_h + gap)
            if cy > y + 180:
                break

            parts.append(
                f'<rect x="{margin}" y="{cy}" width="{half_w}" height="{item_h}" rx="6" '
                f'fill="{colors["surface"]}" stroke="{colors["border"]}" stroke-width="0.5"/>'
                f'<rect x="{margin}" y="{cy}" width="{half_w}" height="3" rx="1.5" '
                f'fill="{colors["primary"]}"/>'
                f'<text x="{margin + 8}" y="{cy + 18}" font-size="{self._style_size("speaker", "dialogue")}" font-weight="bold" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["primary"]}">'
                f'{d.get("speaker", "A")}</text>'
                f'<text x="{margin + 8}" y="{cy + 36}" font-size="{self._style_size("text", "dialogue")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">'
                f'{self._escape_svg_text(text)}</text>'
            )

        # 右侧：发言者 B
        for i, d in enumerate(right_dialogues[:4]):
            text = d.get("text", "")
            trans = d.get("translation", "")
            cx = mid_x + 10
            cy = y + i * (item_h + gap)
            if cy > y + 180:
                break

            parts.append(
                f'<rect x="{cx}" y="{cy}" width="{half_w}" height="{item_h}" rx="6" '
                f'fill="{colors["surface"]}" stroke="{colors["border"]}" stroke-width="0.5"/>'
                f'<rect x="{cx}" y="{cy}" width="3" height="{item_h}" rx="1.5" '
                f'fill="{colors["accent"]}"/>'
                f'<text x="{cx + 8}" y="{cy + 18}" font-size="{self._style_size("speaker", "dialogue")}" font-weight="bold" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["accent"]}">'
                f'{d.get("speaker", "B")}</text>'
                f'<text x="{cx + 8}" y="{cy + 36}" font-size="{self._style_size("text", "dialogue")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">'
                f'{self._escape_svg_text(text)}</text>'
            )

        return parts

    def _render_grammar_table(
        self, content: Dict, colors: Dict,
        margin: int, y: int, content_w: int,
        gap_adjust: int = 0,
    ) -> List[str]:
        """语法讲解 — 表格布局（适合规则对比/并列展示）

        表头 + 数据行，三列：规则 | 例句 | 解释
        """
        parts = []
        points = content.get("points", [])[:5]
        row_h = 36
        header_h = 28
        col1_w = int(content_w * 0.28)
        col2_w = int(content_w * 0.38)
        col3_w = content_w - col1_w - col2_w

        # 表头底色
        parts.append(
            f'<rect x="{margin}" y="{y}" width="{content_w}" height="{header_h}" rx="6" '
            f'fill="{colors["primary"]}" opacity="0.1"/>'
            # 规则列
            f'<text x="{margin + 8}" y="{y + header_h // 2 + 5}" font-size="{self._style_size("note", "grammar")}" font-weight="bold" '
            f'font-family=\'{self._style_font("body")}\' fill="{colors["primary"]}">'
            f'\u89c4\u5219</text>'
            # 例句列
            f'<text x="{margin + col1_w + 8}" y="{y + header_h // 2 + 5}" font-size="{self._style_size("note", "grammar")}" font-weight="bold" '
            f'font-family=\'{self._style_font("body")}\' fill="{colors["primary"]}">'
            f'\u4f8b\u53e5</text>'
            # 解释列
            f'<text x="{margin + col1_w + col2_w + 8}" y="{y + header_h // 2 + 5}" font-size="{self._style_size("note", "grammar")}" font-weight="bold" '
            f'font-family=\'{self._style_font("body")}\' fill="{colors["primary"]}">'
            f'\u89e3\u91ca</text>'
        )
        y += header_h + 4

        for i, pt in enumerate(points):
            rule, example = pt.get("rule", ""), pt.get("example", "")
            expl = pt.get("explanation", "")
            row_bg = colors["surface"] if i % 2 == 0 else colors["background"]

            parts.append(
                f'<rect x="{margin}" y="{y}" width="{content_w}" height="{row_h}" '
                f'fill="{row_bg}" stroke="{colors["border"]}" stroke-width="0.5"/>'
                # 规则
                f'<text x="{margin + 8}" y="{y + row_h // 2 + 5}" font-size="{self._style_size("rule", "grammar")}" font-weight="bold" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">'
                f'{self._escape_svg_text(rule)}</text>'
                # 例句
                f'<text x="{margin + col1_w + 8}" y="{y + row_h // 2 + 5}" font-size="{self._style_size("example", "grammar")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text"]}">'
                f'{self._escape_svg_text(example[:30])}</text>'
                # 解释
                f'<text x="{margin + col1_w + col2_w + 8}" y="{y + row_h // 2 + 5}" font-size="{self._style_size("explanation", "grammar")}" '
                f'font-family=\'{self._style_font("body")}\' fill="{colors["text_secondary"]}">'
                f'{self._escape_svg_text(expl[:30])}</text>'
            )
            y += row_h

        return parts

    def _fallback_slide(self, page: Dict, idx: int, canvas: Dict, colors: Dict) -> str:
        """生成回退幻灯片（当 SVG 质量检查失败时）"""
        canvas_w = int(canvas["viewBox"].split()[2])
        canvas_h = int(canvas["viewBox"].split()[3])
        title = page.get("title", f"第 {idx + 1} 页")
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{canvas["viewBox"]}">'
            f'<rect width="{canvas_w}" height="{canvas_h}" fill="white"/>'
            f'<text x="60" y="100" font-size="{self._style_size("large", "title_slide")}" font-weight="bold" fill="#333">{self._escape_svg_text(title)}</text>'
            f'<text x="60" y="150" font-size="{self._style_size("body", "title_slide")}" fill="#999">PPT Master Generation</text>'
            f'</svg>'
        )

    def _default_colors(self) -> Dict:
        """默认主题色"""
        return {
            "primary": "#1A56DB",
            "secondary": "#7E3AF2",
            "background": "#FFFFFF",
            "surface": "#F9FAFB",
            "text": "#111827",
            "text_secondary": "#6B7280",
            "accent": "#F59E0B",
            "border": "#E5E7EB",
        }

    def _style_font(self, role: str = "body") -> str:
        """获取当前视觉风格对应的字体栈"""
        if self._current_style_name:
            return VisualStyleEngine.get_font_stack(self._current_style_name, role)
        return FONT_STACK

    def _style_size(self, role: str = "body", page_type: str = "") -> int:
        """获取语义角色对应的字号（px），关联当前风格 + 页面类型

        Args:
            role: 语义角色名（如 header / item / word / stem）
            page_type: 页面类型（用于角色别名映射）
        """
        if self._current_style_name:
            return VisualStyleEngine.get_role_font_size(
                self._current_style_name, role, page_type)
        return FONT_SCALE.get(role, 16)

    @staticmethod
    def _escape_svg_text(text: str, max_len: int = MAX_TEXT_LENGTH) -> str:
        """转义 SVG 文本内容并截断超长文本"""
        if not isinstance(text, str):
            text = str(text) if text is not None else ""
        if len(text) > max_len:
            text = text[:max_len - 3] + "..."
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    # ==================== 源文档转 PPTX ====================

    def generate_from_pdf(
        self,
        pdf_path: str,
        title: str = "PDF 课件",
        canvas_format: str = "ppt169",
    ) -> Dict:
        """从 PDF 直接生成 PPTX

        Args:
            pdf_path: PDF 文件路径
            title: PPT 标题
            canvas_format: 画布格式

        Returns:
            导出结果
        """
        # 1. PDF → MD
        converter = PDFConverter()
        md_text = converter.convert(pdf_path)

        # 2. MD → 结构化页面（简易分割）
        pages = self._md_to_slides(md_text, title)

        # 3. 生成 PPTX（同步调用）
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.generate_from_pages_json(pages, title, canvas_format=canvas_format)
            )
        finally:
            loop.close()

    def generate_from_docx(
        self,
        docx_path: str,
        title: str = "Word 课件",
        canvas_format: str = "ppt169",
    ) -> Dict:
        """从 DOCX 直接生成 PPTX"""
        converter = DOCXConverter()
        md_text = converter.convert(docx_path)
        pages = self._md_to_slides(md_text, title)

        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.generate_from_pages_json(pages, title, canvas_format=canvas_format)
            )
        finally:
            loop.close()

    def _md_to_slides(self, md_text: str, title: str) -> List[Dict]:
        """将 Markdown 文本分割为幻灯片页面"""
        import re

        slides = []
        # 以 H2 (##) 或 H1 (#) 作为分页标记
        sections = re.split(r'\n(?=#{1,3}\s)', md_text)

        first_section = True
        for section in sections:
            section = section.strip()
            if not section:
                continue

            lines = section.split("\n")
            # 提取标题
            section_title = ""
            content_lines = []
            for line in lines:
                if line.startswith("#"):
                    section_title = line.lstrip("#").strip()
                else:
                    content_lines.append(line)

            if first_section:
                # 第一页作为封面
                slides.append({
                    "type": "title",
                    "title": title,
                    "content": {"main_title": title, "subtitle": section_title},
                })
                first_section = False
            else:
                # 后续页作为内容页
                slides.append({
                    "type": "content",
                    "title": section_title or f"Slide {len(slides) + 1}",
                    "content": {"items": [l.strip() for l in content_lines if l.strip()]},
                })

        # 如果只有一页，添加内容页
        if len(slides) <= 1 and not first_section:
            slides.append({
                "type": "content",
                "title": "内容",
                "content": {"items": md_text.split("\n")[:10]},
            })

        return slides

    # ==================== 静态文件路径 ====================

    def get_output_path(self, file_url: str) -> str:
        """将文件 URL 转换为本地路径"""
        if file_url.startswith("/uploads/"):
            return str(UPLOADS_DIR.parent / file_url.lstrip("/"))
        return file_url

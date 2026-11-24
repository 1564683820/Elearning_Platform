"""SpecLock 设计规格锁定管理器

将用户选择的视觉风格 / 配色 / 字体 / 布局策略锁定为一个结构化规范，
确保生成管线中每一页都遵循一致的设计决策，防止"漂移"。

参考 ppt-master 的 spec_lock.md 可执行合约概念。
"""

from __future__ import annotations
import json
import copy
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, ClassVar

logger = logging.getLogger(__name__)


# ==================== 数据结构 ====================

@dataclass
class ColorSpec:
    """锁定配色方案"""
    primary: str = "#1A56DB"
    secondary: str = "#7E3AF2"
    background: str = "#FFFFFF"
    surface: str = "#F9FAFB"
    text: str = "#111827"
    text_secondary: str = "#6B7280"
    accent: str = "#F59E0B"
    border: str = "#E5E7EB"
    success: str = "#10B981"
    error: str = "#EF4444"

    @classmethod
    def from_scheme(cls, scheme: Dict[str, str]) -> "ColorSpec":
        """从配色方案 dict 构建"""
        return cls(**{k: v for k, v in scheme.items() if k in cls.__dataclass_fields__})


@dataclass
class TypographySpec:
    """锁定排版系统"""
    font_family: str = "Arial"                      # 正文默认字体
    heading_font: str = "Arial"                     # 标题字体
    mono_font: str = "Courier New"                   # 等宽字体
    title_size: int = 48                              # 封面大标题
    heading1_size: int = 36                           # 一级标题
    heading2_size: int = 28                           # 二级标题
    heading3_size: int = 24                           # 三级标题
    body_size: int = 18                               # 正文
    small_size: int = 14                              # 小字
    caption_size: int = 12                            # 注释
    line_height: float = 1.6                          # 行高

    @classmethod
    def from_font_families_and_style(
        cls,
        font_families: Dict[str, str],
        style_typo: Optional[Dict[str, Any]] = None,
    ) -> "TypographySpec":
        """从字体家族配置 + 视觉风格排版字符构建"""
        spec = cls(
            font_family=font_families.get("body", "Arial"),
            heading_font=font_families.get("heading", "Arial"),
            mono_font=font_families.get("mono", "Courier New"),
        )
        if style_typo:
            spec.body_size = style_typo.get("body_size", spec.body_size)
            spec.title_size = style_typo.get("title_size", spec.title_size)
            # 视觉风格中的 note_size 映射为 caption_size
            spec.caption_size = style_typo.get("note_size", spec.caption_size)
            spec.line_height = style_typo.get("line_height", spec.line_height)
        return spec


@dataclass
class LayoutStrategySpec:
    """锁定各页面类型的布局策略"""
    catalog: str = "list"
    vocabulary: str = "grid"
    dialogue: str = "cards"
    grammar: str = "list"
    practice: str = "cards"
    title: str = "center"
    summary: str = "list"
    objective: str = "cards"
    interactive: str = "cards"
    ai_interaction: str = "cards"
    listening: str = "list"
    speaking: str = "cards"
    content: str = "cards"
    review: str = "list"
    reading: str = "cards"
    writing: str = "cards"
    exercise: str = "cards"
    introduction: str = "center"

    @classmethod
    def from_layout_overrides(cls, overrides: Dict[str, str]) -> "LayoutStrategySpec":
        """从布局覆盖 dict 构建（未指定的使用默认值）"""
        spec = cls()
        for k, v in overrides.items():
            if hasattr(spec, k):
                setattr(spec, k, v)
        return spec

    def to_overrides(self) -> Dict[str, str]:
        """转换为 layout_overrides dict（过滤掉默认值）"""
        defaults = LayoutStrategySpec()
        result = {}
        for k in self.__dataclass_fields__:
            current = getattr(self, k)
            if current != getattr(defaults, k):
                result[k] = current
        return result


@dataclass
class PageRhythmSpec:
    """页面节奏序列 — 控制页面的视觉密度/装饰"""
    sequence: List[str] = field(default_factory=lambda: [])  # anchor / dense / breathing
    pattern_name: str = "auto"                                # 节奏模式名称

    RHYTHM_PATTERNS: ClassVar[Dict[str, List[str]]] = {
        "teaching": [
            "anchor", "dense", "breathing", "dense",
            "breathing", "anchor", "dense", "breathing",
        ],
        "presentation": [
            "anchor", "breathing", "dense", "dense",
            "breathing", "anchor",
        ],
        "knowledge": [
            "anchor", "dense", "dense", "breathing",
            "dense", "breathing", "anchor",
        ],
    }

    @classmethod
    def generate(cls, page_count: int, pattern: str = "auto") -> "PageRhythmSpec":
        """根据页数和模式生成节奏序列"""
        if pattern == "auto":
            # 自动选择模式
            if page_count <= 6:
                pattern = "presentation"
            elif page_count <= 10:
                pattern = "teaching"
            else:
                pattern = "knowledge"

        base = cls.RHYTHM_PATTERNS.get(pattern, cls.RHYTHM_PATTERNS["teaching"])
        # 按页数循环
        sequence = [base[i % len(base)] for i in range(page_count)]
        return cls(sequence=sequence, pattern_name=pattern)


# ==================== 主 SpecLock 类 ====================

@dataclass
class DesignSpec:
    """完整的设计规格锁定 — 生成管线的"可执行合约"

    所有设计决策在此锁定，管线各方（HTML渲染 / PPTX引擎 / 质量检查）均读取此规格，
    确保视觉一致性。
    """
    visual_style: str = "warm-simple"                   # 视觉风格名称
    color_scheme_name: str = "professional"             # 配色方案名称
    font_family_name: str = "system"                    # 字体家族名称
    colors: ColorSpec = field(default_factory=ColorSpec)
    typography: TypographySpec = field(default_factory=TypographySpec)
    layout_strategy: LayoutStrategySpec = field(default_factory=LayoutStrategySpec)
    page_rhythm: PageRhythmSpec = field(default_factory=PageRhythmSpec)
    canvas_format: str = "ppt169"                        # 画布格式

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 dict（用于 JSON 存储）"""
        return {
            "visual_style": self.visual_style,
            "color_scheme_name": self.color_scheme_name,
            "font_family_name": self.font_family_name,
            "colors": asdict(self.colors),
            "typography": asdict(self.typography),
            "layout_strategy": asdict(self.layout_strategy),
            "page_rhythm": {
                "sequence": self.page_rhythm.sequence,
                "pattern_name": self.page_rhythm.pattern_name,
            },
            "canvas_format": self.canvas_format,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesignSpec":
        """从 dict 反序列化"""
        colors_data = data.get("colors", {})
        typo_data = data.get("typography", {})
        layout_data = data.get("layout_strategy", {})
        rhythm_data = data.get("page_rhythm", {})

        # 兼容旧字段名：text -> text, text_secondary -> text_secondary
        return cls(
            visual_style=data.get("visual_style", "warm-simple"),
            color_scheme_name=data.get("color_scheme_name", "professional"),
            font_family_name=data.get("font_family_name", "system"),
            colors=ColorSpec(**colors_data),
            typography=TypographySpec(**typo_data),
            layout_strategy=LayoutStrategySpec(**layout_data),
            page_rhythm=PageRhythmSpec(
                sequence=rhythm_data.get("sequence", []),
                pattern_name=rhythm_data.get("pattern_name", "auto"),
            ),
            canvas_format=data.get("canvas_format", "ppt169"),
        )

    def to_json(self, indent: int = 2) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ==================== SpecLockManager ====================

class SpecLockManager:
    """设计规格锁定管理器

    职责：
    1. 从用户选择（visual_style, color_scheme, font_family）构建完整 DesignSpec
    2. 允许按字段覆盖（如手动选择配色覆盖风格的默认配色）
    3. 将完整 spec 注入到生成管线
    4. 从已有 PPT 还原 spec
    """

    # 视觉风格 → 推荐配色方案映射
    STYLE_TO_COLOR_SCHEME: Dict[str, str] = {
        "swiss-minimal": "professional",
        "soft-rounded": "nature",
        "editorial": "elegant",
        "dark-tech": "dark",
        "sketch-notes": "warm",
        "chalkboard": "nature",
        "glassmorphism": "professional",
        "paper-cut": "elegant",
        "warm-simple": "warm",
    }

    # 视觉风格 → 推荐字体家族映射
    STYLE_TO_FONT_FAMILY: Dict[str, str] = {
        "swiss-minimal": "modern",
        "soft-rounded": "system",
        "editorial": "elegant",
        "dark-tech": "modern",
        "sketch-notes": "system",
        "chalkboard": "system",
        "glassmorphism": "modern",
        "paper-cut": "elegant",
        "warm-simple": "system",
    }

    def __init__(self):
        # 延迟导入以避免循环依赖
        from app.ppt_generator.config import COLOR_SCHEMES, FONT_FAMILIES, FONT_SIZES, DEFAULT_CANVAS
        from app.ppt_generator.services.ppt_generation_service import VisualStyleEngine
        self._color_schemes = COLOR_SCHEMES
        self._font_families = FONT_FAMILIES
        self._font_sizes = FONT_SIZES
        self._default_canvas = DEFAULT_CANVAS
        self._style_engine = VisualStyleEngine

    def build_spec(
        self,
        visual_style: str = "warm-simple",
        color_scheme_name: Optional[str] = None,
        font_family_name: Optional[str] = None,
        layout_strategy: Optional[Dict[str, str]] = None,
        page_rhythm_pattern: str = "auto",
        canvas_format: str = "ppt169",
    ) -> DesignSpec:
        """从用户选择构建完整 DesignSpec

        Args:
            visual_style: 视觉风格名称（如 soft-rounded）
            color_scheme_name: 配色方案名称，None 则根据视觉风格自动推荐
            font_family_name: 字体家族名称，None 则根据视觉风格自动推荐
            layout_strategy: 布局策略覆盖（可选）
            page_rhythm_pattern: 页面节奏模式
            canvas_format: 画布格式

        Returns:
            完整的 DesignSpec 实例
        """
        # 1. 解析配色
        effective_color_scheme = (color_scheme_name or
                                  self.STYLE_TO_COLOR_SCHEME.get(visual_style, "professional"))
        scheme_colors = self._color_schemes.get(effective_color_scheme, self._color_schemes["professional"])
        colors = ColorSpec.from_scheme(scheme_colors)
        # 补充 theme 使用的 border 字段
        if not hasattr(colors, "border") or not colors.border:
            colors.border = colors.text_secondary + "40"  # 低透明度版本

        # 2. 解析字体
        effective_font_family = (font_family_name or
                                 self.STYLE_TO_FONT_FAMILY.get(visual_style, "system"))
        families = self._font_families.get(effective_font_family, self._font_families["system"])

        # 从视觉风格引擎获取排版配置
        style_config = self._style_engine.STYLE_REGISTRY.get(visual_style, {})
        style_typo = style_config.get("typography", None) if style_config else None
        typography = TypographySpec.from_font_families_and_style(families, style_typo)

        # 3. 应用全局字号层级覆盖
        global_sizes = self._font_sizes
        typography.title_size = global_sizes.get("title", typography.title_size)
        typography.heading1_size = global_sizes.get("heading1", typography.heading1_size)
        typography.heading2_size = global_sizes.get("heading2", typography.heading2_size)
        typography.heading3_size = global_sizes.get("heading3", typography.heading3_size)
        typography.body_size = global_sizes.get("body", typography.body_size)
        typography.small_size = global_sizes.get("small", typography.small_size)
        typography.caption_size = global_sizes.get("caption", typography.caption_size)

        # 4. 布局策略
        if layout_strategy:
            layout_spec = LayoutStrategySpec.from_layout_overrides(layout_strategy)
        else:
            layout_spec = LayoutStrategySpec()

        # 5. 页面节奏 — 暂未知页数，调用处再填充
        rhythm = PageRhythmSpec(pattern_name=page_rhythm_pattern)

        return DesignSpec(
            visual_style=visual_style,
            color_scheme_name=effective_color_scheme,
            font_family_name=effective_font_family,
            colors=colors,
            typography=typography,
            layout_strategy=layout_spec,
            page_rhythm=rhythm,
            canvas_format=canvas_format,
        )

    def finalize_rhythm(self, spec: DesignSpec, page_count: int) -> DesignSpec:
        """锁定页数后生成节奏序列"""
        spec.page_rhythm = PageRhythmSpec.generate(page_count, spec.page_rhythm.pattern_name)
        return spec

    def validate(self, spec: DesignSpec) -> List[str]:
        """验证 spec 完整性，返回问题列表（空列表 = 验证通过）"""
        issues: List[str] = []

        if not spec.visual_style:
            issues.append("visual_style 未设置")
        elif spec.visual_style not in self._style_engine.STYLE_REGISTRY:
            issues.append(f"未知的 visual_style: {spec.visual_style}")

        if not spec.colors.primary:
            issues.append("colors.primary 未设置")
        if not spec.typography.font_family:
            issues.append("typography.font_family 未设置")

        rhythm = spec.page_rhythm
        if rhythm.sequence and len(rhythm.sequence) > 0:
            valid_rhythms = {"anchor", "dense", "breathing"}
            for r in rhythm.sequence:
                if r not in valid_rhythms:
                    issues.append(f"无效的节奏标签: {r}")
                    break

        return issues

    def apply_to_pages(self, spec: DesignSpec, pages: List[Dict]) -> List[Dict]:
        """将 spec 应用到页面数据上（注入 layout / rhythm 字段）"""
        result = copy.deepcopy(pages)
        layout_strategy = spec.layout_strategy

        # 锁定后的节奏序列
        spec = self.finalize_rhythm(spec, len(result))
        rhythm_seq = spec.page_rhythm.sequence

        for i, page in enumerate(result):
            page_type = page.get("type", "content")

            # 注入布局（如果页面尚未指定）
            if not page.get("layout") and hasattr(layout_strategy, page_type):
                layout = getattr(layout_strategy, page_type)
                if layout:
                    page["layout"] = layout

            # 注入节奏
            if i < len(rhythm_seq):
                page["rhythm"] = rhythm_seq[i]

        return result

    def merge_with_request(
        self,
        spec: DesignSpec,
        existing_overrides: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """将 spec 转换为 HTTP 请求可用的参数扩展

        Returns:
            dict 可解包到请求参数中
        """
        result: Dict[str, Any] = {
            "visual_style": spec.visual_style,
            "layout_strategy": spec.layout_strategy.to_overrides(),
        }

        # layout_overrides 优先使用 spec 中的值，再合并已存在的覆盖
        overrides = spec.layout_strategy.to_overrides()
        if existing_overrides:
            overrides.update(existing_overrides)
        if overrides:
            result["layout_overrides"] = overrides

        return result

    def from_ppt_record(self, ppt_data: Dict[str, Any]) -> Optional[DesignSpec]:
        """从数据库记录的 spec_lock 字段恢复 DesignSpec"""
        raw = ppt_data.get("spec_lock")
        if not raw:
            return None
        try:
            if isinstance(raw, str):
                data = json.loads(raw)
            else:
                data = raw
            return DesignSpec.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(f"从 ppt 记录恢复 spec_lock 失败: {e}")
            return None


# 全局单例
spec_lock_manager = SpecLockManager()

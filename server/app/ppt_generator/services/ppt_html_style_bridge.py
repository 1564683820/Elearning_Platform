"""PPT HTML 风格桥接 — VisualStyleEngine → CSS 变量/装饰类

将 ppt_generation_service 中的 VisualStyleEngine 配置（9 种视觉风格）
转换为 HTML 渲染器可消费的 CSS 变量声明和装饰类样式。
"""

from typing import Optional

# ==================== 风格到 CSS 变量映射 ====================

def generate_style_css_variables(style_name: str) -> str:
    """根据风格名称生成 :root CSS 变量声明块

    输出格式:
      --slide-corner-radius: 0px;
      --slide-card-shadow: none;
      --slide-font-title: 'Montserrat','SCDream','Microsoft YaHei',sans-serif;
      ...
    """
    config = _get_style_config(style_name)
    if not config:
        return ""

    shape = config.get("shape", {})
    typo = config.get("typography", {})
    spacing = config.get("spacing", {})
    deco = config.get("decoration", {})

    lines = ["/* === Style Bridge: {} === */".format(style_name)]

    # — 形状语言
    card_r = shape.get("card_radius", 8)
    lines.append(f"  --slide-corner-radius: {card_r}px;")
    lines.append(f"  --slide-card-border-width: {shape.get('card_border', 1)}px;")

    shadow = shape.get("shadow", "light")
    if shadow == "none":
        lines.append("  --slide-card-shadow: none;")
        lines.append("  --slide-card-hover-shadow: none;")
    elif shadow == "light":
        lines.append("  --slide-card-shadow: 0 2px 12px rgba(0,0,0,0.06);")
        lines.append("  --slide-card-hover-shadow: 0 4px 16px rgba(0,0,0,0.12);")
    elif shadow == "medium":
        lines.append("  --slide-card-shadow: 0 4px 20px rgba(0,0,0,0.10);")
        lines.append("  --slide-card-hover-shadow: 0 8px 28px rgba(0,0,0,0.16);")

    # — 排版性格
    lines.append(f"  --slide-font-title: {typo.get('title_font', 'inherit')};")
    lines.append(f"  --slide-font-body: {typo.get('body_font', 'inherit')};")
    lines.append(f"  --slide-font-title-weight: {typo.get('title_weight', 'bold')};")
    lines.append(f"  --slide-font-body-weight: {typo.get('body_weight', 'normal')};")
    lines.append(f"  --slide-title-font-size: {typo.get('title_size', 28)}px;")
    lines.append(f"  --slide-body-font-size: {typo.get('body_size', 15)}px;")
    lines.append(f"  --slide-note-font-size: {typo.get('note_size', 12)}px;")

    # — 留白与间距
    lines.append(f"  --slide-margin: {spacing.get('margin', 55)}px;")
    lines.append(f"  --slide-gap: {spacing.get('gap', 14)}px;")
    lines.append(f"  --slide-card-gap: {spacing.get('card_gap', 12)}px;")
    lines.append(f"  --slide-line-height: {spacing.get('line_height', 1.6)};")

    # — 装饰风格
    if deco.get("separator") == "dotted":
        lines.append("  --slide-divider-style: dotted;")
    elif deco.get("separator") == "dashed":
        lines.append("  --slide-divider-style: dashed;")
    elif deco.get("separator") == "solid":
        lines.append("  --slide-divider-style: solid;")
    elif deco.get("separator") == "wavy":
        lines.append("  --slide-divider-style: wavy;")
    else:
        lines.append("  --slide-divider-style: none;")

    lines.append(f"  --slide-header-style: {'left-border' if deco.get('left_accent', True) else 'none'};")
    lines.append(f"  --slide-top-bar-display: {'block' if deco.get('top_bar', False) else 'none'};")
    lines.append(f"  --slide-bg-decoration: '{deco.get('bg_decoration', 'none')}';")
    lines.append(f"  --slide-show-page-number: {'block' if deco.get('show_page_number', False) else 'none'};")

    return "\n".join(lines)


def generate_style_decorations_css(style_name: str) -> str:
    """生成风格装饰 CSS（伪元素 / 背景 / 顶部条等）

    这些 CSS 规则配合 HTML 容器上的 data-style 属性工作，
    由 _generate_style_classes 提供容器对应类名。
    """
    config = _get_style_config(style_name)
    if not config:
        return ""

    deco = config.get("decoration", {})
    shape = config.get("shape", {})
    css_parts = []

    # — 顶部色条（top_bar）
    if deco.get("top_bar", False):
        css_parts.append(""".ppt-slide[data-style="{style}"] .slide-top-bar {{
  display: block;
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 5px;
  background: var(--slide-primary);
  z-index: 10;
}}""".format(style=style_name))

    # — 背景装饰
    bg_dec = deco.get("bg_decoration", "none")
    if bg_dec == "circle":
        css_parts.append(""".ppt-slide[data-style="{style}"]::before {{
  content: '';
  position: absolute;
  right: -80px;
  bottom: -80px;
  width: 300px;
  height: 300px;
  border-radius: 50%;
  background: var(--slide-primary);
  opacity: 0.04;
  pointer-events: none;
}}""".format(style=style_name))
    elif bg_dec == "grid":
        css_parts.append(""".ppt-slide[data-style="{style}"] {{
  background-image:
    linear-gradient(var(--slide-border) 1px, transparent 1px),
    linear-gradient(90deg, var(--slide-border) 1px, transparent 1px);
  background-size: 40px 40px;
  background-position: -1px -1px;
}}""".format(style=style_name))
    elif bg_dec == "glow":
        css_parts.append(""".ppt-slide[data-style="{style}"]::before {{
  content: '';
  position: absolute;
  top: -100px;
  right: -100px;
  width: 400px;
  height: 400px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--slide-primary-light) 0%, transparent 70%);
  pointer-events: none;
}}""".format(style=style_name))
    elif bg_dec == "grid-paper":
        css_parts.append(""".ppt-slide[data-style="{style}"] {{
  background-image:
    linear-gradient(var(--slide-border) 1px, transparent 1px),
    linear-gradient(90deg, var(--slide-border) 1px, transparent 1px);
  background-size: 20px 20px;
  background-position: -1px -1px;
  opacity: 0.3;
}}""".format(style=style_name))
    elif bg_dec == "pattern":
        css_parts.append(""".ppt-slide[data-style="{style}"]::before {{
  content: '';
  position: absolute;
  top: 0; right: 0;
  width: 120px; height: 120px;
  background: repeating-linear-gradient(
    45deg,
    transparent,
    transparent 8px,
    var(--slide-primary-light) 8px,
    var(--slide-primary-light) 10px
  );
  opacity: 0.15;
  pointer-events: none;
}}""".format(style=style_name))

    # — 标题左侧色标（left_accent marker）
    marker_r = shape.get("marker_radius", 6)
    marker_w = shape.get("marker_width", 5)
    if deco.get("left_accent", True):
        css_parts.append(""".ppt-slide[data-style="{style}"] .slide-title::before {{
  content: '';
  display: inline-block;
  width: {marker_w}px;
  height: 1.2em;
  border-radius: {marker_r}px;
  background: var(--slide-primary);
  margin-right: 10px;
  vertical-align: middle;
  flex-shrink: 0;
}}""".format(style=style_name, marker_r=marker_r, marker_w=marker_w))

    # — 分隔线样式（非 none 时替换默认分隔线）
    sep = deco.get("separator", "solid")
    if sep == "dotted":
        css_parts.append(""".ppt-slide[data-style="{style}"] .section-divider {{
  border: none;
  border-top: 1px dotted var(--slide-border);
  opacity: 0.5;
  margin: 8px 0;
}}""".format(style=style_name))
    elif sep == "dashed":
        css_parts.append(""".ppt-slide[data-style="{style}"] .section-divider {{
  border: none;
  border-top: 1px dashed var(--slide-primary);
  opacity: 0.4;
  margin: 8px 0;
}}""".format(style=style_name))
    elif sep == "wavy":
        css_parts.append(""".ppt-slide[data-style="{style}"] .section-divider {{
  border: none;
  height: 3px;
  background: repeating-linear-gradient(
    45deg,
    var(--slide-border),
    var(--slide-border) 4px,
    transparent 4px,
    transparent 8px
  );
  margin: 8px 0;
}}""".format(style=style_name))

    return "\n\n".join(css_parts)


def generate_style_full_css(style_name: str) -> str:
    """生成视觉风格的完整 CSS 块（变量 + 装饰类）"""
    variables = generate_style_css_variables(style_name)
    decorations = generate_style_decorations_css(style_name)
    if decorations:
        return f":root {{\n{variables}\n}}\n\n{decorations}"
    return f":root {{\n{variables}\n}}"


# ==================== 主题色→风格色 CSS 变量映射 ====================

def generate_theme_color_variables(colors: dict) -> str:
    """将主题色字典转换为 :root 颜色变量声明

    输入: {"primary": "#2d7d46", "secondary": "#e8f5e9", ...}
    输出: "--slide-primary: #2d7d46;\n  --slide-primary-light: #e8f5e9;\n  ..."
    """
    color_map = {
        "primary": "--slide-primary",
        "primary_light": "--slide-primary-light",
        "secondary": "--slide-secondary",
        "background": "--slide-bg",
        "surface": "--slide-surface",
        "text": "--slide-text",
        "text_secondary": "--slide-subtitle-color",
        "accent": "--slide-accent",
        "border": "--slide-border",
        "success": "--slide-correct-color",
        "error": "--slide-wrong-color",
    }
    lines = ["/* === Theme Colors === */"]
    for key, var_name in color_map.items():
        val = colors.get(key, "")
        if val:
            lines.append(f"  {var_name}: {val};")
    return "\n".join(lines)


# ==================== 内部工具 ====================

_STYLE_CACHE: dict = {}

def _get_style_config(style_name: str) -> Optional[dict]:
    """延迟导入 VisualStyleEngine 避免循环依赖"""
    if style_name in _STYLE_CACHE:
        return _STYLE_CACHE[style_name]
    try:
        from .ppt_generation_service import VisualStyleEngine
        config = VisualStyleEngine.get_style_config(style_name)
        _STYLE_CACHE[style_name] = config
        return config
    except ImportError:
        return None

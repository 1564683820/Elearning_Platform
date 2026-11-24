# 图标内联工具包装器
# 将 ppt-master 参考实现中的 embed_icons 函数导入本模块供编辑器使用

import sys
from pathlib import Path

# 定位参考 embed_icons 模块路径
_REFERENCE_PATH = (
    Path(__file__).resolve().parents[4]  # 仓库根目录
    / "docs"
    / "ppt-master-main"
    / "ppt-master-main"
    / "skills"
    / "ppt-master"
    / "scripts"
    / "svg_finalize"
)
_REFERENCE_MODULE_PATH = str(_REFERENCE_PATH)

if _REFERENCE_MODULE_PATH not in sys.path:
    sys.path.insert(0, _REFERENCE_MODULE_PATH)


# 默认图标库路径（相对于 仓库根目录）
def get_default_icons_dir() -> Path:
    """返回项目图标库根目录"""
    candidates = [
        Path(__file__).resolve().parents[4] / "docs" / "ppt-master-main" / "ppt-master-main" / "skills" / "ppt-master" / "templates" / "icons",
        Path(__file__).resolve().parents[2] / "templates" / "icons",
        Path(__file__).resolve().parents[2] / "svg_finalize" / "icons",
    ]
    for p in candidates:
        if p.exists() and p.is_dir():
            return p
    # 兜底：使用参考库路径
    return candidates[0]


# 从参考模块导入公开函数
try:
    from embed_icons import (  # noqa: F811, F401
        parse_use_element,
        resolve_icon_path,
        extract_paths_from_icon,
        generate_icon_group,
        ICON_BASE_SIZES,
    )
except ImportError:
    # 降级：直接内联实现关键函数
    import re
    import xml.etree.ElementTree as ET
    from typing import Optional

    def parse_use_element(use_match: str) -> dict:
        """解析 <use data-icon .../> 元素的属性"""
        attrs: dict = {}
        icon_value = _attr_value(use_match, "data-icon")
        if icon_value:
            attrs["icon"] = icon_value
        for attr in ["x", "y", "width", "height"]:
            val = _attr_value(use_match, attr)
            if val is not None:
                try:
                    attrs[attr] = float(val)
                except (ValueError, TypeError):
                    attrs[attr] = val
        fill_val = _attr_value(use_match, "fill")
        if fill_val is not None:
            attrs["fill"] = fill_val
        stroke_val = _attr_value(use_match, "stroke")
        if stroke_val is not None:
            attrs["stroke"] = stroke_val
        transform_val = _attr_value(use_match, "transform")
        if transform_val is not None:
            attrs["transform"] = transform_val
        sw_val = _attr_value(use_match, "stroke-width")
        if sw_val is not None:
            attrs["stroke-width"] = sw_val
        return attrs

    def _attr_value(tag_text: str, attr: str) -> Optional[str]:
        m = re.search(rf'\b{re.escape(attr)}\s*=\s*(["\'])(.*?)\1', tag_text, re.DOTALL)
        return m.group(2) if m else None

    def resolve_icon_path(icon_name: str, icons_dir: Path, fallback_dir: Optional[Path] = None):
        icon_path = icons_dir / f"{icon_name}.svg"
        if not icon_path.exists():
            if "/" in icon_name:
                lib, name = icon_name.split("/", 1)
                icon_path = icons_dir / lib / f"{name}.svg"
            else:
                icon_path = icons_dir / "chunk-filled" / f"{icon_name}.svg"
        if not icon_path.exists() and fallback_dir:
            fb = fallback_dir / f"{icon_name}.svg"
            if fb.exists():
                return fb, 24
        return icon_path, 16

    def extract_paths_from_icon(icon_path: Path, target_color: str = "#000000"):
        if not icon_path.exists():
            return [], "fill", 16
        content = icon_path.read_text(encoding="utf-8")
        m = re.search(r'viewBox=["\']0 0 ([\d.]+)', content)
        base_size = float(m.group(1)) if m else 16
        paths = re.findall(r'<path\s[^>]*?/>', content)
        cleaned = []
        for p in paths:
            p = re.sub(r'\s*fill="(?:currentColor|#[0-9a-fA-F]{3,6})"', "", p)
            cleaned.append(p)
        return cleaned, "fill", base_size

    def generate_icon_group(attrs: dict, elements: list, style: str, base_size) -> str:
        x = attrs.get("x", 0)
        y = attrs.get("y", 0)
        width = attrs.get("width", base_size)
        height = attrs.get("height", base_size)
        color = attrs.get("fill", "#000000")
        icon_name = attrs.get("icon", "unknown")
        scale_x = float(width) / float(base_size) if float(base_size) > 0 else 1
        scale_y = float(height) / float(base_size) if float(base_size) > 0 else 1
        transform = f"translate({x}, {y}) scale({scale_x}, {scale_y})"
        elements_str = "\n    ".join(elements)
        return f'<!-- icon: {icon_name} -->\n  <g transform="{transform}" fill="{color}">\n    {elements_str}\n  </g>'

    ICON_BASE_SIZES = {}

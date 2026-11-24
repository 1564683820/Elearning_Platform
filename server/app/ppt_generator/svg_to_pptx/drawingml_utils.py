"""DrawingML 工具函数"""
import re
from typing import Tuple, Optional


def parse_transform(transform_str: str) -> dict:
    """解析 SVG transform 字符串

    Args:
        transform_str: 如 "translate(10,20) rotate(45) scale(1.5,1.5)"

    Returns:
        dict: {'translate': (x,y), 'rotate': angle, 'scale': (sx,sy)}
    """
    result = {}
    if not transform_str:
        return result

    patterns = [
        (r'translate\s*\(([^)]+)\)', 'translate'),
        (r'rotate\s*\(([^)]+)\)', 'rotate'),
        (r'scale\s*\(([^)]+)\)', 'scale'),
        (r'matrix\s*\(([^)]+)\)', 'matrix'),
        (r'skewX\s*\(([^)]+)\)', 'skewX'),
        (r'skewY\s*\(([^)]+)\)', 'skewY'),
    ]

    for pattern, key in patterns:
        m = re.search(pattern, transform_str)
        if m:
            values = [float(v.strip()) for v in m.group(1).split(',')]
            result[key] = values[0] if len(values) == 1 else tuple(values)

    return result


def parse_viewbox(viewbox_str: str) -> Tuple[float, float, float, float]:
    """解析 SVG viewBox 属性

    Returns:
        (min_x, min_y, width, height)
    """
    parts = viewbox_str.strip().split()
    if len(parts) == 4:
        return tuple(float(p) for p in parts)
    return (0, 0, 1280, 720)


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """十六进制颜色转 RGB"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c * 2 for c in hex_color)
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """RGB 转十六进制颜色"""
    return f"{r:02X}{g:02X}{b:02X}"


def px_to_pt(px: float) -> float:
    """像素转磅值"""
    return px * 0.75


def px_to_emu(px: float) -> int:
    """像素转 EMU (English Metric Unit)"""
    return int(px * 0.75 * 12700)


def pt_to_emu(pt: float) -> int:
    """磅值转 EMU"""
    return int(pt * 12700)


def extract_float(s: str, default: float = 0.0) -> float:
    """从字符串中提取浮点数"""
    if not s:
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def escape_xml(text: str) -> str:
    """转义 XML 特殊字符"""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text
